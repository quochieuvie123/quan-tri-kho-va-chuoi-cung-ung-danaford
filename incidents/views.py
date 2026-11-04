import json
from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.mail import EmailMessage, get_connection
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone

from database.models import BienBanPDI, ChiTietNhap

from . import exports
from .forms import GhiNhanForm, GuiYeuCauForm, KetQuaForm, LocForm
from .models import (CHUA_XU_LY, DA_GUI_YEU_CAU, DA_XU_LY, AnhSuCo, DvvcLienHe, HoSoSuCo,
                     LichSuPhanHoi, nhan_trang_thai)
from .services import sinh_ma_pdi

TIEU_DE = "Quản lý sự cố vận chuyển"
SO_DONG = 10
HAN_PHAN_HOI_NGAY = 7


def _ds_goc():
    return BienBanPDI.objects.select_related(
        "xe", "nhan_vien", "hoa_don_nhap__don_vi_van_chuyen", "ho_so").order_by("-ngay_ghi_nhan", "-ma_pdi")


def _loc(params):
    """Áp bộ lọc từ GET. Trả về (form, queryset)."""
    form = LocForm(params or None)
    qs = _ds_goc()
    if form.is_valid():
        d = form.cleaned_data
        if d["q"]:
            k = d["q"].strip()
            qs = qs.filter(Q(xe__vin__icontains=k) | Q(hoa_don_nhap__bien_so_xe__icontains=k)
                           | Q(hoa_don_nhap__ma_hdn__icontains=k) | Q(ma_pdi__icontains=k))
        if d["tu_ngay"]:
            qs = qs.filter(ngay_ghi_nhan__date__gte=d["tu_ngay"])
        if d["den_ngay"]:
            qs = qs.filter(ngay_ghi_nhan__date__lte=d["den_ngay"])
        if d["dvvc"]:
            qs = qs.filter(hoa_don_nhap__don_vi_van_chuyen=d["dvvc"])
        if d["trang_thai"] == "dang_xu_ly":
            qs = qs.exclude(trang_thai_claim=DA_XU_LY)
        elif d["trang_thai"] == "da_dong":
            qs = qs.filter(trang_thai_claim=DA_XU_LY)
    return form, qs


def _co_loc(params):
    return any(params.get(k) for k in ("q", "tu_ngay", "den_ngay", "dvvc", "trang_thai"))


def _lay_bien_ban(request, ma_pdi):
    """E1 (UC-10.1.2): không tìm thấy -> báo và quay về danh sách."""
    bb = _ds_goc().filter(pk=ma_pdi).first()
    if bb is None:
        messages.error(request, "Không tìm thấy dữ liệu phiếu sự cố yêu cầu.")
    return bb


def _ho_so(bb):
    return HoSoSuCo.objects.get_or_create(bien_ban=bb)[0]


def _ghi_lich_su(request, bb, hanh_dong, noi_dung=""):
    LichSuPhanHoi.objects.create(bien_ban=bb, nguoi_thuc_hien=request.user, hanh_dong=hanh_dong, noi_dung=noi_dung)


# ---------- UC-10.2.1 / 10.2.2: danh sách + lọc ----------
@login_required
def danh_sach(request):
    form, qs = _loc(request.GET)
    trang = Paginator(qs, SO_DONG).get_page(request.GET.get("page"))
    for bb in trang:
        bb.nhan_tt = nhan_trang_thai(bb.trang_thai_claim)
    giu = request.GET.copy()
    giu.pop("page", None)
    return render(request, "incidents/danh_sach.html", {
        "page_title": TIEU_DE, "form": form, "trang": trang, "tong": trang.paginator.count,
        "co_loc": _co_loc(request.GET), "query": giu.urlencode(),
    })


