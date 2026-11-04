from math import ceil

from django.core.management.base import BaseCommand, CommandError

from analytics.du_lieu import thu_thap
from analytics.models import ChiTieuPhanBo


class Command(BaseCommand):
    help = "Tạo chỉ tiêu phân bổ mẫu của hãng cho một kỳ (= 120% nhu cầu trung bình gần đây, tối thiểu 1 xe)."

    def add_arguments(self, parser):
        parser.add_argument("--thang", type=int, required=True)
        parser.add_argument("--nam", type=int, required=True)

    def handle(self, *args, **o):
        if not 1 <= o["thang"] <= 12:
            raise CommandError("--thang phải từ 1 đến 12")
        bo = thu_thap(o["thang"], o["nam"])
        n = 0
        for ten, dl in bo.dong_xe.items():
            gan = dl.chuoi[-6:]
            tb = sum(gan) / len(gan) if gan else 0
            _, tao = ChiTieuPhanBo.objects.get_or_create(
                nam=o["nam"], thang=o["thang"], ten_xe=ten, defaults={"so_luong": max(1, ceil(tb * 1.2))})
            n += tao
        self.stdout.write(self.style.SUCCESS(f"Đã tạo {n} chỉ tiêu mẫu cho {o['thang']:02d}/{o['nam']}."))
