# warehouse/tests.py
from decimal import Decimal
from datetime import timedelta
from django.test import TestCase
from django.utils import timezone

from database.models import (
    ChiTietNhap,
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
            phien_ban="Titanium",
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
        self.hd.dong_xe_yeu_cau = self.xe.ten_xe
        self.hd.phien_ban_yeu_cau = self.xe.phien_ban
        self.hd.mau_sac_yeu_cau = self.xe.mau_sac
        self.hd.save()
        self.ct_ban = ChiTietBan.objects.create(
            hoa_don_ban=self.hdb,
            xe=self.xe,
            so_luong_ban=1,
            gia_ban=Decimal("1200000000")
        )
        ChiTietHopDong.objects.create(hop_dong=self.hd, xe=self.xe)

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
            ngay_vao_kho=timezone.localdate() - timedelta(days=45),
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


class TransferToIntakeWorkflowTests(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        self.user = User.objects.create_superuser(username='test_workflow_admin', password='password123', email='admin@danaford.com.vn')
        self.cn_dn = ChiNhanh.objects.create(ma_cn="CN01", ten_cn="Dana Ford Đà Nẵng", dia_chi_cn="Đà Nẵng")
        self.cn_bd = ChiNhanh.objects.create(ma_cn="CN02", ten_cn="Dana Ford Bình Định", dia_chi_cn="Bình Định")

        self.kho_dn = Kho.objects.create(ma_kho="KHO01", chi_nhanh=self.cn_dn)
        self.kho_bd = Kho.objects.create(ma_kho="KHO02", chi_nhanh=self.cn_bd)

        self.nv_dn = NhanVien.objects.create(ma_nv="NV_DN_01", ten_nv="Lê Kho ĐN", chi_nhanh=self.cn_dn, sdt_nv="0901111111")
        self.user.nhan_vien = self.nv_dn
        self.user.save()

        self.dvvc = DonViVanChuyen.objects.create(ma_dvvc="DVVC_01", ten_dvvc="Vận Tải Miền Trung", sdt_dvvc="0905999999")
        self.ncc = NhaCungCap.objects.create(ma_ncc="NCC_FORD", ten_ncc="Ford Hải Dương", mst="0123456789")

        self.xe = Xe.objects.create(
            vin="VIN-TRANSFER-001", ten_xe="Ford Ranger Wildtrak", phien_ban="Wildtrak 2.0L",
            loai_xe="Ranger", so_may="SM-WF001", mau_sac="Cam Saber", trang_thai=TrangThaiXe.DANG_LUU_CHUYEN
        )

        from transfers.models import LenhLuuChuyen, ChiTietLenhLuuChuyen
        self.lenh = LenhLuuChuyen.objects.create(
            ma_lenh="LLC-TEST-001",
            kho_xuat=self.kho_bd,
            kho_nhap=self.kho_dn,
            trang_thai=LenhLuuChuyen.TrangThai.DA_GIAO_DEN_DA_NANG,
            don_vi_van_chuyen=self.dvvc,
            bien_so_xe="43C-999.88",
            tai_xe="Bác Tài",
            nguoi_lap=self.user,
        )
        ChiTietLenhLuuChuyen.objects.create(lenh=self.lenh, xe=self.xe)

    def test_01_nhap_tu_lenh_khi_xe_chua_den_da_nang(self):
        """Không cho phép lập phiếu nhập kho khi lệnh lưu chuyển chưa được phê duyệt."""
        from django.core.exceptions import ValidationError
        from transfers.models import LenhLuuChuyen
        from warehouse import nhap_services as services

        # Thử với trạng thái NHAP (chưa duyệt)
        self.lenh.trang_thai = LenhLuuChuyen.TrangThai.NHAP
        self.lenh.save(update_fields=['trang_thai'])

        with self.assertRaises(ValidationError) as ctx:
            services.create_receipt(
                self.user,
                ma_phieu="PN-TEST-CHUA-DUYET",
                kho_id=self.kho_dn.pk,
                ngay_nhap=timezone.localdate(),
                lenh_luu_chuyen_id=self.lenh.pk,
                xe_id=self.xe.vin
            )
        self.assertIn("đã được phê duyệt", str(ctx.exception))

        # Thử với trạng thái CHO_DUYET (chưa duyệt)
        self.lenh.trang_thai = LenhLuuChuyen.TrangThai.CHO_DUYET
        self.lenh.save(update_fields=['trang_thai'])

        with self.assertRaises(ValidationError) as ctx:
            services.create_receipt(
                self.user,
                ma_phieu="PN-TEST-CHUA-DUYET-2",
                kho_id=self.kho_dn.pk,
                ngay_nhap=timezone.localdate(),
                lenh_luu_chuyen_id=self.lenh.pk,
                xe_id=self.xe.vin
            )
        self.assertIn("đã được phê duyệt", str(ctx.exception))

    def test_02_nhap_trung_vin_tu_lenh(self):
        """Chống nhập trùng VIN: không cho lập 2 phiếu nhập cùng VIN hoặc khi VIN đã có tồn kho."""
        from django.core.exceptions import ValidationError
        from warehouse import nhap_services as services

        # Tạo phiếu nhập đầu tiên thành công
        receipt = services.create_receipt(
            self.user,
            ma_phieu="PN-TEST-VIN-01",
            kho_id=self.kho_dn.pk,
            ngay_nhap=timezone.localdate(),
            lenh_luu_chuyen_id=self.lenh.pk,
            xe_id=self.xe.vin
        )
        self.assertEqual(receipt.trang_thai, 'NHAP')

        # Thử tạo phiếu thứ hai cho cùng VIN khi phiếu 1 đang mở -> ValidationError
        with self.assertRaises(ValidationError) as ctx:
            services.create_receipt(
                self.user,
                ma_phieu="PN-TEST-VIN-02",
                kho_id=self.kho_dn.pk,
                ngay_nhap=timezone.localdate(),
                lenh_luu_chuyen_id=self.lenh.pk,
                xe_id=self.xe.vin
            )
        self.assertTrue("chưa hoàn tất" in str(ctx.exception) or "đã có phiếu nhập" in str(ctx.exception))

        # Giả sử xe đã có tồn kho sẵn trong hệ thống
        receipt.delete()
        TonKho.objects.create(kho=self.kho_dn, xe=self.xe, so_luong_ton=1, ngay_vao_kho=timezone.localdate())

        with self.assertRaises(ValidationError) as ctx:
            services.create_receipt(
                self.user,
                ma_phieu="PN-TEST-VIN-03",
                kho_id=self.kho_dn.pk,
                ngay_nhap=timezone.localdate(),
                lenh_luu_chuyen_id=self.lenh.pk,
                xe_id=self.xe.vin
            )
        self.assertIn("đã có tồn kho", str(ctx.exception))

    def test_03_pdi_khong_dat_chuyen_trang_thai_su_co(self):
        """Khi PDI không đạt: xe chuyển sang SU_CO_PDI và không cho duyệt nhập kho."""
        from django.core.exceptions import ValidationError
        from warehouse import nhap_services as services

        receipt = services.create_receipt(
            self.user,
            ma_phieu="PN-TEST-PDI-FAIL",
            kho_id=self.kho_dn.pk,
            ngay_nhap=timezone.localdate(),
            lenh_luu_chuyen_id=self.lenh.pk,
            xe_id=self.xe.vin
        )

        pdi = services.record_pdi(
            self.user,
            receipt.pk,
            tinh_trang="Trầy xước sơn cản trước và móp cánh cửa",
            ket_qua="KHONG_DAT",
            ghi_chu="Sự cố trong quá trình lưu chuyển đường dài",
            hang_muc=[
                {"hang_muc": "Ngoại thất", "tinh_trang": "Trầy xước cản trước", "ket_qua": "KHONG_DAT", "ghi_chu": "Trầy sơn"},
                {"hang_muc": "Nội thất", "tinh_trang": "Bình thường", "ket_qua": "DAT", "ghi_chu": ""},
                {"hang_muc": "Vận hành", "tinh_trang": "Bình thường", "ket_qua": "DAT", "ghi_chu": ""},
            ]
        )

        # Duyệt PDI không đạt
        services.approve_pdi(self.user, receipt.pk, pdi_id=pdi.pk)

        # Kiểm tra trạng thái xe phải là SU_CO_PDI
        self.xe.refresh_from_db()
        self.assertEqual(self.xe.trang_thai, TrangThaiXe.SU_CO_PDI)

        # Cố gửi duyệt phiếu nhập kho -> Bị chặn
        with self.assertRaises(ValidationError):
            services.submit_receipt(self.user, receipt.pk, pdi_id=pdi.pk)

    def test_04_sau_su_co_hoan_tat_nhap_kho_va_lenh_hoan_tat(self):
        """Sau khi xử lý và đóng sự cố: phiếu nhập hoàn tất DA_DUYET, tồn kho KHO01 +1, xe SAN_SANG, LenhLuuChuyen HOAN_TAT."""
        from transfers.models import LenhLuuChuyen
        from warehouse import nhap_services as services

        receipt = services.create_receipt(
            self.user,
            ma_phieu="PN-TEST-RESOLVE",
            kho_id=self.kho_dn.pk,
            ngay_nhap=timezone.localdate(),
            lenh_luu_chuyen_id=self.lenh.pk,
            xe_id=self.xe.vin
        )

        pdi = services.record_pdi(
            self.user,
            receipt.pk,
            tinh_trang="Trầy xước nhẹ",
            ket_qua="KHONG_DAT",
            ghi_chu="Đưa sang xử lý sự cố bồi thường",
            hang_muc=[
                {"hang_muc": "Ngoại thất", "tinh_trang": "Xước sơn", "ket_qua": "KHONG_DAT", "ghi_chu": ""},
                {"hang_muc": "Nội thất", "tinh_trang": "Bình thường", "ket_qua": "DAT", "ghi_chu": ""},
                {"hang_muc": "Vận hành", "tinh_trang": "Bình thường", "ket_qua": "DAT", "ghi_chu": ""},
            ]
        )
        services.approve_pdi(self.user, receipt.pk, pdi_id=pdi.pk)

        # Ghi nhận biên bản sự cố PDI liên kết lệnh lưu chuyển
        bb = BienBanPDI.objects.create(
            ma_pdi="PDI-CLAIM-001",
            lenh_luu_chuyen=self.lenh,
            xe=self.xe,
            nhan_vien=self.nv_dn,
            ngay_ghi_nhan=timezone.now(),
            loai_su_co="Trầy xước sơn",
            mo_ta_chi_tiet="ĐVVC đồng ý khắc phục sơn lại",
            trang_thai_claim="Chưa xử lý"
        )

        # Giả lập đóng hồ sơ sự cố qua complete_after_incident_closed
        bb.trang_thai_claim = "Đã xử lý"
        bb.save(update_fields=['trang_thai_claim'])
        services.complete_after_incident_closed(bb)

        # Kiểm tra phiếu nhập kho
        receipt.refresh_from_db()
        self.assertEqual(receipt.trang_thai, 'DA_DUYET')

        # Kiểm tra tồn kho tại Đà Nẵng (KHO01)
        ton = TonKho.objects.get(kho=self.kho_dn, xe=self.xe)
        self.assertEqual(ton.so_luong_ton, 1)

        # Kiểm tra trạng thái xe
        self.xe.refresh_from_db()
        self.assertEqual(self.xe.trang_thai, TrangThaiXe.SAN_SANG)

        # Kiểm tra Lệnh lưu chuyển chuyển sang HOAN_TAT
        self.lenh.refresh_from_db()
        self.assertEqual(self.lenh.trang_thai, LenhLuuChuyen.TrangThai.HOAN_TAT)

    def test_05_luong_nhap_tu_hoa_don_van_chay_dung(self):
        """Đảm bảo luồng nhập kho từ hóa đơn thông thường (HoaDonNhap) không bị ảnh hưởng (regression)."""
        from warehouse import nhap_services as services
        from warehouse.models import PhieuNhapKho

        hdn = HoaDonNhap.objects.create(
            ma_hdn="HDN-FACTORY-01", nha_cung_cap=self.ncc, chi_nhanh=self.cn_dn,
            don_vi_van_chuyen=self.dvvc, ngay_nhap=timezone.now(),
            so_hoa_don="HD001", bien_so_xe="43C-111.22", ten_tai_xe="Bác Tài Nhà Máy"
        )
        xe_hdn = Xe.objects.create(
            vin="VIN-FACTORY-001", ten_xe="Ford Territory Titanium", phien_ban="Titanium X",
            loai_xe="Territory", so_may="SM-TT001", mau_sac="Đỏ Ruby", trang_thai=TrangThaiXe.SAN_SANG
        )
        ctn = ChiTietNhap.objects.create(
            hoa_don_nhap=hdn, xe=xe_hdn, so_luong_nhap=1, don_gia=Decimal("800000000"), thanh_tien=Decimal("800000000")
        )

        receipt = services.create_receipt(
            self.user,
            ma_phieu="PN-FACTORY-001",
            kho_id=self.kho_dn.pk,
            ngay_nhap=timezone.localdate(),
            chi_tiet_nhap_id=ctn.pk
        )
        self.assertEqual(receipt.loai_nguon, PhieuNhapKho.LoaiNguon.HOA_DON)
        self.assertEqual(receipt.chi_tiet_nhap_id, ctn.pk)
        self.assertIsNone(receipt.lenh_luu_chuyen)

        # Ghi PDI Đạt
        pdi = services.record_pdi(
            self.user, receipt.pk,
            tinh_trang="Xe mới xuất xưởng nguyên bản",
            ket_qua="DAT",
            ghi_chu="Đạt 100% tiêu chuẩn nghiệm thu",
            hang_muc=[
                {"hang_muc": "Ngoại thất", "tinh_trang": "Tốt", "ket_qua": "DAT", "ghi_chu": ""},
                {"hang_muc": "Nội thất", "tinh_trang": "Tốt", "ket_qua": "DAT", "ghi_chu": ""},
                {"hang_muc": "Vận hành", "tinh_trang": "Tốt", "ket_qua": "DAT", "ghi_chu": ""},
            ]
        )
        services.approve_pdi(self.user, receipt.pk, pdi_id=pdi.pk)
        services.submit_receipt(self.user, receipt.pk, pdi_id=pdi.pk)
        services.approve_receipt(self.user, receipt.pk, pdi_id=pdi.pk)

        receipt.refresh_from_db()
        self.assertEqual(receipt.trang_thai, 'DA_DUYET')

        ton = TonKho.objects.get(kho=self.kho_dn, xe=xe_hdn)
        self.assertEqual(ton.so_luong_ton, 1)

        xe_hdn.refresh_from_db()
        self.assertEqual(xe_hdn.trang_thai, TrangThaiXe.SAN_SANG)

    def test_06_khong_the_tao_phieu_hai_nguon_hoac_khong_nguon(self):
        """Bắt buộc phải có đúng 1 nguồn chứng từ (XOR)."""
        from django.core.exceptions import ValidationError
        from warehouse import nhap_services as services

        # Không nguồn nào
        with self.assertRaises(ValidationError) as ctx:
            services.create_receipt(
                self.user,
                ma_phieu="PN-TEST-NO-SOURCE",
                kho_id=self.kho_dn.pk,
                ngay_nhap=timezone.localdate()
            )
        self.assertIn("chính xác một nguồn", str(ctx.exception))
