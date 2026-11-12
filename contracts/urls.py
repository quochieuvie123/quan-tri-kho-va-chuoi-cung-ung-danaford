from django.urls import path
from . import views

app_name = 'contracts'
urlpatterns = [
    path('import-excel/', views.import_contracts_excel, name='import_contracts_excel'),
    path('<str:ma_hd>/cho-phan-bo/', views.wait_allocation, name='wait_allocation'),
    path('<str:ma_hd>/cap-nhat-ngay-giao/', views.cap_nhat_ngay_giao, name='cap_nhat_ngay_giao'),
    path('<str:ma_hd>/xe-phu-hop/<str:vin>/chon/', views.choose_suggested_vehicle, name='choose_suggested_vehicle'),
    path('<str:ma_hd>/xe-phu-hop/<str:vin>/', views.suggested_vehicle_detail, name='suggested_vehicle_detail'),
    path('', views.index, name='index'),
    path('<str:ma_hd>/xe-phu-hop/', views.suitable_vehicles, name='xe_phu_hop'),
    path('<str:ma_hd>/hoan-tat/', views.hoan_tat_hop_dong, name='hoan_tat'),
    path('<str:ma_hd>/', views.detail, name='detail'),
]
