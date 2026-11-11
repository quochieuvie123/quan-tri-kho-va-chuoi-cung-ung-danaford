from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from database.models import ChiNhanh, Kho, TonKho, Xe
from .models import CanhBao, NguongCanhBao
from .utils import (
    cap_nhat_canh_bao_thieu_hang,
    cap_nhat_canh_bao_ton_lau,
)


class CanhBaoTheoNhomTest(TestCase):
    def setUp(self):
        self.cac_kho = []

        for i in range(1, 4):
            chi_nhanh = ChiNhanh.objects.create(
                ma_cn=f"CN{i}",
                ten_cn=f"Chi nhánh {i}",
            )

            kho = Kho.objects.create(
                ma_kho=f"KHO0{i}",
                chi_nhanh=chi_nhanh,
            )

            self.cac_kho.append(kho)

    def tao_ton(
        self,
        vin,
        kho,
        so_luong=1,
        ten="Ford Ranger XLS",
        mau="Trắng",
    ):
        xe = Xe.objects.create(
            vin=vin,
            ten_xe=ten,
            mau_sac=mau,
            so_may=f"MAY{vin}",
            loai_xe="SUV",
        )

        return TonKho.objects.create(
            xe=xe,
            kho=kho,
            so_luong_ton=so_luong,
            ngay_vao_kho=timezone.localdate(),
        )

    def lay_canh_bao(self, dong="Ranger", mau="Trắng"):
        return CanhBao.objects.get(
            nguong__ten_xe=dong,
            nguong__mau_sac=mau,
            con_hieu_luc=True,
        )

    def test_nhom_thuong_mot_xe_duoi_nguong(self):
        self.tao_ton("V1", self.cac_kho[0])
        cap_nhat_canh_bao_thieu_hang()

        cb = self.lay_canh_bao()

        self.assertEqual(cb.loai, CanhBao.Loai.DUOI_NGUONG)
        self.assertEqual(cb.so_luong_hien_tai, 1)
        self.assertEqual(cb.nguong.ton_toi_thieu, 2)

    def test_cung_dong_khac_phien_ban_duoc_cong_chung(self):
        self.tao_ton("V1", self.cac_kho[0])

        self.tao_ton(
            "V2",
            self.cac_kho[1],
            ten="Ford Ranger Wildtrak",
        )

        cap_nhat_canh_bao_thieu_hang()

        self.assertFalse(
            CanhBao.objects.filter(con_hieu_luc=True).exists()
        )

    def test_everest_hai_xe_hai_kho_chi_mot_canh_bao(self):
        self.tao_ton(
            "V1",
            self.cac_kho[0],
            ten="Ford Everest Titanium",
            mau="Trắng Tuyết",
        )

        self.tao_ton(
            "V2",
            self.cac_kho[1],
            ten="Ford Everest Titanium+",
            mau="Trắng Tuyết",
        )

        cap_nhat_canh_bao_thieu_hang()

        cb = self.lay_canh_bao("Everest", "Trắng Tuyết")

        self.assertEqual(cb.so_luong_hien_tai, 2)
        self.assertEqual(cb.nguong.ton_toi_thieu, 3)
        self.assertEqual(cb.kho_hien_thi, "KHO01 và KHO02")

        self.assertEqual(
            CanhBao.objects.filter(con_hieu_luc=True).count(),
            1,
        )

    def test_everest_ba_xe_khong_canh_bao(self):
        self.tao_ton(
            "V1",
            self.cac_kho[0],
            3,
            "Ford Everest Sport",
            "Trắng Tuyết",
        )

        cap_nhat_canh_bao_thieu_hang()

        self.assertFalse(
            CanhBao.objects.filter(con_hieu_luc=True).exists()
        )

    def test_ton_ve_khong_van_co_canh_bao_va_loc_duoc_ba_kho(self):
        ton = self.tao_ton("V1", self.cac_kho[0])

        cap_nhat_canh_bao_thieu_hang()
        ton.delete()
        cap_nhat_canh_bao_thieu_hang()

        cb = self.lay_canh_bao()

        self.assertEqual(cb.loai, CanhBao.Loai.HET_HANG)
        self.assertEqual(cb.so_luong_hien_tai, 0)
        self.assertEqual(cb.cac_kho.count(), 3)
        self.assertEqual(cb.kho_hien_thi, "Tổng ba kho")

    def test_cap_nhat_lap_lai_khong_trung(self):
        self.tao_ton("V1", self.cac_kho[0])

        cap_nhat_canh_bao_thieu_hang()
        cap_nhat_canh_bao_thieu_hang()

        self.assertEqual(
            CanhBao.objects.filter(con_hieu_luc=True).count(),
            1,
        )

    def test_khong_cong_chung_khac_mau(self):
        self.tao_ton("V1", self.cac_kho[0])

        self.tao_ton(
            "V2",
            self.cac_kho[0],
            mau="Đen",
        )

        cap_nhat_canh_bao_thieu_hang()

        self.assertEqual(
            CanhBao.objects.filter(con_hieu_luc=True).count(),
            2,
        )

    def test_du_nguong_het_hieu_luc_khong_tu_doi_trang_thai_xu_ly(self):
        ton = self.tao_ton("V1", self.cac_kho[0])
        cap_nhat_canh_bao_thieu_hang()

        cb = self.lay_canh_bao()
        cb.trang_thai = CanhBao.TrangThai.DANG_XU_LY
        cb.save()

        ton.so_luong_ton = 2
        ton.save()
        cap_nhat_canh_bao_thieu_hang()

        cb.refresh_from_db()

        self.assertFalse(cb.con_hieu_luc)
        self.assertEqual(
            cb.trang_thai,
            CanhBao.TrangThai.DANG_XU_LY,
        )

    def test_tai_phat_tao_dot_canh_bao_moi(self):
        ton = self.tao_ton("V1", self.cac_kho[0])
        cap_nhat_canh_bao_thieu_hang()

        cu = self.lay_canh_bao()

        ton.so_luong_ton = 2
        ton.save()
        cap_nhat_canh_bao_thieu_hang()

        ton.so_luong_ton = 1
        ton.save()
        cap_nhat_canh_bao_thieu_hang()

        self.assertNotEqual(
            cu.pk,
            self.lay_canh_bao().pk,
        )

    def test_loc_kho_giu_nguyen_tong_toan_he_thong(self):
        self.tao_ton(
            "V1",
            self.cac_kho[0],
            ten="Ford Everest Sport",
            mau="Trắng Tuyết",
        )

        self.tao_ton(
            "V2",
            self.cac_kho[1],
            ten="Ford Everest Titanium",
            mau="Trắng Tuyết",
        )

        cap_nhat_canh_bao_thieu_hang()

        user = get_user_model().objects.create_superuser(
            username="admin-test",
            password="test-password",
        )

        self.client.force_login(user)

        for kho in self.cac_kho[:2]:
            response = self.client.get(
                "/canh-bao/",
                {"kho": kho.pk},
            )

            self.assertEqual(response.status_code, 200)

            cb = response.context["danh_sach"].get()

            self.assertEqual(cb.so_luong_hien_tai, 2)

        response = self.client.get(
            "/canh-bao/",
            {"kho": self.cac_kho[2].pk},
        )

        self.assertEqual(
            response.context["danh_sach"].count(),
            0,
        )

    def test_ngung_theo_doi(self):
        self.tao_ton("V1", self.cac_kho[0])
        cap_nhat_canh_bao_thieu_hang()

        NguongCanhBao.objects.update(dang_theo_doi=False)
        cap_nhat_canh_bao_thieu_hang()

        self.assertFalse(
            CanhBao.objects.filter(con_hieu_luc=True).exists()
        )

    def test_ton_lau_van_theo_vin_va_kho(self):
        ton = self.tao_ton("V1", self.cac_kho[0])

        ton.ngay_vao_kho = (
            timezone.localdate() - timedelta(days=61)
        )

        ton.save()
        cap_nhat_canh_bao_ton_lau()

        cb = CanhBao.objects.get(
            loai=CanhBao.Loai.TON_LAU,
        )

        self.assertEqual(cb.xe_id, ton.xe_id)
        self.assertEqual(cb.kho_id, ton.kho_id)
