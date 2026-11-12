"""
warehouse/services.py
Cung cấp toàn bộ hàm nghiệp vụ cốt lõi cho phân hệ Quản lý Xuất kho (Đặc tả Mục 5).
Đảm bảo an toàn giao dịch (Atomic Transaction) và chống xung đột (Pessimistic Locking).
"""
import uuid
from decimal import Decimal
from django.db import transaction
from django.db.models import Q
from core.iii_iv_access import is_da_nang_branch
from contracts.demand import matches, remaining_requirements
from django.utils import timezone

from database.models import (
    HopDong, HoaDonBan, ChiTietBan, Xe, TonKho, Kho, NhanVien,
    PhieuXuatKho, LichSuXuatKho, BienBanPDI, ChiTietHopDong,
    TrangThaiXe, TrangThaiHopDong, TrangThaiPhieuXuat
)


class XuatKhoError(Exception):
    """Custom exception cho lỗi nghiệp vụ xuất kho"""
    pass


class XuatKhoService:

    @staticmethod
    def doi_chieu_hop_dong_hoa_don(ma_hd: str, vin=None) -> dict:
        """
        Nghiệp vụ UC-LPXK-02 & UC-LPXK-04:
        Đối chiếu thông tin hợp đồng và hóa đơn bán hàng.
        Chỉ đối chiếu; GET không thay đổi trạng thái hợp đồng.
        """
        try:
            hop_dong = HopDong.objects.select_related('khach_hang', 'chi_nhanh').get(ma_hd=ma_hd)
        except HopDong.DoesNotExist:
            raise XuatKhoError(f"Hợp đồng {ma_hd} không tồn tại trên hệ thống.")

        # Bảng HoaDonBan không có MaHD theo tài liệu; đối chiếu bằng khách hàng,
        # chi nhánh và VIN tại ChiTietBan.
        hoa_don = HoaDonBan.objects.filter(khach_hang=hop_dong.khach_hang, chi_nhanh=hop_dong.chi_nhanh)
        if vin is not None:
            hoa_don = hoa_don.filter(chitietban__xe_id=vin)
        hoa_don = hoa_don.order_by('ma_hdb').first()

        if not hoa_don:
            raise XuatKhoError(f"Chưa có hóa đơn bán hàng hợp lệ cho hợp đồng {ma_hd}.")

        # Kiểm tra chi tiết bán hàng
        chi_tiet = ChiTietBan.objects.filter(hoa_don_ban=hoa_don).first()
        if not chi_tiet:
            raise XuatKhoError("Hóa đơn bán hàng chưa có thông tin chi tiết xe.")

        # Kiểm tra tính khớp dữ liệu cơ bản
        is_khop = True
        ly_do_sai_lech = []

        if hoa_don.khach_hang_id != hop_dong.khach_hang_id or hoa_don.chi_nhanh_id != hop_dong.chi_nhanh_id:
            raise XuatKhoError('Hóa đơn không khớp khách hàng hoặc chi nhánh hợp đồng.')
        if not hoa_don.so_hoa_don:
            is_khop = False
            ly_do_sai_lech.append("Hóa đơn chưa có số chứng từ hợp lệ.")

        if chi_tiet.tong_thanh_toan <= Decimal('0'):
            is_khop = False
            ly_do_sai_lech.append("Số tiền thanh toán trên hóa đơn không hợp lệ.")

        if not is_khop:
            raise XuatKhoError(f"Đối chiếu thất bại: {'; '.join(ly_do_sai_lech)}")

        return {
            "hop_le": True,
            "ma_hd": hop_dong.ma_hd,
            "khach_hang": hop_dong.khach_hang.ten_kh,
            "ma_hdb": hoa_don.ma_hdb,
            "so_hoa_don": hoa_don.so_hoa_don,
            "so_tien": chi_tiet.tong_thanh_toan,
            "xe_chot_ban": chi_tiet.xe.vin if chi_tiet.xe else None
        }

    @staticmethod
    def lay_danh_sach_xe_kha_dung(ma_hd: str, ma_kho: str = "KHO01"):
        """
        Nghiệp vụ UC-LPXK-03:
        Tra cứu xe tồn kho Đà Nẵng phù hợp tiêu chí hợp đồng và CHƯA BỊ KHÓA BỞI BẤT KỲ NGHIỆP VỤ NÀO.
        """
        hop_dong = HopDong.objects.get(ma_hd=ma_hd)

        # Query xe trong kho Đà Nẵng có số lượng tồn > 0
        qs = TonKho.objects.filter(
            kho_id=ma_kho,
            so_luong_ton__gt=0,
            xe__trang_thai=TrangThaiXe.SAN_SANG
        ).select_related('xe')

        # Lọc bỏ những xe đang vướng sự cố PDI chưa đóng (UC-10 / PDI conflict prevention)
        xe_su_co_ids = BienBanPDI.objects.exclude(
            trang_thai_claim="Đã xử lý"
        ).values_list('xe_id', flat=True)
        qs = qs.exclude(xe__vin__in=xe_su_co_ids)

        # Lọc bỏ những xe đã được gán vào một phiếu xuất kho đang 'Chờ duyệt' khác
        xe_dang_giu_ids = PhieuXuatKho.objects.filter(
            trang_thai=TrangThaiPhieuXuat.CHO_DUYET
        ).values_list('chi_tiet_hop_dong__xe_id', flat=True)
        qs = qs.exclude(xe__vin__in=xe_dang_giu_ids)

        requirements = remaining_requirements(hop_dong, include_reserved=True)
        return [item.xe for item in qs if any(matches(item.xe, row) for row in requirements)]

    @classmethod
    def lap_phieu_xuat_kho(cls, ma_hd: str, vin: str, ma_kho: str, ma_nv_lap: str, nguoi_nhan: str, ghi_chu: str = "") -> PhieuXuatKho:
        """
        Nghiệp vụ UC-LPXK-01: Lập phiếu xuất kho.
        Pessimistic Locking + Atomic Transaction.
        """
        if not nguoi_nhan or not nguoi_nhan.strip():
            raise XuatKhoError("Thông tin người nhận xe là bắt buộc.")

        with transaction.atomic():
            # 1. Khóa và kiểm tra Hợp đồng
            try:
                hop_dong = HopDong.objects.select_for_update().get(ma_hd=ma_hd)
            except HopDong.DoesNotExist:
                raise XuatKhoError(f"Hợp đồng {ma_hd} không tồn tại.")

            if hop_dong.trang_thai == TrangThaiHopDong.HOAN_TAT:
                raise XuatKhoError('Hợp đồng đã hoàn tất.')
            if not is_da_nang_branch(hop_dong.chi_nhanh):
                raise XuatKhoError('Chỉ xuất xe cho hợp đồng tại Đà Nẵng.')
            cls.doi_chieu_hop_dong_hoa_don(ma_hd, vin=vin)

            # 2. Khóa và kiểm tra Xe
            try:
                xe = Xe.objects.select_for_update().get(vin=vin)
            except Xe.DoesNotExist:
                raise XuatKhoError(f"Xe có số VIN {vin} không tồn tại trong hệ thống.")

            if xe.trang_thai != TrangThaiXe.SAN_SANG:
                raise XuatKhoError(f"Xe số VIN {vin} hiện không khả dụng (Trạng thái: {xe.get_trang_thai_display()}). Đã có phiếu khác giữ chỗ hoặc xe đang gặp sự cố.")

            requirements = remaining_requirements(hop_dong, include_reserved=True)
            requirement = next((row for row in requirements if matches(xe, row)), None)
            if requirement is None:
                raise XuatKhoError('VIN không khớp nhu cầu còn thiếu của hợp đồng.')
            if ChiTietHopDong.objects.filter(xe=xe).exclude(hop_dong=hop_dong).exists():
                raise XuatKhoError('VIN đã liên kết hợp đồng khác.')
            if not is_da_nang_branch(Kho.objects.get(pk=ma_kho).chi_nhanh):
                raise XuatKhoError('Phải lưu chuyển xe về Đà Nẵng trước khi xuất.')
            if not ChiTietBan.objects.filter(hoa_don_ban__khach_hang=hop_dong.khach_hang, hoa_don_ban__chi_nhanh=hop_dong.chi_nhanh, xe=xe).exists():
                raise XuatKhoError('Hóa đơn liên kết chưa có đúng VIN xuất.')

            # 3. Kiểm tra tồn kho
            try:
                ton_kho = TonKho.objects.select_for_update().get(kho_id=ma_kho, xe=xe)
                if ton_kho.so_luong_ton <= 0:
                    raise XuatKhoError(f"Xe {vin} không còn tồn kho tại kho {ma_kho}.")
            except TonKho.DoesNotExist:
                raise XuatKhoError(f"Xe {vin} không tồn tại trong dữ liệu kho {ma_kho}.")

            # 4. Kiểm tra sự cố PDI
            if BienBanPDI.objects.filter(xe=xe).exclude(trang_thai_claim="Đã xử lý").exists():
                raise XuatKhoError(f"Xe {vin} đang có biên bản sự cố PDI chưa được xử lý xong. Không được phép lập phiếu xuất.")

            # 5. Sinh mã phiếu xuất tự động
            ma_pxk = f"PX-{timezone.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"

            # 6. Đảm bảo có ChiTietHopDong liên kết HopDong và Xe
            ct_hd, _ = ChiTietHopDong.objects.get_or_create(hop_dong=hop_dong, xe=xe)

            # 7. Tạo phiếu xuất kho qua chi_tiet_hop_dong
            old = PhieuXuatKho.objects.filter(chi_tiet_hop_dong=ct_hd).first()
            if old and old.trang_thai != TrangThaiPhieuXuat.DA_HUY:
                raise XuatKhoError('VIN đã có phiếu xuất chưa hủy.')
            phieu_xuat, _ = PhieuXuatKho.objects.update_or_create(
                chi_tiet_hop_dong=ct_hd, defaults=dict(
                    ma_pxk=old.pk if old else ma_pxk, kho_id=ma_kho,
                    nguoi_lap_id=ma_nv_lap, nguoi_nhan=nguoi_nhan.strip(), ghi_chu=ghi_chu,
                    trang_thai=TrangThaiPhieuXuat.CHO_DUYET,
                    nguoi_duyet=None, ngay_duyet=None, ngay_xuat=None))

            # 8. Cập nhật trạng thái Xe & Hợp đồng
            xe.trang_thai = TrangThaiXe.GIU_CHO_XUAT
            xe.save(update_fields=['trang_thai'])

            hop_dong.trang_thai = TrangThaiHopDong.DANG_XUAT_KHO
            hop_dong.save(update_fields=['trang_thai'])

            # 9. Ghi nhật ký
            LichSuXuatKho.objects.create(
                phieu_xuat=phieu_xuat,
                xe=xe,
                kho_id=ma_kho,
                hanh_dong="TAO_PHIEU_CHO_DUYET",
                nguoi_thuc_hien_id=ma_nv_lap,
                ghi_chu=f"Lập phiếu xuất cho HĐ {ma_hd}, giữ chỗ xe VIN {vin}"
            )

            return phieu_xuat

    @classmethod
    def duyet_phieu_xuat_kho(cls, ma_pxk: str, ma_nv_duyet: str) -> PhieuXuatKho:
        """
        Nghiệp vụ UC-PXK-03 & UC-PXK-04: Duyệt phiếu xuất kho và Tự động Cập nhật tồn kho.
        """
        with transaction.atomic():
            try:
                phieu = PhieuXuatKho.objects.select_for_update().select_related(
                    'chi_tiet_hop_dong__hop_dong__khach_hang',
                    'chi_tiet_hop_dong__xe',
                    'kho'
                ).get(ma_pxk=ma_pxk)
            except PhieuXuatKho.DoesNotExist:
                raise XuatKhoError(f"Phiếu xuất kho {ma_pxk} không tồn tại.")

            if phieu.trang_thai != TrangThaiPhieuXuat.CHO_DUYET:
                raise XuatKhoError(f"Phiếu {ma_pxk} đang ở trạng thái '{phieu.get_trang_thai_display()}', không thể duyệt lại.")

            # Lấy xe từ chi_tiet_hop_dong
            xe = Xe.objects.select_for_update().get(vin=phieu.chi_tiet_hop_dong.xe.vin)
            try:
                ton_kho = TonKho.objects.select_for_update().get(kho=phieu.kho, xe=xe)
            except TonKho.DoesNotExist:
                raise XuatKhoError(f"Xe {xe.vin} không còn trong tồn kho của {phieu.kho.ma_kho}. Không thể duyệt xuất kho!")

            if ton_kho.so_luong_ton <= 0 or xe.trang_thai == TrangThaiXe.DA_XUAT:
                raise XuatKhoError(f"Xe {xe.vin} đã bị xuất hoặc không còn khả dụng trong kho.")

            cls.doi_chieu_hop_dong_hoa_don(phieu.chi_tiet_hop_dong.hop_dong_id, vin=xe.pk)
            if xe.trang_thai != TrangThaiXe.GIU_CHO_XUAT or BienBanPDI.objects.filter(xe=xe).exclude(trang_thai_claim='Đã xử lý').exists():
                raise XuatKhoError('Xe không còn được giữ hợp lệ hoặc đang có sự cố.')
            if not ChiTietBan.objects.filter(hoa_don_ban__khach_hang=phieu.chi_tiet_hop_dong.hop_dong.khach_hang, hoa_don_ban__chi_nhanh=phieu.chi_tiet_hop_dong.hop_dong.chi_nhanh, xe=xe).exists():
                raise XuatKhoError('Hóa đơn không còn liên kết đúng VIN.')

            # Trừ tồn kho về 0
            ton_kho.so_luong_ton = 0
            ton_kho.save(update_fields=['so_luong_ton'])

            # Cập nhật xe sang Đã xuất
            xe.trang_thai = TrangThaiXe.DA_XUAT
            xe.save(update_fields=['trang_thai'])

            # Cập nhật hợp đồng sang Hoàn tất
            hop_dong = phieu.chi_tiet_hop_dong.hop_dong
            hop_dong.trang_thai = TrangThaiHopDong.DANG_XUAT_KHO
            hop_dong.save(update_fields=['trang_thai'])

            # Cập nhật phiếu xuất
            now = timezone.now()
            phieu.trang_thai = TrangThaiPhieuXuat.DA_DUYET
            phieu.nguoi_duyet_id = ma_nv_duyet
            phieu.ngay_duyet = now
            phieu.ngay_xuat = now
            phieu.save(update_fields=['trang_thai', 'nguoi_duyet', 'ngay_duyet', 'ngay_xuat'])
            hop_dong.trang_thai = TrangThaiHopDong.DANG_XUAT_KHO if remaining_requirements(hop_dong) else TrangThaiHopDong.HOAN_TAT
            hop_dong.save(update_fields=['trang_thai'])

            # Ghi nhật ký lịch sử
            LichSuXuatKho.objects.create(
                phieu_xuat=phieu,
                xe=xe,
                kho=phieu.kho,
                hanh_dong="DUYET_XUAT_KHO",
                nguoi_thuc_hien_id=ma_nv_duyet,
                ghi_chu=f"Đã duyệt xuất kho cho khách {hop_dong.khach_hang.ten_kh}. Tồn kho đã giảm 1."
            )

            return phieu

    @classmethod
    def huy_phieu_xuat_kho(cls, ma_pxk: str, ma_nv_huy: str, ly_do: str = "") -> PhieuXuatKho:
        """
        Nghiệp vụ Hủy phiếu xuất kho: giải phóng xe về SAN_SANG.
        """
        with transaction.atomic():
            phieu = PhieuXuatKho.objects.select_for_update().select_related(
                'chi_tiet_hop_dong__hop_dong',
                'chi_tiet_hop_dong__xe'
            ).get(ma_pxk=ma_pxk)

            if phieu.trang_thai != TrangThaiPhieuXuat.CHO_DUYET:
                raise XuatKhoError("Chỉ có thể hủy phiếu xuất đang ở trạng thái 'Chờ duyệt'.")

            xe = Xe.objects.select_for_update().get(vin=phieu.chi_tiet_hop_dong.xe.vin)
            if xe.trang_thai == TrangThaiXe.GIU_CHO_XUAT:
                xe.trang_thai = TrangThaiXe.SAN_SANG
                xe.save(update_fields=['trang_thai'])

            hop_dong = phieu.chi_tiet_hop_dong.hop_dong
            still_waiting = PhieuXuatKho.objects.filter(chi_tiet_hop_dong__hop_dong=hop_dong, trang_thai=TrangThaiPhieuXuat.CHO_DUYET).exclude(pk=phieu.pk).exists()
            hop_dong.trang_thai = TrangThaiHopDong.DANG_XUAT_KHO if still_waiting else TrangThaiHopDong.DU_DIEU_KIEN_XUAT
            hop_dong.save(update_fields=['trang_thai'])

            phieu.trang_thai = TrangThaiPhieuXuat.DA_HUY
            phieu.ghi_chu = f"{phieu.ghi_chu or ''} | Lý do hủy: {ly_do}".strip()
            phieu.save(update_fields=['trang_thai', 'ghi_chu'])

            LichSuXuatKho.objects.create(
                phieu_xuat=phieu,
                xe=xe,
                kho=phieu.kho,
                hanh_dong="HUY_PHIEU_XUAT",
                nguoi_thuc_hien_id=ma_nv_huy,
                ghi_chu=f"Hủy phiếu xuất kho {ma_pxk}. Giải phóng xe VIN {xe.vin} về trạng thái Sẵn sàng."
            )

            return phieu

    @staticmethod
    def trich_xuat_du_lieu_in(ma_pxk: str) -> dict:
        """
        Nghiệp vụ UC-PXK-05: Trích xuất dữ liệu phiếu xuất kho đã duyệt để in hoặc xuất file.
        """
        try:
            phieu = PhieuXuatKho.objects.select_related(
                'chi_tiet_hop_dong__hop_dong__khach_hang',
                'chi_tiet_hop_dong__xe',
                'kho',
                'nguoi_lap',
                'nguoi_duyet'
            ).get(ma_pxk=ma_pxk)
        except PhieuXuatKho.DoesNotExist:
            raise XuatKhoError(f"Phiếu xuất kho {ma_pxk} không tồn tại.")

        if phieu.trang_thai != TrangThaiPhieuXuat.DA_DUYET:
            raise XuatKhoError("Chỉ có thể xuất file đối với phiếu xuất kho đã được duyệt.")

        hop_dong = phieu.chi_tiet_hop_dong.hop_dong
        xe = phieu.chi_tiet_hop_dong.xe

        return {
            "ma_pxk": phieu.ma_pxk,
            "ngay_xuat": phieu.ngay_xuat.strftime("%d/%m/%Y %H:%M") if phieu.ngay_xuat else "",
            "kho_xuat": phieu.kho.ma_kho,
            "nguoi_lap": phieu.nguoi_lap.ten_nv if phieu.nguoi_lap else "",
            "nguoi_duyet": phieu.nguoi_duyet.ten_nv if phieu.nguoi_duyet else "",
            "nguoi_nhan": phieu.nguoi_nhan,
            "hop_dong": {
                "ma_hd": hop_dong.ma_hd,
                "khach_hang": hop_dong.khach_hang.ten_kh,
                "sdt_khach_hang": hop_dong.khach_hang.sdt_kh,
            },
            "xe": {
                "vin": xe.vin,
                "ten_xe": xe.ten_xe,
                "loai_xe": xe.loai_xe,
                "so_may": xe.so_may,
                "mau_sac": xe.mau_sac,
                "nam_sx": xe.nam_sx,
            },
            "ghi_chu": phieu.ghi_chu or ""
        }
