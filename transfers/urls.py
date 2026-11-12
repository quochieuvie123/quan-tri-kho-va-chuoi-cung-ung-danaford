from django.urls import path
from . import views

app_name = "transfers"

urlpatterns = [
    path("", views.danh_sach_ton_kho, name="index"),
    path("chi-tiet-xe/<int:id>/", views.chi_tiet_xe, name="chi_tiet_xe"),
    path("xoa-xe-da-chon/<int:index>/", views.xoa_xe_da_chon, name="xoa_xe_da_chon"),
    path("tao-lenh/", views.tao_lenh_luu_chuyen, name="tao_lenh"),
    path("xac-nhan-lenh/", views.xac_nhan_lenh_luu_chuyen, name="xac_nhan_lenh"),
    path("danh-sach-lenh/", views.danh_sach_lenh_luu_chuyen, name="danh_sach_lenh"),
    path("danh-sach-lenh/<int:id>/", views.chi_tiet_lenh_luu_chuyen, name="chi_tiet_lenh"),
    path("lenh/<int:id>/", views.chi_tiet_lenh_luu_chuyen, name="chi_tiet"),
    path("danh-sach-lenh/<int:id>/chinh-sua/", views.chinh_sua_lenh_luu_chuyen, name="chinh_sua_lenh"),
    path("danh-sach-lenh/<int:id>/gui/", views.gui_lenh_luu_chuyen, name="gui_lenh"),
    path("danh-sach-lenh/<int:id>/duyet/", views.phe_duyet_lenh, name="phe_duyet_lenh"),
    path("danh-sach-lenh/<int:id>/tu-choi/", views.tu_choi_lenh, name="tu_choi_lenh"),
    path("danh-sach-lenh/<int:id>/huy/", views.huy_lenh, name="huy_lenh"),
    path("danh-sach-lenh/<int:id>/xuat-kho-nguon/", views.xuat_kho_nguon, name="xuat_kho_nguon"),
    path("danh-sach-lenh/<int:id>/den-da-nang/", views.xac_nhan_den_da_nang, name="xac_nhan_den_da_nang"),
    path("danh-sach-lenh/<int:id>/cap-nhat-trang-thai/", views.cap_nhat_trang_thai_lenh, name="cap_nhat_trang_thai"),
]
