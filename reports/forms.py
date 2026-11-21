from datetime import date
import re
from django import forms
from django.utils import timezone

from database.models import BienBanPDI, HopDong, Kho, PhieuXuatKho


MAX_KHOANG_BAO_CAO_THANG = 120
THANG_PATTERN = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")


def lay_danh_sach_thang_bao_cao():
    """Tổng hợp danh sách (value, label) các tháng có dữ liệu thực tế kèm tháng hiện tại."""
    from alerts.models import CanhBao
    from analytics.models import HOAN_TAT, PhienDuBao
    from orders.models import VehicleRequest
    from transfers.models import LenhLuuChuyen
    from warehouse.models import PhieuNhapKho

    cac_moc = {timezone.localdate().replace(day=1)}
    sources = (
        (PhieuNhapKho.objects, "ngay_nhap"),
        (PhieuXuatKho.objects, "ngay_lap"),
        (HopDong.objects, "ngay_ky"),
        (BienBanPDI.objects, "ngay_ghi_nhan"),
        (VehicleRequest.objects, "created_at"),
        (LenhLuuChuyen.objects, "ngay_lap"),
        (CanhBao.objects, "ngay_phat_sinh"),
    )
    for qs, field_name in sources:
        try:
            for d in qs.filter(**{f"{field_name}__isnull": False}).dates(field_name, "month"):
                cac_moc.add(d.replace(day=1))
        except Exception:
            continue

    try:
        for nam, thang in PhienDuBao.objects.filter(trang_thai=HOAN_TAT).values_list("nam", "thang").distinct():
            if 1 <= thang <= 12:
                cac_moc.add(date(nam, thang, 1))
    except Exception:
        pass

    sorted_months = sorted(cac_moc, reverse=True)
    return [(d.strftime("%Y-%m"), f"Tháng {d.month:02d}/{d.year}") for d in sorted_months]


class LuaChonKho(forms.ModelChoiceField):
    def label_from_instance(self, kho):
        ten_chi_nhanh = kho.chi_nhanh.ten_cn

        ten_khu_vuc = ten_chi_nhanh.replace(
            "Dana Ford ",
            "",
            1,
        ).strip()

        return f"Kho {ten_khu_vuc} ({kho.ma_kho})"

class BoLocBaoCaoForm(forms.Form):
    thang = forms.MultipleChoiceField(
        label="Tháng / Năm",
        required=False,
        choices=(),
        widget=forms.CheckboxSelectMultiple,
    )

    kho = LuaChonKho(
        label="Kho",
        queryset=Kho.objects.none(),
        required=False,
        empty_label="Tất cả kho được phép xem",
    )

    ten_xe = forms.CharField(
        label="Tên xe",
        max_length=255,
        required=False,
    )

    tu_ngay = forms.DateField(
        label="Từ ngày",
        required=False,
        input_formats=["%Y-%m-%d"],
        widget=forms.DateInput(
            format="%Y-%m-%d",
            attrs={"type": "date"},
        ),
    )

    den_ngay = forms.DateField(
        label="Đến ngày",
        required=False,
        input_formats=["%Y-%m-%d"],
        widget=forms.DateInput(
            format="%Y-%m-%d",
            attrs={"type": "date"},
        ),
    )

    def __init__(self, *args, danh_sach_kho, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["kho"].queryset = (
            danh_sach_kho.select_related("chi_nhanh")
        )

        choices = lay_danh_sach_thang_bao_cao()
        choice_keys = {k for k, _ in choices}
        if self.is_bound:
            raw_months = self.data.getlist("thang") if hasattr(self.data, "getlist") else (self.data.get("thang") or [])
            if isinstance(raw_months, str):
                raw_months = [raw_months]
            for val in raw_months:
                m = THANG_PATTERN.match(str(val).strip())
                if m and val not in choice_keys:
                    y_v, m_v = int(m.group(1)), int(m.group(2))
                    choices.append((val, f"Tháng {m_v:02d}/{y_v}"))
                    choice_keys.add(val)
        choices.sort(key=lambda item: item[0], reverse=True)
        self.fields["thang"].choices = choices

        self.fields["ten_xe"].widget.attrs["placeholder"] = (
            "Ví dụ: Ranger, Everest..."
        )

    def clean(self):
        du_lieu = super().clean()

        cac_thang_str = du_lieu.get("thang") or []
        cac_thang = []
        seen = set()
        for val in cac_thang_str:
            m = THANG_PATTERN.match(str(val).strip())
            if m:
                d = date(int(m.group(1)), int(m.group(2)), 1)
                if d not in seen:
                    seen.add(d)
                    cac_thang.append(d)
        cac_thang.sort()
        du_lieu["cac_thang"] = cac_thang

        if len(cac_thang) > MAX_KHOANG_BAO_CAO_THANG:
            self.add_error(
                "thang",
                "Số tháng báo cáo không được vượt quá 120 tháng.",
            )

        if cac_thang:
            du_lieu["tu_ngay"] = None
            du_lieu["den_ngay"] = None
            return du_lieu

        tu_ngay = du_lieu.get("tu_ngay")
        den_ngay = du_lieu.get("den_ngay")

        if tu_ngay and den_ngay:
            if tu_ngay > den_ngay:
                self.add_error(
                    "den_ngay",
                    "Đến ngày phải bằng hoặc sau Từ ngày.",
                )
            else:
                so_thang = (
                    (den_ngay.year - tu_ngay.year) * 12
                    + den_ngay.month
                    - tu_ngay.month
                    + 1
                )

                if so_thang > MAX_KHOANG_BAO_CAO_THANG:
                    self.add_error(
                        "den_ngay",
                        "Khoảng thời gian báo cáo không được vượt quá 120 tháng.",
                    )

        return du_lieu
