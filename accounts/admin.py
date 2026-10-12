from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ("username", "get_full_name", "nhan_vien", "get_roles", "is_active")
    list_filter = ("is_active", "groups")
    search_fields = ("username", "first_name", "last_name", "nhan_vien__ten_nv")
    autocomplete_fields = ("nhan_vien",)

    fieldsets = UserAdmin.fieldsets + (("Liên kết nhân viên", {"fields": ("nhan_vien",)}),)
    add_fieldsets = UserAdmin.add_fieldsets + (
        ("Thông tin thêm", {"fields": ("first_name", "last_name", "email", "nhan_vien", "groups")}),
    )

    @admin.display(description="Vai trò")
    def get_roles(self, obj):
        return ", ".join(obj.groups.values_list("name", flat=True)) or "—"