# ---------- UC-10.2.3: xuất báo cáo ----------
@login_required
def xuat_bao_cao(request):
    pham_vi = request.GET.get("pham_vi", "loc")
    dinh_dang = request.GET.get("dinh_dang", "xlsx")
    if pham_vi == "tat_ca":
        qs = _ds_goc()
    else:
        _, qs = _loc(request.GET)
    danh_sach_bb = list(qs)
    quay_lai = reverse("incidents:index")
    if not danh_sach_bb:  # E1
        messages.warning(request, "Không có dữ liệu sự cố để trích xuất báo cáo.")
        return redirect(quay_lai)
    ten = f"bao_cao_su_co_{timezone.localtime():%Y%m%d_%H%M}"
    try:
        if dinh_dang == "pdf":
            noi_dung, loai, duoi = exports.tao_pdf(danh_sach_bb), "application/pdf", "pdf"
        else:
            noi_dung = exports.tao_xlsx(danh_sach_bb)
            loai = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            duoi = "xlsx"
    except ImportError as e:
        messages.error(request, f"Thiếu thư viện để xuất file ({e.name}). Chạy: pip install openpyxl reportlab")
        return redirect(quay_lai)
    except RuntimeError as e:
        messages.error(request, str(e))
        return redirect(quay_lai)
    resp = HttpResponse(noi_dung, content_type=loai)
    resp["Content-Disposition"] = f'attachment; filename="{ten}.{duoi}"'
    return resp


# ---------- UC-10.1.1: ghi nhận ----------
@login_required
def ghi_nhan(request):
    ban_dau = {k: request.GET[k] for k in ("hoa_don_nhap", "xe") if request.GET.get(k)}
    if "hdn" in request.GET:
        ban_dau["hoa_don_nhap"] = request.GET["hdn"]
    form = GhiNhanForm(request.POST or None, request.FILES or None, initial=ban_dau, user=request.user)
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        nv = form.nv_tai_khoan or d["nhan_vien"]
        with transaction.atomic():
            bb = BienBanPDI.objects.create(
                ma_pdi=sinh_ma_pdi(), hoa_don_nhap=d["hoa_don_nhap"], xe=d["xe"], nhan_vien=nv,
                ngay_ghi_nhan=timezone.now(), loai_su_co=d["loai_su_co"],
                mo_ta_chi_tiet=d["mo_ta_chi_tiet"].strip(), trang_thai_claim=CHUA_XU_LY)
            anh = [AnhSuCo.objects.create(bien_ban=bb, tep=f) for f in d["anh"]]
            bb.hinh_anh_url = request.build_absolute_uri(reverse("incidents:tep_anh", args=[anh[0].pk]))
            bb.save(update_fields=["hinh_anh_url"])
            _ho_so(bb)
            _ghi_lich_su(request, bb, "Ghi nhận sự cố", f"{bb.loai_su_co}: {bb.mo_ta_chi_tiet}")
        messages.success(request, f"Ghi nhận sự cố thành công (mã hồ sơ {bb.ma_pdi}). "
                                  "Xe đang xử lý sự cố - khóa nhập kho.")
        return redirect("incidents:chi_tiet", ma_pdi=bb.ma_pdi)
    xe_theo_hdn = {}
    for hdn, vin in ChiTietNhap.objects.values_list("hoa_don_nhap_id", "xe_id"):
        xe_theo_hdn.setdefault(hdn, []).append(vin)
    return render(request, "incidents/ghi_nhan.html", {
        "page_title": "Ghi nhận sự cố vận chuyển", "form": form, "xe_theo_hdn": json.dumps(xe_theo_hdn)})


# ---------- UC-10.1.2: chi tiết ----------
@login_required
def chi_tiet(request, ma_pdi):
    bb = _lay_bien_ban(request, ma_pdi)
    if bb is None:
        return redirect("incidents:index")
    hdn = bb.hoa_don_nhap
    return render(request, "incidents/chi_tiet.html", {
        "page_title": f"Sự cố {bb.ma_pdi}", "bb": bb, "hdn": hdn, "xe": bb.xe,
        "ho_so": getattr(bb, "ho_so", None), "nhan_tt": nhan_trang_thai(bb.trang_thai_claim),
        "anh": bb.anh_su_co.all(), "lich_su": bb.lich_su.select_related("nguoi_thuc_hien"),
        "co_the_gui": bb.trang_thai_claim not in (DA_GUI_YEU_CAU, DA_XU_LY),
        "co_the_cap_nhat": bb.trang_thai_claim == DA_GUI_YEU_CAU,
    })


