from django.urls import path
from django.views.generic import RedirectView
from core.views import PlaceholderView
from .views import (
    DanhSachPhieuXuatView,
    ChiTietPhieuXuatView,
    TraCuuXeKhaDungView,
    LapPhieuXuatKhoActionView,
    DuyetPhieuXuatKhoActionView,
    HuyPhieuXuatKhoActionView,
    XuatFilePhieuXuatView,
    DanhSachTonKhoView,
    ChiTietXeTonKhoView,
    TaoPhieuKiemKeView,
    GhiNhanKiemDemView,
    XuLyChenhLechView,
    DuyetPhieuKiemKeView,
    LichSuKiemKeView,

)
app_name = "warehouse"

urlpatterns = [
    # 0. Tên URL mà menu sidebar (core/context_processors.py) đang gọi - KHÔNG xóa
    path("nhap/", PlaceholderView.as_view(title="Quản lý nhập kho"), name="nhap"),
    path("xuat/", RedirectView.as_view(pattern_name="warehouse:ds_phieu_xuat"), name="xuat"),
    path("ton-kho/", RedirectView.as_view(pattern_name="warehouse:ds_ton_kho"), name="ton_kho"),

    # 1. Quản lý Xuất kho
    path("xuat-kho/danh-sach/", DanhSachPhieuXuatView.as_view(), name="ds_phieu_xuat"),
    path("xuat-kho/<str:ma_pxk>/chi-tiet/", ChiTietPhieuXuatView.as_view(), name="chi_tiet_phieu_xuat"),
    path("xuat-kho/xe-kha-dung/", TraCuuXeKhaDungView.as_view(), name="xe_kha_dung"),
    path("xuat-kho/lap-phieu/", LapPhieuXuatKhoActionView.as_view(), name="lap_phieu_xuat"),
    path("xuat-kho/<str:ma_pxk>/duyet/", DuyetPhieuXuatKhoActionView.as_view(), name="duyet_phieu_xuat"),
    path("xuat-kho/<str:ma_pxk>/huy/", HuyPhieuXuatKhoActionView.as_view(), name="huy_phieu_xuat"),
    path("xuat-kho/<str:ma_pxk>/xuat-file/", XuatFilePhieuXuatView.as_view(), name="xuat_file_phieu"),

    # 2. Quản lý Tồn kho (UC-TK-01, 02, 03)
    path("ton-kho/danh-sach/", DanhSachTonKhoView.as_view(), name="ds_ton_kho"),
    path("ton-kho/<str:vin>/chi-tiet/", ChiTietXeTonKhoView.as_view(), name="chi_tiet_xe_ton"),

    # 3. Quản lý Kiểm kê (UC-KK-01 -> 08)
    path("kiem-ke/tao-phieu/", TaoPhieuKiemKeView.as_view(), name="tao_phieu_kiem_ke"),
    path("kiem-ke/<str:ma_pkk>/kiem-dem/", GhiNhanKiemDemView.as_view(), name="ghi_nhan_kiem_dem"),
    path("kiem-ke/<str:ma_pkk>/chenh-lech/", XuLyChenhLechView.as_view(), name="xu_ly_chenh_lech"),
    path("kiem-ke/<str:ma_pkk>/duyet/", DuyetPhieuKiemKeView.as_view(), name="duyet_kiem_ke"),
    path("kiem-ke/lich-su/", LichSuKiemKeView.as_view(), name="lich_su_kiem_ke"),
]