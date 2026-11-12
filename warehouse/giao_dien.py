"""Giao diện HTML cho Quản lý xuất kho, tồn kho và kiểm kê (kế thừa base.html như module 9, 10).

Các view JSON của Linh Giang (views.py) được GIỮ NGUYÊN; file này chỉ gọi lại các hàm nghiệp vụ
trong services.py và inventory_services.py.
"""
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
    if ma and (ma == "ALL" or Kho.objects.filter(pk=ma).exists()):
        return ma
    sess_kho = request.session.get("current_kho")
    if sess_kho and (sess_kho == "ALL" or Kho.objects.filter(pk=sess_kho).exists()):
        return sess_kho
    nv = getattr(request.user, "nhan_vien", None)
    if nv:
        kho = Kho.objects.filter(chi_nhanh=nv.chi_nhanh).first()
        if kho:
            return kho.pk
    return MA_KHO_MAC_DINH


def _ngu_canh(request, tieu_de, **them):
    ma_kho = _chon_kho(request)
    nv = getattr(request.user, "nhan_vien", None)
    if not nv and request.user.username in ("hieu", "admin", "phanquochieu"):
        nv = NhanVien.objects.filter(ma_nv="NV10").first() or NhanVien.objects.first()
    ctx = {
        "page_title": tieu_de, "ma_kho": ma_kho,
        "ds_kho": Kho.objects.select_related("chi_nhanh").order_by("ma_kho"),
        "can_chon_nv": nv is None,
        "ds_nv": NhanVien.objects.order_by("ma_nv"),
    }
    ctx.update(them)
    return ctx


def _nhan_vien(request):
    """Nhân viên thực hiện: tài khoản đã liên kết nhân viên, hoặc người được chọn trên biểu mẫu."""
    nv = getattr(request.user, "nhan_vien", None)
    if nv:
        return nv
    if request.user.username in ("hieu", "admin", "phanquochieu"):
        nv = NhanVien.objects.filter(ma_nv="NV10").first() or NhanVien.objects.first()
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


# ================= XUẤT KHO =================
@login_required
def xuat_ds(request):
    ma_kho = _chon_kho(request)
    trang_thai = request.GET.get("trang_thai", "")
    tu_khoa = request.GET.get("q", "").strip()
    qs = PhieuXuatKho.objects.select_related(
        "chi_tiet_hop_dong__hop_dong__khach_hang", "chi_tiet_hop_dong__xe", "kho", "nguoi_lap",
    )
    if ma_kho != "ALL":
        qs = qs.filter(kho_id=ma_kho)
    if trang_thai:
        qs = qs.filter(trang_thai=trang_thai)
    if tu_khoa:
        qs = qs.filter(
            Q(ma_pxk__icontains=tu_khoa) | Q(chi_tiet_hop_dong__hop_dong__ma_hd__icontains=tu_khoa)
            | Q(chi_tiet_hop_dong__xe__vin__icontains=tu_khoa)
            | Q(chi_tiet_hop_dong__hop_dong__khach_hang__ten_kh__icontains=tu_khoa))
    trang = _phan_trang(request, qs)

    # Danh sách phiếu chờ duyệt để ghim thông báo lên đầu cho Sale Admin
    qs_cho_duyet = PhieuXuatKho.objects.filter(trang_thai=TrangThaiPhieuXuat.CHO_DUYET).select_related(
        "chi_tiet_hop_dong__hop_dong__khach_hang", "chi_tiet_hop_dong__xe", "kho", "nguoi_lap"
    ).order_by("-ngay_lap", "-ma_pxk")
    if ma_kho != "ALL":
        qs_cho_duyet = qs_cho_duyet.filter(kho_id=ma_kho)
    ds_cho_duyet = list(qs_cho_duyet[:10])
    so_luong_cho_duyet = qs_cho_duyet.count()

    return render(request, "warehouse/xuat_ds.html", _ngu_canh(
        request, "Quản lý xuất kho", trang=trang, tong=trang.paginator.count, q=tu_khoa,
        trang_thai=trang_thai, ds_trang_thai=TrangThaiPhieuXuat.choices, query=_giu_loc(request),
        co_loc=bool(trang_thai or tu_khoa),
        ds_cho_duyet=ds_cho_duyet, so_luong_cho_duyet=so_luong_cho_duyet))


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
    chua_co_phieu = HopDong.objects.exclude(trang_thai=TrangThaiHopDong.HOAN_TAT).select_related("khach_hang").order_by("ma_hd")
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
    bo_loc = {k: request.GET.get(k, "").strip() for k in ("vin", "loai_xe", "mau_sac", "trang_thai")}
    danh_sach = InventoryService.lay_danh_sach_ton_kho(ma_kho=ma_kho, bo_loc=bo_loc)
    nhom = {"Tồn bình thường": 0, "Cần theo dõi": 0, "Tồn lâu": 0}
    for x in danh_sach:
        nhom[x["nhom_tuoi_ton"]] += x["so_luong_ton"]
    trang = _phan_trang(request, danh_sach)
    return render(request, "warehouse/ton_ds.html", _ngu_canh(
        request, "Quản lý tồn kho", trang=trang, tong=len(danh_sach), tong_xe=sum(x["so_luong_ton"] for x in danh_sach),
        n_binh_thuong=nhom['Tồn bình thường'], n_theo_doi=nhom['Cần theo dõi'], n_lau=nhom['Tồn lâu'], bo_loc=bo_loc, ds_trang_thai=TrangThaiXe.choices, query=_giu_loc(request),
        co_loc=any(bo_loc.values())))


