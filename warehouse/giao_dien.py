"""Giao diện HTML cho Quản lý xuất kho, tồn kho và kiểm kê (kế thừa base.html như module 9, 10).

Các view JSON của Linh Giang (views.py) được GIỮ NGUYÊN; file này chỉ gọi lại các hàm nghiệp vụ
trong services.py và inventory_services.py.
"""
import json

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils.dateparse import parse_date

from database.models import Xe
from .models import LichSuNhapKho
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from database.models import (
    BienBanPDI, ChiTietKiemKe, HopDong, Kho, LichSuXuatKho, NhanVien, PhanLoaiKiemKe, PhieuKiemKe,
    PhieuXuatKho, TrangThaiHopDong, TrangThaiKiemKe, TrangThaiPhieuXuat, TrangThaiXe,
)

from .inventory_services import InventoryError, InventoryService
from .services import XuatKhoError, XuatKhoService

MA_KHO_MAC_DINH = "KHO01"
SO_DONG = 15
CHENH_LECH = [PhanLoaiKiemKe.THIEU, PhanLoaiKiemKe.THUA, PhanLoaiKiemKe.SAI_VI_TRI]


# ---------- tiện ích dùng chung ----------
def _chon_kho(request):
    ma = request.GET.get("kho") or request.POST.get("kho")
    if ma and Kho.objects.filter(pk=ma).exists():
        return ma
    nv = getattr(request.user, "nhan_vien", None)
    if nv:
        kho = Kho.objects.filter(chi_nhanh=nv.chi_nhanh).first()
        if kho:
            return kho.pk
    return MA_KHO_MAC_DINH


def _ngu_canh(request, tieu_de, **them):
    ma_kho = _chon_kho(request)
    ctx = {
        "page_title": tieu_de, "ma_kho": ma_kho,
        "ds_kho": Kho.objects.select_related("chi_nhanh").order_by("ma_kho"),
        "can_chon_nv": getattr(request.user, "nhan_vien", None) is None,
        "ds_nv": NhanVien.objects.order_by("ma_nv"),
    }
    ctx.update(them)
    return ctx


def _nhan_vien(request):
    """Nhân viên thực hiện: tài khoản đã liên kết nhân viên, hoặc người được chọn trên biểu mẫu."""
    nv = getattr(request.user, "nhan_vien", None)
    if nv:
        return nv
    ma = request.POST.get("ma_nv")
    nv = NhanVien.objects.filter(pk=ma).first() if ma else None
    if nv is None:
        messages.error(request, "Tài khoản chưa liên kết với nhân viên. Hãy chọn “Nhân viên thực hiện” "
                                "hoặc gán nhân viên cho tài khoản trong Trang quản trị.")
    return nv


def _phan_trang(request, ds):
    return Paginator(ds, SO_DONG).get_page(request.GET.get("page"))


def _giu_loc(request):
    q = request.GET.copy()
    q.pop("page", None)
    return q.urlencode()

def _ton_context(
    request,
    title,
    ma_kho=None,
    locked=False,
    allow_all=False,
    **extra,
):
    ma_kho = ma_kho or _chon_kho(request)

    ctx = _ngu_canh(
        request,
        title,
        ma_kho=ma_kho,
        **extra,
    )

    warehouses = list(
        Kho.objects
        .select_related("chi_nhanh")
        .order_by("ma_kho")
    )

    items = [
        {
            "value": k.pk,
            "label": k.chi_nhanh.ten_cn,
        }
        for k in warehouses
    ]

    if allow_all:
        items.insert(
            0,
            {
                "value": "ALL",
                "label": "Cả ba kho (ĐN - BĐ - GL)",
            },
        )

    ctx["kho_hien_tai"] = next(
        (k for k in warehouses if k.pk == ma_kho),
        None,
    )

    ctx["inventory_warehouses"] = {
        "items": items,
        "selected": ma_kho,
        "locked": locked,
    }

    return ctx
