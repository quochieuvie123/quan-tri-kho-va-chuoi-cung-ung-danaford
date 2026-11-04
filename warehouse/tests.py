# warehouse/tests.py
from decimal import Decimal
from datetime import timedelta
from django.test import TestCase
from django.utils import timezone

from database.models import (
    ChiNhanh, Kho, NhanVien, KhachHang, Xe, TonKho,
    HopDong, HoaDonBan, ChiTietBan, BienBanPDI,
    NhaCungCap, DonViVanChuyen, HoaDonNhap,
    ChiTietHopDong, PhieuXuatKho,
    TrangThaiXe, TrangThaiHopDong, TrangThaiPhieuXuat,
    TrangThaiKiemKe, PhanLoaiKiemKe
)
from warehouse.services import XuatKhoService, XuatKhoError
from warehouse.inventory_services import InventoryService, InventoryError

class XuatKhoConflictPreventionTests(TestCase):
    def setUp(self):
        # 1. Tạo chi nhánh & kho Đà Nẵng
        self.cn = ChiNhanh.objects.create(ma_cn="DANA_DN", ten_cn="Dana Ford Đà Nẵng")
        self.kho = Kho.objects.create(ma_kho="KHO01", chi_nhanh=self.cn)

        # 2. Tạo nhân viên (chỉ gồm các trường thực tế của bảng NhanVien)
        self.nv = NhanVien.objects.create(
            ma_nv="NV001",
            chi_nhanh=self.cn,
            ten_nv="Lê Minh Anh",
            sdt_nv="0905123456"
        )

        # 3. Tạo nhà cung cấp, đơn vị vận chuyển và hóa đơn nhập (hỗ trợ test PDI)
        self.ncc = NhaCungCap.objects.create(ma_ncc="NCC01", ten_ncc="Ford Việt Nam", mst="0101010101")
        self.dvvc = DonViVanChuyen.objects.create(ma_dvvc="DVVC01", ten_dvvc="Vận Tải Dana", sdt_dvvc="0905111222")
        self.hdn = HoaDonNhap.objects.create(
            ma_hdn="HDN001",
            nha_cung_cap=self.ncc,
            chi_nhanh=self.cn,
            don_vi_van_chuyen=self.dvvc,
            ngay_nhap=timezone.now()
        )

        # 4. Tạo khách hàng
        self.kh = KhachHang.objects.create(ma_kh="KH001", ten_kh="Nguyễn Văn A", sdt_kh="0905123456")

        # 5. Tạo xe ô tô sẵn sàng xuất
        self.xe = Xe.objects.create(
            vin="VIN123456789",
            ten_xe="Ford Everest Titanium",
            loai_xe="Everest",
            so_may="SM9999",
            mau_sac="Trắng",
            trang_thai=TrangThaiXe.SAN_SANG
        )

        # 6. Ghi nhận tồn kho tại kho Đà Nẵng
        self.ton_kho = TonKho.objects.create(
            kho=self.kho,
            xe=self.xe,
            ngay_vao_kho=timezone.now().date(),
            so_luong_ton=1
        )

        # 7. Tạo hợp đồng & hóa đơn bán hàng
        self.hd = HopDong.objects.create(
            ma_hd="HD001",
            chi_nhanh=self.cn,
            khach_hang=self.kh,
            ngay_ky=timezone.now(),
            so_tien_coc=Decimal("50000000"),
            trang_thai=TrangThaiHopDong.DU_DIEU_KIEN_XUAT
        )
        self.hdb = HoaDonBan.objects.create(
            ma_hdb="HDB001",
            khach_hang=self.kh,
            chi_nhanh=self.cn,
            ngay_ban=timezone.now(),
            so_hoa_don="HD-00123"
        )
        self.ct_ban = ChiTietBan.objects.create(
            hoa_don_ban=self.hdb,
            xe=self.xe,
            so_luong_ban=1,
            gia_ban=Decimal("1200000000")
        )

    def test_01_lap_phieu_xuat_kho_thanh_cong_va_giu_cho_xe(self):
        """Test: Khi lập phiếu xuất thành công, xe phải chuyển sang GIU_CHO_XUAT"""
        phieu = XuatKhoService.lap_phieu_xuat_kho(
            ma_hd=self.hd.ma_hd,
            vin=self.xe.vin,
            ma_kho=self.kho.ma_kho,
            ma_nv_lap=self.nv.ma_nv,
            nguoi_nhan="Nguyễn Văn A"
        )
        self.assertEqual(phieu.trang_thai, TrangThaiPhieuXuat.CHO_DUYET)

        self.xe.refresh_from_db()
        self.assertEqual(self.xe.trang_thai, TrangThaiXe.GIU_CHO_XUAT)

    def test_02_chong_xung_dot_ban_trung_xe(self):
        """Test: Không thể lập phiếu xuất thứ 2 cho cùng 1 xe khi xe đang bị giữ chỗ"""
        XuatKhoService.lap_phieu_xuat_kho(
            ma_hd=self.hd.ma_hd,
            vin=self.xe.vin,
            ma_kho=self.kho.ma_kho,
            ma_nv_lap=self.nv.ma_nv,
            nguoi_nhan="Khách 1"
        )

        hd2 = HopDong.objects.create(
            ma_hd="HD002",
            chi_nhanh=self.cn,
            khach_hang=self.kh,
            ngay_ky=timezone.now(),
            trang_thai=TrangThaiHopDong.DU_DIEU_KIEN_XUAT
        )

        with self.assertRaises(XuatKhoError) as ctx:
            XuatKhoService.lap_phieu_xuat_kho(
                ma_hd=hd2.ma_hd,
                vin=self.xe.vin,
                ma_kho=self.kho.ma_kho,
                ma_nv_lap=self.nv.ma_nv,
                nguoi_nhan="Khách 2"
            )
        self.assertIn("không khả dụng", str(ctx.exception))

    def test_03_chong_xung_dot_voi_su_co_pdi(self):
        """Test: Xe đang vướng sự cố PDI chưa xử lý không được phép xuất kho"""
        BienBanPDI.objects.create(
            ma_pdi="PDI-001",
            hoa_don_nhap=self.hdn,
            xe=self.xe,
            nhan_vien=self.nv,
            ngay_ghi_nhan=timezone.now(),
            loai_su_co="Trầy xước sơn",
            trang_thai_claim="Chưa xử lý"
        )

        with self.assertRaises(XuatKhoError) as ctx:
            XuatKhoService.lap_phieu_xuat_kho(
                ma_hd=self.hd.ma_hd,
                vin=self.xe.vin,
                ma_kho=self.kho.ma_kho,
                ma_nv_lap=self.nv.ma_nv,
                nguoi_nhan="Khách"
            )
        self.assertIn("sự cố PDI", str(ctx.exception))

    def test_04_duyet_phieu_va_tru_ton_kho_atomic(self):
        """Test: Duyệt phiếu xuất kho thành công phải giảm tồn kho và chuyển trạng thái xe sang DA_XUAT"""
        phieu = XuatKhoService.lap_phieu_xuat_kho(
            ma_hd=self.hd.ma_hd,
            vin=self.xe.vin,
            ma_kho=self.kho.ma_kho,
            ma_nv_lap=self.nv.ma_nv,
            nguoi_nhan="Nguyễn Văn A"
        )

        # Duyệt phiếu
        phieu_duyet = XuatKhoService.duyet_phieu_xuat_kho(phieu.ma_pxk, self.nv.ma_nv)
        self.assertEqual(phieu_duyet.trang_thai, TrangThaiPhieuXuat.DA_DUYET)

        # Kiểm tra tồn kho đã giảm về 0
        self.ton_kho.refresh_from_db()
        self.assertEqual(self.ton_kho.so_luong_ton, 0)

        # Kiểm tra trạng thái xe đã cập nhật sang Đã xuất
        self.xe.refresh_from_db()
        self.assertEqual(self.xe.trang_thai, TrangThaiXe.DA_XUAT)

