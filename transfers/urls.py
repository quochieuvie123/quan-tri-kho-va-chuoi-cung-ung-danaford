from django.urls import path
from core.views import PlaceholderView

app_name = "transfers"
urlpatterns = [
    path("", PlaceholderView.as_view(title="Quản lý luân chuyển"), name="index"),
]