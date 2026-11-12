import logging
from io import BytesIO
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.mail import EmailMessage
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from xhtml2pdf import pisa

from core.roles import get_user_role_info
from database.models import Kho, TonKho, Xe, DonViVanChuyen
from .models import LenhLuuChuyen, ChiTietLenhLuuChuyen
from . import services

FONT_DIR = settings.BASE_DIR / "transfers" / "static" / "fonts"

pdfmetrics.registerFont(
    TTFont(
        "DejaVuSans",
        str(FONT_DIR / "DejaVuSans.ttf")
    )
)

pdfmetrics.registerFont(
    TTFont(
        "DejaVuSans-Bold",
        str(FONT_DIR / "DejaVuSans-Bold.ttf")
    )
)

pdfmetrics.registerFontFamily(
    "DejaVuSans",
    normal="DejaVuSans",
    bold="DejaVuSans-Bold",
)


def link_callback(uri, rel):
    font_files = {
        "DejaVuSans.ttf": "DejaVuSans.ttf",
        "DejaVuSans-Bold.ttf": "DejaVuSans-Bold.ttf",
    }
    if uri in font_files:
        return str(FONT_DIR / font_files[uri])
    return uri


@login_required
def danh_sach_ton_kho(request):
    """Màn hình danh sách xe tồn kho sẵn sàng lập lệnh lưu chuyển."""
    ds_kho = Kho.objects.select_related('chi_nhanh').all()
    ds_ton_kho = TonKho.objects.select_related(
        'kho',
        'kho__chi_nhanh',
        'xe'
    ).filter(
        so_luong_ton__gt=0
    )

    tu_khoa = request.GET.get('q', '').strip()
    if tu_khoa:
        ds_ton_kho = ds_ton_kho.filter(
            Q(xe__ten_xe__icontains=tu_khoa) |
            Q(xe__vin__icontains=tu_khoa) |
            Q(kho__ma_kho__icontains=tu_khoa) |
            Q(kho__chi_nhanh__ten_cn__icontains=tu_khoa)
        )

    ds_ton_kho = ds_ton_kho.order_by('kho__ma_kho')

    context = {
        'ds_kho': ds_kho,
        'ds_ton_kho': ds_ton_kho,
        'tu_khoa': tu_khoa,
    }

    ds_da_chon = request.session.get("ds_xe_luu_chuyen", [])
    danh_sach_da_chon = []

    for index, item in enumerate(ds_da_chon):
        ton_kho = TonKho.objects.select_related(
            "xe", "kho", "kho__chi_nhanh"
        ).filter(pk=item["ton_kho_id"]).first()

        kho_nhan = Kho.objects.select_related(
            "chi_nhanh"
        ).filter(pk=item["kho_nhan_id"]).first()

        if ton_kho and kho_nhan:
            danh_sach_da_chon.append({
                "index": index,
                "ton_kho": ton_kho,
                "kho_nhan": kho_nhan,
                "so_luong": item.get("so_luong", 1)
            })
    context['danh_sach_da_chon'] = danh_sach_da_chon
    return render(request, 'transfers/danh_sach_ton_kho.html', context)


