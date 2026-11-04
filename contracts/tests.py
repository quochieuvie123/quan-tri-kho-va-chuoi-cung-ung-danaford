from datetime import date
from decimal import Decimal
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.utils import timezone
from unittest.mock import patch
from django.db import OperationalError
from django.core.management import call_command
from django.contrib.auth.models import Group
from database.models import HopDong, ChiTietHopDong, Xe, KhachHang, ChiNhanh, Kho, TonKho, NhanVien, HoaDonBan, PhieuXuatKho


class ContractTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(username='viewer', password='test-only')
        self.user.user_permissions.add(*Permission.objects.filter(content_type__app_label='database', codename__in=['view_hopdong', 'view_tonkho']))
        self.client.force_login(self.user)
        self.cn = ChiNhanh.objects.create(ma_cn='DN', ten_cn='Đà Nẵng')
        self.kho = Kho.objects.create(ma_kho='KDN', chi_nhanh=self.cn)
        kh = KhachHang.objects.create(ma_kh='KH', ten_kh='Khách A', sdt_kh='0901234567')
        self.hd = HopDong.objects.create(ma_hd='HD1', chi_nhanh=self.cn, khach_hang=kh, ngay_ky=timezone.now(), so_tien_coc=Decimal('100'))
        self.car = Xe.objects.create(vin='VIN1', ten_xe='Everest', loai_xe='SUV', mau_sac='Trắng', so_may='M1', phien_ban='Titanium')
        ChiTietHopDong.objects.create(hop_dong=self.hd, xe=self.car)
        TonKho.objects.create(kho=self.kho, xe=self.car, ngay_vao_kho=date.today())

    def test_list_detail_search(self):
        self.assertEqual(len(self.client.get('/hop-dong/?q=Khách').json()['hop_dong']), 1)
        self.assertEqual(self.client.get('/hop-dong/?q=missing').json()['hop_dong'], [])
        self.assertEqual(self.client.get('/hop-dong/HD1/').json()['xe'][0]['xe_id'], 'VIN1')
        self.assertEqual(self.client.get('/hop-dong/missing/').status_code, 404)

    def test_suggestions_are_read_only_and_exclude_zero_stock(self):
        zero = Xe.objects.create(vin='VIN2', ten_xe='Everest', loai_xe='SUV', mau_sac='Trắng', so_may='M2')
        TonKho.objects.create(kho=self.kho, xe=zero, ngay_vao_kho=date.today(), so_luong_ton=0)
        self.assertEqual([r['xe_id'] for r in self.client.get('/hop-dong/HD1/xe-phu-hop/').json()['xe_phu_hop']], ['VIN1'])
        self.assertEqual(ChiTietHopDong.objects.count(), 1)
        self.assertEqual(TonKho.objects.get(xe=self.car).so_luong_ton, 1)

    def test_missing_criteria_and_permissions(self):
        self.car.mau_sac = None
        self.car.save()
        self.assertEqual(self.client.get('/hop-dong/HD1/xe-phu-hop/').status_code, 400)
        self.user.is_superuser = False
        self.user.save()
        self.user.user_permissions.clear()
        self.assertEqual(self.client.get('/hop-dong/').status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get('/hop-dong/').status_code, 302)

    def test_unassigned_contract_exact_variant(self):
        ChiTietHopDong.objects.all().delete()
        self.hd.dong_xe_yeu_cau = 'Everest'
        self.hd.phien_ban_yeu_cau = 'Titanium'
        self.hd.mau_sac_yeu_cau = 'Trắng'
        self.hd.save()
        self.car.phien_ban = 'Titanium X'
        self.car.save()
        self.assertEqual(self.client.get('/hop-dong/HD1/xe-phu-hop/').json()['xe_phu_hop'], [])
        self.car.phien_ban = 'Titanium'
        self.car.save()
        self.assertEqual(len(self.client.get('/hop-dong/HD1/xe-phu-hop/').json()['xe_phu_hop']), 1)
        self.hd.mau_sac_yeu_cau = None
        self.hd.save()
        self.assertEqual(self.client.get('/hop-dong/HD1/xe-phu-hop/').status_code, 400)

    def test_legacy_vehicle_filters_match_the_displayed_criteria(self):
        data = self.client.get('/hop-dong/', {'dong_xe': ' everest ', 'phien_ban': 'titanium', 'mau_sac': 'Trắng'}).json()
        self.assertEqual([row['ma_hd'] for row in data['hop_dong']], ['HD1'])
        second = Xe.objects.create(vin='VIN2', ten_xe='Ranger', phien_ban='XLS', loai_xe='PICKUP', so_may='M2', mau_sac='Đen')
        ChiTietHopDong.objects.create(hop_dong=self.hd, xe=second)
        self.assertEqual(self.client.get('/hop-dong/', {'dong_xe': 'Everest', 'phien_ban': 'XLS'}).json()['hop_dong'], [])

    def test_partial_independent_criteria_do_not_fall_back_to_an_assigned_vin(self):
        self.hd.dong_xe_yeu_cau = 'Ranger'
        self.hd.save()
        data = self.client.get('/hop-dong/', {'dong_xe': 'Ranger'}).json()['hop_dong']
        self.assertEqual(len(data), 1)
        self.assertTrue(data[0]['canh_bao'])
        self.assertEqual(self.client.get('/hop-dong/HD1/xe-phu-hop/').status_code, 400)

    def test_empty_states_invalid_date_and_data_failure(self):
        self.assertEqual(self.client.get('/hop-dong/?ngay_du_kien_giao=bad').status_code, 400)
        self.assertIn('phù hợp', self.client.get('/hop-dong/?q=missing').json()['message'])
        self.hd.delete()
        self.assertIn('Chưa có', self.client.get('/hop-dong/').json()['message'])
        with self.assertLogs('core.iii_iv_api', level='ERROR'):
            with patch('contracts.views.HopDong.objects.select_related', side_effect=OperationalError('private SQL')):
                response = self.client.get('/hop-dong/')
        self.assertEqual(response.status_code, 503)
        self.assertNotIn('private SQL', response.content.decode())

    def test_invoice_must_be_linked_to_this_contract(self):
        unrelated = HoaDonBan.objects.create(ma_hdb='HDB-OTHER', khach_hang=self.hd.khach_hang, chi_nhanh=self.cn, ngay_ban=timezone.now())
        self.assertEqual(self.client.get('/hop-dong/HD1/').json()['hoa_don'], [])
        line = ChiTietHopDong.objects.get(hop_dong=self.hd)
        export = PhieuXuatKho.objects.create(ma_pxk='PXK', chi_tiet_hop_dong=line, kho=self.kho, ngay_xuat=timezone.now())
        unrelated.phieu_xuat_kho = export
        unrelated.save()
        self.assertEqual(self.client.get('/hop-dong/HD1/').json()['hoa_don'][0]['ma_hdb'], 'HDB-OTHER')

    def test_suggested_vehicle_detail_and_state_do_not_reserve_a_car(self):
        row = self.client.get('/hop-dong/HD1/xe-phu-hop/VIN1/').json()['xe'][0]
        self.assertEqual(row['vi_tri_kho'], 'Đà Nẵng')
        self.assertNotEqual(row['trang_thai_hien_thi'], 'Sẵn sàng')
        TonKho.objects.filter(xe=self.car).update(so_luong_ton=0)
        self.assertEqual(self.client.get('/hop-dong/HD1/xe-phu-hop/VIN1/').status_code, 404)
        self.assertEqual(ChiTietHopDong.objects.count(), 1)
        self.assertIsNone(HopDong.objects.get(pk=self.hd.pk).trang_thai)

    def make_business_user(self, name, group, branch=None):
        call_command('setup_hopdong_nhapkho_roles', stdout=__import__('io').StringIO())
        user = get_user_model().objects.create_user(username=name)
        user.groups.add(Group.objects.get(name=group))
        if branch:
            user.nhan_vien = NhanVien.objects.create(ma_nv=name, ten_nv=name, chi_nhanh=branch)
            user.save()
        return user

    def test_real_sale_admin_and_da_nang_worker_have_different_actions(self):
        sale = self.make_business_user('sale', 'III-IV Sale Admin')
        worker = self.make_business_user('worker', 'III-IV Nhân viên kho', self.cn)
        for user, detail_status, suggestion_status in [(sale, 200, 403), (worker, 403, 200)]:
            with self.subTest(user=user.username):
                self.client.force_login(user)
                row = self.client.get('/hop-dong/').json()['hop_dong'][0]
                self.assertEqual(row['thao_tac']['xem_chi_tiet'], detail_status == 200)
                self.assertEqual(row['thao_tac']['de_xuat_xe'], suggestion_status == 200)
                self.assertEqual(self.client.get('/hop-dong/HD1/').status_code, detail_status)
                self.assertEqual(self.client.get('/hop-dong/HD1/xe-phu-hop/').status_code, suggestion_status)

    def test_staff_or_a_worker_from_another_branch_is_not_authorized(self):
        other = ChiNhanh.objects.create(ma_cn='GL', ten_cn='Gia Lai')
        worker = self.make_business_user('other', 'III-IV Nhân viên kho', other)
        worker.is_staff = True
        worker.save()
        self.client.force_login(worker)
        self.assertEqual(self.client.get('/hop-dong/').status_code, 403)
        staff = get_user_model().objects.create_user(username='staff', is_staff=True)
        staff.user_permissions.add(Permission.objects.get(content_type__app_label='database', codename='view_hopdong'))
        self.client.force_login(staff)
        self.assertEqual(self.client.get('/hop-dong/').status_code, 403)

    def test_action_flags_also_require_model_permissions(self):
        worker = self.make_business_user('limited', 'III-IV Nhân viên kho', self.cn)
        group = Group.objects.get(name='III-IV Nhân viên kho')
        group.permissions.remove(Permission.objects.get(content_type__app_label='database', codename='view_tonkho'))
        self.client.force_login(worker)
        self.assertFalse(self.client.get('/hop-dong/').json()['hop_dong'][0]['thao_tac']['de_xuat_xe'])
        self.assertEqual(self.client.get('/hop-dong/HD1/xe-phu-hop/').status_code, 403)