# ================= XUẤT KHO =================
@login_required
def xuat_ds(request):
    # ALL: xem phiếu xuất của cả ba kho.
    # Các trường hợp khác vẫn dùng cách chọn kho hiện tại.
    if request.GET.get("kho") == "ALL":
        ma_kho = "ALL"
    else:
        ma_kho = _chon_kho(request)

    trang_thai = request.GET.get("trang_thai", "")
    tu_khoa = request.GET.get("q", "").strip()

    qs = PhieuXuatKho.objects.select_related(
        "chi_tiet_hop_dong__hop_dong__khach_hang",
        "chi_tiet_hop_dong__xe",
        "kho__chi_nhanh",
        "nguoi_lap",
    )

    # Chỉ lọc theo kho khi người dùng chọn một kho cụ thể.
    if ma_kho != "ALL":
        qs = qs.filter(kho_id=ma_kho)

    if trang_thai:
        qs = qs.filter(trang_thai=trang_thai)

    if tu_khoa:
        qs = qs.filter(
            Q(ma_pxk__icontains=tu_khoa)
            | Q(
                chi_tiet_hop_dong__hop_dong__ma_hd__icontains=tu_khoa
            )
            | Q(
                chi_tiet_hop_dong__xe__vin__icontains=tu_khoa
            )
            | Q(
                chi_tiet_hop_dong__hop_dong__khach_hang__ten_kh__icontains=tu_khoa
            )
        )

    qs = qs.order_by("-ngay_lap", "ma_pxk")
    trang = _phan_trang(request, qs)

    return render(
        request,
        "warehouse/xuat_ds.html",
        _ngu_canh(
            request,
            "Quản lý xuất kho",
            ma_kho=ma_kho,
            trang=trang,
            tong=trang.paginator.count,
            q=tu_khoa,
            trang_thai=trang_thai,
            ds_trang_thai=TrangThaiPhieuXuat.choices,
            query=_giu_loc(request),
            co_loc=bool(trang_thai or tu_khoa),
        ),
    )


@login_required
def xuat_chi_tiet(request, ma_pxk):
    phieu = PhieuXuatKho.objects.select_related(
        "chi_tiet_hop_dong__hop_dong__khach_hang", "chi_tiet_hop_dong__xe", "kho", "nguoi_lap", "nguoi_duyet",
    ).filter(pk=ma_pxk).first()
    if phieu is None:
        messages.error(request, "Phiếu xuất kho không tồn tại.")
        return redirect("warehouse:xuat")
    hd = phieu.chi_tiet_hop_dong.hop_dong
    try:
        doi_chieu = XuatKhoService.doi_chieu_hop_dong_hoa_don(hd.ma_hd)
    except XuatKhoError as e:
        doi_chieu = {"hop_le": False, "canh_bao": str(e)}
    cho_duyet = phieu.trang_thai == TrangThaiPhieuXuat.CHO_DUYET
    return render(request, "warehouse/xuat_chi_tiet.html", _ngu_canh(
        request, f"Phiếu xuất kho {phieu.ma_pxk}", phieu=phieu, hd=hd, xe=phieu.chi_tiet_hop_dong.xe,
        doi_chieu=doi_chieu, co_the_duyet=cho_duyet and doi_chieu.get("hop_le", False), co_the_huy=cho_duyet,
        co_the_in=phieu.trang_thai == TrangThaiPhieuXuat.DA_DUYET,
        lich_su=LichSuXuatKho.objects.filter(phieu_xuat=phieu).select_related("nguoi_thuc_hien")))


