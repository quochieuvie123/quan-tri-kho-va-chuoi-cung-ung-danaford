from django.urls import path
from . import views
from django.views.generic import RedirectView
app_name = "orders"
urlpatterns = [
    path("",RedirectView.as_view(pattern_name="orders:allocation_list",permanent=False),name="index"),
    path("danh-sach/", views.allocation_list, name="allocation_list"),
path(
    "de-xuat/",
    views.danh_sach_de_xuat,
    name="proposal_list"
),

    path(
        "dat-xe/",
        views.dat_xe,
        name="vehicle_orders"
    ),
    path(
    "dat-xe/chi-tiet/<int:id>/",
    views.chi_tiet_xe,
    name="chi_tiet_xe"
),
path(
    "dat-xe/xoa/<int:xe_id>/",
    views.xoa_xe_da_chon,
    name="xoa_xe_da_chon"
),
path(
    "dat-xe/lap-phieu/",
    views.lap_phieu_yeu_cau,
    name="lap_phieu_yeu_cau"
),
path(
    "phieu-yeu-cau/<int:id>/gui/",
    views.gui_phieu_yeu_cau,
    name="gui_phieu_yeu_cau",
),
path(
    "phieu-yeu-cau/<int:id>/",
    views.phieu_yeu_cau,
    name="phieu_yeu_cau"
),
path(
    "danh-sach-yeu-cau/",
    views.danh_sach_yeu_cau,
    name="danh_sach_yeu_cau"
),

path(
    "phieu-yeu-cau/<int:id>/xac-nhan/",
    views.xac_nhan_phieu,
    name="xac_nhan_phieu"
),
path(
    "de-xuat/<int:id>/",
    views.chi_tiet_de_xuat,
    name="proposal_detail"
),
]
