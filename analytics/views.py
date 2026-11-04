from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from . import exports, forecast
from .models import DA_DIEU_CHINH, NhatKyXuatFile, PhienDuBao
from .services import chay_phan_tich, tong_ket

TIEU_DE = "Dự báo nhu cầu và đề xuất nhập xe"
HET_HAN_MSG = "Kết quả phân tích chưa sẵn sàng hoặc đã hết hạn, vui lòng bấm Khởi tạo lại dự báo."


def _doc_ky(du_lieu):
    """Đọc tháng/năm từ form; trả về (thang, nam) hoặc None nếu không hợp lệ."""
    try:
        thang, nam = int(du_lieu.get("thang")), int(du_lieu.get("nam"))
    except (TypeError, ValueError):
        return None
    return (thang, nam) if 1 <= thang <= 12 and 2000 <= nam <= 2100 else None


@login_required
def index(request):
    nam, thang = forecast.cong_thang(timezone.localdate().year, timezone.localdate().month, 1)
    ky = _doc_ky(request.GET)
    thang, nam = ky if ky else (thang, nam)
    return render(request, "analytics/index.html", {
        "page_title": TIEU_DE, "thang": thang, "nam": nam, "thang_ds": range(1, 13),
        "phien_da_luu": PhienDuBao.objects.select_related("nguoi_tao")[:15], "bay_gio": timezone.now()})


# ---------- UC-09.1 + UC-09.2: bắt đầu phân tích ----------
@login_required
def phan_tich(request):
    if request.method != "POST":
        return redirect("analytics:index")
    ky = _doc_ky(request.POST)
    if ky is None:
        messages.error(request, "Vui lòng chọn kỳ dự báo hợp lệ (tháng 1-12, năm).")
        return redirect("analytics:index")
    phien = chay_phan_tich(*ky, nguoi_tao=request.user)
    messages.success(request, f"Phân tích hoàn tất cho kỳ {ky[0]:02d}/{ky[1]}.")
    return redirect("analytics:phien", pk=phien.pk)


# ---------- UC-09.3: danh sách nhu cầu ----------
def _ngu_canh(phien, nhom, nhap=None, canh_bao_vuot=False):
    tat_ca = list(phien.dong.all())
    hien = [d for d in tat_ca if not nhom or d.loai_xe == nhom]
    nhap = nhap or {}
    cac_nhom = {}
    for d in hien:
        d.gia_tri_nhap = nhap.get(d.pk, d.so_luong_nhap)
        d.ly_do_nhap = nhap.get(f"ly_do_{d.pk}", d.ly_do_dieu_chinh)
        cac_nhom.setdefault(d.loai_xe, []).append(d)
    lon_nhat = max([max(d.ky_truoc, d.du_bao_sarima) for d in hien] + [1])
    for d in hien:
        d.rong_ky_truoc = round(d.ky_truoc * 100 / lon_nhat)
        d.rong_du_bao = round(d.du_bao_sarima * 100 / lon_nhat)
    so_luong = {d.pk: nhap.get(d.pk, d.so_luong_nhap) for d in tat_ca}
    return {
        "page_title": f"{TIEU_DE} - kỳ {phien.thang:02d}/{phien.nam}", "phien": phien, "nhom": nhom,
        "cac_nhom": cac_nhom, "ds_nhom": sorted({d.loai_xe for d in tat_ca}),
        "tk": tong_ket(tat_ca, so_luong), "canh_bao_vuot": canh_bao_vuot,
        "ds_canh_bao": [x for x in phien.canh_bao.splitlines() if x], "co_dong": bool(tat_ca),
        "tong_chi_tieu_js": sum(d.chi_tieu or 0 for d in tat_ca),
        "co_chi_tieu_js": any(d.chi_tieu is not None for d in tat_ca),
        "ly_do_ngoai_le": nhap.get("ly_do_ngoai_le", phien.ly_do_ngoai_le),
    }


@login_required
def danh_sach_nhu_cau(request, pk):
    phien = get_object_or_404(PhienDuBao, pk=pk)
    if not phien.san_sang:
        messages.warning(request, HET_HAN_MSG)
        return render(request, "analytics/het_han.html", {"page_title": TIEU_DE, "phien": phien})
    return render(request, "analytics/phien.html", _ngu_canh(phien, request.GET.get("nhom", "")))


