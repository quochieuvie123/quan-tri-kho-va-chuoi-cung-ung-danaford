from datetime import datetime
from decimal import Decimal
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone
from openpyxl import Workbook

from database.models import ChiNhanh, ChiTietNhap, DonViVanChuyen, HoaDonNhap, Kho, NhaCungCap, NhanVien, TonKho, Xe, BienBanPDI
from warehouse.models import KetQuaPDI, PhieuNhapKho
from warehouse.pdi_import import HEADERS


class PdiImportTests(TestCase):
    def test_transfer_import_keeps_each_vin_independent(self):
        from transfers.models import LenhLuuChuyen, ChiTietLenhLuuChuyen
        from warehouse.pdi_import import read_file, import_rows
        branch = ChiNhanh.objects.create(ma_cn='CN02', ten_cn='Bình Định')
        source = Kho.objects.create(ma_kho='KHO02', chi_nhanh=branch)
        transfer = LenhLuuChuyen.objects.create(
            ma_lenh='LC-PDI-IMPORT', kho_xuat=source, kho_nhap=self.store,
            nguoi_lap=self.user, trang_thai=LenhLuuChuyen.TrangThai.DA_GIAO_DEN_DA_NANG)
        for vin in ('VIN1', 'VIN3'):
            ChiTietLenhLuuChuyen.objects.create(lenh=transfer, xe_id=vin)
            PhieuNhapKho.objects.filter(xe_id=vin).update(
                loai_nguon=PhieuNhapKho.LoaiNguon.LUU_CHUYEN,
                chi_tiet_nhap=None, lenh_luu_chuyen=transfer)
        import_rows(self.user, read_file(self.file().read()))
        self.assertEqual(PhieuNhapKho.objects.get(xe_id='VIN1').trang_thai, 'DA_DUYET')
        self.assertEqual(PhieuNhapKho.objects.get(xe_id='VIN3').trang_thai, 'NHAP')
        incident = BienBanPDI.objects.get(xe_id='VIN3')
        self.assertEqual(incident.lenh_luu_chuyen_id, transfer.pk)
        self.assertIsNone(incident.hoa_don_nhap_id)
        transfer.refresh_from_db()
        self.assertNotEqual(transfer.trang_thai, LenhLuuChuyen.TrangThai.HOAN_TAT)

    def setUp(self):
        branch = ChiNhanh.objects.create(ma_cn='CN01', ten_cn='Đà Nẵng')
        self.store = Kho.objects.create(ma_kho='KHO01', chi_nhanh=branch)
        employee = NhanVien.objects.create(ma_nv='NV1', chi_nhanh=branch, ten_nv='Kho')
        self.user = get_user_model().objects.create_superuser(username='testadmin', password='test')
        self.user.nhan_vien = employee
        self.user.save()
        supplier = NhaCungCap.objects.create(ma_ncc='NCC', ten_ncc='Ford', mst='1234567890')
        carrier = DonViVanChuyen.objects.create(ma_dvvc='DV', ten_dvvc='Vận chuyển')
        invoice = HoaDonNhap.objects.create(ma_hdn='HDN', nha_cung_cap=supplier, chi_nhanh=branch,
                                            don_vi_van_chuyen=carrier, ngay_nhap=timezone.now())
        for i in range(1, 5):
            car = Xe.objects.create(vin=f'VIN{i}', ten_xe='Ranger', loai_xe='Ranger', so_may=f'SM{i}', mau_sac='Trắng')
            line = ChiTietNhap.objects.create(hoa_don_nhap=invoice, xe=car, so_luong_nhap=1, don_gia=Decimal('1'))
            PhieuNhapKho.objects.create(ma_phieu=f'PN{i}', chi_tiet_nhap=line, xe=car, kho=self.store,
                                        ngay_nhap=timezone.localdate(), nguoi_lap=self.user)
        self.client.force_login(self.user)

    def file(self, invalid=False):
        book = Workbook(); sheet = book.active; sheet.append(HEADERS)
        for i in range(1, 5):
            failed = i > 2
            sheet.append([f'PN{i}', f'VIN{i}', f'PDI{i}', datetime(2026, 11, 11), 'Xưởng',
                          'KHONG_DAT' if failed else 'DAT', 'DAT', 'DAT',
                          'DAT' if invalid and failed else ('KHONG_DAT' if failed else 'DAT'),
                          'Trầy xước sơn' if failed else '', 'Trầy cửa' if failed else '', 'Giả lập'])
        output = BytesIO(); book.save(output)
        return SimpleUploadedFile('pdi.xlsx', output.getvalue(), content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

    def test_preview_confirm_and_repeat(self):
        response = self.client.post('/kho/nhap/import-pdi/', {'file': self.file()}, HTTP_HOST='localhost')
        self.assertContains(response, 'Xem trước 4 xe')
        self.assertEqual(KetQuaPDI.objects.count(), 0)
        response = self.client.post('/kho/nhap/import-pdi/', {'confirm': '1'}, HTTP_HOST='localhost')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(PhieuNhapKho.objects.filter(trang_thai='DA_DUYET').count(), 2)
        self.assertEqual(PhieuNhapKho.objects.filter(trang_thai='NHAP').count(), 2)
        self.assertEqual(TonKho.objects.filter(so_luong_ton=1).count(), 2)
        self.assertEqual(BienBanPDI.objects.filter(trang_thai_claim='Chưa xử lý').count(), 2)
        self.client.post('/kho/nhap/import-pdi/', {'file': self.file()}, HTTP_HOST='localhost')
        self.assertEqual(KetQuaPDI.objects.count(), 4)
        self.assertEqual(TonKho.objects.filter(so_luong_ton=1).count(), 2)

    def test_bad_file_does_not_update_anything(self):
        response = self.client.post('/kho/nhap/import-pdi/', {'file': self.file(invalid=True)}, HTTP_HOST='localhost')
        self.assertContains(response, 'kết quả tổng không khớp')
        self.assertEqual(KetQuaPDI.objects.count(), 0)
        self.assertEqual(TonKho.objects.count(), 0)

    def test_admin_without_employee_selects_recording_employee(self):
        self.user.nhan_vien = None
        self.user.save(update_fields=['nhan_vien'])
        response = self.client.post('/kho/nhap/import-pdi/', {'file': self.file(), 'nhan_vien': 'NV1'}, HTTP_HOST='localhost')
        self.assertContains(response, 'Xem trước 4 xe')
        response = self.client.post('/kho/nhap/import-pdi/', {'confirm': '1'}, HTTP_HOST='localhost')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(BienBanPDI.objects.filter(nhan_vien_id='NV1').count(), 2)
        self.assertEqual(KetQuaPDI.objects.filter(nguoi_kiem_tra=self.user).count(), 4)
