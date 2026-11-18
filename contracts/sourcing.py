from django.core.exceptions import ValidationError
from core.iii_iv_access import is_da_nang_branch


class SourcingTier:
    DA_NANG = "DA_NANG"
    CHI_NHANH = "CHI_NHANH"
    PHAN_BO = "PHAN_BO"


def get_sourcing_counts_by_tier(hd):
    """
    Tính số lượng xe phù hợp ở mỗi tầng nguồn cung cho hợp đồng bán tại Đà Nẵng:
    - DA_NANG: Xe sẵn sàng tại kho Đà Nẵng khớp tiêu chí hợp đồng.
    - CHI_NHANH: Xe sẵn sàng tại kho chi nhánh (Bình Định / Gia Lai) khớp tiêu chí (cần lưu chuyển).
    - PHAN_BO: Xe phân bổ từ nhà máy (và PYC) khớp tiêu chí.
    """
    from .views import find_suitable, find_allocation_vehicles

    criteria, results, error = find_suitable(hd)
    if error or not criteria:
        so_da_nang = 0
        so_chi_nhanh = 0
        so_pyc = 0
    else:
        so_da_nang = len([r for r in results if r.get('uu_tien') == 0])
        so_chi_nhanh = len([r for r in results if r.get('uu_tien') == 1])
        # Tầng "xe từ PYC chờ PDI" (uu_tien=4) được xếp cùng tầng với lịch phân bổ (Tầng 3)
        so_pyc = len([r for r in results if r.get('uu_tien') == 4 or r.get('nguon_pyc')])

    xe_phan_bo = find_allocation_vehicles(hd, criteria) if criteria else []
    so_phan_bo = len(xe_phan_bo) + so_pyc

    return {
        SourcingTier.DA_NANG: so_da_nang,
        SourcingTier.CHI_NHANH: so_chi_nhanh,
        SourcingTier.PHAN_BO: so_phan_bo,
    }


def check_can_source_from_tier(hd, tier):
    """
    Kiểm tra xem hợp đồng có được phép chốt xe từ tầng nguồn cung `tier` hay không.
    Quy tắc nghiệp vụ (Single Source of Truth):
    - Chỉ tính xe khớp đủ dòng xe, phiên bản và màu sắc (`uu_tien == 0` tại Đà Nẵng, `uu_tien == 1` tại Chi nhánh).
    - Nếu Kho Đà Nẵng còn xe phù hợp -> khóa chốt từ Chi nhánh và Lịch phân bổ.
    - Nếu Kho Đà Nẵng hết và Kho Chi nhánh còn xe phù hợp -> mở Chi nhánh, khóa Lịch phân bổ.
    - Nếu cả Kho Đà Nẵng và Kho Chi nhánh đều không có xe phù hợp -> mở Lịch phân bổ / PYC.

    Trả về: (duoc_chon: bool, ly_do_khoa: str)
    """
    from .views import find_suitable
    criteria, results, error = find_suitable(hd)
    if error or not criteria:
        so_da_nang_dung_mau = 0
        so_chi_nhanh_dung_mau = 0
    else:
        so_da_nang_dung_mau = len([r for r in results if r.get('uu_tien') == 0])
        so_chi_nhanh_dung_mau = len([r for r in results if r.get('uu_tien') == 1])

    if tier == SourcingTier.DA_NANG:
        return True, ""

    elif tier == SourcingTier.CHI_NHANH:
        if so_da_nang_dung_mau > 0:
            return False, f"Kho Đà Nẵng còn {so_da_nang_dung_mau} xe phù hợp đúng màu hợp đồng, hãy chốt xe Đà Nẵng trước."
        return True, ""

    elif tier == SourcingTier.PHAN_BO:
        if so_da_nang_dung_mau > 0:
            return False, f"Kho Đà Nẵng còn {so_da_nang_dung_mau} xe phù hợp đúng màu hợp đồng, hãy chốt xe Đà Nẵng trước."
        if so_chi_nhanh_dung_mau > 0:
            return False, f"Kho chi nhánh còn {so_chi_nhanh_dung_mau} xe phù hợp đúng màu cần lưu chuyển, hãy chốt xe chi nhánh trước."
        return True, ""

    return False, "Tầng nguồn cung không hợp lệ."


def get_sourcing_tiers_info(hd):
    """
    Trả về cấu trúc thông tin các tầng nguồn cung phục vụ cho UI & API.
    """
    counts = get_sourcing_counts_by_tier(hd)
    info = {}
    for tier in (SourcingTier.DA_NANG, SourcingTier.CHI_NHANH, SourcingTier.PHAN_BO):
        duoc_chon, ly_do = check_can_source_from_tier(hd, tier)
        info[tier] = {
            "count": counts[tier],
            "duoc_chon": duoc_chon,
            "ly_do_khoa": ly_do,
        }
    return info