# ---------- UC-09.4: điều chỉnh số lượng ----------
@login_required
def dieu_chinh(request, pk):
    phien = get_object_or_404(PhienDuBao, pk=pk)
    if request.method != "POST" or not phien.san_sang:
        return redirect("analytics:phien", pk=pk)
    dong = {d.pk: d for d in phien.dong.all()}
    nhap, loi = {}, []
    for pk_dong, d in dong.items():
        tho = request.POST.get(f"sl_{pk_dong}")
        if tho is None:
            continue
        try:
            sl = int(tho)
            if sl < 0:
                raise ValueError
        except ValueError:
            loi.append(d.ten_xe)
            continue
        nhap[pk_dong] = sl
        nhap[f"ly_do_{pk_dong}"] = request.POST.get(f"ly_do_{pk_dong}", "").strip()
    nhap["ly_do_ngoai_le"] = request.POST.get("ly_do_ngoai_le", "").strip()
    nhom = request.POST.get("nhom", "")
    if loi:
        messages.error(request, "Số lượng nhập phải là số nguyên không âm (>= 0). Dòng lỗi: " + "; ".join(loi))
        return render(request, "analytics/phien.html", _ngu_canh(phien, nhom, nhap))
    tk = tong_ket(list(dong.values()), {k: v for k, v in nhap.items() if isinstance(k, int)})
    if tk["vuot"] and not (request.POST.get("xac_nhan_ngoai_le") and nhap["ly_do_ngoai_le"]):
        messages.error(request, f"Tổng số lượng xe vượt quá hạn mức phân bổ được giao "
                                f"[{tk['tong_sl']}/{tk['tong_chi_tieu']} xe]. Vui lòng xác nhận lý do ngoại lệ "
                                "trước khi lưu.")
        return render(request, "analytics/phien.html", _ngu_canh(phien, nhom, nhap, canh_bao_vuot=True))
    with transaction.atomic():
        da_doi = 0
        for pk_dong, d in dong.items():
            if pk_dong not in nhap:
                continue
            moi, ly_do = nhap[pk_dong], nhap[f"ly_do_{pk_dong}"]
            if moi != d.so_luong_nhap or ly_do != d.ly_do_dieu_chinh:
                d.so_luong_dieu_chinh = moi if moi != d.de_xuat_poq or d.so_luong_dieu_chinh is not None else None
                d.ly_do_dieu_chinh = ly_do
                d.save(update_fields=["so_luong_dieu_chinh", "ly_do_dieu_chinh"])
                da_doi += 1
        if da_doi:
            phien.trang_thai_de_xuat = DA_DIEU_CHINH
        phien.ly_do_ngoai_le = nhap["ly_do_ngoai_le"] if tk["vuot"] else ""
        phien.save(update_fields=["trang_thai_de_xuat", "ly_do_ngoai_le"])
    messages.success(request, "Đã lưu điều chỉnh." if da_doi else "Không có thay đổi nào để lưu.")
    return redirect("analytics:phien", pk=pk)


# ---------- UC-09.5: xuất danh sách đề xuất ----------
@login_required
def xuat_danh_sach(request, pk):
    phien = get_object_or_404(PhienDuBao, pk=pk)
    quay_lai = redirect("analytics:phien", pk=pk)
    if not phien.san_sang:
        messages.warning(request, HET_HAN_MSG)
        return quay_lai
    dinh_dang = request.GET.get("dinh_dang", "xlsx")
    ghi_chu = request.GET.get("ghi_chu", "").strip()
    kem = bool(request.GET.get("kem_bieu_do"))
    cac_dong = list(phien.dong.all())
    nguoi_lap = request.user.get_full_name() or request.user.get_username()
    try:
        if not cac_dong:
            raise ValueError("rỗng")
        if dinh_dang == "pdf":
            noi_dung, loai, duoi = exports.tao_pdf(phien, cac_dong, nguoi_lap, ghi_chu, kem), "application/pdf", "pdf"
        else:
            noi_dung = exports.tao_xlsx(phien, cac_dong, nguoi_lap, ghi_chu, kem)
            loai = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            duoi = "xlsx"
    except Exception:  # dữ liệu rỗng, thiếu thư viện/font, lỗi định dạng mẫu
        messages.error(request, "Không thể tạo file xuất do dữ liệu trống hoặc lỗi định dạng mẫu. "
                                "Vui lòng thử lại sau vài giây. (Nếu lỗi lặp lại: pip install openpyxl reportlab)")
        return quay_lai
    NhatKyXuatFile.objects.create(phien=phien, nguoi_xuat=request.user, dinh_dang=duoi, ghi_chu=ghi_chu)
    resp = HttpResponse(noi_dung, content_type=loai)
    resp["Content-Disposition"] = f'attachment; filename="ke_hoach_nhap_xe_{phien.nam}_{phien.thang:02d}.{duoi}"'
    return resp