@login_required
def xuat_lap(request):
    """UC-LPXK: chọn hợp đồng -> xem xe khả dụng -> lập phiếu."""
    ma_kho = _chon_kho(request)
    if request.method == "POST":
        nv = _nhan_vien(request)
        if nv is not None:
            try:
                phieu = XuatKhoService.lap_phieu_xuat_kho(
                    ma_hd=request.POST.get("ma_hd", ""), vin=request.POST.get("vin", ""), ma_kho=ma_kho,
                    ma_nv_lap=nv.ma_nv, nguoi_nhan=request.POST.get("nguoi_nhan", ""),
                    ghi_chu=request.POST.get("ghi_chu", ""))
                messages.success(request, f"Đã lập phiếu xuất kho {phieu.ma_pxk}, đang chờ duyệt.")
                return redirect("warehouse:xuat_chi_tiet", ma_pxk=phieu.ma_pxk)
            except XuatKhoError as e:
                messages.error(request, str(e))
        ma_hd = request.POST.get("ma_hd", "")
    else:
        ma_hd = request.GET.get("ma_hd", "")
    xe_kha_dung, doi_chieu = [], None
    if ma_hd:
        try:
            doi_chieu = XuatKhoService.doi_chieu_hop_dong_hoa_don(ma_hd)
        except XuatKhoError as e:
            doi_chieu = {"hop_le": False, "canh_bao": str(e)}
        try:
            xe_kha_dung = XuatKhoService.lay_danh_sach_xe_kha_dung(ma_hd=ma_hd, ma_kho=ma_kho)
        except HopDong.DoesNotExist:
            messages.error(request, f"Hợp đồng {ma_hd} không tồn tại.")
    chua_co_phieu = HopDong.objects.exclude(
        chitiethopdong__phieuxuatkho__trang_thai__in=[TrangThaiPhieuXuat.CHO_DUYET, TrangThaiPhieuXuat.DA_DUYET]
    ).exclude(trang_thai=TrangThaiHopDong.HOAN_TAT).select_related("khach_hang").order_by("ma_hd")
    return render(request, "warehouse/xuat_lap.html", _ngu_canh(
        request, "Lập phiếu xuất kho", ma_hd=ma_hd, ds_hop_dong=chua_co_phieu, xe_kha_dung=xe_kha_dung,
        doi_chieu=doi_chieu))


@login_required
@require_POST
def xuat_duyet(request, ma_pxk):
    nv = _nhan_vien(request)
    if nv is not None:
        try:
            XuatKhoService.duyet_phieu_xuat_kho(ma_pxk=ma_pxk, ma_nv_duyet=nv.ma_nv)
            messages.success(request, f"Đã duyệt phiếu {ma_pxk}. Xe đã được xuất khỏi kho.")
        except XuatKhoError as e:
            messages.error(request, str(e))
    return redirect("warehouse:xuat_chi_tiet", ma_pxk=ma_pxk)


@login_required
@require_POST
def xuat_huy(request, ma_pxk):
    nv = _nhan_vien(request)
    if nv is not None:
        try:
            XuatKhoService.huy_phieu_xuat_kho(ma_pxk=ma_pxk, ma_nv_huy=nv.ma_nv, ly_do=request.POST.get("ly_do", ""))
            messages.success(request, f"Đã hủy phiếu {ma_pxk}. Xe được trả về trạng thái Sẵn sàng.")
        except XuatKhoError as e:
            messages.error(request, str(e))
    return redirect("warehouse:xuat_chi_tiet", ma_pxk=ma_pxk)


@login_required
def xuat_in(request, ma_pxk):
    """UC-PXK-05: trang in phiếu xuất kho đã duyệt (dùng Ctrl+P hoặc nút In để lưu PDF)."""
    try:
        du_lieu = XuatKhoService.trich_xuat_du_lieu_in(ma_pxk)
    except XuatKhoError as e:
        messages.error(request, str(e))
        return redirect("warehouse:xuat_chi_tiet", ma_pxk=ma_pxk)
    return render(request, "warehouse/xuat_in.html", {"page_title": f"In phiếu {ma_pxk}", "d": du_lieu})


# ================= TỒN KHO =================
@login_required
def ton_ds(request):
    ma_kho = _chon_kho(request)

    bo_loc = {
        key: request.GET.get(key, "").strip()
        for key in (
            "vin",
            "loai_xe",
            "mau_sac",
            "trang_thai",
            "phien_ban",
        )
    }

    data = InventoryService.lay_danh_sach_ton_kho(
        ma_kho=ma_kho,
        bo_loc=bo_loc,
    )

    versions = dict(
        Xe.objects
        .filter(vin__in=[x["vin"] for x in data])
        .values_list("vin", "phien_ban")
    )

    for x in data:
        x["phien_ban"] = versions.get(x["vin"]) or ""

    if bo_loc["phien_ban"]:
        keyword = bo_loc["phien_ban"].casefold()

        data = [
            x for x in data
            if keyword in x["phien_ban"].casefold()
        ]

    data.sort(key=lambda x: x["vin"])

    return render(
        request,
        "warehouse/ton_ds.html",
        _ton_context(
            request,
            "Danh sách xe tồn kho",
            ma_kho=ma_kho,
            trang=_phan_trang(request, data),
            tong=len(data),
            tong_xe=sum(x["so_luong_ton"] for x in data),
            bo_loc=bo_loc,
            ds_trang_thai=TrangThaiXe.choices,
            co_loc=any(bo_loc.values()),
            query=_giu_loc(request),
        ),
    )


