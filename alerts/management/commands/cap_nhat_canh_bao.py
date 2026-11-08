#Chạy lệnh khởi động cảnh báo hàng ngày: py manage.py cap_nhat_canh_bao --lap-lai

import time
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError
from django.utils import timezone

from alerts.utils import cap_nhat_tat_ca_canh_bao


class Command(BaseCommand):
    help = "Kiểm tra và cập nhật cảnh báo tồn kho"

    def add_arguments(self, parser):
        parser.add_argument(
            "--lap-lai",
            action="store_true",
            help="Tự cập nhật cảnh báo mỗi ngày.",
        )

    def handle(self, *args, **options):
        if not options["lap_lai"]:
            self.cap_nhat_canh_bao()
            return

        self.stdout.write("Bắt đầu tự động cập nhật cảnh báo.")

        while True:
            try:
                self.cap_nhat_canh_bao()
            except CommandError as error:
                self.stderr.write(self.style.ERROR(str(error)))

            bay_gio = timezone.localtime()
            lan_tiep_theo = (
                bay_gio + timedelta(days=1)
            ).replace(
                hour=0,
                minute=0,
                second=0,
                microsecond=0,
            )

            thoi_gian_cho = (
                lan_tiep_theo - bay_gio
            ).total_seconds()

            self.stdout.write(
                f"Lần cập nhật tiếp theo: "
                f"{lan_tiep_theo:%d/%m/%Y %H:%M:%S}"
            )
            time.sleep(max(1, thoi_gian_cho))

    def cap_nhat_canh_bao(self):
        try:
            cap_nhat_tat_ca_canh_bao()
        except (DatabaseError, ValueError) as error:
            raise CommandError(
                f"Không thể cập nhật cảnh báo: {error}"
            ) from error

        self.stdout.write(
            self.style.SUCCESS("Đã cập nhật cảnh báo thành công.")
        )
