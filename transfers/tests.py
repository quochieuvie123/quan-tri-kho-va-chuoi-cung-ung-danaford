from datetime import date, timedelta
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase

from database.models import ChiNhanh, DonViVanChuyen, Kho, NhanVien, TonKho, TrangThaiXe, Xe
from transfers.models import LenhLuuChuyen
from transfers import services

User = get_user_model()


class TransfersWorkflowTests(TestCase):
    def setUp(self):
        # 1. Tạo chi nhánh
        self.cn_danang = ChiNhanh.objects.create(ma_cn="CN01", ten_cn="Dana Ford Đà Nẵng", dia_chi_cn="56 Điện Biên Phủ")
        self.cn_binhdinh = ChiNhanh.objects.create(ma_cn="CN02", ten_cn="Dana Ford Bình Định", dia_chi_cn="Tây Sơn, Quy Nhơn")
        self.cn_gialai = ChiNhanh.objects.create(ma_cn="CN03", ten_cn="Dana Ford Gia Lai", dia_chi_cn="Pleiku, Gia Lai")

        # 2. Tạo kho
        self.kho_danang = Kho.objects.create(ma_kho="KHO01", chi_nhanh=self.cn_danang)
        self.kho_binhdinh = Kho.objects.create(ma_kho="KHO02", chi_nhanh=self.cn_binhdinh)
        self.kho_gialai = Kho.objects.create(ma_kho="KHO03", chi_nhanh=self.cn_gialai)

        # 3. Tạo nhân viên & tài khoản người dùng
        # Sale Admin (Đà Nẵng)
        self.nv_danang_admin = NhanVien.objects.create(ma_nv="NV_DN_ADMIN", chi_nhanh=self.cn_danang, ten_nv="Quốc Hiếu Admin", sdt_nv="0901")
        self.user_admin = User.objects.create_superuser(username="admin_hieu", email="hieu@danaford.vn", password="123", nhan_vien=self.nv_danang_admin)

        # Nhân viên Bình Định
        self.nv_binhdinh = NhanVien.objects.create(ma_nv="NV_BD", chi_nhanh=self.cn_binhdinh, ten_nv="Sale Bình Định", sdt_nv="0902")
        self.user_binhdinh = User.objects.create_user(username="sale_binhdinh", email="bd@danaford.vn", password="123", nhan_vien=self.nv_binhdinh)

        # Nhân viên Gia Lai
        self.nv_gialai = NhanVien.objects.create(ma_nv="NV_GL", chi_nhanh=self.cn_gialai, ten_nv="Sale Gia Lai", sdt_nv="0903")
        self.user_gialai = User.objects.create_user(username="sale_gialai", email="gl@danaford.vn", password="123", nhan_vien=self.nv_gialai)

        # Nhân viên kho Đà Nẵng
        self.nv_danang = NhanVien.objects.create(ma_nv="NV_DN", chi_nhanh=self.cn_danang, ten_nv="Kho Đà Nẵng", sdt_nv="0904")
        self.user_danang = User.objects.create_user(username="kho_danang", email="dn@danaford.vn", password="123", nhan_vien=self.nv_danang)

        # 4. Đơn vị vận chuyển
        self.dvvc = DonViVanChuyen.objects.create(ma_dvvc="DVVC_TEST", ten_dvvc="Logistics Miền Trung")

        # 5. Tạo xe & tồn kho mẫu tại Bình Định
        self.xe1 = Xe.objects.create(vin="VIN_TEST_0001", ten_xe="Ford Ranger XLS", loai_xe="Bán tải", so_may="SM01", trang_thai=TrangThaiXe.SAN_SANG)
        self.ton1 = TonKho.objects.create(kho=self.kho_binhdinh, xe=self.xe1, so_luong_ton=1, ngay_vao_kho=date.today())

        self.xe2 = Xe.objects.create(vin="VIN_TEST_0002", ten_xe="Ford Everest Titanium", loai_xe="SUV", so_may="SM02", trang_thai=TrangThaiXe.SAN_SANG)
        self.ton2 = TonKho.objects.create(kho=self.kho_binhdinh, xe=self.xe2, so_luong_ton=1, ngay_vao_kho=date.today())

    def test_vin_da_nam_trong_lenh_khac(self):
        """1. Kiểm tra: Một VIN đang nằm trong một lệnh lưu chuyển mở thì không thể đưa vào lệnh mở khác."""
        # Tạo lệnh 1 ở trạng thái NHAP chứa xe1
        lenh1 = services.tao_lenh_luu_chuyen(
            self.user_binhdinh,
            kho_xuat=self.kho_binhdinh,
            kho_nhap=self.kho_danang,
            ds_xe=[self.xe1]
        )
        self.assertEqual(lenh1.trang_thai, LenhLuuChuyen.TrangThai.NHAP)

        # Cố gắng tạo lệnh 2 chứa xe1 -> Phải ném ValidationError
        with self.assertRaises(ValidationError) as ctx:
            services.tao_lenh_luu_chuyen(
                self.user_binhdinh,
                kho_xuat=self.kho_binhdinh,
                kho_nhap=self.kho_danang,
                ds_xe=[self.xe1]
            )
        self.assertIn("đang nằm trong lệnh lưu chuyển", str(ctx.exception))

        # Cố gắng thêm xe1 vào một lệnh nháp khác bằng them_xe_vao_lenh -> Phải ném ValidationError
        lenh2 = services.tao_lenh_luu_chuyen(
            self.user_binhdinh,
            kho_xuat=self.kho_binhdinh,
            kho_nhap=self.kho_danang,
            ds_xe=[self.xe2]
        )
        with self.assertRaises(ValidationError):
            services.them_xe_vao_lenh(self.user_binhdinh, lenh2.pk, self.xe1)

    def test_sai_chi_nhanh_khong_the_thao_tac(self):
        """2. Kiểm tra: Phân quyền theo chi nhánh - người dùng sai chi nhánh không thể thao tác."""
        # Nhân viên Gia Lai không được phép lập lệnh xuất từ kho Bình Định
        with self.assertRaises(PermissionDenied):
            services.tao_lenh_luu_chuyen(
                self.user_gialai,
                kho_xuat=self.kho_binhdinh,
                kho_nhap=self.kho_danang,
                ds_xe=[self.xe1]
            )

        # Lệnh xuất từ Bình Định được tạo hợp lệ bởi nhân viên Bình Định
        lenh = services.tao_lenh_luu_chuyen(
            self.user_binhdinh,
            kho_xuat=self.kho_binhdinh,
            kho_nhap=self.kho_danang,
            ds_xe=[self.xe1]
        )
        services.gui_lenh_luu_chuyen(self.user_binhdinh, lenh.pk)
        services.duyet_lenh_luu_chuyen(self.user_admin, lenh.pk)

        # Nhân viên Gia Lai không được phép xác nhận xuất kho cho kho Bình Định
        with self.assertRaises(PermissionDenied):
            services.xac_nhan_xuat_kho_nguon(
                self.user_gialai,
                lenh.pk,
                don_vi_van_chuyen_id=self.dvvc.pk,
                bien_so_xe="43C-999.99",
                tai_xe="Tài xế GL",
                ngay_du_kien_den=date.today() + timedelta(days=2)
            )

        # Kho Bình Định xuất xe hợp lệ
        services.xac_nhan_xuat_kho_nguon(
            self.user_binhdinh,
            lenh.pk,
            don_vi_van_chuyen_id=self.dvvc.pk,
            bien_so_xe="43C-999.99",
            tai_xe="Tài xế BD",
            ngay_du_kien_den=date.today() + timedelta(days=2)
        )

        # Nhân viên Bình Định không được phép bấm xác nhận tiếp nhận tại kho Đà Nẵng
        with self.assertRaises(PermissionDenied):
            services.xac_nhan_den_da_nang(self.user_binhdinh, lenh.pk)

    def test_bam_hai_lan_khong_the_chuyen_trang_thai_lap_lai(self):
        """3. Kiểm tra: Bấm hai lần (idempotency) hoặc chuyển trạng thái không hợp lệ."""
        lenh = services.tao_lenh_luu_chuyen(
            self.user_binhdinh,
            kho_xuat=self.kho_binhdinh,
            kho_nhap=self.kho_danang,
            ds_xe=[self.xe1]
        )
        services.gui_lenh_luu_chuyen(self.user_binhdinh, lenh.pk)

        # Bấm gửi lần 2 -> ValidationError
        with self.assertRaises(ValidationError):
            services.gui_lenh_luu_chuyen(self.user_binhdinh, lenh.pk)

        services.duyet_lenh_luu_chuyen(self.user_admin, lenh.pk)

        # Bấm duyệt lần 2 -> ValidationError
        with self.assertRaises(ValidationError):
            services.duyet_lenh_luu_chuyen(self.user_admin, lenh.pk)

        # Kho nguồn xuất xe
        services.xac_nhan_xuat_kho_nguon(
            self.user_binhdinh,
            lenh.pk,
            don_vi_van_chuyen_id=self.dvvc.pk,
            bien_so_xe="43C-888.88",
            tai_xe="Tài xế B",
            ngay_du_kien_den=date.today() + timedelta(days=1)
        )

        # Bấm xuất kho lần 2 -> ValidationError
        with self.assertRaises(ValidationError):
            services.xac_nhan_xuat_kho_nguon(
                self.user_binhdinh,
                lenh.pk,
                don_vi_van_chuyen_id=self.dvvc.pk,
                bien_so_xe="43C-888.88",
                tai_xe="Tài xế B",
                ngay_du_kien_den=date.today() + timedelta(days=1)
            )

        # Tiếp nhận tại Đà Nẵng
        services.xac_nhan_den_da_nang(self.user_danang, lenh.pk)

        # Bấm tiếp nhận lần 2 -> ValidationError
        with self.assertRaises(ValidationError):
            services.xac_nhan_den_da_nang(self.user_danang, lenh.pk)

    def test_ton_kho_nguon_tru_va_khong_am(self):
        """4. Kiểm tra: Tồn nguồn chỉ bị trừ khi xuất xe, tồn không bao giờ âm, transfers không cộng tồn đích."""
        lenh = services.tao_lenh_luu_chuyen(
            self.user_binhdinh,
            kho_xuat=self.kho_binhdinh,
            kho_nhap=self.kho_danang,
            ds_xe=[self.xe1]
        )

        # Bước 1: Gửi lệnh -> Tồn Bình Định vẫn = 1, Tồn Đà Nẵng = 0
        services.gui_lenh_luu_chuyen(self.user_binhdinh, lenh.pk)
        self.ton1.refresh_from_db()
        self.assertEqual(self.ton1.so_luong_ton, 1)
        self.assertFalse(TonKho.objects.filter(kho=self.kho_danang, xe=self.xe1).exists())

        # Bước 2: Duyệt lệnh -> Tồn Bình Định vẫn = 1
        services.duyet_lenh_luu_chuyen(self.user_admin, lenh.pk)
        self.ton1.refresh_from_db()
        self.assertEqual(self.ton1.so_luong_ton, 1)

        # Bước 3: Kho nguồn xuất xe -> Tồn Bình Định bị trừ về 0, Xe chuyển DANG_LUU_CHUYEN
        services.xac_nhan_xuat_kho_nguon(
            self.user_binhdinh,
            lenh.pk,
            don_vi_van_chuyen_id=self.dvvc.pk,
            bien_so_xe="77B-1234",
            tai_xe="Nguyễn Văn Tài",
            ngay_du_kien_den=date.today() + timedelta(days=2)
        )
        self.ton1.refresh_from_db()
        self.assertEqual(self.ton1.so_luong_ton, 0)
        self.assertGreaterEqual(self.ton1.so_luong_ton, 0)

        self.xe1.refresh_from_db()
        self.assertEqual(self.xe1.trang_thai, TrangThaiXe.DANG_LUU_CHUYEN)

        # Bước 4: Xe đến Đà Nẵng -> BƯỚC NÀY KHÔNG CỘNG TỒN TẠI KHO ĐÀ NẴNG
        services.xac_nhan_den_da_nang(self.user_danang, lenh.pk)
        lenh.refresh_from_db()
        self.assertEqual(lenh.trang_thai, LenhLuuChuyen.TrangThai.DA_GIAO_DEN_DA_NANG)

        # Kiểm tra tồn Đà Nẵng vẫn là 0 hoặc không tồn tại (chưa được cộng tồn)
        ton_danang = TonKho.objects.filter(kho=self.kho_danang, xe=self.xe1).first()
        ton_so_luong = ton_danang.so_luong_ton if ton_danang else 0
        self.assertEqual(ton_so_luong, 0)

    def test_huy_lenh_nha_giu_cho_xe(self):
        """5. Kiểm tra: Hủy lệnh hoặc từ chối lệnh sẽ hoàn trả trạng thái giữ chỗ xe về SẴN SÀNG."""
        # Trường hợp A: Hủy lệnh khi đang Chờ duyệt
        lenh_a = services.tao_lenh_luu_chuyen(
            self.user_binhdinh,
            kho_xuat=self.kho_binhdinh,
            kho_nhap=self.kho_danang,
            ds_xe=[self.xe1]
        )
        services.gui_lenh_luu_chuyen(self.user_binhdinh, lenh_a.pk)

        self.xe1.refresh_from_db()
        self.assertEqual(self.xe1.trang_thai, TrangThaiXe.GIU_CHO_XUAT)

        # Hủy lệnh
        services.huy_lenh_luu_chuyen(self.user_binhdinh, lenh_a.pk, ly_do="Khách hủy nhu cầu")
        lenh_a.refresh_from_db()
        self.assertEqual(lenh_a.trang_thai, LenhLuuChuyen.TrangThai.HUY)

        self.xe1.refresh_from_db()
        self.assertEqual(self.xe1.trang_thai, TrangThaiXe.SAN_SANG)

        # Trường hợp B: Sale Admin từ chối lệnh
        lenh_b = services.tao_lenh_luu_chuyen(
            self.user_binhdinh,
            kho_xuat=self.kho_binhdinh,
            kho_nhap=self.kho_danang,
            ds_xe=[self.xe2]
        )
        services.gui_lenh_luu_chuyen(self.user_binhdinh, lenh_b.pk)

        self.xe2.refresh_from_db()
        self.assertEqual(self.xe2.trang_thai, TrangThaiXe.GIU_CHO_XUAT)

        services.tu_choi_lenh_luu_chuyen(self.user_admin, lenh_b.pk, ly_do="Kho Đà Nẵng hết chỗ đỗ")
        lenh_b.refresh_from_db()
        self.assertEqual(lenh_b.trang_thai, LenhLuuChuyen.TrangThai.TU_CHOI)

        self.xe2.refresh_from_db()
        self.assertEqual(self.xe2.trang_thai, TrangThaiXe.SAN_SANG)