# ---------- UC-10.1.3: gửi yêu cầu cho ĐVVC ----------
def _soan_thu(bb, ghi_chu, han):
    hdn, xe = bb.hoa_don_nhap, bb.xe
    tieu_de = f"[Dana Ford] Yêu cầu xử lý sự cố vận chuyển {bb.ma_pdi} - xe {xe.vin}"
    dong = [
        f"Kính gửi {hdn.don_vi_van_chuyen.ten_dvvc},", "",
        "Dana Ford ghi nhận xe sau không đạt yêu cầu kỹ thuật khi bàn giao và đề nghị Quý đơn vị giải trình, "
        "bồi thường thiệt hại:", "",
        f"- Mã sự cố: {bb.ma_pdi}", f"- Số khung VIN: {xe.vin}", f"- Dòng xe: {xe.ten_xe}",
        f"- Màu sắc: {xe.mau_sac or ''}", f"- Đơn hàng nhập: {hdn.ma_hdn}",
        f"- Biển số xe chở: {hdn.bien_so_xe or ''}", f"- Tài xế: {hdn.ten_tai_xe or ''}",
        f"- Loại lỗi: {bb.loai_su_co}", f"- Mô tả lỗi: {bb.mo_ta_chi_tiet or ''}",
        "- Hình ảnh hư hại: xem tệp đính kèm", f"- Hạn phản hồi: {han:%d/%m/%Y}",
    ]
    if ghi_chu:
        dong += ["", f"Ghi chú: {ghi_chu}"]
    dong += ["", "Trân trọng,", "Kho Dana Ford"]
    return tieu_de, "\n".join(dong)


def _ket_noi_mail():
    """Chưa cấu hình SMTP thật -> in email ra cửa sổ lệnh (dùng khi phát triển)."""
    if settings.EMAIL_BACKEND.endswith("smtp.EmailBackend") and not settings.EMAIL_HOST_USER:
        return get_connection("django.core.mail.backends.console.EmailBackend"), True
    return get_connection(), False


@login_required
def gui_yeu_cau(request, ma_pdi):
    bb = _lay_bien_ban(request, ma_pdi)
    if bb is None:
        return redirect("incidents:index")
    if bb.trang_thai_claim in (DA_GUI_YEU_CAU, DA_XU_LY):
        messages.warning(request, "Chỉ gửi được yêu cầu cho sự cố ở trạng thái chưa xử lý.")
        return redirect("incidents:chi_tiet", ma_pdi=ma_pdi)
    dvvc = bb.hoa_don_nhap.don_vi_van_chuyen
    lien_he = DvvcLienHe.objects.filter(dvvc=dvvc).first()
    if lien_he is None:  # E1
        messages.error(request, "Đơn vị vận chuyển chưa được cấu hình địa chỉ email liên hệ. "
                                "Vui lòng cập nhật danh mục ĐVVC (Trang quản trị > Email liên hệ ĐVVC) "
                                "hoặc xuất biên bản giấy thủ công.")
        return redirect("incidents:chi_tiet", ma_pdi=ma_pdi)

    form = GuiYeuCauForm(request.POST or None)
    han = timezone.localdate() + timedelta(days=HAN_PHAN_HOI_NGAY)
    ghi_chu = form.data.get("ghi_chu", "").strip() if request.method == "POST" else ""
    tieu_de, noi_dung = _soan_thu(bb, ghi_chu, han)
    if request.method == "POST" and form.is_valid():
        ket_noi, che_do_thu = _ket_noi_mail()
        mail = EmailMessage(tieu_de, noi_dung, settings.DEFAULT_FROM_EMAIL, [lien_he.email], connection=ket_noi)
        for a in bb.anh_su_co.all():
            try:
                mail.attach(a.tep.name.rsplit("/", 1)[-1], a.tep.read())
            except OSError:
                pass
            finally:
                a.tep.close()
        try:
            mail.send()
        except Exception as e:  # SMTP lỗi: giữ nguyên trạng thái để gửi lại
            messages.error(request, f"Gửi email không thành công: {e}")
            return redirect("incidents:gui_yeu_cau", ma_pdi=ma_pdi)
        with transaction.atomic():
            bb.trang_thai_claim = DA_GUI_YEU_CAU
            bb.save(update_fields=["trang_thai_claim"])
            hs = _ho_so(bb)
            hs.han_phan_hoi = han
            hs.save(update_fields=["han_phan_hoi"])
            _ghi_lich_su(request, bb, "Gửi yêu cầu xử lý cho ĐVVC", f"Gửi tới {lien_he.email}. {ghi_chu}".strip())
        messages.success(request, "Gửi yêu cầu xử lý cho ĐVVC thành công." +
                         (" (Chế độ thử nghiệm: nội dung email được in ra cửa sổ lệnh.)" if che_do_thu else ""))
        return redirect("incidents:chi_tiet", ma_pdi=ma_pdi)
    return render(request, "incidents/gui_yeu_cau.html", {
        "page_title": "Gửi yêu cầu xử lý cho ĐVVC", "bb": bb, "form": form, "email": lien_he.email,
        "tieu_de_mail": tieu_de, "noi_dung_mail": noi_dung, "dvvc": dvvc})


