from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import TestCase
from django.utils import timezone

from .models import (
    TIEN_MAX, ChiNhanh, ChiTietBan, ChiTietKiemKe, ChiTietNhap, DonViVanChuyen,
    HoaDonBan, HoaDonNhap, KhachHang, NhaCungCap, NhanVien, Xe,
)

D = Decimal


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
    def test_sdt_phai_dung_10_chu_so_ascii(self):
        cn = ChiNhanh.objects.create(ma_cn="CN1", ten_cn="Chi nhanh 1")
        sai = (
            "012345678",            # thiếu số
            "01234567890",          # thừa số
            "abcdefghij",           # chữ cái
            "0123456789\n",         # xuống dòng ở cuối
            "\u0660\u0661\u0662\u0663\u0664\u0665\u0666\u0667\u0668\u0669",  # chữ số Ả Rập
        )
        for sdt in sai:
            with self.assertRaises(ValidationError, msg=repr(sdt)):
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

    def tao(self, so_luong, don_gia):
        return ChiTietNhap(
            hoa_don_nhap=self.hdn, xe=self.xe, so_luong_nhap=so_luong, don_gia=D(don_gia),
        )

    def test_thanh_tien_tu_tinh(self):
        ct = self.tao(3, "100.50")
        ct.save()
        ct.refresh_from_db()
        self.assertEqual(ct.thanh_tien, D("301.50"))

    def test_cap_nhat_so_luong_don_gia_tinh_lai(self):
        ct = self.tao(1, "100.00")
        ct.save()
        ct.so_luong_nhap, ct.don_gia = 2, D("50.05")
        ct.save()
        ct.refresh_from_db()
        self.assertEqual(ct.thanh_tien, D("100.10"))

    def test_so_luong_khong_hop_le(self):
        for so_luong in (0, -1):
            with self.assertRaises(ValidationError, msg=so_luong) as ctx:
                self.tao(so_luong, "1").full_clean()
            self.assertIn("so_luong_nhap", ctx.exception.message_dict)

    def test_don_gia_am(self):
        with self.assertRaises(ValidationError) as ctx:
            self.tao(1, "-1").full_clean()
        self.assertIn("don_gia", ctx.exception.message_dict)

    def test_don_gia_qua_2_chu_so_thap_phan(self):
        with self.assertRaises(ValidationError) as ctx:
            self.tao(1, "1.005").full_clean()
        self.assertIn("don_gia", ctx.exception.message_dict)

    def test_vuot_gioi_han_truong_du_lieu(self):
        with self.assertRaises(ValidationError):
            self.tao(2, str(TIEN_MAX)).full_clean()

    def test_check_constraint_chan_thanh_tien_am(self):
        ct = self.tao(1, "10")
        ct.save()
        with self.assertRaises(IntegrityError), transaction.atomic():
            ChiTietNhap.objects.filter(pk=ct.pk).update(thanh_tien=D("-1"))

    def test_khong_xoa_duoc_xe_da_co_chung_tu(self):
        self.tao(1, "1").save()
        with self.assertRaises(ProtectedError):
            self.xe.delete()


class ChiTietBanTests(TestCase):
    def setUp(self):
        kh = KhachHang.objects.create(ma_kh="KH1", ten_kh="KH", sdt_kh="0123456789")
        cn = ChiNhanh.objects.create(ma_cn="CN1", ten_cn="CN")
        self.hdb = HoaDonBan.objects.create(
            ma_hdb="HDB1", khach_hang=kh, chi_nhanh=cn, ngay_ban=timezone.now(),
        )
        self.xe = Xe.objects.create(vin="VIN1", ten_xe="Xe 1", loai_xe="SUV", so_may="SM1")

    def tao(self, so_luong, gia_ban):
        return ChiTietBan(
            hoa_don_ban=self.hdb, xe=self.xe, so_luong_ban=so_luong, gia_ban=D(gia_ban),
        )

    def kiem_tra(self, so_luong, gia_ban, vat, tong):
        ct = self.tao(so_luong, gia_ban)
        ct.save()
        ct.refresh_from_db()
        self.assertEqual(ct.tien_vat, D(vat))
        self.assertEqual(ct.tong_thanh_toan, D(tong))

    def test_vat_10_phan_tram_khong_tinh_hai_lan(self):
        # tiền hàng 2 x 500 = 1000 -> VAT 100 -> tổng 1100 (không phải 1210)
        self.kiem_tra(2, "500.00", "100.00", "1100.00")

    def test_vat_phat_sinh_so_le_lam_tron_half_up(self):
        self.kiem_tra(1, "100.05", "10.01", "110.06")   # 10.005 -> 10.01
        self.kiem_tra_moi(3, "33.33", "10.00", "109.99")  # 9.999 -> 10.00

    def kiem_tra_moi(self, so_luong, gia_ban, vat, tong):
        ChiTietBan.objects.all().delete()
        self.kiem_tra(so_luong, gia_ban, vat, tong)

    def test_cap_nhat_so_luong_don_gia_tinh_lai(self):
        ct = self.tao(1, "100.00")
        ct.save()
        ct.so_luong_ban, ct.gia_ban = 2, D("50.05")
        ct.save()
        ct.refresh_from_db()
        self.assertEqual(ct.tien_vat, D("10.01"))
        self.assertEqual(ct.tong_thanh_toan, D("110.11"))

    def test_so_luong_khong_hop_le(self):
        for so_luong in (0, -1):
            with self.assertRaises(ValidationError, msg=so_luong) as ctx:
                self.tao(so_luong, "1").full_clean()
            self.assertIn("so_luong_ban", ctx.exception.message_dict)

    def test_gia_ban_am(self):
        with self.assertRaises(ValidationError) as ctx:
            self.tao(1, "-5").full_clean()
        self.assertIn("gia_ban", ctx.exception.message_dict)

    def test_vuot_gioi_han_truong_du_lieu(self):
        with self.assertRaises(ValidationError):
            self.tao(2, str(TIEN_MAX)).full_clean()

    def test_check_constraint_chan_tien_am(self):
        ct = self.tao(1, "10")
        ct.save()
        for truong in ("tien_vat", "tong_thanh_toan"):
            with self.assertRaises(IntegrityError, msg=truong), transaction.atomic():
                ChiTietBan.objects.filter(pk=ct.pk).update(**{truong: D("-1")})


class ChiTietKiemKeTests(TestCase):
    def test_ton_thuc_te_chi_nhan_0_hoac_1(self):
        ct = ChiTietKiemKe(ton_he_thong=1, ton_thuc_te=5)
        with self.assertRaises(ValidationError) as ctx:
            ct.full_clean(exclude=["phieu_kiem_ke", "xe"])
        self.assertIn("ton_thuc_te", ctx.exception.message_dict)
