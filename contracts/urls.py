from django.urls import path
from . import views

app_name = 'contracts'
urlpatterns = [
    path('<str:ma_hd>/xe-phu-hop/<str:vin>/', views.suggested_vehicle_detail, name='suggested_vehicle_detail'),
    path('', views.index, name='index'),
    path('<str:ma_hd>/xe-phu-hop/', views.suitable_vehicles, name='xe_phu_hop'),
    path('<str:ma_hd>/', views.detail, name='detail'),
]