class InventoryConflictPreventionTests(TestCase):
    def setUp(self):
        self.cn = ChiNhanh.objects.create(ma_cn="DANA_DN", ten_cn="Dana Ford Đà Nẵng")
        self.kho = Kho.objects.create(ma_kho="KHO01", chi_nhanh=self.cn)
        self.nv = NhanVien.objects.create(ma_nv="NV002", chi_nhanh=self.cn, ten_nv="Trần Kho", sdt_nv="0905999888")
        # Tạo xe có tuổi tồn 45 ngày (nhóm Cần theo dõi)
        self.xe = Xe.objects.create(
            vin="VIN_INVENTORY_01", ten_xe="Ford Ranger XLS", loai_xe="Ranger",
            so_may="SM_INV_01", mau_sac="Đen", trang_thai=TrangThaiXe.SAN_SANG
        )
        self.ton = TonKho.objects.create(
            kho=self.kho, xe=self.xe,
            ngay_vao_kho=timezone.now().date() - timedelta(days=45),
            so_luong_ton=1, vi_tri="A01"
        )
    def test_05_tinh_tuoi_ton_chinh_xac(self):
        """Test: Xe nhập 45 ngày trước phải được phân nhóm 'Cần theo dõi'"""
        chi_tiet = InventoryService.lay_chi_tiet_xe_ton(vin=self.xe.vin, ma_kho=self.kho.ma_kho)
        self.assertEqual(chi_tiet["so_ngay_ton"], 45)
        self.assertEqual(chi_tiet["nhom_tuoi_ton"], "Cần theo dõi")
    def test_06_tao_phieu_kiem_ke_chup_snapshot(self):
        """Test: Tạo phiếu kiểm kê thành công và tự động snapshot tồn kho hệ thống"""
        phieu = InventoryService.tao_phieu_kiem_ke(
            ma_kho=self.kho.ma_kho, ma_nv=self.nv.ma_nv, ky_kiem_ke="Tháng 10/2026"
        )
        self.assertEqual(phieu.trang_thai, TrangThaiKiemKe.DANG_KIEM_KE)
        self.assertTrue(phieu.chitietkiemke_set.filter(xe=self.xe).exists())
    def test_07_chong_xung_dot_hai_phieu_kiem_ke_cung_mo(self):
        """Test: Không cho phép tạo 2 phiếu kiểm kê đồng thời trên cùng một kho"""
        InventoryService.tao_phieu_kiem_ke(
            ma_kho=self.kho.ma_kho, ma_nv=self.nv.ma_nv, ky_kiem_ke="Kỳ 1"
        )
        with self.assertRaises(InventoryError) as ctx:
            InventoryService.tao_phieu_kiem_ke(
                ma_kho=self.kho.ma_kho, ma_nv=self.nv.ma_nv, ky_kiem_ke="Kỳ 2"
            )
        self.assertIn("chưa hoàn tất", str(ctx.exception))
    def test_08_chong_xung_dot_xe_dang_xuat_kho_duoc_danh_dau_nghiep_vu(self):
        """
        Test quan trọng nhất: Xe đang vướng Phiếu xuất kho 'Chờ duyệt'
        khi quét kiểm kê phải được đánh dấu 'DANG_XU_LY_NGHIEP_VU' (không bị tính chênh lệch thiếu/thừa).
        """
        # Giả lập xe đang nằm trong phiếu xuất chờ duyệt
        self.xe.trang_thai = TrangThaiXe.GIU_CHO_XUAT
        self.xe.save()
        # Tạo hợp đồng & chi tiết để tạo phiếu xuất chờ duyệt
        kh = KhachHang.objects.create(ma_kh="KH002", ten_kh="Khách Test", sdt_kh="0905123999")
        hd = HopDong.objects.create(ma_hd="HD_TEST", chi_nhanh=self.cn, khach_hang=kh, ngay_ky=timezone.now())
        ct_hd = ChiTietHopDong.objects.create(hop_dong=hd, xe=self.xe)
        PhieuXuatKho.objects.create(
            ma_pxk="PX-TEST", chi_tiet_hop_dong=ct_hd, kho=self.kho,
            trang_thai=TrangThaiPhieuXuat.CHO_DUYET
        )
        # Tạo phiếu kiểm kê
        phieu_kk = InventoryService.tao_phieu_kiem_ke(
            ma_kho=self.kho.ma_kho, ma_nv=self.nv.ma_nv, ky_kiem_ke="Tháng 10/2026"
        )
        # Quét kiểm đếm (bỏ trống danh sách quét - thực tế không quét thấy xe)
        InventoryService.ghi_nhan_kiem_dem_thuc_te(ma_pkk=phieu_kk.ma_pkk, danh_sach_vin_quet=[])
        # Kết quả: Xe phải được gắn nhãn DANG_XU_LY_NGHIEP_VU chứ không phải THIEU!
        ct_item = phieu_kk.chitietkiemke_set.get(xe=self.xe)
        self.assertEqual(ct_item.phan_loai, PhanLoaiKiemKe.DANG_XU_LY_NGHIEP_VU)