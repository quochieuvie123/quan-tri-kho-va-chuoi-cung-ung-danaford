from django.contrib import admin
from .models import SuKienNoiBat, ThongBaoHoatDong


@admin.register(SuKienNoiBat)
class SuKienNoiBatAdmin(admin.ModelAdmin):
    list_display = ("tieu_de", "loai_su_kien", "dia_diem", "thoi_gian_dien_ra", "nguoi_tao", "is_active")
    list_filter = ("loai_su_kien", "is_active", "thoi_gian_dien_ra")
    search_fields = ("tieu_de", "noi_dung", "dia_diem")
    date_hierarchy = "thoi_gian_dien_ra"


@admin.register(ThongBaoHoatDong)
class ThongBaoHoatDongAdmin(admin.ModelAdmin):
    list_display = ("ten_nhan_vien", "chuc_vu", "hanh_dong", "module", "loai", "thoi_gian", "is_active")
    list_filter = ("module", "loai", "is_active", "thoi_gian")
    search_fields = ("ten_nhan_vien", "hanh_dong", "chi_tiet")
    date_hierarchy = "thoi_gian"
