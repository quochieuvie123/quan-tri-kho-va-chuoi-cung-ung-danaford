from django.urls import path

from . import views

app_name = "alerts"

urlpatterns = [
    path("", views.danh_sach_canh_bao, name="index"),
    path(
        "<int:pk>/",
        views.chi_tiet_canh_bao,
        name="chi_tiet",
    ),
]