@login_required
def chi_tiet_xe(request, id):
    """Chi tiết xe trước khi thêm vào danh sách điều chuyển."""
    ton_kho = get_object_or_404(
        TonKho.objects.select_related("xe", "kho", "kho__chi_nhanh"),
        pk=id
    )

    ds_kho_nhan = Kho.objects.exclude(pk=ton_kho.kho_id).select_related("chi_nhanh")

    if request.method == "POST":
        kho_nhan_id = request.POST.get("kho_nhan")
        so_luong_nhap = request.POST.get("so_luong", "1")

        try:
            so_luong = int(so_luong_nhap)
        except (ValueError, TypeError):
            so_luong = 1

        if so_luong <= 0:
            messages.error(request, "Số lượng điều chuyển phải lớn hơn 0.")
            return redirect("transfers:chi_tiet_xe", id=id)

        kho_nhan = get_object_or_404(Kho, pk=kho_nhan_id)
        if ton_kho.kho_id == kho_nhan.pk:
            messages.error(request, "Kho xuất và kho tiếp nhận không được trùng nhau.")
            return redirect("transfers:chi_tiet_xe", id=id)

        # Kiểm tra VIN có đang nằm trong lệnh lưu chuyển khác chưa hoàn tất
        try:
            services.kiem_tra_vin_trong_lenh_mo(ton_kho.xe)
        except ValidationError as exc:
            messages.error(request, str(exc.message if hasattr(exc, "message") else exc))
            return redirect("transfers:chi_tiet_xe", id=id)

        ds_da_chon = request.session.get("ds_xe_luu_chuyen", [])
        da_co = False
        for item in ds_da_chon:
            if item["ton_kho_id"] == ton_kho.pk:
                item["so_luong"] = 1
                item["kho_nhan_id"] = kho_nhan.pk
                da_co = True
                break

        if not da_co:
            ds_da_chon.append({
                "ton_kho_id": ton_kho.pk,
                "kho_nhan_id": kho_nhan.pk,
                "so_luong": 1,
            })

        request.session["ds_xe_luu_chuyen"] = ds_da_chon
        messages.success(request, f"Đã thêm xe {ton_kho.xe.vin} vào danh sách dự kiến lưu chuyển.")
        return redirect(reverse("transfers:index") + "?tab=da-chon")

    return render(request, "transfers/chi_tiet_xe.html", {
        "ton_kho": ton_kho,
        "ds_kho_nhan": ds_kho_nhan,
    })


@login_required
@require_POST
def xoa_xe_da_chon(request, index):
    """Xóa một xe khỏi danh sách tạm trong session."""
    ds = request.session.get("ds_xe_luu_chuyen", [])
    if 0 <= index < len(ds):
        ds.pop(index)
        request.session["ds_xe_luu_chuyen"] = ds
        messages.success(request, "Đã xóa xe khỏi danh sách dự kiến lưu chuyển.")
    return redirect(reverse("transfers:index") + "?tab=da-chon")


@login_required
def tao_lenh_luu_chuyen(request):
    """Xem và xác nhận tạo lệnh lưu chuyển từ session."""
    danh_sach = request.session.get("ds_xe_luu_chuyen", [])
    if not danh_sach:
        messages.warning(request, "Chưa có xe nào trong danh sách điều chuyển.")
        return redirect("transfers:index")

    chi_tiet = []
    for item in danh_sach:
        ton_kho = get_object_or_404(TonKho.objects.select_related("xe", "kho", "kho__chi_nhanh"), pk=item["ton_kho_id"])
        kho_nhan = get_object_or_404(Kho.objects.select_related("chi_nhanh"), pk=item["kho_nhan_id"])
        chi_tiet.append({
            "ton_kho": ton_kho,
            "kho_nhan": kho_nhan,
            "so_luong": item.get("so_luong", 1),
        })

    kho_xuat = chi_tiet[0]["ton_kho"].kho
    kho_nhap = chi_tiet[0]["kho_nhan"]

    for item in chi_tiet:
        if item["ton_kho"].kho_id != kho_xuat.pk or item["kho_nhan"].pk != kho_nhap.pk:
            messages.error(request, "Một lệnh lưu chuyển phải có cùng kho xuất và kho tiếp nhận.")
            return redirect(reverse("transfers:index") + "?tab=da-chon")

    if request.method == "POST":
        lenh_id = request.session.get("lenh_nhap_dang_sua_id")
        try:
            if lenh_id:
                lenh = get_object_or_404(LenhLuuChuyen.objects.select_for_update(), pk=lenh_id, trang_thai=LenhLuuChuyen.TrangThai.NHAP)
                services.kiem_tra_quyen_chi_nhanh(request.user, kho_xuat)
                with transaction.atomic():
                    lenh.kho_xuat = kho_xuat
                    lenh.kho_nhap = kho_nhap
                    lenh.save(update_fields=["kho_xuat", "kho_nhap"])
                    lenh.chi_tiet.all().delete()
                    for it in chi_tiet:
                        services.kiem_tra_vin_trong_lenh_mo(it["ton_kho"].xe, exclude_order_id=lenh.pk)
                        ChiTietLenhLuuChuyen.objects.create(lenh=lenh, xe=it["ton_kho"].xe, so_luong=1)
            else:
                ds_xe = [it["ton_kho"].xe for it in chi_tiet]
                lenh = services.tao_lenh_luu_chuyen(request.user, kho_xuat, kho_nhap, ds_xe=ds_xe)

            request.session.pop("lenh_nhap_dang_sua_id", None)
            request.session.pop("ds_xe_luu_chuyen", None)
            messages.success(request, f"Đã lưu lệnh lưu chuyển bản nháp {lenh.ma_lenh}.")
            return redirect("transfers:chi_tiet_lenh", id=lenh.pk)
        except (PermissionDenied, ValidationError) as exc:
            messages.error(request, str(exc.message if hasattr(exc, "message") else exc))
            return redirect(reverse("transfers:index") + "?tab=da-chon")

    return render(request, "transfers/lenh_luu_chuyen.html", {
        "kho_xuat": kho_xuat,
        "kho_nhap": kho_nhap,
        "chi_tiet": chi_tiet,
        "tong_so_luong": len(chi_tiet),
    })


