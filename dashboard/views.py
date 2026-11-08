from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.db.models import Q

from core.roles import (
    get_user_role_info,
    get_user_allowed_modules,
    ALL_MODULES,
)
from .models import SuKienNoiBat, ThongBaoHoatDong


@login_required
def trang_chu(request):
    """
    Trang chủ Trung tâm (Portal Dashboard) của Hệ thống Chuỗi Cung Ứng Dana Ford.
    Hiển thị thông tin nhân viên, phân quyền theo chức danh, thông báo cập nhật mới nhất,
    và các sự kiện nổi bật.
    """
    user = request.user
    role_info = get_user_role_info(user)
    allowed_modules = get_user_allowed_modules(user)

    # Đánh dấu các module trong ALL_MODULES xem user có quyền không (phục vụ hiển thị toàn bộ module nếu cần)
    allowed_url_names = [m["url_name"] for m in allowed_modules]
    all_modules_with_perm = []
    for m in ALL_MODULES:
        item = dict(m)
        item["has_perm"] = (m["url_name"] in allowed_url_names) or (role_info and "*" in role_info.get("allowed_urls", []))
        all_modules_with_perm.append(item)

    # Sự kiện nổi bật (đang kích hoạt)
    events = SuKienNoiBat.objects.filter(is_active=True).order_by("-thoi_gian_dien_ra", "-ngay_tao")

    # Nhật ký hoạt động & Thông báo cập nhật
    if role_info and role_info.get("can_monitor_subordinates"):
        # Admin / BA: Theo dõi toàn bộ hành động của nhân viên cấp dưới
        activities = ThongBaoHoatDong.objects.filter(is_active=True).order_by("-thoi_gian")[:25]
    else:
        # Nhân viên chuyên trách: Chỉ hiển thị các hoạt động thuộc module của mình hoặc thông báo chung
        allowed_prefixes = []
        for url_name in allowed_url_names:
            prefix = url_name.split(":")[0]
            if prefix == "warehouse":
                allowed_prefixes.append("warehouse")
            elif prefix == "transfers":
                allowed_prefixes.append("transfers")
            elif prefix == "contracts":
                allowed_prefixes.append("contracts")
            elif prefix == "orders":
                allowed_prefixes.append("orders")
            elif prefix == "incidents":
                allowed_prefixes.append("incidents")
            elif prefix == "analytics":
                allowed_prefixes.append("analytics")
            elif prefix == "alerts":
                allowed_prefixes.append("alerts")

        activities = ThongBaoHoatDong.objects.filter(is_active=True).filter(
            Q(module__in=allowed_prefixes) | Q(module="he_thong") | Q(user=user)
        ).order_by("-thoi_gian")[:15]

    # Câu chào theo thời gian trong ngày
    gio_hien_tai = timezone.localtime(timezone.now()).hour
    if 5 <= gio_hien_tai < 12:
        loi_chao = "Chào buổi sáng"
    elif 12 <= gio_hien_tai < 18:
        loi_chao = "Chào buổi chiều"
    else:
        loi_chao = "Chào buổi tối"

    # Lấy tên nhân viên
    ten_hien_thi = user.get_full_name()
    if not ten_hien_thi:
        if hasattr(user, "nhan_vien") and user.nhan_vien:
            ten_hien_thi = user.nhan_vien.ten_nv
        else:
            ten_hien_thi = user.username

    context = {
        "page_title": "Trang chủ",
        "role_info": role_info,
        "allowed_modules": allowed_modules,
        "all_modules": all_modules_with_perm,
        "events": events,
        "activities": activities,
        "loi_chao": loi_chao,
        "ten_nhan_vien": ten_hien_thi,
        "total_events": events.count(),
        "total_activities": activities.count(),
        "total_modules": len(allowed_modules),
    }
    return render(request, "dashboard/trang_chu.html", context)


