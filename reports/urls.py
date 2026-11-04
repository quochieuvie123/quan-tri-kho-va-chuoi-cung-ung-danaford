from django.urls import path

from . import views


app_name = "reports"

urlpatterns = [
    path(
        "xuat-excel/",
        views.xuat_excel,
        name="xuat_excel",
    ),
    path(
        "<str:loai>/",
        views.chi_tiet,
        name="chi_tiet",
    ),
]
