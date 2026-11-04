from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError

from alerts.utils import cap_nhat_tat_ca_canh_bao


class Command(BaseCommand):
    help = "Kiểm tra và cập nhật toàn bộ cảnh báo tồn kho"

    def handle(self, *args, **options):
        try:
            cap_nhat_tat_ca_canh_bao()
        except (DatabaseError, ValueError) as error:
            raise CommandError(
                f"Không thể cập nhật cảnh báo: {error}"
            ) from error

        self.stdout.write(
            self.style.SUCCESS("Đã cập nhật cảnh báo thành công.")
        )