@login_required
def them_su_kien(request):
    """
    Thêm sự kiện nổi bật trực tiếp từ giao diện Website (Modal).
    """
    if request.method != "POST":
        return redirect("dashboard:home")

    role_info = get_user_role_info(request.user)
    if not (role_info and role_info.get("can_manage_events")):
        messages.error(request, "Bạn không có quyền hạn tạo sự kiện nổi bật!")
        return redirect("dashboard:home")

    tieu_de = request.POST.get("tieu_de", "").strip()
    noi_dung = request.POST.get("noi_dung", "").strip()
    loai_su_kien = request.POST.get("loai_su_kien", "thong_bao")
    dia_diem = request.POST.get("dia_diem", "").strip()
    thoi_gian_str = request.POST.get("thoi_gian_dien_ra", "")

    if not tieu_de or not noi_dung:
        messages.warning(request, "Vui lòng nhập đầy đủ tiêu đề và nội dung sự kiện!")
        return redirect("dashboard:home")

    thoi_gian = timezone.now()
    if thoi_gian_str:
        try:
            thoi_gian = timezone.datetime.fromisoformat(thoi_gian_str)
            if timezone.is_naive(thoi_gian):
                thoi_gian = timezone.make_aware(thoi_gian)
        except Exception:
            thoi_gian = timezone.now()

    su_kien = SuKienNoiBat.objects.create(
        tieu_de=tieu_de,
        noi_dung=noi_dung,
        loai_su_kien=loai_su_kien,
        dia_diem=dia_diem,
        thoi_gian_dien_ra=thoi_gian,
        nguoi_tao=request.user,
        is_active=True,
    )

    # Ghi nhận vào nhật ký hoạt động
    ten_nv = request.user.get_full_name() or request.user.username
    ThongBaoHoatDong.objects.create(
        user=request.user,
        ten_nhan_vien=ten_nv,
        chuc_vu=role_info.get("title", ""),
        hanh_dong=f"Đã công bố sự kiện mới: '{tieu_de}'",
        chi_tiet=f"Thời gian: {thoi_gian.strftime('%d/%m/%Y %H:%M')}. Địa điểm: {dia_diem or 'Toàn công ty'}",
        module="he_thong",
        loai="thu_cong",
    )

    messages.success(request, f"Đã thêm thành công sự kiện: '{su_kien.tieu_de}' trực tiếp vào hệ thống!")
    return redirect("dashboard:home")


@login_required
def xoa_su_kien(request, event_id):
    """
    Xóa sự kiện nổi bật trực tiếp trên giao diện Website.
    """
    if request.method != "POST":
        return redirect("dashboard:home")

    role_info = get_user_role_info(request.user)
    if not (role_info and role_info.get("can_manage_events")):
        messages.error(request, "Bạn không có quyền hạn xóa sự kiện!")
        return redirect("dashboard:home")

    su_kien = get_object_or_404(SuKienNoiBat, id=event_id)
    tieu_de = su_kien.tieu_de
    su_kien.delete()

    messages.success(request, f"Đã xóa thành công sự kiện: '{tieu_de}'!")
    return redirect("dashboard:home")


@login_required
def them_thong_bao(request):
    """
    Tạo nhanh một thông báo cập nhật / chỉ đạo của cấp quản lý cho nhân viên.
    """
    if request.method != "POST":
        return redirect("dashboard:home")

    role_info = get_user_role_info(request.user)
    if not (role_info and role_info.get("can_manage_notifications")):
        messages.error(request, "Chỉ Quản trị viên và Cấp quản lý mới có quyền tạo thông báo cập nhật!")
        return redirect("dashboard:home")

    hanh_dong = request.POST.get("hanh_dong", "").strip()
    chi_tiet = request.POST.get("chi_tiet", "").strip()
    module = request.POST.get("module", "he_thong")

    if not hanh_dong:
        messages.warning(request, "Vui lòng nhập nội dung tiêu đề thông báo cập nhật!")
        return redirect("dashboard:home")

    ten_nv = request.user.get_full_name() or request.user.username
    ThongBaoHoatDong.objects.create(
        user=request.user,
        ten_nhan_vien=ten_nv,
        chuc_vu=role_info.get("title", "Quản lý"),
        hanh_dong=hanh_dong,
        chi_tiet=chi_tiet,
        module=module,
        loai="thu_cong",
    )

    messages.success(request, "Đã gửi thông báo cập nhật đến toàn thể nhân viên thành công!")
    return redirect("dashboard:home")


@login_required
def xoa_thong_bao(request, notif_id):
    """
    Xóa hoặc gỡ bỏ thông báo cập nhật trên giao diện Website.
    """
    if request.method != "POST":
        return redirect("dashboard:home")

    role_info = get_user_role_info(request.user)
    if not (role_info and role_info.get("can_manage_notifications")):
        messages.error(request, "Bạn không có quyền xóa thông báo cập nhật!")
        return redirect("dashboard:home")

    notif = get_object_or_404(ThongBaoHoatDong, id=notif_id)
    notif.delete()

    messages.success(request, "Đã xóa bản ghi cập nhật thành công!")
    return redirect("dashboard:home")
