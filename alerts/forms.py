from django import forms

from database.models import Kho
from .models import CanhBao


class BoLocCanhBaoForm(forms.Form):
    kho = forms.ModelChoiceField(
        label="Kho",
        queryset=Kho.objects.none(),
        required=False,
        empty_label="Tất cả kho được phép xem",
    )
    loai = forms.ChoiceField(
        label="Loại cảnh báo",
        choices=[("", "Tất cả loại cảnh báo")] + list(CanhBao.Loai.choices),
        required=False,
    )
    ten_xe = forms.CharField(
        label="Tên xe",
        required=False,
        max_length=255,
    )
    mau_sac = forms.CharField(
        label="Màu sắc",
        required=False,
        max_length=50,
    )

    def __init__(self, *args, danh_sach_kho, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["kho"].queryset = danh_sach_kho


class CapNhatTrangThaiForm(forms.Form):
    trang_thai = forms.ChoiceField(label="Trạng thái mới")

    def __init__(self, *args, canh_bao, **kwargs):
        super().__init__(*args, **kwargs)

        chuyen_doi = {
            CanhBao.TrangThai.CHUA_XU_LY: [
                CanhBao.TrangThai.DANG_XU_LY,
                CanhBao.TrangThai.DA_XU_LY,
            ],
            CanhBao.TrangThai.DANG_XU_LY: [
                CanhBao.TrangThai.DA_XU_LY,
            ],
            CanhBao.TrangThai.DA_XU_LY: [],
        }

        hop_le = chuyen_doi.get(canh_bao.trang_thai, [])

        self.fields["trang_thai"].choices = [
            (gia_tri, nhan)
            for gia_tri, nhan in CanhBao.TrangThai.choices
            if gia_tri in hop_le
        ]
