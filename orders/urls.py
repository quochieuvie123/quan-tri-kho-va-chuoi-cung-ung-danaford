from django.urls import path
from core.views import PlaceholderView

app_name = "orders"
urlpatterns = [
    path("", PlaceholderView.as_view(title="Quản lý đặt xe"), name="index"),
]