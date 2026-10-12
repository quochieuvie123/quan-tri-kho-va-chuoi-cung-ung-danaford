from django.urls import path
from core.views import PlaceholderView

app_name = "contracts"
urlpatterns = [
    path("", PlaceholderView.as_view(title="Quản lý hợp đồng xe bán"), name="index"),
]