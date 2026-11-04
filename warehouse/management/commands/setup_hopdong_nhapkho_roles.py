"""Bổ sung quyền vào hai nhóm III–IV chuyên dụng; không sửa nhóm dự án cũ hoặc gán tài khoản."""
from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Tạo/bổ sung quyền hai nhóm III–IV; không tự gán người dùng, không sửa nhóm Quản lý/Nhân viên cũ.'

    def handle(self, **options):
        reads = ['database.view_hopdong', 'database.view_tonkho', 'database.view_xe',
                 'database.view_chitietnhap', 'database.view_hoadonnhap', 'database.view_bienbanpdi',
                 'warehouse.view_phieunhapkho', 'warehouse.view_ketquapdi', 'warehouse.view_lichsunhapkho']
        groups = {
            'III-IV Sale Admin': reads + ['warehouse.approve_phieunhapkho'],
            'III-IV Nhân viên kho': reads + ['warehouse.add_phieunhapkho', 'warehouse.change_phieunhapkho',
                                            'warehouse.add_ketquapdi', 'warehouse.approve_ketquapdi'],
        }
        for name, codenames in groups.items():
            group, _ = Group.objects.get_or_create(name=name)
            perms = []
            for code in codenames:
                app, codename = code.split('.')
                perms.append(Permission.objects.get(content_type__app_label=app, codename=codename))
            group.permissions.add(*perms)
            self.stdout.write(f'Đã bổ sung quyền nhóm {name}. Chưa gán tài khoản.')
        self.stdout.write('Gán nhóm bằng admin; tài khoản phải liên kết NhanVien đúng chi nhánh kho.')
