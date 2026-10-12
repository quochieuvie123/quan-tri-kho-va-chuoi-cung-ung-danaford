from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from .models import (
    ChiNhanh, ChiTietKiemKe, ChiTietNhap, DonViVanChuyen, HoaDonNhap,
    NhaCungCap, NhanVien, Xe,
)


class NhaCungCapModelTests(TestCase):
    def test_str_returns_supplier_name(self):
        supplier = NhaCungCap(
            ma_ncc="NCC-TEST",
            ten_ncc="Nha cung cap thu nghiem",
            dia_chi_ncc="Da Nang",
            mst="MST-TEST",
        )
        self.assertEqual(str(supplier), "Nha cung cap thu nghiem")


class SdtValidatorTests(TestCase):
    def test_sdt_phai_dung_10_chu_so(self):
        cn = ChiNhanh.objects.create(ma_cn="CN1", ten_cn="Chi nhanh 1")
        for sdt in ("012345678", "01234567890", "abcdefghij", "0123456789\n"):
            with self.assertRaises(ValidationError, msg=sdt):
                NhanVien(ma_nv="NV1", chi_nhanh=cn, ten_nv="A", sdt_nv=sdt).full_clean()
        NhanVien(ma_nv="NV1", chi_nhanh=cn, ten_nv="A", sdt_nv="0123456789").full_clean()


class ChiTietNhapTests(TestCase):
    def setUp(self):
        ncc = NhaCungCap.objects.create(ma_ncc="NCC1", ten_ncc="NCC", mst="111")
        dvvc = DonViVanChuyen.objects.create(ma_dvvc="VC1", ten_dvvc="VC")
        cn = ChiNhanh.objects.create(ma_cn="CN1", ten_cn="CN")
        self.hdn = HoaDonNhap.objects.create(
            ma_hdn="HDN1", nha_cung_cap=ncc, chi_nhanh=cn,
            don_vi_van_chuyen=dvvc, ngay_nhap=timezone.now(),
        )
        self.xe = Xe.objects.create(vin="VIN1", ten_xe="Xe 1", loai_xe="SUV", so_may="SM1")

    def test_thanh_tien_tu_tinh(self):
        ct = ChiTietNhap.objects.create(
            hoa_don_nhap=self.hdn, xe=self.xe, so_luong_nhap=3, don_gia=Decimal("100.50"),
        )
        ct.refresh_from_db()
        self.assertEqual(ct.thanh_tien, Decimal("301.50"))

    def test_so_luong_phai_duong(self):
        ct = ChiTietNhap(hoa_don_nhap=self.hdn, xe=self.xe, so_luong_nhap=0, don_gia=Decimal("1"))
        with self.assertRaises(ValidationError):
            ct.full_clean()

    def test_khong_xoa_duoc_xe_da_co_chung_tu(self):
        ChiTietNhap.objects.create(
            hoa_don_nhap=self.hdn, xe=self.xe, so_luong_nhap=1, don_gia=Decimal("1"),
        )
        from django.db.models import ProtectedError
        with self.assertRaises(ProtectedError):
            self.xe.delete()


class ChiTietKiemKeTests(TestCase):
    def test_ton_thuc_te_chi_nhan_0_hoac_1(self):
        ct = ChiTietKiemKe(ton_he_thong=1, ton_thuc_te=5)
        with self.assertRaises(ValidationError) as ctx:
            ct.full_clean(exclude=["phieu_kiem_ke", "xe"])
        self.assertIn("ton_thuc_te", ctx.exception.message_dict)
