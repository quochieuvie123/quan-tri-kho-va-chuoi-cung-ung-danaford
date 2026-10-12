from django.urls import path
from core.views import PlaceholderView

app_name = "incidents"
urlpatterns = [
    path("", PlaceholderView.as_view(title="Quản lý sự cố vận chuyến"), name="index"),
]