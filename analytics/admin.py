from django.contrib import admin

from .models import ChiTieuPhanBo, DongDuBao, NhatKyXuatFile, PhienDuBao


@admin.register(ChiTieuPhanBo)
class ChiTieuPhanBoAdmin(admin.ModelAdmin):
    list_display = ("nam", "thang", "ten_xe", "so_luong")
    list_filter = ("nam", "thang")
    search_fields = ("ten_xe",)


admin.site.register([PhienDuBao, DongDuBao, NhatKyXuatFile])
