from django.contrib import admin

from .models import CanhBao, NguongCanhBao


@admin.register(NguongCanhBao)
class NguongCanhBaoAdmin(admin.ModelAdmin):
    list_display = (
        "ten_xe",
        "mau_sac",
        "ton_toi_thieu",
        "dang_theo_doi",
    )

    list_filter = ("dang_theo_doi",)
    search_fields = ("ten_xe", "mau_sac")

    readonly_fields = (
        "ten_xe",
        "mau_sac",
        "ton_toi_thieu",
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(CanhBao)
class CanhBaoAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "loai",
        "kho_hien_thi",
        "nguong",
        "xe",
        "con_hieu_luc",
        "trang_thai",
        "ngay_phat_sinh",
    )

    list_filter = (
        "loai",
        "kho",
        "cac_kho",
        "con_hieu_luc",
        "trang_thai",
    )

    search_fields = (
        "xe__vin",
        "nguong__ten_xe",
        "nguong__mau_sac",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
