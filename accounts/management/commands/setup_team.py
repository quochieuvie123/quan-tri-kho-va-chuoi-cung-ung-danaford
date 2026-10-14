from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Tạo tài khoản superuser cho cả nhóm trên máy này"

    def add_arguments(self, parser):
        parser.add_argument("--users", required=True, help="Tên đăng nhập, cách nhau bằng dấu phẩy")
        parser.add_argument("--password", required=True, help="Mật khẩu ban đầu dùng chung")

    def handle(self, *args, **options):
        User = get_user_model()
        for username in [u.strip() for u in options["users"].split(",") if u.strip()]:
            user, created = User.objects.get_or_create(username=username)
            user.is_staff = True
            user.is_superuser = True
            user.is_active = True
            if created:
                user.set_password(options["password"])
            user.save()
            self.stdout.write(f"{'Tạo mới' if created else 'Đã có, cập nhật quyền'}: {username}")
        self.stdout.write(self.style.SUCCESS("Xong. Nhớ đổi mật khẩu sau khi đăng nhập."))