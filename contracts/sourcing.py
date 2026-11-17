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
        so_da_nang = len([r for r in results if r.get('uu_tien') in (0, 2)])
        so_chi_nhanh = len([r for r in results if r.get('uu_tien') in (1, 3)])
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
    Quy tắc nghiệp vụ:
    - Còn xe phù hợp tại Đà Nẵng thì CHỈ được chốt xe Đà Nẵng.
    - Đà Nẵng không còn xe phù hợp nhưng chi nhánh còn thì CHỈ được chốt xe chi nhánh.
    - Cả hai không còn xe phù hợp mới được chốt từ lịch phân bổ/PYC.
    - Không có ngoại lệ cho bất kỳ vai trò nào (kể cả Sale Admin).

    Trả về: (duoc_chon: bool, ly_do_khoa: str)
    """
    counts = get_sourcing_counts_by_tier(hd)
    so_da_nang = counts[SourcingTier.DA_NANG]
    so_chi_nhanh = counts[SourcingTier.CHI_NHANH]

    if tier == SourcingTier.DA_NANG:
        return True, ""

    elif tier == SourcingTier.CHI_NHANH:
        if so_da_nang > 0:
            return False, f"Kho Đà Nẵng còn {so_da_nang} xe phù hợp, hãy chốt xe Đà Nẵng trước."
        return True, ""

    elif tier == SourcingTier.PHAN_BO:
        if so_da_nang > 0:
            return False, f"Kho Đà Nẵng còn {so_da_nang} xe phù hợp, hãy chốt xe Đà Nẵng trước."
        if so_chi_nhanh > 0:
            return False, f"Kho chi nhánh còn {so_chi_nhanh} xe phù hợp cần lưu chuyển, hãy chốt xe chi nhánh trước."
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
