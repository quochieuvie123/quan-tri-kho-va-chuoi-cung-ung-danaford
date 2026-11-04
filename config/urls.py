from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("accounts.urls")),
    path("phan-bo/", include("orders.urls")),
    path("luu-chuyen/", include("transfers.urls")),
    path("hop-dong/", include("contracts.urls")),
    path("kho/", include("warehouse.urls")),
    path("du-bao/", include("analytics.urls")),
    path("su-co/", include("incidents.urls")),
    path("canh-bao/", include("alerts.urls")),
    path("", include("dashboard.urls")),   # đặt cuối, là trang chủ "/"
]