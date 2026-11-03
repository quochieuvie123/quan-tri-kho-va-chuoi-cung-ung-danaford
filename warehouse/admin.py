from django.contrib import admin
from database.models import PhieuXuatKho, LichSuXuatKho

@admin.register(PhieuXuatKho)
class PhieuXuatKhoAdmin(admin.ModelAdmin):
    list_display = ("ma_pxk", "kho", "trang_thai", "ngay_lap", "nguoi_lap", "nguoi_duyet")
    list_filter = ("trang_thai", "kho")
    search_fields = ("ma_pxk", "nguoi_nhan")

@admin.register(LichSuXuatKho)
class LichSuXuatKhoAdmin(admin.ModelAdmin):
    list_display = ("phieu_xuat", "xe", "kho", "hanh_dong", "nguoi_thuc_hien", "thoi_gian")
    list_filter = ("hanh_dong", "kho")