from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import PermissionDenied
from django.db import DatabaseError
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods
import csv

from database.models import Kho, TonKho
from .forms import BoLocCanhBaoForm, CapNhatTrangThaiForm
from .models import CanhBao
from .utils import cap_nhat_tat_ca_canh_bao


def lay_kho_duoc_xem(user):
    if user.is_superuser or user.groups.filter(name="Quản lý").exists():
        return Kho.objects.all().order_by("ma_kho")

    if user.nhan_vien_id:
        return Kho.objects.filter(
            chi_nhanh_id=user.nhan_vien.chi_nhanh_id
        ).order_by("ma_kho")

    return Kho.objects.none()


@login_required
@permission_required("alerts.view_canhbao", raise_exception=True)
def danh_sach_canh_bao(request):
    danh_sach_kho = lay_kho_duoc_xem(request.user)

    if not danh_sach_kho.exists():
        raise PermissionDenied(
            "Tài khoản chưa được phân quyền xem kho."
        )

    cap_nhat_tat_ca_canh_bao()

    danh_sach = (
        CanhBao.objects.filter(
            con_hieu_luc=True,
        )
        .filter(
            Q(kho__in=danh_sach_kho)
            | Q(cac_kho__in=danh_sach_kho)
        )
        .select_related("kho", "nguong", "xe")
        .prefetch_related("cac_kho")
        .distinct()
        .order_by("-ngay_phat_sinh")
    )

    form = BoLocCanhBaoForm(
        request.GET,
        danh_sach_kho=danh_sach_kho,
    )

    if form.is_valid():
        kho = form.cleaned_data["kho"]
        loai = form.cleaned_data["loai"]
        ten_xe = form.cleaned_data["ten_xe"]
        mau_sac = form.cleaned_data["mau_sac"]

        if kho:
            danh_sach = danh_sach.filter(
                Q(kho=kho) | Q(cac_kho=kho)
            ).distinct()

        if loai:
            danh_sach = danh_sach.filter(loai=loai)

        if ten_xe:
            danh_sach = danh_sach.filter(
                Q(nguong__ten_xe__icontains=ten_xe)
                | Q(xe__ten_xe__icontains=ten_xe)
            )

        if mau_sac:
            danh_sach = danh_sach.filter(
                Q(nguong__mau_sac__icontains=mau_sac)
                | Q(xe__mau_sac__icontains=mau_sac)
            )
        thang = (request.GET.get("thang") or request.GET.get("month") or "").strip()
        if thang and thang != "ALL" and "-" in thang:
            try:
                y_val, m_val = map(int, thang.split("-", 1))
                danh_sach = danh_sach.filter(ngay_phat_sinh__year=y_val, ngay_phat_sinh__month=m_val)
            except ValueError:
                pass
    else:
        danh_sach = danh_sach.none()

    nhom_cb = (request.GET.get("nhom_cb") or "").strip()
    so_tat_ca = danh_sach.count()
    so_ton_kho = danh_sach.filter(loai__in=[CanhBao.Loai.DUOI_NGUONG, CanhBao.Loai.TON_LAU]).count()
    so_het_hang = danh_sach.filter(loai=CanhBao.Loai.HET_HANG).count()

    if nhom_cb == "ton_kho":
        danh_sach = danh_sach.filter(loai__in=[CanhBao.Loai.DUOI_NGUONG, CanhBao.Loai.TON_LAU])
    elif nhom_cb == "het_hang":
        danh_sach = danh_sach.filter(loai=CanhBao.Loai.HET_HANG)

    context = {
        "page_title": "Cảnh báo",
        "form": form,
        "danh_sach": danh_sach,
        "tong_so": danh_sach.count(),
        "nhom_cb": nhom_cb,
        "so_tat_ca": so_tat_ca,
        "so_ton_kho": so_ton_kho,
        "so_het_hang": so_het_hang,
    }

    return render(
        request,
        "alerts/danh_sach.html",
        context,
    )


