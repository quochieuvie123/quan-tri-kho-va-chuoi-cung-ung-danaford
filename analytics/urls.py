from django.urls import path
from core.views import PlaceholderView

app_name = "analytics"
urlpatterns = [
    path("", PlaceholderView.as_view(title="Dự báo nhu cầu và đề xuất nhập"), name="index"),
]