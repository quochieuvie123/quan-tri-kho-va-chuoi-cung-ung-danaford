from datetime import date, timedelta

from django.test import TestCase
from django.utils import timezone

from database.models import ChiNhanh, Kho, TonKho, Xe
from .forms import (
    MAX_KHOANG_BAO_CAO_THANG,
    BoLocBaoCaoForm,
)
from .utils import tao_bao_cao


class BaoCaoTonKhoTest(TestCase):
    def setUp(self):
        self.kho = self.tao_kho("KHO-REPORT-1", "CN-REPORT-1")
        self.kho_khac = self.tao_kho("KHO-REPORT-2", "CN-REPORT-2")

    def tao_kho(self, ma_kho, ma_chi_nhanh):
        chi_nhanh = ChiNhanh.objects.create(
            ma_cn=ma_chi_nhanh,
            ten_cn=f"Chi nhánh {ma_chi_nhanh}",
        )
        return Kho.objects.create(
            ma_kho=ma_kho,
            chi_nhanh=chi_nhanh,
        )

    def tao_xe(self, vin, ten_xe, mau_sac="Đỏ"):
        return Xe.objects.create(
            vin=vin,
            ten_xe=ten_xe,
            loai_xe="SUV",
            so_may=f"MAY-{vin}",
            mau_sac=mau_sac,
        )

    def tao_ton_kho(self, kho, xe, so_luong, ngay_vao_kho):
        return TonKho.objects.create(
            kho=kho,
            xe=xe,
            so_luong_ton=so_luong,
            ngay_vao_kho=ngay_vao_kho,
        )

    def test_bao_cao_tinh_tong_ton_va_nhom_tuoi_ton(self):
        hom_nay = timezone.localdate()
        xe_ton_lau = self.tao_xe("VIN-REPORT-OLD", "Ford Ranger")
        xe_ton_moi = self.tao_xe("VIN-REPORT-NEW", "Ford Everest")

        self.tao_ton_kho(
            self.kho,
            xe_ton_lau,
            so_luong=2,
            ngay_vao_kho=hom_nay - timedelta(days=61),
        )
        self.tao_ton_kho(
            self.kho,
            xe_ton_moi,
            so_luong=1,
            ngay_vao_kho=hom_nay - timedelta(days=20),
        )

        bao_cao = tao_bao_cao(
            Kho.objects.filter(pk=self.kho.pk),
            {},
            kem_thong_ke=True,
        )

        self.assertEqual(bao_cao["ton_kho"]["tong"], 3)
        self.assertEqual(bao_cao["tuoi_ton"]["tong"], 3)
        self.assertEqual(bao_cao["tuoi_ton"]["ton_lau"], 2)
        self.assertEqual(bao_cao["tuoi_ton"]["ty_le_ton_lau"], 66.7)
        self.assertEqual(
            dict(bao_cao["tuoi_ton"]["nhom"])["Trên 60 ngày"],
            2,
        )
        self.assertEqual(
            dict(bao_cao["tuoi_ton"]["nhom"])["Từ 0 đến 30 ngày"],
            1,
        )

    def test_bao_cao_danh_dau_xe_co_ngay_vao_kho_trong_tuong_lai(self):
        xe = self.tao_xe("VIN-REPORT-FUTURE", "Ford Ranger")
        self.tao_ton_kho(
            self.kho,
            xe,
            so_luong=2,
            ngay_vao_kho=timezone.localdate() + timedelta(days=1),
        )

        bao_cao = tao_bao_cao(
            Kho.objects.filter(pk=self.kho.pk),
            {},
        )

        self.assertEqual(bao_cao["ton_kho"]["tong"], 2)
        self.assertEqual(bao_cao["tuoi_ton"]["ngay_khong_hop_le"], 2)
        self.assertEqual(
            bao_cao["tuoi_ton"]["dong"][0][4],
            "Ngày vào kho không hợp lệ",
        )

    def test_bo_loc_gioi_han_bao_cao_theo_kho_va_ten_xe(self):
        xe_dung_ten = self.tao_xe("VIN-REPORT-MATCH", "Ford Ranger")
        xe_khac_ten = self.tao_xe("VIN-REPORT-OTHER", "Ford Everest")
        xe_kho_khac = self.tao_xe("VIN-REPORT-OTHER-WH", "Ford Ranger")

        self.tao_ton_kho(
            self.kho,
            xe_dung_ten,
            so_luong=2,
            ngay_vao_kho=timezone.localdate(),
        )
        self.tao_ton_kho(
            self.kho,
            xe_khac_ten,
            so_luong=4,
            ngay_vao_kho=timezone.localdate(),
        )
        self.tao_ton_kho(
            self.kho_khac,
            xe_kho_khac,
            so_luong=5,
            ngay_vao_kho=timezone.localdate(),
        )

        bao_cao = tao_bao_cao(
            Kho.objects.all(),
            {
                "kho": self.kho,
                "ten_xe": "Ranger",
            },
            kem_thong_ke=True,
        )

        self.assertEqual(bao_cao["ton_kho"]["tong"], 2)
        self.assertEqual(len(bao_cao["ton_kho"]["dong"]), 1)
        self.assertEqual(bao_cao["ton_kho"]["dong"][0][2], "Ford Ranger")
        self.assertEqual(
            bao_cao["ton_kho"]["theo_kho"],
            [[self.kho.pk, 2]],
        )

    def test_thong_ke_theo_kho_van_co_kho_khong_co_ton(self):
        xe = self.tao_xe("VIN-REPORT-ONE-WAREHOUSE", "Ford Ranger")
        self.tao_ton_kho(
            self.kho,
            xe,
            so_luong=3,
            ngay_vao_kho=timezone.localdate(),
        )

        bao_cao = tao_bao_cao(
            Kho.objects.all(),
            {},
            kem_thong_ke=True,
        )

        self.assertEqual(
            dict(bao_cao["ton_kho"]["theo_kho"]),
            {
                self.kho.pk: 3,
                self.kho_khac.pk: 0,
            },
        )

    def test_form_bao_cao_bao_loi_khi_ngay_bat_dau_sau_ngay_ket_thuc(self):
        form = BoLocBaoCaoForm(
            data={
                "tu_ngay": "2026-11-10",
                "den_ngay": "2026-11-09",
            },
            danh_sach_kho=Kho.objects.all(),
        )

        self.assertFalse(form.is_valid())
        self.assertIn("den_ngay", form.errors)

    def test_form_chap_nhan_khoang_bao_cao_dung_120_thang(self):
        ngay_ket_thuc = date(
            timezone.localdate().year,
            timezone.localdate().month,
            1,
        )
        chi_so_thang_cuoi = (
            ngay_ket_thuc.year * 12
            + ngay_ket_thuc.month
            - 1
        )
        chi_so_thang_dau = (
            chi_so_thang_cuoi
            - MAX_KHOANG_BAO_CAO_THANG
            + 1
        )
        ngay_bat_dau = date(
            chi_so_thang_dau // 12,
            chi_so_thang_dau % 12 + 1,
            1,
        )

        form = BoLocBaoCaoForm(
            data={
                "tu_ngay": ngay_bat_dau.isoformat(),
                "den_ngay": ngay_ket_thuc.isoformat(),
            },
            danh_sach_kho=Kho.objects.all(),
        )

        self.assertEqual(MAX_KHOANG_BAO_CAO_THANG, 120)
        self.assertTrue(form.is_valid(), form.errors)

    def test_form_tu_choi_khoang_bao_cao_vuot_qua_120_thang(self):
        ngay_ket_thuc = date(
            timezone.localdate().year,
            timezone.localdate().month,
            1,
        )
        chi_so_thang_cuoi = (
            ngay_ket_thuc.year * 12
            + ngay_ket_thuc.month
            - 1
        )
        chi_so_thang_dau = (
            chi_so_thang_cuoi
            - MAX_KHOANG_BAO_CAO_THANG
        )
        ngay_bat_dau = date(
            chi_so_thang_dau // 12,
            chi_so_thang_dau % 12 + 1,
            1,
        )

        form = BoLocBaoCaoForm(
            data={
                "tu_ngay": ngay_bat_dau.isoformat(),
                "den_ngay": ngay_ket_thuc.isoformat(),
            },
            danh_sach_kho=Kho.objects.all(),
        )

        self.assertFalse(form.is_valid())
        self.assertIn("den_ngay", form.errors)
