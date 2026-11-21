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
        self.assertEqual(bao_cao["theo_loai_va_xu_ly"]["Tồn dưới ngưỡng"]["Đã xử lý"], 1)
        self.assertEqual(bao_cao["dong"][0][5], "Còn hiệu lực")
        self.assertEqual(bao_cao["dong"][0][6], "Đã xử lý")

        # Kiểm tra gộp 2 biểu đồ cảnh báo thành 1 biểu đồ cột chồng theo loại và trạng thái xử lý.
        from .views import tao_cac_bieu_do
        bieu_do_ds = tao_cac_bieu_do({"ton_kho": {"theo_ten": [], "theo_kho": []}, "tuoi_ton": {"nhom": []}, "nhap_kho": {"theo_thang": []}, "hop_dong": {"theo_thang": []}, "pdi": {"nhom": []}, "canh_bao": bao_cao})
        tieu_de_ds = [bd["tieu_de"] for bd in bieu_do_ds]
        self.assertIn("Cảnh báo theo loại và trạng thái xử lý", tieu_de_ds)
        self.assertNotIn("Cảnh báo theo loại", tieu_de_ds)
        self.assertNotIn("Cảnh báo theo trạng thái xử lý", tieu_de_ds)
        bd_cb = next(bd for bd in bieu_do_ds if bd["tieu_de"] == "Cảnh báo theo loại và trạng thái xử lý")
        self.assertIn('"barmode":"stack"', bd_cb["html"])

        # Thay đổi trạng thái ở module alerts -> số liệu gộp tự động cập nhật.
        cb.trang_thai = CanhBao.TrangThai.DANG_XU_LY
        cb.save(update_fields=["trang_thai"])
        bao_cao_moi = tao_bao_cao_canh_bao(Kho.objects.all(), {"ten_xe": "Everest"})
        self.assertEqual(bao_cao_moi["theo_loai_va_xu_ly"]["Tồn dưới ngưỡng"]["Đang xử lý"], 1)
        self.assertEqual(bao_cao_moi["theo_loai_va_xu_ly"]["Tồn dưới ngưỡng"]["Đã xử lý"], 0)

    def test_thieu_quyen_khong_them_bao_cao_moi(self):
        bao_cao = tao_bao_cao(Kho.objects.all(), {}, user=self.user)
        for loai in ["dat_xe", "luu_chuyen", "canh_bao", "du_bao", "su_co"]:
            self.assertNotIn(loai, bao_cao)

    def test_bo_loc_nhieu_thang_cung_luc_va_bieu_do_bi(self):
        """Bộ lọc hỗ trợ chọn nhiều tháng (liên tiếp hoặc cách quãng) và render UI/Excel/BI chính xác."""
        from django.contrib.auth import get_user_model
        from django.test import Client
        from django.urls import reverse
        from database.models import HopDong, KhachHang
        from transfers.models import LenhLuuChuyen, ChiTietLenhLuuChuyen

        kh = KhachHang.objects.create(ma_kh="KH-REP-M", ten_kh="Khách Multi", sdt_kh="0909888777")
        HopDong.objects.create(
            ma_hd="HD-REP-08", khach_hang=kh, chi_nhanh=self.khos[0].chi_nhanh,
            dong_xe_yeu_cau="Ford Ranger", ngay_ky=timezone.make_aware(timezone.datetime(2026, 8, 10, 9, 0)),
        )
        HopDong.objects.create(
            ma_hd="HD-REP-09", khach_hang=kh, chi_nhanh=self.khos[0].chi_nhanh,
            dong_xe_yeu_cau="Ford Ranger", ngay_ky=timezone.make_aware(timezone.datetime(2026, 9, 10, 9, 0)),
        )
        HopDong.objects.create(
            ma_hd="HD-REP-11", khach_hang=kh, chi_nhanh=self.khos[0].chi_nhanh,
            dong_xe_yeu_cau="Ford Everest", ngay_ky=timezone.make_aware(timezone.datetime(2026, 11, 10, 9, 0)),
        )

        # Tạo lệnh lưu chuyển ở trạng thái HOAN_TAT cũng phải được tính trong xe_da_xac_nhan
        lenh_ht = LenhLuuChuyen.objects.create(
            ma_lenh="LLC-HT-01", kho_xuat=self.khos[0], kho_nhap=self.khos[1],
            nguoi_lap=self.user, trang_thai=LenhLuuChuyen.TrangThai.HOAN_TAT,
        )
        xe_ht = Xe.objects.create(vin="VIN-REP-HT01", ten_xe="Ford Ranger", so_may="MAY-HT01", loai_xe="Pickup", mau_sac="Đen")
        ChiTietLenhLuuChuyen.objects.create(lenh=lenh_ht, xe=xe_ht, so_luong=1)

        form = BoLocBaoCaoForm(
            data={"thang": ["2026-11", "2026-08"]},
            danh_sach_kho=Kho.objects.all(),
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["cac_thang"], [date(2026, 8, 1), date(2026, 11, 1)])

        bao_cao = tao_bao_cao(Kho.objects.all(), form.cleaned_data, kem_thong_ke=True)
        # Chỉ có 2 hợp đồng tháng 08 và tháng 11 (loại tháng 09)
        self.assertEqual(bao_cao["hop_dong"]["tong"], 2)
        self.assertEqual(bao_cao["hop_dong"]["theo_thang"], [["08/2026", 1], ["11/2026", 1]])

        # Lọc theo tên xe Ranger bao gồm cả HĐ mới ghi dong_xe_yeu_cau chưa gán VIN
        bao_cao_ranger = tao_bao_cao(Kho.objects.all(), {"ten_xe": "Ranger", "cac_thang": [date(2026, 8, 1), date(2026, 11, 1)]}, kem_thong_ke=True)
        self.assertEqual(bao_cao_ranger["hop_dong"]["tong"], 1)

        # Kiểm tra luu_chuyen đếm đúng HOAN_TAT
        from .utils import tao_bao_cao_luu_chuyen
        lc_rep = tao_bao_cao_luu_chuyen(Kho.objects.all(), {}, True)
        self.assertIn("đã xác nhận: 1", lc_rep["ghi_chu"])

        # Kiểm tra UI /thong-ke-bao-cao/ unbound và multi-month GET
        admin = get_user_model().objects.create_superuser(username="rep-admin", email="r@df.vn", password="password123")
        client = Client()
        client.force_login(admin)
        resp_unbound = client.get(reverse("dashboard:index"))
        self.assertEqual(resp_unbound.status_code, 200)
        resp_multi = client.get(reverse("dashboard:index") + "?thang=2026-11&thang=2026-10")
        self.assertEqual(resp_multi.status_code, 200)
        html = resp_multi.content.decode("utf-8")
        self.assertIn("thang=2026-11&amp;thang=2026-10", html)
        # Bỏ 2 ghi chú trên giao diện
        self.assertNotIn("Tổng hợp lúc:", html)
        self.assertNotIn("Tồn kho và tuổi tồn phản ánh thời điểm hiện tại.", html)
        # Mọi khối thống kê tổng đều có ghi_chu nhỏ ở dưới
        self.assertTrue(all(item.get("ghi_chu") for item in resp_multi.context["cac_chi_so"]))

    def test_bao_cao_va_bieu_do_du_bao_nhu_cau_loc_va_cap_nhat(self):
        """Thống kê dự báo nhu cầu lấy phiên mới nhất mỗi kỳ, hỗ trợ lọc và cập nhật theo module analytics."""
        from django.contrib.auth import get_user_model
        from django.test import Client
        from django.urls import reverse
        from analytics.models import DongDuBao, PhienDuBao
        from .utils import tao_bao_cao_du_bao
        from .views import tao_cac_bieu_do

        # Phiên cũ và phiên mới cho cùng kỳ 12/2026: chỉ tính phiên mới nhất.
        phien_cu = PhienDuBao.objects.create(
            nam=2026, thang=12, tao_luc=timezone.now() - timedelta(days=2),
        )
        DongDuBao.objects.create(
            phien=phien_cu, ten_xe="Ford Ranger Wildtrak 2.0L", loai_xe="Pickup",
            ma_dong_xe="RANGER-WILDTRAK", ten_ngan="Ford Ranger", phien_ban="Wildtrak 2.0L",
            du_bao_sarima=9.9, ky_truoc=5, ton_kho=1, de_xuat_poq=8,
        )

        phien_moi = PhienDuBao.objects.create(
            nam=2026, thang=12, tao_luc=timezone.now() - timedelta(days=1),
        )
        dong_ranger = DongDuBao.objects.create(
            phien=phien_moi, ten_xe="Ford Ranger Raptor 2.0L", loai_xe="Pickup",
            ma_dong_xe="RANGER-RAPTOR", ten_ngan="Ford Ranger", phien_ban="Raptor 2.0L",
            du_bao_sarima=2.4, ky_truoc=3, ton_kho=1, de_xuat_poq=2,
        )
        DongDuBao.objects.create(
            phien=phien_moi, ten_xe="Ford Everest Titanium 2.0L", loai_xe="SUV",
            ma_dong_xe="EVEREST-TITANIUM", ten_ngan="Ford Everest", phien_ban="Titanium 2.0L",
            du_bao_sarima=1.6, ky_truoc=2, ton_kho=0, de_xuat_poq=2,
        )

        # Thêm một kỳ khác (11/2026) để kiểm tra bộ lọc tháng.
        phien_11 = PhienDuBao.objects.create(
            nam=2026, thang=11, tao_luc=timezone.now() - timedelta(days=5),
        )
        DongDuBao.objects.create(
            phien=phien_11, ten_xe="Ford Ranger Raptor 2.0L", loai_xe="Pickup",
            ma_dong_xe="RANGER-RAPTOR", ten_ngan="Ford Ranger", phien_ban="Raptor 2.0L",
            du_bao_sarima=3.0, ky_truoc=4, ton_kho=1, de_xuat_poq=2,
        )

        # Kiểm tra tháng dự báo 12/2026 xuất hiện trong form lọc.
        form = BoLocBaoCaoForm(
            data={"thang": ["2026-12"], "ten_xe": "Ranger"},
            danh_sach_kho=Kho.objects.all(),
        )
        self.assertIn("2026-12", dict(form.fields["thang"].choices))
        self.assertTrue(form.is_valid(), form.errors)

        admin = get_user_model().objects.create_superuser(
            username="rep-du-bao-admin", email="db@df.vn", password="password123",
        )
        bao_cao_loc = tao_bao_cao(Kho.objects.all(), form.cleaned_data, kem_thong_ke=True, user=admin)
        du_bao_rep = bao_cao_loc["du_bao"]
        self.assertEqual(du_bao_rep["tong"], 2.4)
        self.assertEqual(len(du_bao_rep["dong"]), 1)
        self.assertEqual(du_bao_rep["so_sanh"]["ky"], "12/2026")
        self.assertEqual(len(du_bao_rep["so_sanh"]["hang"]), 1)

        # Thay đổi dữ liệu ở module analytics -> báo cáo tự động cập nhật.
        dong_ranger.so_luong_dieu_chinh = 5
        dong_ranger.save(update_fields=["so_luong_dieu_chinh"])
        du_bao_cap_nhat = tao_bao_cao_du_bao(form.cleaned_data, kem_thong_ke=True)
        self.assertEqual(du_bao_cap_nhat["dong"][0][8], 5)
        self.assertIn("Đề xuất nhập: 5 xe", du_bao_cap_nhat["ghi_chu"])

        # Sinh biểu đồ và kiểm tra giao diện tổng quan / chi tiết / xuất Excel.
        import json
        bieu_do_ds = tao_cac_bieu_do(bao_cao_loc)
        tieu_de_ds = [bd["tieu_de"] for bd in bieu_do_ds]
        self.assertIn("So sánh nhu cầu dự báo với tháng trước", tieu_de_ds)
        bd_du_bao = next(bd for bd in bieu_do_ds if bd["tieu_de"] == "So sánh nhu cầu dự báo với tháng trước")
        self.assertIn(json.dumps("Bán tháng trước"), bd_du_bao["html"])
        self.assertIn(json.dumps("Dự báo kỳ 12/2026").replace("/", "\\u002f"), bd_du_bao["html"])
        self.assertIn('"barmode":"group"', bd_du_bao["html"])

        client = Client()
        client.force_login(admin)
        resp_tq = client.get(reverse("dashboard:index") + "?thang=2026-12&ten_xe=Ranger")
        self.assertEqual(resp_tq.status_code, 200)
        self.assertIn("So sánh nhu cầu dự báo với tháng trước", resp_tq.content.decode("utf-8"))

        resp_ct = client.get(reverse("dashboard:reports:chi_tiet", args=["du_bao"]) + "?thang=2026-12")
        self.assertEqual(resp_ct.status_code, 200)
        self.assertIn("Ford Ranger Raptor 2.0L", resp_ct.content.decode("utf-8"))

        resp_xls = client.get(reverse("dashboard:reports:xuat_excel") + "?loai=du_bao&thang=2026-12")
        self.assertEqual(resp_xls.status_code, 200)

        # User không có quyền bị chặn khi vào chi tiết du_bao.
        client.force_login(self.user)
        resp_forbidden = client.get(reverse("dashboard:reports:chi_tiet", args=["du_bao"]))
        self.assertEqual(resp_forbidden.status_code, 403)

    def test_bao_cao_va_bieu_do_su_co_van_chuyen_loc_va_cap_nhat(self):
        """Thống kê sự cố vận chuyển lọc theo kho/tháng/tên xe và cập nhật khi module incidents thay đổi."""
        from decimal import Decimal
        from django.contrib.auth import get_user_model
        from django.test import Client
        from django.urls import reverse
        from database.models import (
            BienBanPDI, DonViVanChuyen, HoaDonNhap, NhaCungCap, NhanVien,
        )
        from incidents.models import CHUA_XU_LY, DA_XU_LY, HoSoSuCo
        from .utils import tao_bao_cao_su_co
        from .views import tao_cac_bieu_do

        ncc = NhaCungCap.objects.create(ma_ncc="NCC-SC", ten_ncc="Ford VN")
        dvvc = DonViVanChuyen.objects.create(ma_dvvc="DVVC-SC", ten_dvvc="Vận tải Miền Trung")
        nv = NhanVien.objects.create(ma_nv="NV-SC", ten_nv="Nhân viên PDI", chi_nhanh=self.khos[0].chi_nhanh)
        hdn_1 = HoaDonNhap.objects.create(
            ma_hdn="HDN-SC-1", nha_cung_cap=ncc, chi_nhanh=self.khos[0].chi_nhanh,
            don_vi_van_chuyen=dvvc, ngay_nhap=timezone.make_aware(timezone.datetime(2026, 11, 5, 9, 0)),
        )
        hdn_2 = HoaDonNhap.objects.create(
            ma_hdn="HDN-SC-2", nha_cung_cap=ncc, chi_nhanh=self.khos[1].chi_nhanh,
            don_vi_van_chuyen=dvvc, ngay_nhap=timezone.make_aware(timezone.datetime(2026, 10, 5, 9, 0)),
        )

        xe_1 = self.tao_xe_test("VIN-SC-01", "Ford Ranger XLS")
        xe_2 = self.tao_xe_test("VIN-SC-02", "Ford Everest Sport")

        bb_1 = BienBanPDI.objects.create(
            ma_pdi="PDI-SC-01", hoa_don_nhap=hdn_1, xe=xe_1, nhan_vien=nv,
            ngay_ghi_nhan=timezone.make_aware(timezone.datetime(2026, 11, 6, 10, 0)),
            loai_su_co="Trầy xước sơn", trang_thai_claim=CHUA_XU_LY,
        )
        BienBanPDI.objects.create(
            ma_pdi="PDI-SC-02", hoa_don_nhap=hdn_2, xe=xe_2, nhan_vien=nv,
            ngay_ghi_nhan=timezone.make_aware(timezone.datetime(2026, 10, 8, 10, 0)),
            loai_su_co="Móp méo thân vỏ", trang_thai_claim=DA_XU_LY,
        )
        HoSoSuCo.objects.create(
            bien_ban=bb_1, hinh_thuc_khac_phuc="TIEN",
            so_tien_boi_thuong=Decimal("5000000"),
        )

        admin = get_user_model().objects.create_superuser(
            username="rep-su-co-admin", email="sc@df.vn", password="password123",
        )
        bo_loc = {
            "kho": self.khos[0],
            "ten_xe": "Ranger",
            "cac_thang": [date(2026, 11, 1)],
        }
        bao_cao_loc = tao_bao_cao(Kho.objects.all(), bo_loc, kem_thong_ke=True, user=admin)
        su_co_rep = bao_cao_loc["su_co"]
        self.assertEqual(su_co_rep["tong"], 1)
        self.assertIn("Đang xử lý: 1", su_co_rep["ghi_chu"])
        self.assertIn("5.000.000 đ", su_co_rep["ghi_chu"])
        self.assertEqual(su_co_rep["theo_loai"], [("Trầy xước sơn", 1, 0)])

        # Cập nhật trạng thái sang Đã xử lý ở module incidents -> báo cáo tự động cập nhật.
        bb_1.trang_thai_claim = DA_XU_LY
        bb_1.save(update_fields=["trang_thai_claim"])
        su_co_cap_nhat = tao_bao_cao_su_co(Kho.objects.all(), bo_loc, kem_thong_ke=True)
        self.assertIn("Đã đóng: 1", su_co_cap_nhat["ghi_chu"])
        self.assertEqual(su_co_cap_nhat["theo_loai"], [("Trầy xước sơn", 0, 1)])

        bieu_do_ds = tao_cac_bieu_do(bao_cao_loc)
        tieu_de_ds = [bd["tieu_de"] for bd in bieu_do_ds]
        self.assertIn("Sự cố vận chuyển theo loại và trạng thái", tieu_de_ds)

        client = Client()
        client.force_login(admin)
        resp_tq = client.get(reverse("dashboard:index") + f"?kho={self.khos[0].pk}&thang=2026-11")
        self.assertEqual(resp_tq.status_code, 200)
        self.assertIn("Sự cố vận chuyển theo loại và trạng thái", resp_tq.content.decode("utf-8"))

        resp_ct = client.get(reverse("dashboard:reports:chi_tiet", args=["su_co"]) + "?thang=2026-11")
        self.assertEqual(resp_ct.status_code, 200)
        self.assertIn("PDI-SC-01", resp_ct.content.decode("utf-8"))

        resp_xls = client.get(reverse("dashboard:reports:xuat_excel") + "?loai=su_co&thang=2026-11")
        self.assertEqual(resp_xls.status_code, 200)

        client.force_login(self.user)
        resp_forbidden = client.get(reverse("dashboard:reports:chi_tiet", args=["su_co"]))
        self.assertEqual(resp_forbidden.status_code, 403)

    def tao_xe_test(self, vin, ten_xe):
        return Xe.objects.create(
            vin=vin, ten_xe=ten_xe, loai_xe="SUV",
            so_may=f"MAY-{vin}", mau_sac="Trắng",
        )
