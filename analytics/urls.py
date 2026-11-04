from django.urls import path

from . import views

app_name = "analytics"
urlpatterns = [
    path("", views.index, name="index"),
    path("phan-tich/", views.phan_tich, name="phan_tich"),
    path("phien/<int:pk>/", views.danh_sach_nhu_cau, name="phien"),
    path("phien/<int:pk>/dieu-chinh/", views.dieu_chinh, name="dieu_chinh"),
    path("phien/<int:pk>/xuat/", views.xuat_danh_sach, name="xuat"),
]