@login_required
@require_POST
def xac_nhan_lenh_luu_chuyen(request):
    """Chuyển hướng hoặc xử lý xác nhận lập lệnh."""
    return tao_lenh_luu_chuyen(request)


@login_required
def danh_sach_lenh_luu_chuyen(request):
    """Màn hình danh sách tất cả các lệnh lưu chuyển nội bộ."""
    trang_thai = request.GET.get("trang_thai", "").strip()
    tu_khoa = request.GET.get("q", "").strip()

    ds_lenh = LenhLuuChuyen.objects.select_related(
        "kho_xuat", "kho_xuat__chi_nhanh",
        "kho_nhap", "kho_nhap__chi_nhanh",
        "nguoi_lap", "don_vi_van_chuyen"
    ).order_by("-ngay_lap")

    if trang_thai:
        if trang_thai == "CHO_DUYET":
            ds_lenh = ds_lenh.filter(trang_thai__in=["CHO_DUYET", "DA_GUI"])
        elif trang_thai == "HOAN_TAT":
            ds_lenh = ds_lenh.filter(trang_thai__in=["HOAN_TAT", "DA_XAC_NHAN"])
        else:
            ds_lenh = ds_lenh.filter(trang_thai=trang_thai)

    if tu_khoa:
        ds_lenh = ds_lenh.filter(
            Q(ma_lenh__icontains=tu_khoa) |
            Q(kho_xuat__ma_kho__icontains=tu_khoa) |
            Q(kho_nhap__ma_kho__icontains=tu_khoa) |
            Q(nguoi_lap__username__icontains=tu_khoa) |
            Q(bien_so_xe__icontains=tu_khoa) |
            Q(tai_xe__icontains=tu_khoa)
        )

    return render(request, "transfers/danh_sach_lenh.html", {
        "ds_lenh": ds_lenh,
        "trang_thai": trang_thai,
        "tu_khoa": tu_khoa,
    })


@login_required
def chi_tiet_lenh_luu_chuyen(request, id):
    """Xem văn bản tờ lệnh lưu chuyển & hiển thị các nút thao tác tương ứng từng bước."""
    lenh = get_object_or_404(
        LenhLuuChuyen.objects.select_related(
            "kho_xuat", "kho_xuat__chi_nhanh",
            "kho_nhap", "kho_nhap__chi_nhanh",
            "nguoi_lap", "nguoi_duyet", "nguoi_xuat", "nguoi_giao", "nguoi_xac_nhan",
            "don_vi_van_chuyen"
        ).prefetch_related("chi_tiet__xe"),
        pk=id
    )

    chi_tiet = list(lenh.chi_tiet.all())
    tong_so_luong = len(chi_tiet)

    is_admin = services.is_admin_or_sale_admin(request.user)
    nv = getattr(request.user, "nhan_vien", None)
    is_kho_xuat = is_admin or (nv and nv.chi_nhanh_id == lenh.kho_xuat.chi_nhanh_id)
    is_kho_nhap = is_admin or (nv and nv.chi_nhanh_id == lenh.kho_nhap.chi_nhanh_id)

    can_cancel = (
        lenh.trang_thai in [
            LenhLuuChuyen.TrangThai.NHAP,
            LenhLuuChuyen.TrangThai.CHO_DUYET,
            LenhLuuChuyen.TrangThai.DA_GUI,
            LenhLuuChuyen.TrangThai.DA_DUYET
        ] and (is_admin or lenh.nguoi_lap_id == request.user.pk or is_kho_xuat)
    )

    ds_dvvc = DonViVanChuyen.objects.all().order_by("ma_dvvc")

    return render(request, "transfers/chi_tiet_lenh.html", {
        "lenh": lenh,
        "chi_tiet": chi_tiet,
        "tong_so_luong": tong_so_luong,
        "is_sale_admin": is_admin,
        "is_kho_xuat": is_kho_xuat,
        "is_kho_nhap": is_kho_nhap,
        "can_cancel": can_cancel,
        "ds_dvvc": ds_dvvc,
    })