@login_required
def ton_chi_tiet(request, vin):
    ma_kho = _chon_kho(request)

    try:
        d = InventoryService.lay_chi_tiet_xe_ton(
            vin=vin,
            ma_kho=ma_kho,
        )
    except InventoryError as e:
        messages.error(request, str(e))
        return redirect("warehouse:ton_kho")

    d["phien_ban"] = (
        Xe.objects
        .filter(pk=vin)
        .values_list("phien_ban", flat=True)
        .first()
    )

    history = []

    nhap = (
        LichSuNhapKho.objects
        .filter(xe_id=vin, kho_id=ma_kho)
        .select_related("phieu_nhap", "kho__chi_nhanh")
    )

    for row in nhap:
        history.append({
            "loai": "Nhập",
            "ma_phieu": row.phieu_nhap.ma_phieu,
            "kho": row.kho.chi_nhanh.ten_cn,
            "thoi_gian": row.thoi_gian,
        })

    labels = {
        "TAO_PHIEU_CHO_DUYET": "Lập phiếu xuất",
        "DUYET_XUAT_KHO": "Xuất",
        "HUY_PHIEU_XUAT": "Hủy phiếu xuất",
    }

    xuat = (
        LichSuXuatKho.objects
        .filter(xe_id=vin, kho_id=ma_kho)
        .select_related("phieu_xuat", "kho__chi_nhanh")
    )

    for row in xuat:
        history.append({
            "loai": labels.get(
                row.hanh_dong,
                row.hanh_dong,
            ),
            "ma_phieu": row.phieu_xuat_id,
            "kho": row.kho.chi_nhanh.ten_cn,
            "thoi_gian": row.thoi_gian,
        })

    history.sort(
        key=lambda x: x["thoi_gian"],
        reverse=True,
    )

    return render(
        request,
        "warehouse/ton_chi_tiet.html",
        _ton_context(
            request,
            "Chi tiết xe tồn kho",
            ma_kho=ma_kho,
            locked=True,
            d=d,
            lich_su_kho=history,
        ),
    )


# ================= KIỂM KÊ =================
@login_required
def kk_ds(request):
    ma_kho = _chon_kho(request)

    qs = (
        PhieuKiemKe.objects
        .filter(kho_id=ma_kho)
        .select_related(
            "kho__chi_nhanh",
            "nhan_vien",
            "nguoi_duyet",
        )
    )

    return render(
        request,
        "warehouse/kk_ds.html",
        _ton_context(
            request,
            "Kiểm kê tồn kho",
            ma_kho=ma_kho,
            ds=qs,
        ),
    )

@login_required
@require_POST
def kk_tao(request):
    nv = _nhan_vien(request)
    if nv is None:
        return redirect("warehouse:kk_ds")
    try:
        phieu = InventoryService.tao_phieu_kiem_ke(
            ma_kho=_chon_kho(request), ma_nv=nv.ma_nv, ky_kiem_ke=request.POST.get("ky_kiem_ke", ""),
            pham_vi=request.POST.get("pham_vi", "").strip() or "Toàn kho", ghi_chu=request.POST.get("ghi_chu", ""))
        messages.success(request, f"Đã tạo phiếu kiểm kê {phieu.ma_pkk} và chụp số liệu tồn kho.")
        return redirect("warehouse:kk_chi_tiet", ma_pkk=phieu.ma_pkk)
    except InventoryError as e:
        messages.error(request, str(e))
        return redirect("warehouse:kk_ds")


