from django import forms
from django.core.validators import FileExtensionValidator

from database.models import ChiTietNhap, DonViVanChuyen, HoaDonNhap, NhanVien, Xe

from .models import HoSoSuCo, LOAI_SU_CO, PHAM_VI_LOI_ANH, PHAM_VI_TAI_LIEU

CSS = {"class": "inp"}


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleFileInput(attrs={"accept": "image/*", "multiple": True}))
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        run = super().clean
        if isinstance(data, (list, tuple)):
            return [run(d, initial) for d in data if d]
        return [run(data, initial)] if data else []


class GhiNhanForm(forms.Form):
    """UC-10.1.1 Ghi nhận sự cố vận chuyển."""
    hoa_don_nhap = forms.ModelChoiceField(
        HoaDonNhap.objects.order_by("-ngay_nhap"), label="Lô hàng nhập (hóa đơn nhập)",
        widget=forms.Select(attrs=CSS))
    xe = forms.ModelChoiceField(Xe.objects.order_by("vin"), label="Xe (số khung VIN)",
                                widget=forms.Select(attrs=CSS))
    nhan_vien = forms.ModelChoiceField(NhanVien.objects.order_by("ma_nv"), label="Nhân viên ghi nhận",
                                       required=False, widget=forms.Select(attrs=CSS))
    loai_su_co = forms.ChoiceField(label="Loại sự cố", choices=[(x, x) for x in LOAI_SU_CO],
                                   widget=forms.Select(attrs=CSS))
    mo_ta_chi_tiet = forms.CharField(label="Mô tả chi tiết lỗi", required=False,
                                     widget=forms.Textarea(attrs={**CSS, "rows": 4}))
    anh = MultipleFileField(label="Hình ảnh minh chứng", required=False)

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.nv_tai_khoan = getattr(user, "nhan_vien", None)
        if self.nv_tai_khoan:
            del self.fields["nhan_vien"]
        else:
            self.fields["nhan_vien"].required = True
            self.fields["nhan_vien"].help_text = "Tài khoản này chưa liên kết nhân viên, hãy chọn người ghi nhận."

    def clean(self):
        d = super().clean()
        # E1: bỏ trống mô tả hoặc không có ảnh
        if self.errors:
            return d
        anh = d.get("anh") or []
        if not (d.get("mo_ta_chi_tiet") or "").strip() or not anh:
            raise forms.ValidationError("Vui lòng nhập đầy đủ chi tiết lỗi và đính kèm hình ảnh PDI")
        kiem_tra = FileExtensionValidator(PHAM_VI_LOI_ANH)
        for f in anh:
            kiem_tra(f)
        hdn, xe = d.get("hoa_don_nhap"), d.get("xe")
        if hdn and xe and not ChiTietNhap.objects.filter(hoa_don_nhap=hdn, xe=xe).exists():
            raise forms.ValidationError("Xe này không thuộc lô hàng nhập đã chọn.")
        return d


class GuiYeuCauForm(forms.Form):
    """UC-10.1.3: ghi chú đặc biệt trước khi gửi."""
    ghi_chu = forms.CharField(label="Ghi chú đặc biệt (nếu có)", required=False,
                              widget=forms.Textarea(attrs={**CSS, "rows": 3}))


class KetQuaForm(forms.Form):
    """UC-10.1.4 Cập nhật kết quả xử lý."""
    hinh_thuc_khac_phuc = forms.ChoiceField(label="Hình thức khắc phục", choices=HoSoSuCo.HINH_THUC,
                                            widget=forms.Select(attrs=CSS))
    so_tien_boi_thuong = forms.DecimalField(label="Số tiền bồi thường (VNĐ)", required=False,
                                            max_digits=18, decimal_places=2,
                                            widget=forms.NumberInput(attrs={**CSS, "step": "any"}))
    ngay_xac_nhan = forms.DateField(label="Ngày xác nhận",
                                    widget=forms.DateInput(attrs={**CSS, "type": "date"}))
    bien_ban_thoa_thuan = forms.FileField(
        label="Biên bản thỏa thuận (đính kèm)", required=False,
        validators=[FileExtensionValidator(PHAM_VI_TAI_LIEU)])

    def clean(self):
        d = super().clean()
        if self.errors:
            return d
        if d["hinh_thuc_khac_phuc"] in ("TIEN", "GIAM_TRU"):
            tien = d.get("so_tien_boi_thuong")
            # E1: số tiền âm / trống chứng từ khi bồi thường tài chính
            if tien is None or tien < 0 or not d.get("bien_ban_thoa_thuan"):
                raise forms.ValidationError(
                    "Số tiền bồi thường phải là số không âm và phải đính kèm chứng từ (biên bản thỏa thuận) "
                    "khi chọn hình thức bồi thường tài chính.")
        else:
            d["so_tien_boi_thuong"] = None
        return d


class LocForm(forms.Form):
    """UC-10.2.2 Lọc / tìm kiếm."""
    q = forms.CharField(required=False, label="Từ khóa",
                        widget=forms.TextInput(attrs={**CSS, "placeholder": "Mã VIN, biển số xe chở, mã đơn hàng..."}))
    tu_ngay = forms.DateField(required=False, label="Từ ngày", widget=forms.DateInput(attrs={**CSS, "type": "date"}))
    den_ngay = forms.DateField(required=False, label="Đến ngày", widget=forms.DateInput(attrs={**CSS, "type": "date"}))
    dvvc = forms.ModelChoiceField(DonViVanChuyen.objects.order_by("ten_dvvc"), required=False,
                                  empty_label="Tất cả ĐVVC", label="Đơn vị vận chuyển",
                                  widget=forms.Select(attrs=CSS))
    trang_thai = forms.ChoiceField(required=False, label="Trạng thái", widget=forms.Select(attrs=CSS),
                                   choices=[("", "Tất cả"), ("dang_xu_ly", "Đang xử lý"), ("da_dong", "Đã đóng")])
