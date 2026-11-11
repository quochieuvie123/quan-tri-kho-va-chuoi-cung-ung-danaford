from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import PermissionDenied
from django.db import DatabaseError
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

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
    else:
        danh_sach = danh_sach.none()

    context = {
        "page_title": "Cảnh báo",
        "form": form,
        "danh_sach": danh_sach,
        "tong_so": danh_sach.count(),
    }

    return render(
        request,
        "alerts/danh_sach.html",
        context,
    )


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