@login_required
def kk_chi_tiet(request, ma_pkk):
    phieu = get_object_or_404(
        PhieuKiemKe.objects.select_related(
            "kho__chi_nhanh",
            "nhan_vien",
            "nguoi_duyet",
        ),
        pk=ma_pkk,
    )

    dong = list(
        ChiTietKiemKe.objects
        .filter(phieu_kiem_ke=phieu)
        .select_related("xe")
        .order_by("xe_id")
    )

    reasons = []

    for d in dong:
        d.la_chenh_lech = d.phan_loai in CHENH_LECH

        if d.la_chenh_lech:
            reasons.append({
                "vin": d.xe_id,
                "type": d.get_phan_loai_display(),
                "cause": d.nguyen_nhan or "",
                "plan": d.phuong_an_xu_ly or "",
            })

    missing = sum(
        1
        for d in dong
        if d.la_chenh_lech
        and (
            not (d.nguyen_nhan or "").strip()
            or not (d.phuong_an_xu_ly or "").strip()
        )
    )

    return render(
        request,
        "warehouse/kk_chi_tiet.html",
        _ton_context(
            request,
            "Chi tiết phiếu kiểm kê",
            ma_kho=phieu.kho_id,
            locked=True,
            phieu=phieu,
            dong=dong,
            dang_kiem=(
                phieu.trang_thai
                == TrangThaiKiemKe.DANG_KIEM_KE
            ),
            cho_xu_ly=(
                phieu.trang_thai
                == TrangThaiKiemKe.CHO_XU_LY
            ),
            hoan_tat=(
                phieu.trang_thai
                == TrangThaiKiemKe.HOAN_TAT
            ),
            so_chenh_lech=len(reasons),
            so_chua_xu_ly=missing,
            so_da_xu_ly=len(reasons) - missing,
            count_reason_data=reasons,
        ),
    )
def _ve_kk(ma_pkk):
    return redirect("warehouse:kk_chi_tiet", ma_pkk=ma_pkk)


@login_required
@require_POST
def kk_kiem_dem(request, ma_pkk):
    try:
        rows = json.loads(
            request.POST.get("kiem_dem_json", "[]")
        )

        if not isinstance(rows, list) or len(rows) > 10000:
            raise InventoryError(
                "Dữ liệu kiểm đếm không hợp lệ."
            )

        clean = {}

        for row in rows:
            if not isinstance(row, dict):
                raise InventoryError(
                    "Dòng kiểm đếm không hợp lệ."
                )

            values = {
                key: row.get(key, "")
                for key in (
                    "vin",
                    "position",
                    "condition",
                    "note",
                )
            }

            if any(
                not isinstance(value, str)
                for value in values.values()
            ):
                raise InventoryError(
                    "Dữ liệu kiểm đếm phải là chuỗi ký tự."
                )

            values = {
                key: value.strip()
                for key, value in values.items()
            }

            vin = values["vin"]

            if (
                not vin
                or len(vin) > 50
                or len(values["position"]) > 50
                or len(values["condition"]) > 100
                or len(values["note"]) > 500
            ):
                raise InventoryError(
                    "VIN hoặc thông tin kiểm đếm "
                    "vượt độ dài cho phép."
                )

            clean[vin] = values

        with transaction.atomic():
            phieu = get_object_or_404(
                PhieuKiemKe.objects.select_for_update(),
                pk=ma_pkk,
            )

            allowed = set(
                ChiTietKiemKe.objects
                .filter(phieu_kiem_ke=phieu)
                .values_list("xe_id", flat=True)
            )

            if set(clean) - allowed:
                raise InventoryError(
                    "Có VIN chưa thuộc danh sách phiếu. "
                    "Vui lòng kiểm tra lại."
                )

            InventoryService.ghi_nhan_kiem_dem_thuc_te(
                ma_pkk=ma_pkk,
                danh_sach_vin_quet=list(clean),
                vi_tri_map={
                    vin: item["position"]
                    for vin, item in clean.items()
                    if item["position"]
                },
            )

            notes = []

            for vin, item in clean.items():
                (
                    ChiTietKiemKe.objects
                    .filter(
                        phieu_kiem_ke=phieu,
                        xe_id=vin,
                    )
                    .update(
                        tinh_trang=(
                            item["condition"] or "Bình thường"
                        )
                    )
                )

                if item["note"]:
                    notes.append(
                        f"{vin}: {item['note']}"
                    )

            if notes:
                phieu.refresh_from_db()

                phieu.ghi_chu = (
                    (phieu.ghi_chu or "")
                    + "\nGhi nhận kiểm đếm:\n"
                    + "\n".join(notes)
                ).strip()

                phieu.save(update_fields=["ghi_chu"])

        messages.success(
            request,
            "Đã hoàn tất kiểm đếm và đối chiếu kết quả.",
        )

    except (ValueError, TypeError, InventoryError) as e:
        message = (
            str(e)
            if isinstance(e, InventoryError)
            else "Dữ liệu kiểm đếm không hợp lệ."
        )

        messages.error(request, message)

    return _ve_kk(ma_pkk)


