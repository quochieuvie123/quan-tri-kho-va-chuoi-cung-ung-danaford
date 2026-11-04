from django.urls import path
from core.views import PlaceholderView
from . import views

app_name = "warehouse"
urlpatterns = [
    path("hoa-don-nhap/", views.nhap, name="invoice_list"),
    path("phieu-nhap/<int:pk>/lich-su/", views.receipt_history, name="receipt_history"),
    path("xe-co-the-nhap/", views.eligible_vehicles, name="eligible_vehicles"),
    path("pdi/<int:pk>/", views.pdi_detail, name="pdi_detail"),
    path("phieu-nhap/", views.receipt_list, name="receipt_list"),
    path("phieu-nhap/tuy-chon/", views.receipt_options, name="receipt_options"),
    path("phieu-nhap/lap-moi/", views.receipt_create_page, name="receipt_create_page"),
    path("phieu-nhap/tao/", views.receipt_action, {"action": "tao"}, name="receipt_create"),
    path("phieu-nhap/<int:pk>/thao-tac/<str:action>/", views.receipt_web_action, name="receipt_web_action"),
    path("phieu-nhap/<int:pk>/", views.receipt_detail, name="receipt_detail"),
    path("phieu-nhap/<int:pk>/<str:action>/", views.receipt_action, name="receipt_action"),
    # Đường dẫn thân thiện cho giao diện; phải đặt trước nhap/<ma_hdn>/
    # để từ "tao" không bị hiểu nhầm là mã hóa đơn nhập.
    path("nhap/tao/", views.receipt_create_page, name="receipt_create_shortcut"),
    path("nhap/<str:ma_hdn>/", views.nhap_detail, name="nhap_detail"),
    path("nhap/", views.receipt_list, name="nhap"),
    path("xuat/", PlaceholderView.as_view(title="Quản lý xuất kho"), name="xuat"),
    path("ton-kho/", PlaceholderView.as_view(title="Quản lý tồn kho"), name="ton_kho"),
]
