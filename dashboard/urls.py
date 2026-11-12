from django.urls import include, path
from reports import views as reports_views
from . import views

app_name = "dashboard"

urlpatterns = [
    # Trang chủ chính thức của hệ thống (/)
    path("", views.trang_chu, name="home"),
    path("doi-kho/", views.doi_kho_hien_tai, name="doi_kho"),

    # Phân hệ Thống kê và Báo cáo (/thong-ke-bao-cao/)
    path("thong-ke-bao-cao/", reports_views.tong_quan, name="index"),
    path("thong-ke-bao-cao/bao-cao/", include("reports.urls")),

    # Thao tác Sự kiện nổi bật trực tiếp trên Web
    path("su-kien/them/", views.them_su_kien, name="them_su_kien"),
    path("su-kien/<int:event_id>/xoa/", views.xoa_su_kien, name="xoa_su_kien"),

    # Thao tác Thông báo cập nhật trực tiếp trên Web
    path("thong-bao/them/", views.them_thong_bao, name="them_thong_bao"),
    path("thong-bao/<int:notif_id>/xoa/", views.xoa_thong_bao, name="xoa_thong_bao"),
]