@login_required
@require_POST
def kk_xu_ly(request, ma_pkk):
    nv = _nhan_vien(request)
    if nv is None:
        return _ve_kk(ma_pkk)
    ds = []
    for vin in request.POST.getlist("vin"):
        nn = request.POST.get(f"nguyen_nhan_{vin}", "").strip()
        pa = request.POST.get(f"phuong_an_{vin}", "").strip()
        if nn or pa:
            ds.append({"vin": vin, "nguyen_nhan": nn, "phuong_an_xu_ly": pa})
    try:
        InventoryService.xu_ly_chenh_lech(ma_pkk=ma_pkk, ma_nv_xuly=nv.ma_nv, danh_sach_xu_ly=ds)
        messages.success(request, "Đã lưu nguyên nhân và phương án xử lý chênh lệch.")
    except InventoryError as e:
        messages.error(request, str(e))
    return _ve_kk(ma_pkk)


@login_required
@require_POST
def kk_duyet(request, ma_pkk):
    nv = _nhan_vien(request)

    if nv is not None:
        try:
            with transaction.atomic():
                get_object_or_404(
                    PhieuKiemKe.objects.select_for_update(),
                    pk=ma_pkk,
                )

                chenh_lech = (
                    ChiTietKiemKe.objects
                    .filter(
                        phieu_kiem_ke_id=ma_pkk,
                        phan_loai__in=CHENH_LECH,
                    )
                )

                for d in chenh_lech:
                    if (
                        not (d.nguyen_nhan or "").strip()
                        or not (
                            d.phuong_an_xu_ly or ""
                        ).strip()
                    ):
                        raise InventoryError(
                            "Cần lưu đủ nguyên nhân và phương án "
                            "cho các dòng chênh lệch trước khi duyệt."
                        )

                InventoryService.duyet_phieu_kiem_ke(
                    ma_pkk=ma_pkk,
                    ma_nv_duyet=nv.ma_nv,
                )

            messages.success(
                request,
                "Đã duyệt phiếu kiểm kê "
                "và điều chỉnh tồn kho.",
            )

        except InventoryError as e:
            messages.error(request, str(e))

    return _ve_kk(ma_pkk)
@login_required
def kk_lich_su(request):
    ma_kho = (
        "ALL"
        if request.GET.get("kho") == "ALL"
        else _chon_kho(request)
    )

    qs = PhieuKiemKe.objects.select_related(
        "kho__chi_nhanh",
        "nguoi_duyet",
    )

    if ma_kho != "ALL":
        qs = qs.filter(kho_id=ma_kho)

    dates = {
        key: request.GET.get(key, "")
        for key in ("tu_ngay", "den_ngay")
    }

    parsed = {}

    for key in dates:
        try:
            parsed[key] = (
                parse_date(dates[key])
                if dates[key]
                else None
            )
        except ValueError:
            parsed[key] = None

        if dates[key] and parsed[key] is None:
            messages.error(
                request,
                "Ngày lọc không hợp lệ. Vui lòng nhập lại.",
            )

    if (
        parsed["tu_ngay"]
        and parsed["den_ngay"]
        and parsed["tu_ngay"] > parsed["den_ngay"]
    ):
        messages.error(
            request,
            "Từ ngày không được sau Đến ngày.",
        )

        qs = qs.none()

    else:
        if parsed["tu_ngay"]:
            qs = qs.filter(
                ngay_kiem_ke__date__gte=parsed["tu_ngay"]
            )

        if parsed["den_ngay"]:
            qs = qs.filter(
                ngay_kiem_ke__date__lte=parsed["den_ngay"]
            )

    return render(
        request,
        "warehouse/kk_lich_su.html",
        _ton_context(
            request,
            "Lịch sử kiểm kê",
            ma_kho=ma_kho,
            allow_all=True,
            trang=_phan_trang(request, qs),
            query=_giu_loc(request),
            **dates,
        ),
    )