@login_required
@require_POST
def gui_lenh_luu_chuyen(request, id):
    """Sale Chi Nhánh gửi lệnh (NHAP -> CHO_DUYET). Không trừ tồn."""
    try:
        lenh = services.gui_lenh_luu_chuyen(request.user, id)
        messages.success(
            request,
            f"Đã gửi lệnh {lenh.ma_lenh} thành công! Lệnh đang chờ Sale Admin phê duyệt."
        )
    except (PermissionDenied, ValidationError) as exc:
        messages.error(request, f"Lỗi gửi lệnh: {exc.message if hasattr(exc, 'message') else exc}")
    return redirect("transfers:chi_tiet_lenh", id=id)


@login_required
@require_POST
def phe_duyet_lenh(request, id):
    """Sale Admin phê duyệt lệnh (CHO_DUYET -> DA_DUYET). Không trừ tồn."""
    try:
        lenh = services.duyet_lenh_luu_chuyen(request.user, id)
        messages.success(
            request,
            f"Đã phê duyệt lệnh lưu chuyển {lenh.ma_lenh}. Kho nguồn {lenh.kho_xuat.ma_kho} có thể tiến hành xuất xe."
        )
    except (PermissionDenied, ValidationError) as exc:
        messages.error(request, f"Lỗi duyệt lệnh: {exc.message if hasattr(exc, 'message') else exc}")
    return redirect("transfers:chi_tiet_lenh", id=id)


@login_required
@require_POST
def tu_choi_lenh(request, id):
    """Sale Admin từ chối lệnh (CHO_DUYET -> TU_CHOI). Nhả giữ chỗ xe."""
    ly_do = request.POST.get("ly_do_tu_choi", "")
    try:
        lenh = services.tu_choi_lenh_luu_chuyen(request.user, id, ly_do=ly_do)
        messages.warning(
            request,
            f"Đã từ chối lệnh {lenh.ma_lenh}. Xe đã được hoàn lại trạng thái SẴN SÀNG."
        )
    except (PermissionDenied, ValidationError) as exc:
        messages.error(request, f"Lỗi từ chối lệnh: {exc.message if hasattr(exc, 'message') else exc}")
    return redirect("transfers:chi_tiet_lenh", id=id)


@login_required
@require_POST
def huy_lenh(request, id):
    """Hủy lệnh lưu chuyển trước khi xuất kho. Nhả giữ chỗ xe."""
    ly_do = request.POST.get("ghi_chu_huy", "")
    try:
        lenh = services.huy_lenh_luu_chuyen(request.user, id, ly_do=ly_do)
        messages.info(
            request,
            f"Đã hủy lệnh lưu chuyển {lenh.ma_lenh}. Xe đã được hoàn lại trạng thái SẴN SÀNG."
        )
    except (PermissionDenied, ValidationError) as exc:
        messages.error(request, f"Lỗi hủy lệnh: {exc.message if hasattr(exc, 'message') else exc}")
    return redirect("transfers:chi_tiet_lenh", id=id)


