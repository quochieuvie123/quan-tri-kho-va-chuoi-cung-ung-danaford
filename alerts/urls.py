from django.urls import path

from . import views

app_name = "alerts"

urlpatterns = [
    path("", views.danh_sach_canh_bao, name="index"),
    path("xuat-het-hang/", views.xuat_xe_het_hang, name="xuat_het_hang"),
    path(
        "<int:pk>/",
        views.chi_tiet_canh_bao,
        name="chi_tiet",
    ),
]
