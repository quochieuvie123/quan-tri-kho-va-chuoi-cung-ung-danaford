from django.urls import path

from . import views

app_name = "incidents"
urlpatterns = [
    path("", views.danh_sach, name="index"),
    path("ghi-nhan/", views.ghi_nhan, name="ghi_nhan"),
    path("xuat-bao-cao/", views.xuat_bao_cao, name="xuat_bao_cao"),
    path("anh/<int:pk>/", views.tep_anh, name="tep_anh"),
    path("<str:ma_pdi>/", views.chi_tiet, name="chi_tiet"),
    path("<str:ma_pdi>/gui-yeu-cau/", views.gui_yeu_cau, name="gui_yeu_cau"),
    path("<str:ma_pdi>/cap-nhat/", views.cap_nhat, name="cap_nhat"),
    path("<str:ma_pdi>/cap-nhat-anh/", views.cap_nhat_anh, name="cap_nhat_anh"),
    path("<str:ma_pdi>/thoa-thuan/", views.tep_thoa_thuan, name="tep_thoa_thuan"),
]
