from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Thiết lập quyền nhóm Sale Admin và Nhân viên kho; không tự gán tài khoản.'

    def handle(self, *args, **options):
        common = {
            'database': ['view_hopdong', 'view_xe', 'view_tonkho', 'view_hoadonnhap', 'view_chitietnhap', 'view_bienbanpdi', 'view_hoadonban', 'view_phieuxuatkho'],
            'warehouse': ['view_phieunhapkho', 'view_ketquapdi', 'view_lichsunhapkho'],
        }
        extras = {
            'III-IV Sale Admin': {'warehouse': ['approve_phieunhapkho'], 'database': ['add_phieuxuatkho', 'change_phieuxuatkho']},
            'III-IV Nhân viên kho': {'warehouse': ['add_phieunhapkho', 'change_phieunhapkho', 'add_ketquapdi', 'approve_ketquapdi'],
                'transfers': ['view_lenhluuchuyen', 'add_lenhluuchuyen', 'change_lenhluuchuyen'],
                'database': ['add_bienbanpdi', 'change_bienbanpdi']},
        }
        for name, extra in extras.items():
            group, _ = Group.objects.get_or_create(name=name)
            permissions = []
            for app in set(common) | set(extra):
                codes = set(common.get(app, [])) | set(extra.get(app, []))
                permissions.extend(Permission.objects.filter(content_type__app_label=app, codename__in=codes))
            group.permissions.set(permissions)
            self.stdout.write(self.style.SUCCESS(name))