@login_required
@require_POST
def xuat_kho_nguon(request, id):
    """Kho nguồn xác nhận xuất xe (DA_DUYET -> DANG_VAN_CHUYEN).
    Trừ tồn kho nguồn, xe = DANG_LUU_CHUYEN.
    """
    dvvc_id = request.POST.get("don_vi_van_chuyen_id")
    bien_so = request.POST.get("bien_so_xe")
    tai_xe = request.POST.get("tai_xe")
    sdt_tai_xe = request.POST.get("sdt_tai_xe")
    ngay_du_kien = request.POST.get("ngay_du_kien_den")

    try:
        lenh = services.xac_nhan_xuat_kho_nguon(
            request.user,
            id,
            don_vi_van_chuyen_id=dvvc_id,
            bien_so_xe=bien_so,
            tai_xe=tai_xe,
            sdt_tai_xe=sdt_tai_xe,
            ngay_du_kien_den=ngay_du_kien
        )
        messages.success(
            request,
            f"Kho nguồn {lenh.kho_xuat.ma_kho} đã xuất xe thành công! Tồn kho nguồn đã trừ, xe đang lưu chuyển về Đà Nẵng."
        )
    except (PermissionDenied, ValidationError) as exc:
        messages.error(request, f"Lỗi xuất xe: {exc.message if hasattr(exc, 'message') else exc}")
    return redirect("transfers:chi_tiet_lenh", id=id)


@login_required
@require_POST
def xac_nhan_den_da_nang(request, id):
    """Tiếp nhận xe đến bãi Đà Nẵng (DANG_VAN_CHUYEN -> DA_GIAO_DEN_DA_NANG).
    TUYỆT ĐỐI KHÔNG CỘNG TỒN TẠI BƯỚC NÀY.
    """
    try:
        lenh = services.xac_nhan_den_da_nang(request.user, id)
        messages.success(
            request,
            f"Lệnh {lenh.ma_lenh}: Xe đã đến bãi Đà Nẵng (chờ nhập kho). Vui lòng chuyển sang module Quản lý nhập kho để lập phiếu nhập và kiểm tra PDI."
        )
    except (PermissionDenied, ValidationError) as exc:
        messages.error(request, f"Lỗi tiếp nhận: {exc.message if hasattr(exc, 'message') else exc}")
    return redirect("transfers:chi_tiet_lenh", id=id)


@login_required
@require_POST
def cap_nhat_trang_thai_lenh(request, id):
    """Tương thích ngược: Điều hướng thao tác theo trạng thái hiện tại của lệnh."""
    lenh = get_object_or_404(LenhLuuChuyen, pk=id)
    if lenh.trang_thai in (LenhLuuChuyen.TrangThai.CHO_DUYET, LenhLuuChuyen.TrangThai.DA_GUI):
        return phe_duyet_lenh(request, id)
    elif lenh.trang_thai == LenhLuuChuyen.TrangThai.DANG_VAN_CHUYEN:
        return xac_nhan_den_da_nang(request, id)
    else:
        messages.warning(request, f"Lệnh đang ở trạng thái {lenh.get_trang_thai_display()}, không thể chuyển đổi nhanh.")
        return redirect("transfers:chi_tiet_lenh", id=id)


@login_required
def chinh_sua_lenh_luu_chuyen(request, id):
    """Nạp danh sách xe của bản nháp vào session để người dùng chỉnh sửa."""
    lenh = get_object_or_404(LenhLuuChuyen.objects.prefetch_related("chi_tiet__xe"), pk=id)
    if lenh.trang_thai != LenhLuuChuyen.TrangThai.NHAP:
        messages.error(request, "Chỉ có thể chỉnh sửa lệnh ở trạng thái Bản nháp.")
        return redirect("transfers:chi_tiet_lenh", id=id)

    services.kiem_tra_quyen_chi_nhanh(request.user, lenh.kho_xuat)

    danh_sach = []
    for item in lenh.chi_tiet.all():
        ton_kho = TonKho.objects.filter(kho=lenh.kho_xuat, xe=item.xe).first()
        if ton_kho:
            danh_sach.append({
                "ton_kho_id": ton_kho.pk,
                "kho_nhan_id": lenh.kho_nhap_id,
                "so_luong": 1,
            })

    request.session["ds_xe_luu_chuyen"] = danh_sach
    request.session["lenh_nhap_dang_sua_id"] = lenh.pk
    messages.success(request, "Đã nạp bản nháp vào phiên làm việc. Bạn có thể tiếp tục chỉnh sửa.")
    return redirect(reverse("transfers:index") + "?tab=da-chon")
