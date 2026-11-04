from django import forms

from database.models import Kho


class BoLocBaoCaoForm(forms.Form):
    kho = forms.ModelChoiceField(
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
        self.fields["kho"].queryset = danh_sach_kho

    def clean(self):
        data = super().clean()

        start = data.get("tu_ngay")
        end = data.get("den_ngay")

        if start and end and start > end:
            self.add_error(
                "den_ngay",
                "Đến ngày phải bằng hoặc sau Từ ngày.",
            )

        return data