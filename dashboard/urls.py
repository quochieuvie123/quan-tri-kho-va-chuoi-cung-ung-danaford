from django.urls import path
from core.views import PlaceholderView

app_name = "dashboard"
urlpatterns = [
    path("", PlaceholderView.as_view(title="Thống kê và báo cáo"), name="index"),
]