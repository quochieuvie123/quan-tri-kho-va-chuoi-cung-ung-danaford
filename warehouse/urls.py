from django.urls import path
from core.views import PlaceholderView
from .views import (
    DanhSachPhieuXuatView,
    ChiTietPhieuXuatView,
    TraCuuXeKhaDungView,
    LapPhieuXuatKhoActionView,
    DuyetPhieuXuatKhoActionView,
    HuyPhieuXuatKhoActionView,
    XuatFilePhieuXuatView,
)
app_name = "warehouse"
urlpatterns = [
    path("nhap/", PlaceholderView.as_view(title="Quản lý nhập kho"), name="nhap"),
    path("xuat/", PlaceholderView.as_view(title="Quản lý xuất kho"), name="xuat"),
    path("ton-kho/", PlaceholderView.as_view(title="Quản lý tồn kho"), name="ton_kho"),
]

urlpatterns = [
    # 1. Quản lý danh sách & xem chi tiết
    path("xuat-kho/danh-sach/", DanhSachPhieuXuatView.as_view(), name="ds_phieu_xuat"),
    path("xuat-kho/<str:ma_pxk>/chi-tiet/", ChiTietPhieuXuatView.as_view(), name="chi_tiet_phieu_xuat"),

    # 2. Hỗ trợ nghiệp vụ Lập phiếu xuất
    path("xuat-kho/xe-kha-dung/", TraCuuXeKhaDungView.as_view(), name="xe_kha_dung"),
    path("xuat-kho/lap-phieu/", LapPhieuXuatKhoActionView.as_view(), name="lap_phieu_xuat"),

    # 3. Phê duyệt & Cập nhật tồn kho / Hủy phiếu
    path("xuat-kho/<str:ma_pxk>/duyet/", DuyetPhieuXuatKhoActionView.as_view(), name="duyet_phieu_xuat"),
    path("xuat-kho/<str:ma_pxk>/huy/", HuyPhieuXuatKhoActionView.as_view(), name="huy_phieu_xuat"),

    # 4. Xuất file / In ấn
    path("xuat-kho/<str:ma_pxk>/xuat-file/", XuatFilePhieuXuatView.as_view(), name="xuat_file_phieu"),
]
