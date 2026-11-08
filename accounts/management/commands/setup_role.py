from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand

BUSINESS_APPS = ["database", "alerts", "analytics", "incidents", "orders", "warehouse", "transfers"]


class Command(BaseCommand):
    help = "Tao nhom quyen Quan ly va Nhan vien"
    verbose_name = "Tai khoan"

    def handle(self, *args, **options):
        perms = Permission.objects.filter(content_type__app_label__in=BUSINESS_APPS)

        quan_ly, _ = Group.objects.get_or_create(name="Quản lý")
        quan_ly.permissions.set(perms)

        nhan_vien, _ = Group.objects.get_or_create(name="Nhân viên")
        nhan_vien.permissions.set(perms.exclude(codename__startswith="delete_"))

        self.stdout.write(self.style.SUCCESS("Da tao/cap nhat 2 nhom quyen"))
