from datetime import date
from decimal import Decimal
from unittest.mock import patch
from io import StringIO
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError, PermissionDenied
from django.utils import timezone
from django.db import OperationalError
from database.models import ChiNhanh, Kho, Xe, NhaCungCap, DonViVanChuyen, HoaDonNhap, ChiTietNhap, TonKho
from .models import PhieuNhapKho, KetQuaPDI, LichSuNhapKho
from . import services as s


class ReceiptTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(username='tester', password='test-only')
        cn = ChiNhanh.objects.create(ma_cn='CN', ten_cn='Đà Nẵng')
        self.kho = Kho.objects.create(ma_kho='K', chi_nhanh=cn)
        xe = Xe.objects.create(vin='VIN-TEST', ten_xe='Everest', phien_ban='Titanium', loai_xe='SUV', so_may='M1', mau_sac='Trắng')
        ncc = NhaCungCap.objects.create(ma_ncc='N', ten_ncc='NCC', mst='123')
        dv = DonViVanChuyen.objects.create(ma_dvvc='D', ten_dvvc='DV')
        hd = HoaDonNhap.objects.create(ma_hdn='HD', nha_cung_cap=ncc, chi_nhanh=cn, don_vi_van_chuyen=dv, ngay_nhap=timezone.now())
        self.line = ChiTietNhap.objects.create(hoa_don_nhap=hd, xe=xe, don_gia=Decimal('100'))
        self.receipt = s.create_receipt(self.user, ma_phieu='PN', chi_tiet_nhap_id=self.line.pk, kho_id='K', ngay_nhap=date.today())

    def record_pdi(self, user, receipt_id, **kwargs):
        current = s.latest_pdi(PhieuNhapKho.objects.get(pk=receipt_id))
        kwargs.setdefault('pdi_id', current.pk if current else None)
        kwargs.setdefault('hang_muc', [{'hang_muc': 'Ngoại thất', 'tinh_trang': 'Đã kiểm tra', 'ket_qua': kwargs.get('ket_qua', 'DAT')}])
        return s.record_pdi(user, receipt_id, **kwargs)

    def prepare(self):
        self.record_pdi(self.user, self.receipt.pk, tinh_trang='Đã kiểm tra', ket_qua='DAT')
        s.approve_pdi(self.user, self.receipt.pk, pdi_id=self.pdi_id())
        s.submit_receipt(self.user, self.receipt.pk, pdi_id=self.pdi_id())

    def pdi_id(self):
        current = s.latest_pdi(self.receipt)
        return current.pk if current else None

    def test_draft_does_not_add_stock(self):
        self.assertFalse(TonKho.objects.exists())
        with self.assertRaises(ValidationError):
            s.submit_receipt(self.user, self.receipt.pk, pdi_id=self.pdi_id())

    def test_failed_or_unapproved_pdi_blocks(self):
        self.record_pdi(self.user, self.receipt.pk, tinh_trang='Trầy', ket_qua='KHONG_DAT')
        with self.assertRaises(ValidationError):
            s.approve_pdi(self.user, self.receipt.pk, pdi_id=self.pdi_id())
        with self.assertRaises(ValidationError):
            s.submit_receipt(self.user, self.receipt.pk, pdi_id=self.pdi_id())
        with self.assertRaises(ValidationError):
            self.record_pdi(self.user, self.receipt.pk, tinh_trang='Đã sửa', ket_qua='DAT')
        with self.assertRaises(ValidationError):
            s.submit_receipt(self.user, self.receipt.pk, pdi_id=self.pdi_id())
        self.assertEqual(KetQuaPDI.objects.count(), 1)

    def test_approval_and_repeat(self):
        self.prepare()
        s.approve_receipt(self.user, self.receipt.pk, pdi_id=self.pdi_id())
        self.assertEqual(TonKho.objects.get().so_luong_ton, 1)
        self.assertEqual(LichSuNhapKho.objects.count(), 1)
        with self.assertRaises(ValidationError):
            s.approve_receipt(self.user, self.receipt.pk, pdi_id=self.pdi_id())
        self.assertEqual(TonKho.objects.get().so_luong_ton, 1)

    def test_rollback_if_history_fails(self):
        self.prepare()
        with patch('warehouse.services.LichSuNhapKho.objects.create', side_effect=RuntimeError('simulated')):
            with self.assertRaises(RuntimeError):
                s.approve_receipt(self.user, self.receipt.pk, pdi_id=self.pdi_id())
        self.receipt.refresh_from_db()
        self.assertEqual(self.receipt.trang_thai, 'CHO_DUYET')
        self.assertFalse(TonKho.objects.exists())

    def test_new_pdi_resets_waiting(self):
        self.prepare()
        self.record_pdi(self.user, self.receipt.pk, tinh_trang='Phát hiện lỗi', ket_qua='KHONG_DAT')
        with self.assertRaises(ValidationError):
            s.approve_receipt(self.user, self.receipt.pk, pdi_id=self.pdi_id())
        self.receipt.refresh_from_db()
        self.assertEqual(self.receipt.trang_thai, 'NHAP')

    def test_duplicate_and_unauthorized(self):
        with self.assertRaises(ValidationError):
            s.create_receipt(self.user, ma_phieu='PN2', chi_tiet_nhap_id=self.line.pk, kho_id='K', ngay_nhap=date.today())
        user = get_user_model().objects.create_user(username='no-permission')
        with self.assertRaises(PermissionDenied):
            s.approve_receipt(user, self.receipt.pk, pdi_id=self.pdi_id())
        self.client.force_login(user)
        self.assertEqual(self.client.post('/kho/phieu-nhap/1/duyet/', data='{}', content_type='application/json').status_code, 403)

    def test_existing_vin_and_wrong_branch(self):
        self.prepare()
        TonKho.objects.create(kho=self.kho, xe=self.line.xe, ngay_vao_kho=date.today())
        with self.assertRaises(ValidationError):
            s.approve_receipt(self.user, self.receipt.pk, pdi_id=self.pdi_id())
        self.assertEqual(LichSuNhapKho.objects.count(), 0)

    def test_http_flow_and_csrf(self):
        from django.test import Client
        self.client.force_login(self.user)
        self.assertEqual(self.client.get('/kho/phieu-nhap/').status_code, 200)
        self.assertEqual(self.client.get(f'/kho/phieu-nhap/{self.receipt.pk}/').status_code, 200)
        self.assertEqual(self.client.get(f'/kho/phieu-nhap/{self.receipt.pk}/duyet/').status_code, 405)
        protected = Client(enforce_csrf_checks=True)
        protected.force_login(self.user)
        self.assertEqual(protected.post(f'/kho/phieu-nhap/{self.receipt.pk}/duyet/').status_code, 403)

    def test_pdi_items_and_blank_text(self):
        with self.assertRaises(ValidationError):
            self.record_pdi(self.user, self.receipt.pk, tinh_trang='  ', ket_qua='DAT')
        with self.assertRaises(ValidationError):
            self.record_pdi(self.user, self.receipt.pk, tinh_trang='Có trầy', ket_qua='DAT',
                         hang_muc=[{'hang_muc': 'Ngoại thất', 'tinh_trang': 'Trầy', 'ket_qua': 'KHONG_DAT'}])
        self.assertEqual(KetQuaPDI.objects.count(), 0)

    def test_employee_branch_and_roles(self):
        from django.core.management import call_command
        from django.contrib.auth.models import Group
        from database.models import NhanVien
        call_command('setup_hopdong_nhapkho_roles', verbosity=0)
        worker = get_user_model().objects.create_user(username='worker')
        worker.groups.add(Group.objects.get(name='III-IV Nhân viên kho'))
        other = ChiNhanh.objects.create(ma_cn='GL', ten_cn='Gia Lai')
        worker.nhan_vien = NhanVien.objects.create(ma_nv='NV', ten_nv='NV Test', chi_nhanh=other)
        worker.save()
        with self.assertRaises(PermissionDenied):
            self.record_pdi(worker, self.receipt.pk, tinh_trang='Kiểm tra', ket_qua='DAT')
        worker.nhan_vien.chi_nhanh = self.kho.chi_nhanh
        worker.nhan_vien.save()
        self.record_pdi(worker, self.receipt.pk, tinh_trang='Kiểm tra', ket_qua='DAT')
        s.approve_pdi(worker, self.receipt.pk, pdi_id=self.pdi_id())
        s.submit_receipt(worker, self.receipt.pk, pdi_id=self.pdi_id())
        with self.assertRaises(PermissionDenied):
            s.approve_receipt(worker, self.receipt.pk, pdi_id=self.pdi_id())

    def test_vehicle_lookup_and_bad_json(self):
        self.client.force_login(self.user)
        response = self.client.get('/kho/xe-co-the-nhap/')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['xe'][0]['dang_co_phieu'])
        self.assertEqual(self.client.get('/kho/phieu-nhap/?ngay_lap=bad').status_code, 400)
        for data in ('[]', '{bad', '{}'):
            self.assertEqual(self.client.post('/kho/phieu-nhap/tao/', data=data, content_type='application/json').status_code, 400)

    def test_end_to_end_post_and_history(self):
        import json
        self.client.force_login(self.user)
        prefix = f'/kho/phieu-nhap/{self.receipt.pk}/'
        payload = {'tinh_trang': 'Nguyên vẹn', 'ket_qua': 'DAT', 'hang_muc': [
            {'hang_muc': 'Ngoại thất', 'tinh_trang': 'Không trầy', 'ket_qua': 'DAT'}]}
        self.assertEqual(self.client.post(prefix+'pdi/', json.dumps(payload), content_type='application/json').status_code, 200)
        for action in ('duyet-pdi', 'gui-duyet', 'duyet'):
            self.assertEqual(self.client.post(prefix+action+'/', json.dumps({'pdi_id': KetQuaPDI.objects.latest('pk').pk}), content_type='application/json').status_code, 200)
        self.assertEqual(len(self.client.get(prefix+'lich-su/').json()['lich_su']), 1)
        self.assertEqual(self.client.post(prefix+'duyet/', '{}', content_type='application/json').status_code, 400)
        self.assertEqual(self.client.post(prefix+'pdi/', json.dumps(payload), content_type='application/json').status_code, 400)

    def test_physical_warehouse_differs_from_invoice_branch(self):
        cn = ChiNhanh.objects.create(ma_cn='BD', ten_cn='Bình Định')
        kho = Kho.objects.create(ma_kho='KBD', chi_nhanh=cn)
        # Chi nhánh sổ sách và vị trí kho thực tế không bắt buộc trùng nhau.
        self.receipt.kho = kho
        self.receipt.full_clean()
        self.receipt.save()
        with self.assertRaises(PermissionDenied):
            self.prepare()
        self.assertFalse(TonKho.objects.exists())

    def post_action(self, action, payload):
        import json
        return self.client.post(f'/kho/phieu-nhap/{self.receipt.pk}/{action}/', json.dumps(payload), content_type='application/json')

    def business_users(self):
        from django.core.management import call_command
        from django.contrib.auth.models import Group
        from database.models import NhanVien
        call_command('setup_hopdong_nhapkho_roles', stdout=StringIO())
        worker = get_user_model().objects.create_user(username='business-worker')
        worker.groups.add(Group.objects.get(name='III-IV Nhân viên kho'))
        worker.nhan_vien = NhanVien.objects.create(ma_nv='NV-DN', ten_nv='Nhân viên thử', chi_nhanh=self.kho.chi_nhanh)
        worker.save()
        sale = get_user_model().objects.create_user(username='business-sale', first_name='Sale', last_name='Admin')
        sale.groups.add(Group.objects.get(name='III-IV Sale Admin'))
        return worker, sale

    def test_business_roles_complete_the_workflow_and_ui_flags_agree(self):
        worker, sale = self.business_users()
        self.client.force_login(worker)
        payload = {'tinh_trang': 'Nguyên vẹn', 'ket_qua': 'DAT', 'hang_muc': [
            {'hang_muc': 'Ngoại thất', 'tinh_trang': 'Không trầy', 'ket_qua': 'DAT'}]}
        response = self.post_action('pdi', payload)
        self.assertEqual(response.status_code, 200)
        pdi_id = response.json()['pdi']['id']
        self.assertEqual(self.post_action('duyet-pdi', {'pdi_id': pdi_id}).status_code, 200)
        self.assertEqual(self.post_action('gui-duyet', {'pdi_id': pdi_id}).status_code, 200)
        details = self.client.get(f'/kho/phieu-nhap/{self.receipt.pk}/').json()['phieu_nhap']
        self.assertEqual(details['nguon_xe'], 'NCC')
        self.assertEqual(details['phien_ban'], 'Titanium')
        self.assertEqual(details['ten_kho'], 'Đà Nẵng')
        self.assertFalse(details['thao_tac']['duyet_nhap'])
        self.assertEqual(self.post_action('duyet', {'pdi_id': pdi_id}).status_code, 403)
        self.client.force_login(sale)
        details = self.client.get(f'/kho/phieu-nhap/{self.receipt.pk}/').json()['phieu_nhap']
        self.assertTrue(details['thao_tac']['duyet_nhap'])
        self.assertFalse(details['thao_tac']['cap_nhat_pdi'])
        self.assertEqual(self.post_action('pdi', payload).status_code, 403)
        approved = self.post_action('duyet', {'pdi_id': pdi_id})
        self.assertEqual(approved.status_code, 200)
        self.assertEqual(approved.json()['phieu_nhap']['nguoi_duyet'], 'Sale Admin')
        history = self.client.get(f'/kho/phieu-nhap/{self.receipt.pk}/lich-su/').json()['lich_su']
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]['su_kien'], 'Nhập kho')
        self.assertEqual(TonKho.objects.get().so_luong_ton, 1)

    def test_outdated_pdi_cannot_be_overwritten_or_approved(self):
        self.client.force_login(self.user)
        old = self.record_pdi(self.user, self.receipt.pk, tinh_trang='Lần đầu', ket_qua='DAT')
        new = self.record_pdi(self.user, self.receipt.pk, tinh_trang='Kiểm tra lại', ket_qua='DAT')
        for payload in ({}, {'pdi_id': None}, {'pdi_id': old.pk}):
            self.assertEqual(self.post_action('duyet-pdi', payload).status_code, 400)
        stale_update = {'pdi_id': old.pk, 'tinh_trang': 'Dữ liệu cũ', 'ket_qua': 'DAT', 'hang_muc': []}
        self.assertEqual(self.post_action('pdi', stale_update).status_code, 400)
        self.assertEqual(KetQuaPDI.objects.count(), 2)
        self.assertEqual(self.post_action('duyet-pdi', {'pdi_id': new.pk}).status_code, 200)
        self.assertEqual(self.post_action('gui-duyet', {'pdi_id': old.pk}).status_code, 400)
        self.assertEqual(self.post_action('gui-duyet', {'pdi_id': new.pk}).status_code, 200)
        self.assertEqual(self.post_action('duyet', {'pdi_id': old.pk}).status_code, 400)
        self.assertFalse(TonKho.objects.exists())

    def test_old_pdi_is_visible_as_history_but_has_no_edit_or_approval_actions(self):
        self.client.force_login(self.user)
        old = self.record_pdi(self.user, self.receipt.pk, tinh_trang='Có lỗi', ket_qua='KHONG_DAT')
        self.record_pdi(self.user, self.receipt.pk, tinh_trang='Tiếp tục theo dõi lỗi', ket_qua='KHONG_DAT')
        response = self.client.get(f'/kho/pdi/{old.pk}/').json()
        self.assertFalse(response['la_moi_nhat'])
        self.assertEqual(response['thao_tac'], {'cap_nhat': False, 'duyet': False})
        self.assertTrue(response['pdi']['canh_bao'])
        history = self.client.get(f'/kho/phieu-nhap/{self.receipt.pk}/').json()['pdi']
        self.assertEqual([row['la_moi_nhat'] for row in history], [True, False])

    def test_incomplete_pdi_warns_and_cannot_be_approved(self):
        self.client.force_login(self.user)
        pdi = s.record_pdi(self.user, self.receipt.pk, tinh_trang='Mới ghi tổng thể', ket_qua='DAT')
        response = self.client.get(f'/kho/pdi/{pdi.pk}/').json()
        self.assertTrue(response['pdi']['canh_bao'])
        self.assertFalse(response['thao_tac']['duyet'])
        self.assertEqual(self.post_action('duyet-pdi', {'pdi_id': pdi.pk}).status_code, 400)
        self.assertFalse(TonKho.objects.exists())

    def test_missing_vehicle_information_blocks_submission(self):
        self.client.force_login(self.user)
        self.prepare()
        self.receipt.trang_thai = 'NHAP'
        self.receipt.save(update_fields=['trang_thai'])
        Xe.objects.filter(pk=self.receipt.xe_id).update(phien_ban=None)
        details = self.client.get(f'/kho/phieu-nhap/{self.receipt.pk}/').json()['phieu_nhap']
        self.assertTrue(details['canh_bao'])
        self.assertFalse(details['thao_tac']['gui_duyet'])
        self.assertEqual(self.post_action('gui-duyet', {'pdi_id': self.pdi_id()}).status_code, 400)
        self.assertFalse(TonKho.objects.exists())

    def test_database_failure_keeps_waiting_receipt_and_stock_unchanged(self):
        self.client.force_login(self.user)
        self.prepare()
        with self.assertLogs('core.iii_iv_api', level='ERROR'):
            with patch('warehouse.services.LichSuNhapKho.objects.create', side_effect=OperationalError('private database error')):
                response = self.post_action('duyet', {'pdi_id': self.pdi_id()})
        self.assertEqual(response.status_code, 503)
        self.assertNotIn('private database error', response.content.decode())
        self.receipt.refresh_from_db()
        self.assertEqual(self.receipt.trang_thai, 'CHO_DUYET')
        self.assertFalse(TonKho.objects.exists())
        self.assertFalse(LichSuNhapKho.objects.exists())

    def test_vehicle_lookup_filters_and_blocks_a_second_receipt_for_the_same_vin(self):
        self.client.force_login(self.user)
        data = self.client.get('/kho/xe-co-the-nhap/', {'dong_xe': 'everest', 'phien_ban': 'titanium', 'mau_sac': 'trắng', 'nguon_xe': 'N'}).json()['xe']
        self.assertEqual(len(data), 1)
        self.assertTrue(data[0]['dang_co_phieu'])
        self.assertFalse(data[0]['co_the_tao'])
        self.assertTrue(data[0]['canh_bao'])
        invoice = HoaDonNhap.objects.create(ma_hdn='HD2', nha_cung_cap=self.line.hoa_don_nhap.nha_cung_cap,
            chi_nhanh=self.kho.chi_nhanh, don_vi_van_chuyen=self.line.hoa_don_nhap.don_vi_van_chuyen, ngay_nhap=timezone.now())
        another = ChiTietNhap.objects.create(hoa_don_nhap=invoice, xe=self.line.xe, don_gia=Decimal('100'))
        with self.assertRaises(ValidationError):
            s.create_receipt(self.user, ma_phieu='PN2', chi_tiet_nhap_id=another.pk, kho_id=self.kho.pk, ngay_nhap=date.today())
        TonKho.objects.create(kho=self.kho, xe=self.line.xe, ngay_vao_kho=date.today())
        self.assertEqual(self.client.get('/kho/xe-co-the-nhap/').json()['xe'], [])

    def test_warehouse_options_and_action_flags_respect_the_workers_branch(self):
        worker, _ = self.business_users()
        other = ChiNhanh.objects.create(ma_cn='GL', ten_cn='Gia Lai')
        other_kho = Kho.objects.create(ma_kho='KGL', chi_nhanh=other)
        self.client.force_login(worker)
        options = self.client.get('/kho/phieu-nhap/tuy-chon/').json()
        self.assertEqual({row['kho_id']: row['co_the_lap'] for row in options['kho']}, {'K': True, 'KGL': False})
        self.receipt.kho = other_kho
        self.receipt.save()
        flags = self.client.get(f'/kho/phieu-nhap/{self.receipt.pk}/').json()['phieu_nhap']['thao_tac']
        self.assertFalse(flags['cap_nhat_pdi'])
        self.assertFalse(flags['duyet_pdi'])
        self.assertEqual(self.post_action('pdi', {'tinh_trang': 'Kiểm tra', 'ket_qua': 'DAT'}).status_code, 403)

    def test_malformed_creation_filters_and_missing_objects(self):
        import json
        self.client.force_login(self.user)
        for line_id in (True, [], {}, -1, 'not-an-id'):
            payload = {'chi_tiet_nhap_id': line_id, 'kho_id': self.kho.pk, 'ngay_nhap': '2026-11-03'}
            response = self.client.post('/kho/phieu-nhap/tao/', json.dumps(payload), content_type='application/json')
            self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client.get('/kho/phieu-nhap/?trang_thai=FAKE').status_code, 400)
        self.assertEqual(self.client.get('/kho/xe-co-the-nhap/?trang_thai=FAKE').status_code, 400)
        self.assertEqual(self.client.get('/kho/phieu-nhap/99999/').status_code, 404)
        self.assertEqual(self.client.get('/kho/pdi/99999/').status_code, 404)
        self.assertEqual(self.post_action('unknown', {}).status_code, 404)

    def test_receipt_creation_by_post_saves_a_draft_without_adding_stock(self):
        import json
        worker, _ = self.business_users()
        car = Xe.objects.create(vin='VIN-NEW', ten_xe='Ranger', phien_ban='XLS', loai_xe='PICKUP', so_may='NEW', mau_sac='Đen')
        line = ChiTietNhap.objects.create(hoa_don_nhap=self.line.hoa_don_nhap, xe=car, don_gia=Decimal('100'))
        self.client.force_login(worker)
        response = self.client.post('/kho/phieu-nhap/tao/', json.dumps({
            'chi_tiet_nhap_id': line.pk, 'kho_id': self.kho.pk, 'ngay_nhap': '2026-11-03'}), content_type='application/json')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()['phieu_nhap']['trang_thai'], 'NHAP')
        self.assertIsNone(response.json()['phieu_nhap']['pdi_moi_nhat'])
        self.assertFalse(TonKho.objects.exists())
