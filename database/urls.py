from django.urls import path
from . import views

app_name = "database"

urlpatterns = [
    path("suppliers/", views.danh_sach_nha_cung_cap, name="nha_cung_cap"),
]
