from django import forms

from database.models import Kho


MAX_KHOANG_BAO_CAO_THANG = 120

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

        self.fields["ten_xe"].widget.attrs["placeholder"] = (
            "Ví dụ: Ranger, Everest..."
        )

    def clean(self):
        du_lieu = super().clean()

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
