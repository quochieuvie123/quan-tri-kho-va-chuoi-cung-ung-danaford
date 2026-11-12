"""Tạo hai VIN giả lập để demo chốt xe và lưu chuyển về Đà Nẵng."""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from database.models import HopDong, Kho, TonKho, TrangThaiXe, Xe


class Command(BaseCommand):
    help = 'Tạo hai xe tồn kho mẫu khớp T10-003 và T10-004; không tự gán hợp đồng.'

    @transaction.atomic
    def handle(self, *args, **options):
        cases = [
            ('T10-003', 'KHO02', 'DEMO-BD-T10003', 'DEMO-ENGINE-BD-T10003'),
            ('T10-004', 'KHO03', 'DEMO-GL-T10004', 'DEMO-ENGINE-GL-T10004'),
        ]
        for contract_id, warehouse_id, vin, engine in cases:
            contract = HopDong.objects.get(pk=contract_id)
            warehouse = Kho.objects.get(pk=warehouse_id)
            criteria = (contract.dong_xe_yeu_cau, contract.phien_ban_yeu_cau, contract.mau_sac_yeu_cau)
            if not all(criteria):
                raise CommandError(f'{contract_id} chưa đủ tiêu chí xe.')
            car, created = Xe.objects.get_or_create(
                vin=vin,
                defaults=dict(ten_xe=criteria[0], phien_ban=criteria[1], mau_sac=criteria[2],
                              loai_xe='DEMO', so_may=engine, nam_sx=2026,
                              trang_thai=TrangThaiXe.SAN_SANG),
            )
            if created:
                TonKho.objects.create(kho=warehouse, xe=car, ngay_vao_kho=timezone.localdate(),
                                      so_luong_ton=1, vi_tri='DEMO-01')
            self.stdout.write(f'{contract_id}: {vin} | {warehouse.chi_nhanh.ten_cn} | '
                              f'{"Đã tạo" if created else "Đã có, giữ nguyên dữ liệu"}')
