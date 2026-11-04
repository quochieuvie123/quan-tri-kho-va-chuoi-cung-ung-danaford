"""Hàm nghiệp vụ của module sự cố. App khác (vd: warehouse) có thể import để dùng."""
import re

from database.models import BienBanPDI, TrangThaiXe, Xe

from .models import DA_XU_LY


def xe_bi_khoa_nhap_kho(xe):
    """True nếu xe (đối tượng Xe hoặc VIN) còn sự cố chưa đóng -> không được lập phiếu nhập kho.

    Dùng trong module nhập kho:
        from incidents.services import xe_bi_khoa_nhap_kho
        if xe_bi_khoa_nhap_kho(vin): báo lỗi
    """
    vin = getattr(xe, "pk", xe)
    return BienBanPDI.objects.filter(xe_id=vin).exclude(trang_thai_claim=DA_XU_LY).exists()


def sinh_ma_pdi():
    """PDI01, PDI02, ... (tự tăng theo số lớn nhất hiện có)."""
    so_lon_nhat = 0
    for ma in BienBanPDI.objects.filter(ma_pdi__startswith="PDI").values_list("ma_pdi", flat=True):
        m = re.fullmatch(r"PDI(\d+)", ma)
        if m:
            so_lon_nhat = max(so_lon_nhat, int(m.group(1)))
    return f"PDI{so_lon_nhat + 1:02d}"


def khoa_xe_vi_su_co(xe):
    """Ghi nhận sự cố -> Xe.trang_thai = "Sự cố PDI - Khóa xuất" (xe đã xuất kho thì giữ nguyên)."""
    if xe.trang_thai not in (TrangThaiXe.SU_CO_PDI, TrangThaiXe.DA_XUAT):
        xe.trang_thai = TrangThaiXe.SU_CO_PDI
        xe.save(update_fields=["trang_thai"])


def mo_khoa_xe_khi_dong_su_co(xe):
    """Đóng sự cố -> trả xe về "Sẵn sàng", trừ khi xe còn sự cố khác chưa đóng."""
    xe = Xe.objects.get(pk=xe.pk)
    if xe.trang_thai == TrangThaiXe.SU_CO_PDI and not xe_bi_khoa_nhap_kho(xe):
        xe.trang_thai = TrangThaiXe.SAN_SANG
        xe.save(update_fields=["trang_thai"])
