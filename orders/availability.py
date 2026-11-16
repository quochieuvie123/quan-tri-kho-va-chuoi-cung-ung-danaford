from datetime import timedelta
from django.conf import settings
from django.utils import timezone
from database.models import ChiTietHopDong, Xe
from warehouse.models import PhieuNhapKho
from .models import Allocation, VehicleRequest, VehicleRequestItem


class AllocationAvailabilityStatus:
    CON_TRONG = "CON_TRONG"
    DANG_GIU = "DANG_GIU"
    DA_DAT = "DA_DAT"
    DA_GAN_HOP_DONG = "DA_GAN_HOP_DONG"


def release_expired_draft_requests():
    """
    Tự động nhả các phiếu nháp (DRAFT) đã hết thời hạn giữ chỗ (hold_until < now).
    Được gọi lazily mỗi khi tra cứu/liệt kê danh sách hoặc trước các thao tác đặt xe.
    """
    now = timezone.now()
    expired_drafts = VehicleRequest.objects.filter(
        status=VehicleRequest.Status.DRAFT,
        hold_until__isnull=False,
        hold_until__lt=now
    )
    for draft in expired_drafts:
        # Xóa các xe khỏi phiếu nháp hết hạn để nhả xe ngay lập tức
        draft.items.all().delete()
        draft.status = VehicleRequest.Status.REJECTED
        draft.rejection_reason = "Hết hạn giữ chỗ nháp (tự động nhả xe)"
        draft.save(update_fields=["status", "rejection_reason"])


def get_allocations_availability_map(allocations_list_or_qs, target_hd=None, exclude_request_id=None):
    """
    Kiểm tra trạng thái sẵn sàng (availability) hàng loạt cho một danh sách Allocation.
    Trả về dict: {alloc_id: {
        'status': AllocationAvailabilityStatus,
        'label': str,
        'is_available': bool,
        'holder': str or None,
        'hold_until': datetime or None,
    }}
    """
    # 1. Nhả lazily các phiếu nháp quá hạn
    release_expired_draft_requests()

    allocs = list(allocations_list_or_qs)
    if not allocs:
        return {}

    alloc_ids = [a.id for a in allocs]
    vins = [a.vin for a in allocs if a.vin]

    now = timezone.now()

    # 2. Lấy các VehicleRequestItem đang giữ hoặc đã đặt
    req_items_qs = VehicleRequestItem.objects.filter(
        allocation_id__in=alloc_ids
    ).select_related("vehicle_request", "vehicle_request__created_by")

    if exclude_request_id:
        req_items_qs = req_items_qs.exclude(vehicle_request_id=exclude_request_id)

    # Phân loại theo alloc_id
    req_map = {}
    for item in req_items_qs:
        req = item.vehicle_request
        if req.status in (VehicleRequest.Status.PENDING, VehicleRequest.Status.ACCEPTED):
            req_map[item.allocation_id] = {
                "type": AllocationAvailabilityStatus.DA_DAT,
                "label": "Đã đặt",
                "holder": req.created_by.get_full_name() or req.created_by.username,
                "hold_until": None
            }
        elif req.status == VehicleRequest.Status.DRAFT:
            if req.hold_until and req.hold_until > now:
                holder_name = req.created_by.get_full_name() or req.created_by.username
                time_str = timezone.localtime(req.hold_until).strftime("%H:%M %d/%m")
                req_map[item.allocation_id] = {
                    "type": AllocationAvailabilityStatus.DANG_GIU,
                    "label": f"Đang giữ chỗ bởi {holder_name} đến {time_str}",
                    "holder": holder_name,
                    "hold_until": req.hold_until
                }

    # 3. Lấy thông tin xe đã gán hợp đồng
    ct_hd_qs = ChiTietHopDong.objects.filter(xe__vin__in=vins)
    if target_hd:
        ct_hd_qs = ct_hd_qs.exclude(hop_dong=target_hd)
    vins_gan_hd = set(ct_hd_qs.values_list("xe__vin", flat=True))

    # 4. Lấy thông tin xe / phiếu nhập kho đang hoạt động
    # Nếu xe đã có bản ghi Xe hoặc Phiếu nhập kho và không phải hợp đồng hiện tại
    active_wh_vins = set(
        PhieuNhapKho.objects.filter(xe__vin__in=vins)
        .exclude(trang_thai="HUY")
        .values_list("xe__vin", flat=True)
    )

    result = {}
    for alloc in allocs:
        # Kiểm tra theo độ ưu tiên
        if alloc.vin in vins_gan_hd:
            result[alloc.id] = {
                "status": AllocationAvailabilityStatus.DA_GAN_HOP_DONG,
                "label": "Đã gán HĐ",
                "is_available": False,
                "holder": None,
                "hold_until": None
            }
        elif alloc.id in req_map:
            info = req_map[alloc.id]
            result[alloc.id] = {
                "status": info["type"],
                "label": info["label"],
                "is_available": False,
                "holder": info["holder"],
                "hold_until": info["hold_until"]
            }
        elif alloc.vin in active_wh_vins:
            result[alloc.id] = {
                "status": AllocationAvailabilityStatus.DA_DAT,
                "label": "Đã đặt (Kho)",
                "is_available": False,
                "holder": None,
                "hold_until": None
            }
        else:
            result[alloc.id] = {
                "status": AllocationAvailabilityStatus.CON_TRONG,
                "label": "Còn trống",
                "is_available": True,
                "holder": None,
                "hold_until": None
            }

    return result


def get_allocation_status(alloc, target_hd=None, exclude_request_id=None):
    """
    Lấy trạng thái của một Allocation duy nhất.
    """
    res = get_allocations_availability_map([alloc], target_hd=target_hd, exclude_request_id=exclude_request_id)
    return res.get(alloc.id, {
        "status": AllocationAvailabilityStatus.CON_TRONG,
        "label": "Còn trống",
        "is_available": True,
        "holder": None,
        "hold_until": None
    })


def get_available_allocations(queryset=None, target_hd=None):
    """
    Lọc danh sách các Allocation thực sự còn trống (CON_TRONG).
    """
    if queryset is None:
        queryset = Allocation.objects.all()

    release_expired_draft_requests()
    now = timezone.now()

    # Các allocation_id đang bị giữ hoặc đã đặt
    active_req_alloc_ids = VehicleRequestItem.objects.filter(
        models_q_filter(now)
    ).values_list("allocation_id", flat=True)

    # VIN đã gán hợp đồng
    ct_hd_qs = ChiTietHopDong.objects.all()
    if target_hd:
        ct_hd_qs = ct_hd_qs.exclude(hop_dong=target_hd)
    vins_gan_hd = ct_hd_qs.values_list("xe__vin", flat=True)

    # VIN trong phiếu nhập kho
    active_wh_vins = PhieuNhapKho.objects.exclude(trang_thai="HUY").values_list("xe__vin", flat=True)

    return (
        queryset
        .exclude(id__in=active_req_alloc_ids)
        .exclude(vin__in=vins_gan_hd)
        .exclude(vin__in=active_wh_vins)
    )


def models_q_filter(now):
    from django.db.models import Q
    return (
        Q(vehicle_request__status__in=[VehicleRequest.Status.PENDING, VehicleRequest.Status.ACCEPTED]) |
        Q(vehicle_request__status=VehicleRequest.Status.DRAFT, vehicle_request__hold_until__gt=now)
    )