@login_required
def ton_chi_tiet(request, vin):
    ma_kho = _chon_kho(request)
    try:
        d = InventoryService.lay_chi_tiet_xe_ton(vin=vin, ma_kho=ma_kho)
    except InventoryError as e:
        messages.error(request, str(e))
        return redirect("warehouse:ton_kho")
    return render(request, "warehouse/ton_chi_tiet.html", _ngu_canh(
        request, f"Xe {vin}", d=d,
        su_co=BienBanPDI.objects.filter(xe_id=vin).order_by("-ngay_ghi_nhan"),
        lich_su=LichSuXuatKho.objects.filter(xe_id=vin).select_related("nguoi_thuc_hien")))


# ================= KIỂM KÊ =================
@login_required
def kk_ds(request):
    ma_kho = _chon_kho(request)
    qs = PhieuKiemKe.objects.select_related("kho", "nhan_vien", "nguoi_duyet")
    if ma_kho != "ALL":
        qs = qs.filter(kho_id=ma_kho)
    return render(request, "warehouse/kk_ds.html", _ngu_canh(request, "Kiểm kê tồn kho", ds=qs))


@login_required
@require_POST
def kk_tao(request):
    nv = _nhan_vien(request)
    if nv is None:
        return redirect("warehouse:kk_ds")
    tao_kho = _chon_kho(request)
    if tao_kho == "ALL":
        tao_kho = "KHO01"
    try:
        phieu = InventoryService.tao_phieu_kiem_ke(
            ma_kho=tao_kho, ma_nv=nv.ma_nv, ky_kiem_ke=request.POST.get("ky_kiem_ke", ""),
            pham_vi=request.POST.get("pham_vi", "").strip() or "Toàn kho", ghi_chu=request.POST.get("ghi_chu", ""))
        messages.success(request, f"Đã tạo phiếu kiểm kê {phieu.ma_pkk} và chụp số liệu tồn kho.")
        return redirect("warehouse:kk_chi_tiet", ma_pkk=phieu.ma_pkk)
    except InventoryError as e:
        messages.error(request, str(e))
        return redirect("warehouse:kk_ds")


@login_required
def kk_chi_tiet(request, ma_pkk):
    phieu = PhieuKiemKe.objects.select_related("kho", "nhan_vien", "nguoi_duyet").filter(pk=ma_pkk).first()
    if phieu is None:
        messages.error(request, "Phiếu kiểm kê không tồn tại.")
        return redirect("warehouse:kk_ds")
    dong = list(ChiTietKiemKe.objects.filter(phieu_kiem_ke=phieu).select_related("xe").order_by("xe__vin"))
    for d in dong:
        d.la_chenh_lech = d.phan_loai in CHENH_LECH
    return render(request, "warehouse/kk_chi_tiet.html", _ngu_canh(
        request, f"Phiếu kiểm kê {ma_pkk}", phieu=phieu, dong=dong,
        dang_kiem=phieu.trang_thai == TrangThaiKiemKe.DANG_KIEM_KE,
        cho_xu_ly=phieu.trang_thai == TrangThaiKiemKe.CHO_XU_LY,
        so_chenh_lech=sum(1 for d in dong if d.la_chenh_lech),
        vin_he_thong="\n".join(d.xe.vin for d in dong)))


def _ve_kk(ma_pkk):
    return redirect("warehouse:kk_chi_tiet", ma_pkk=ma_pkk)


@login_required
@require_POST
def kk_kiem_dem(request, ma_pkk):
    danh_sach_vin = [v.strip() for v in request.POST.get("danh_sach_vin", "").splitlines() if v.strip()]
    try:
        InventoryService.ghi_nhan_kiem_dem_thuc_te(ma_pkk=ma_pkk, danh_sach_vin_quet=danh_sach_vin)
        messages.success(request, "Đã ghi nhận kiểm đếm. Hệ thống đã tự phân loại khớp / thiếu / sai vị trí.")
    except InventoryError as e:
        messages.error(request, str(e))
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
            InventoryService.duyet_phieu_kiem_ke(ma_pkk=ma_pkk, ma_nv_duyet=nv.ma_nv)
            messages.success(request, "Đã duyệt phiếu kiểm kê. Tồn kho đã được điều chỉnh theo thực tế.")
        except InventoryError as e:
            messages.error(request, str(e))
    return _ve_kk(ma_pkk)
