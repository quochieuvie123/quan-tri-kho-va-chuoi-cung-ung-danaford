from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from database.models import ChiNhanh, Kho, TonKho, Xe
from .forms import CapNhatTrangThaiForm
from .models import CanhBao, NguongCanhBao
from .utils import (
    cap_nhat_canh_bao_thieu_hang,
    cap_nhat_canh_bao_ton_lau,
    cap_nhat_tat_ca_canh_bao,
)


class CapNhatCanhBaoTest(TestCase):
    def setUp(self):
        chi_nhanh = ChiNhanh.objects.create(
            ma_cn="CN-TEST-1",
            ten_cn="Chi nhánh kiểm thử 1",
        )
        self.kho = Kho.objects.create(
            ma_kho="KHO-TEST-1",
            chi_nhanh=chi_nhanh,
        )
        self.nguong = NguongCanhBao.objects.create(
            kho=self.kho,
            ten_xe="Ford Ranger",
            mau_sac="Đỏ",
            ton_toi_thieu=3,
        )

    def tao_kho(self, ma_kho, ma_chi_nhanh):
        chi_nhanh = ChiNhanh.objects.create(
            ma_cn=ma_chi_nhanh,
            ten_cn=f"Chi nhánh {ma_chi_nhanh}",
        )
        return Kho.objects.create(
            ma_kho=ma_kho,
            chi_nhanh=chi_nhanh,
        )

    def tao_xe(self, vin, ten_xe="Ford Ranger", mau_sac="Đỏ"):
        return Xe.objects.create(
            vin=vin,
            ten_xe=ten_xe,
            loai_xe="SUV",
            so_may=f"MAY-{vin}",
            mau_sac=mau_sac,
        )

    def tao_ton_kho(self, kho, xe, so_luong, ngay_vao_kho=None):
        return TonKho.objects.create(
            kho=kho,
            xe=xe,
            so_luong_ton=so_luong,
            ngay_vao_kho=ngay_vao_kho or timezone.localdate(),
        )

    def test_khong_co_ton_kho_tao_canh_bao_het_hang(self):
        cap_nhat_canh_bao_thieu_hang()

        canh_bao = CanhBao.objects.get(nguong=self.nguong)

        self.assertEqual(canh_bao.loai, CanhBao.Loai.HET_HANG)
        self.assertEqual(canh_bao.so_luong_hien_tai, 0)
        self.assertTrue(canh_bao.con_hieu_luc)

    def test_ton_duoi_nguong_tao_canh_bao_duoi_nguong(self):
        xe = self.tao_xe("VIN-UNDER")
        self.tao_ton_kho(self.kho, xe, so_luong=2)

        cap_nhat_canh_bao_thieu_hang()

        canh_bao = CanhBao.objects.get(nguong=self.nguong)

        self.assertEqual(canh_bao.loai, CanhBao.Loai.DUOI_NGUONG)
        self.assertEqual(canh_bao.so_luong_hien_tai, 2)
        self.assertTrue(canh_bao.con_hieu_luc)

    def test_ton_dat_nguong_lam_canh_bao_thieu_hang_het_hieu_luc(self):
        xe = self.tao_xe("VIN-REACH")
        ton_kho = self.tao_ton_kho(self.kho, xe, so_luong=2)

        cap_nhat_canh_bao_thieu_hang()
        canh_bao = CanhBao.objects.get(nguong=self.nguong)

        ton_kho.so_luong_ton = 3
        ton_kho.save(update_fields=["so_luong_ton"])
        cap_nhat_canh_bao_thieu_hang()

        canh_bao.refresh_from_db()

        self.assertFalse(canh_bao.con_hieu_luc)

    def test_ton_kho_duoc_tinh_theo_dung_kho_va_mau_xe(self):
        kho_khac = self.tao_kho("KHO-TEST-2", "CN-TEST-2")

        xe_cung_nhom = self.tao_xe("VIN-SAME-GROUP")
        xe_kho_khac = self.tao_xe("VIN-OTHER-WAREHOUSE")
        xe_khac_mau = self.tao_xe(
            "VIN-OTHER-COLOR",
            mau_sac="Đen",
        )

        self.tao_ton_kho(self.kho, xe_cung_nhom, so_luong=2)
        self.tao_ton_kho(kho_khac, xe_kho_khac, so_luong=2)
        self.tao_ton_kho(self.kho, xe_khac_mau, so_luong=2)

        cap_nhat_canh_bao_thieu_hang()

        canh_bao = CanhBao.objects.get(nguong=self.nguong)

        self.assertEqual(canh_bao.loai, CanhBao.Loai.DUOI_NGUONG)
        self.assertEqual(canh_bao.so_luong_hien_tai, 2)

    def test_cap_nhat_lap_lai_khong_tao_canh_bao_thieu_hang_trung(self):
        cap_nhat_canh_bao_thieu_hang()
        cap_nhat_canh_bao_thieu_hang()

        self.assertEqual(
            CanhBao.objects.filter(nguong=self.nguong).count(),
            1,
        )

    def test_ngung_theo_doi_lam_canh_bao_thieu_hang_het_hieu_luc(self):
        xe = self.tao_xe("VIN-STOP-TRACKING")
        self.tao_ton_kho(self.kho, xe, so_luong=2)

        cap_nhat_canh_bao_thieu_hang()
        canh_bao = CanhBao.objects.get(nguong=self.nguong)

        self.nguong.dang_theo_doi = False
        self.nguong.save(update_fields=["dang_theo_doi"])
        cap_nhat_canh_bao_thieu_hang()

        canh_bao.refresh_from_db()

        self.assertFalse(canh_bao.con_hieu_luc)

    def test_xe_ton_tren_60_ngay_co_canh_bao_ton_lau(self):
        hom_nay = timezone.localdate()
        xe_60_ngay = self.tao_xe("VIN-60-DAYS")
        xe_61_ngay = self.tao_xe("VIN-61-DAYS")

        self.tao_ton_kho(
            self.kho,
            xe_60_ngay,
            so_luong=1,
            ngay_vao_kho=hom_nay - timedelta(days=60),
        )
        self.tao_ton_kho(
            self.kho,
            xe_61_ngay,
            so_luong=1,
            ngay_vao_kho=hom_nay - timedelta(days=61),
        )

        cap_nhat_canh_bao_ton_lau()

        self.assertFalse(
            CanhBao.objects.filter(
                kho=self.kho,
                xe=xe_60_ngay,
                loai=CanhBao.Loai.TON_LAU,
                con_hieu_luc=True,
            ).exists()
        )
        self.assertTrue(
            CanhBao.objects.filter(
                kho=self.kho,
                xe=xe_61_ngay,
                loai=CanhBao.Loai.TON_LAU,
                con_hieu_luc=True,
            ).exists()
        )

    def test_xe_het_ton_lam_canh_bao_ton_lau_het_hieu_luc(self):
        xe = self.tao_xe("VIN-OUT-OF-STOCK")
        ton_kho = self.tao_ton_kho(
            self.kho,
            xe,
            so_luong=1,
            ngay_vao_kho=timezone.localdate() - timedelta(days=61),
        )

        cap_nhat_canh_bao_ton_lau()
        canh_bao = CanhBao.objects.get(
            kho=self.kho,
            xe=xe,
            loai=CanhBao.Loai.TON_LAU,
        )

        ton_kho.so_luong_ton = 0
        ton_kho.save(update_fields=["so_luong_ton"])
        cap_nhat_canh_bao_ton_lau()

        canh_bao.refresh_from_db()

        self.assertFalse(canh_bao.con_hieu_luc)

    def test_ngay_tuong_lai_khong_chan_cap_nhat_cac_canh_bao_khac(self):
        hom_nay = timezone.localdate()
        xe_duoi_nguong = self.tao_xe("VIN-LOW-STOCK")
        xe_ton_lau = self.tao_xe(
            "VIN-LONG-STOCK",
            ten_xe="Ford Everest",
        )
        xe_ngay_tuong_lai = self.tao_xe(
            "VIN-FUTURE-DATE",
            ten_xe="Ford Everest",
        )

        self.tao_ton_kho(
            self.kho,
            xe_duoi_nguong,
            so_luong=2,
        )
        self.tao_ton_kho(
            self.kho,
            xe_ton_lau,
            so_luong=1,
            ngay_vao_kho=hom_nay - timedelta(days=61),
        )
        self.tao_ton_kho(
            self.kho,
            xe_ngay_tuong_lai,
            so_luong=1,
            ngay_vao_kho=hom_nay + timedelta(days=1),
        )

        canh_bao_cu = CanhBao.objects.create(
            kho=self.kho,
            loai=CanhBao.Loai.TON_LAU,
            xe=xe_ngay_tuong_lai,
            so_ngay_ton=70,
        )

        cap_nhat_tat_ca_canh_bao()

        self.assertTrue(
            CanhBao.objects.filter(
                nguong=self.nguong,
                loai=CanhBao.Loai.DUOI_NGUONG,
                con_hieu_luc=True,
                so_luong_hien_tai=2,
            ).exists()
        )
        self.assertTrue(
            CanhBao.objects.filter(
                kho=self.kho,
                xe=xe_ton_lau,
                loai=CanhBao.Loai.TON_LAU,
                con_hieu_luc=True,
            ).exists()
        )
        self.assertFalse(
            CanhBao.objects.filter(
                kho=self.kho,
                xe=xe_ngay_tuong_lai,
                loai=CanhBao.Loai.TON_LAU,
                con_hieu_luc=True,
            ).exclude(pk=canh_bao_cu.pk).exists()
        )

        canh_bao_cu.refresh_from_db()

        self.assertTrue(canh_bao_cu.con_hieu_luc)
        self.assertEqual(canh_bao_cu.so_ngay_ton, 70)

    def test_form_chi_cho_phep_chuyen_trang_thai_hop_le(self):
        cac_truong_hop = [
            (
                CanhBao.TrangThai.CHUA_XU_LY,
                CanhBao.TrangThai.DANG_XU_LY,
                True,
            ),
            (
                CanhBao.TrangThai.CHUA_XU_LY,
                CanhBao.TrangThai.DA_XU_LY,
                True,
            ),
            (
                CanhBao.TrangThai.DANG_XU_LY,
                CanhBao.TrangThai.DA_XU_LY,
                True,
            ),
            (
                CanhBao.TrangThai.DANG_XU_LY,
                CanhBao.TrangThai.CHUA_XU_LY,
                False,
            ),
            (
                CanhBao.TrangThai.DA_XU_LY,
                CanhBao.TrangThai.DANG_XU_LY,
                False,
            ),
        ]

        for trang_thai_hien_tai, trang_thai_moi, hop_le in cac_truong_hop:
            with self.subTest(
                trang_thai_hien_tai=trang_thai_hien_tai,
                trang_thai_moi=trang_thai_moi,
            ):
                canh_bao = CanhBao(
                    trang_thai=trang_thai_hien_tai,
                )
                form = CapNhatTrangThaiForm(
                    data={"trang_thai": trang_thai_moi},
                    canh_bao=canh_bao,
                )

                self.assertEqual(form.is_valid(), hop_le)