# ---------- UC-10.1.4: cập nhật kết quả ----------
@login_required
def cap_nhat(request, ma_pdi):
    bb = _lay_bien_ban(request, ma_pdi)
    if bb is None:
        return redirect("incidents:index")
    if bb.trang_thai_claim != DA_GUI_YEU_CAU:
        messages.warning(request, "Chỉ cập nhật kết quả cho sự cố ở trạng thái “Đã gửi yêu cầu”.")
        return redirect("incidents:chi_tiet", ma_pdi=ma_pdi)
    form = KetQuaForm(request.POST or None, request.FILES or None,
                      initial={"ngay_xac_nhan": timezone.localdate()})
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        with transaction.atomic():
            hs = _ho_so(bb)
            hs.hinh_thuc_khac_phuc = d["hinh_thuc_khac_phuc"]
            hs.so_tien_boi_thuong = d["so_tien_boi_thuong"]
            hs.ngay_xac_nhan = d["ngay_xac_nhan"]
            if d["bien_ban_thoa_thuan"]:
                hs.bien_ban_thoa_thuan = d["bien_ban_thoa_thuan"]
            hs.save()
            bb.trang_thai_claim = DA_XU_LY
            bb.save(update_fields=["trang_thai_claim"])
            ten = dict(HoSoSuCo.HINH_THUC)[hs.hinh_thuc_khac_phuc]
            tien = f" - {hs.so_tien_boi_thuong:,.0f} đ" if hs.so_tien_boi_thuong is not None else ""
            _ghi_lich_su(request, bb, "Cập nhật kết quả xử lý, đóng sự cố", f"{ten}{tien}")
        messages.success(request, "Đã đóng sự cố. Xe đủ điều kiện nhập kho.")
        return redirect("incidents:chi_tiet", ma_pdi=ma_pdi)
    return render(request, "incidents/cap_nhat.html", {
        "page_title": "Cập nhật kết quả xử lý", "bb": bb, "form": form})


# ---------- Tải tệp (chỉ người đã đăng nhập) ----------
@login_required
def tep_anh(request, pk):
    a = AnhSuCo.objects.filter(pk=pk).first()
    if a is None:
        raise Http404
    return FileResponse(a.tep.open("rb"))


@login_required
def tep_thoa_thuan(request, ma_pdi):
    hs = HoSoSuCo.objects.filter(bien_ban_id=ma_pdi).first()
    if hs is None or not hs.bien_ban_thoa_thuan:
        raise Http404
    return FileResponse(hs.bien_ban_thoa_thuan.open("rb"), as_attachment=True)
