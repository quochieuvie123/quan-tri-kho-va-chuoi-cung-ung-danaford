from django.urls import include, path
from django.views.generic import RedirectView

from reports import views


app_name = "dashboard"

urlpatterns = [
    path(
        "",
        RedirectView.as_view(
            pattern_name="dashboard:index",
            permanent=False,
        ),
        name="home",
    ),
    path(
        "thong-ke-bao-cao/",
        views.tong_quan,
        name="index",
    ),
    path(
        "thong-ke-bao-cao/bao-cao/",
        include("reports.urls"),
    ),
]
