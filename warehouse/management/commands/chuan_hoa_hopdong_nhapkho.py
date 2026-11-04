"""Chuẩn hóa dữ liệu mẫu đã có; không nạp lại fixture hay xóa tài khoản."""
from django.core.management.base import BaseCommand
from django.db import transaction
from database.models import Xe, HopDong, ChiNhanh, NhaCungCap, HoaDonNhap


class Command(BaseCommand):
    help = 'Chuẩn hóa dữ liệu mẫu hợp đồng/nhập kho. Mặc định chỉ xem; --apply để lưu.'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true')

    @transaction.atomic
    def handle(self, *args, **options):
        changed = 0
        for car in Xe.objects.filter(phien_ban__isnull=True):
            parts = car.ten_xe.split()
            if len(parts) >= 3 and parts[0] == 'Ford':
                car.phien_ban = ' '.join(parts[2:])
                car.save(update_fields=['phien_ban'])
                changed += 1
        for hd in HopDong.objects.all():
            lines = list(hd.chitiethopdong_set.select_related('xe'))
            if len(lines) == 1 and not any([hd.dong_xe_yeu_cau, hd.phien_ban_yeu_cau, hd.mau_sac_yeu_cau]):
                car = lines[0].xe
                hd.dong_xe_yeu_cau, hd.phien_ban_yeu_cau, hd.mau_sac_yeu_cau = car.ten_xe, car.phien_ban, car.mau_sac
                hd.save(update_fields=['dong_xe_yeu_cau', 'phien_ban_yeu_cau', 'mau_sac_yeu_cau'])
                changed += 1
        self.stdout.write(f'{changed} bản ghi có thể chuẩn hóa từ dữ liệu xe hiện có.')
        if not options['apply']:
            transaction.set_rollback(True)
            self.stdout.write('Chỉ xem; chạy lại với --apply để lưu.')
