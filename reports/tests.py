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


class BaoCaoBoSungTest(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model

        self.user = get_user_model().objects.create_user(username="report-extra")
        self.user_khac = get_user_model().objects.create_user(username="report-other")
        self.khos = []

        for i in range(1, 3):
            cn = ChiNhanh.objects.create(
                ma_cn=f"CN-EXTRA-{i}", ten_cn=f"Chi nhánh thử {i}",
            )
            self.khos.append(Kho.objects.create(
                ma_kho=f"KHO-EXTRA-{i}", chi_nhanh=cn,
            ))

    def test_dat_xe_dem_phieu_va_so_luong_rieng(self):
        from orders.models import Allocation, VehicleRequest, VehicleRequestItem
        from .utils import tao_bao_cao_dat_xe

        phieu = VehicleRequest.objects.create(created_by=self.user)
        VehicleRequest.objects.create(created_by=self.user_khac)

        for i, so_luong in enumerate([2, 3], start=1):
            xe = Allocation.objects.create(
                order_number=f"ORDER-{i}", vehicle_code="RANGER",
                description="Ford Ranger", vin=f"ALLOC-EXTRA-{i}",
                color_code="W", exterior_color="Trắng",
                engine_number=f"ENGINE-{i}",
            )
            VehicleRequestItem.objects.create(
                vehicle_request=phieu, allocation=xe, quantity=so_luong,
            )

        bao_cao = tao_bao_cao_dat_xe(
            self.user, {"ten_xe": "Ranger"}, True,
        )
        self.assertEqual(bao_cao["tong"], 1)
        self.assertEqual(sum(row[7] for row in bao_cao["dong"]), 5)
        self.assertEqual(len(bao_cao["dong"]), 2)

    def test_luu_chuyen_hai_kho_khong_dem_trung(self):
        from transfers.models import LenhLuuChuyen, ChiTietLenhLuuChuyen
        from .utils import tao_bao_cao_luu_chuyen

        lenh = LenhLuuChuyen.objects.create(
            ma_lenh="LLC-EXTRA", kho_xuat=self.khos[0],
            kho_nhap=self.khos[1], nguoi_lap=self.user,
        )

        for i in range(1, 3):
            xe = Xe.objects.create(
                vin=f"VIN-EXTRA-{i}", ten_xe="Ford Ranger",
                so_may=f"MAY-EXTRA-{i}", loai_xe="SUV", mau_sac="Trắng",
            )
            ChiTietLenhLuuChuyen.objects.create(
                lenh=lenh, xe=xe, so_luong=1,
            )

        for bo_loc in [{}, {"kho": self.khos[0]}, {"kho": self.khos[1]}]:
            bao_cao = tao_bao_cao_luu_chuyen(Kho.objects.all(), bo_loc, True)
            self.assertEqual(bao_cao["tong"], 1)
            self.assertEqual(sum(row[6] for row in bao_cao["dong"]), 2)

    def test_canh_bao_nhieu_kho_chi_dem_mot_lan(self):
        from alerts.models import CanhBao, NguongCanhBao
        from .utils import tao_bao_cao_canh_bao

        nguong = NguongCanhBao.objects.create(
            ten_xe="Everest", mau_sac="Trắng Tuyết", ton_toi_thieu=3,
        )
        cb = CanhBao.objects.create(
            nguong=nguong, loai=CanhBao.Loai.DUOI_NGUONG,
            so_luong_hien_tai=2, con_hieu_luc=True,
            trang_thai=CanhBao.TrangThai.DA_XU_LY,
        )
        cb.cac_kho.set(self.khos)

        bao_cao = tao_bao_cao_canh_bao(Kho.objects.all(), {})
        self.assertEqual(bao_cao["tong"], 1)
        self.assertEqual(sum(bao_cao["theo_loai"].values()), 1)
        self.assertEqual(bao_cao["dong"][0][5], "Còn hiệu lực")
        self.assertEqual(bao_cao["dong"][0][6], "Đã xử lý")

    def test_thieu_quyen_khong_them_bao_cao_moi(self):
        bao_cao = tao_bao_cao(Kho.objects.all(), {}, user=self.user)
        for loai in ["dat_xe", "luu_chuyen", "canh_bao"]:
            self.assertNotIn(loai, bao_cao)