@login_required
@permission_required("alerts.view_canhbao", raise_exception=True)
def xuat_xe_het_hang(request):
    """Xuất danh sách các dòng xe đã hết hàng (so_luong_hien_tai = 0) ra file CSV/Excel."""
    danh_sach_kho = lay_kho_duoc_xem(request.user)
    if not danh_sach_kho.exists():
        raise PermissionDenied("Tài khoản chưa được phân quyền xem kho.")

    cap_nhat_tat_ca_canh_bao()
    ds_het_hang = (
        CanhBao.objects.filter(
            con_hieu_luc=True,
            loai=CanhBao.Loai.HET_HANG,
        )
        .filter(Q(kho__in=danh_sach_kho) | Q(cac_kho__in=danh_sach_kho))
        .select_related("nguong")
        .prefetch_related("cac_kho")
        .distinct()
        .order_by("-ngay_phat_sinh")
    )

    response = HttpResponse(content_type="text/csv; charset=utf-8-sig")
    response["Content-Disposition"] = 'attachment; filename="danh_sach_dong_xe_het_hang.csv"'
    writer = csv.writer(response)
    writer.writerow([
        "Mã cảnh báo",
        "Dòng xe",
        "Màu sắc",
        "Số lượng tồn hiện tại",
        "Ngưỡng tồn tối thiểu",
        "Phạm vi kho",
        "Hướng xử lý nghiệp vụ",
        "Thời điểm ghi nhận hết hàng",
    ])
    for cb in ds_het_hang:
        writer.writerow([
            f"CB{cb.pk}",
            cb.nguong.ten_xe if cb.nguong else "",
            cb.nguong.mau_sac if cb.nguong else "",
            0,
            cb.nguong.ton_toi_thieu if cb.nguong else 2,
            cb.kho_hien_thi,
            "Ngừng chốt tồn kho - Chuyển sang đặt xe theo Lịch phân bổ kỳ tiếp theo",
            timezone.localtime(cb.ngay_phat_sinh).strftime("%d/%m/%Y %H:%M") if cb.ngay_phat_sinh else "",
        ])
    return response


@login_required
@permission_required("alerts.view_canhbao", raise_exception=True)
@require_http_methods(["GET", "POST"])
def chi_tiet_canh_bao(request, pk):
    danh_sach_kho = lay_kho_duoc_xem(request.user)

    if not danh_sach_kho.exists():
        raise PermissionDenied(
            "Tài khoản chưa được phân quyền xem kho."
        )

    cap_nhat_tat_ca_canh_bao()

    canh_bao = get_object_or_404(
        CanhBao.objects.select_related(
            "kho",
            "nguong",
            "xe",
            "nguoi_xu_ly",
        )
        .prefetch_related("cac_kho")
        .filter(
            Q(kho__in=danh_sach_kho)
            | Q(cac_kho__in=danh_sach_kho)
        )
        .distinct(),
        pk=pk,
    )

    form = CapNhatTrangThaiForm(
        request.POST if request.method == "POST" else None,
        canh_bao=canh_bao,
    )

    if request.method == "POST":
        if not request.user.has_perm("alerts.change_canhbao"):
            raise PermissionDenied(
                "Bạn không có quyền cập nhật cảnh báo."
            )

        if not canh_bao.con_hieu_luc:
            form.add_error(None, "Cảnh báo đã hết hiệu lực.")

        elif canh_bao.trang_thai == CanhBao.TrangThai.DA_XU_LY:
            form.add_error(
                None,
                "Cảnh báo đã được ghi nhận xử lý.",
            )

        elif form.is_valid():
            thoi_diem = timezone.now()

            try:
                so_ban_ghi = CanhBao.objects.filter(
                    pk=canh_bao.pk,
                    con_hieu_luc=True,
                    trang_thai=canh_bao.trang_thai,
                ).update(
                    trang_thai=form.cleaned_data["trang_thai"],
                    nguoi_xu_ly=request.user,
                    thoi_diem_xu_ly=thoi_diem,
                    ngay_cap_nhat=thoi_diem,
                )

            except DatabaseError:
                form.add_error(
                    None,
                    "Không thể lưu trạng thái. Vui lòng thử lại.",
                )

            else:
                if so_ban_ghi:
                    messages.success(
                        request,
                        "Cập nhật trạng thái thành công.",
                    )
                    return redirect(request.get_full_path())

                form.add_error(
                    None,
                    "Cảnh báo đã thay đổi. Vui lòng tải lại trang.",
                )

    ngay_vao_kho = None

    if canh_bao.xe_id:
        ton_kho = TonKho.objects.filter(
            kho_id=canh_bao.kho_id,
            xe_id=canh_bao.xe_id,
            so_luong_ton__gt=0,
        ).first()

        if ton_kho:
            ngay_vao_kho = ton_kho.ngay_vao_kho

    quay_lai = reverse("alerts:index")
    dieu_kien_loc = request.GET.urlencode()

    if dieu_kien_loc:
        quay_lai = f"{quay_lai}?{dieu_kien_loc}"

    co_the_cap_nhat = (
        request.user.has_perm("alerts.change_canhbao")
        and canh_bao.con_hieu_luc
        and canh_bao.trang_thai != CanhBao.TrangThai.DA_XU_LY
    )

    context = {
        "page_title": "Chi tiết cảnh báo",
        "canh_bao": canh_bao,
        "ngay_vao_kho": ngay_vao_kho,
        "quay_lai": quay_lai,
        "form": form,
        "co_the_cap_nhat": co_the_cap_nhat,
    }

    return render(
        request,
        "alerts/chi_tiet.html",
        context,
    )
