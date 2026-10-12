from django.urls import path
from core.views import PlaceholderView

app_name = "warehouse"
urlpatterns = [
    path("nhap/", PlaceholderView.as_view(title="Quản lý nhập kho"), name="nhap"),
    path("xuat/", PlaceholderView.as_view(title="Quản lý xuất kho"), name="xuat"),
    path("ton-kho/", PlaceholderView.as_view(title="Quản lý tồn kho"), name="ton_kho"),
]