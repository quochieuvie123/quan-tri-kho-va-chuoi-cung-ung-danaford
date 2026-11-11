from django import forms

from database.models import Kho
from .models import CanhBao

class LuaChonKho(forms.ModelChoiceField):
    def label_from_instance(self, kho):
        ten_chi_nhanh = kho.chi_nhanh.ten_cn

        ten_khu_vuc = ten_chi_nhanh.replace(
            "Dana Ford ",
            "",
            1,
        ).strip()

        return f"Kho {ten_khu_vuc} ({kho.ma_kho})"

class BoLocCanhBaoForm(forms.Form):
    kho = LuaChonKho(
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
        label="Dòng xe",
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

        self.fields["kho"].queryset = (
            danh_sach_kho.select_related("chi_nhanh")
        )

        self.fields["ten_xe"].widget.attrs["placeholder"] = (
            "Ví dụ: Ranger, Everest..."
        )

        self.fields["mau_sac"].widget.attrs["placeholder"] = (
            "Ví dụ: Trắng, Đen, Đỏ..."
        )

class CapNhatTrangThaiForm(forms.Form):
    trang_thai = forms.ChoiceField(label="Trạng thái mới")

    def __init__(self, *args, canh_bao, **kwargs):
        super().__init__(*args, **kwargs)

        if canh_bao.trang_thai == CanhBao.TrangThai.CHUA_XU_LY:
            trang_thai_duoc_chon = [
                CanhBao.TrangThai.DANG_XU_LY,
                CanhBao.TrangThai.DA_XU_LY,
            ]
        elif canh_bao.trang_thai == CanhBao.TrangThai.DANG_XU_LY:
            trang_thai_duoc_chon = [
                CanhBao.TrangThai.DA_XU_LY,
            ]
        else:
            trang_thai_duoc_chon = []

        danh_sach_lua_chon = []

        for gia_tri, nhan in CanhBao.TrangThai.choices:
            if gia_tri in trang_thai_duoc_chon:
                danh_sach_lua_chon.append((gia_tri, nhan))

        self.fields["trang_thai"].choices = danh_sach_lua_chon
