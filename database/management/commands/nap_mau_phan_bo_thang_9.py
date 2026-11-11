"""Nạp đúng 10 xe demo từ file phân bổ tháng 9; không ghi đè dữ liệu đã có."""
from datetime import datetime, time
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from openpyxl import load_workbook

from database.models import ChiTietNhap, DonViVanChuyen, HoaDonNhap, Kho, NhaCungCap, TonKho, Xe
from orders.models import Allocation, VehicleRequest, VehicleRequestItem
from warehouse.models import LichSuNhapKho, PhieuNhapKho


class Command(BaseCommand):
    help = 'Nạp 10 xe demo tháng 9: Đà Nẵng 4, Bình Định 3, Gia Lai 3.'

    def add_arguments(self, parser):
        parser.add_argument('xlsx', help='Đường dẫn file Excel mẫu tháng 9')

    @transaction.atomic
    def handle(self, *args, **options):
        workbook = load_workbook(options['xlsx'], read_only=True, data_only=True)
        try:
            rows = list(workbook.active.values)
        finally:
            workbook.close()
        expected = ('ORDER_NO', 'MODEL CODE', 'DESCRIPTION', 'VIN', 'COLOR CODE', 'EXTERIOR COLOUR',
                    'ENGINE_NUMBER', 'QUANTITY', 'EXPECTED SHIP DATE', 'CONTRACTUAL DELIVERY DATE', 'ALLOCATION MONTH')
        if not rows or tuple(rows[0][:11]) != expected or len(rows[1:]) != 10:
            raise CommandError('File không đúng định dạng mẫu hoặc không có đúng 10 xe.')
        data = rows[1:]
        vins = [str(row[3] or '').strip() for row in data]
        if len(set(vins)) != 10 or any(not vin for vin in vins):
            raise CommandError('VIN thiếu hoặc trùng trong file.')
        if Allocation.objects.filter(vin__in=vins).exists() or Xe.objects.filter(pk__in=vins).exists():
            raise CommandError('Có VIN đã tồn tại. Dừng để bảo vệ dữ liệu hiện có.')
        codes = [f'PN-DEMO-T09-{i:02}' for i in range(1, 11)]
        if PhieuNhapKho.objects.filter(ma_phieu__in=codes).exists():
            raise CommandError('Mã phiếu demo đã tồn tại; không ghi đè.')
        stores = [Kho.objects.select_related('chi_nhanh').get(pk=key) for key in ['KHO01', 'KHO02', 'KHO03']]
        worker = get_user_model().objects.get(username='kho_mau')
        admin = get_user_model().objects.get(username='sale_mau')
        supplier = NhaCungCap.objects.get(pk='NCC_MAU')
        carrier = DonViVanChuyen.objects.get(pk='DVVC_MAU')
        request = VehicleRequest.objects.create(created_by=admin, status=VehicleRequest.Status.ACCEPTED, sent_at=timezone.now())
        invoices = []
        for i, store in enumerate(stores, 1):
            invoices.append(HoaDonNhap.objects.create(
                ma_hdn=f'HDN-DEMO-T09-{i:02}', nha_cung_cap=supplier, chi_nhanh=store.chi_nhanh,
                don_vi_van_chuyen=carrier, ngay_nhap=timezone.now(), so_hoa_don=f'DEMO-T09-{i:02}',
                ky_hieu='DEMO', ten_tai_xe='Dữ liệu mẫu'))
        for index, row in enumerate(data):
            order, code, description, vin, color_code, color, engine, quantity, ship, delivery, month = row[:11]
            if not isinstance(month, datetime) or month.year != 2026 or month.month != 9 or int(quantity) != 1:
                raise CommandError(f'Dòng {index + 2} sai tháng hoặc số lượng.')
            allocation = Allocation.objects.create(order_number=order, vehicle_code=code, description=description,
                vin=vin, color_code=color_code, exterior_color=color, engine_number=engine, quantity=1,
                expected_ship_date=ship.date() if isinstance(ship, datetime) else ship,
                contractual_delivery_date=delivery.date() if isinstance(delivery, datetime) else delivery,
                allocation_month=month.date())
            VehicleRequestItem.objects.create(vehicle_request=request, allocation=allocation, quantity=1)
            xe = Xe.objects.create(vin=vin, ten_xe=description, loai_xe=code, so_may=engine, mau_sac=color)
            group = 0 if index < 4 else (1 if index < 7 else 2)
            store = stores[group]
            line = ChiTietNhap.objects.create(hoa_don_nhap=invoices[group], xe=xe, so_luong_nhap=1, don_gia=Decimal('0'))
            approved = group != 0
            now = timezone.now()
            receipt = PhieuNhapKho.objects.create(ma_phieu=codes[index], chi_tiet_nhap=line, xe=xe, kho=store,
                ngay_nhap=timezone.localdate(), trang_thai='DA_DUYET' if approved else 'NHAP', nguoi_lap=worker,
                nguoi_duyet=admin if approved else None, thoi_gian_duyet=now if approved else None)
            if approved:
                TonKho.objects.create(kho=store, xe=xe, ngay_vao_kho=timezone.localdate(), so_luong_ton=1)
                LichSuNhapKho.objects.create(phieu_nhap=receipt, xe=xe, kho=store, nguoi_thuc_hien=admin, thoi_gian=now)
            self.stdout.write(f'{receipt.ma_phieu} | {vin} | {store.chi_nhanh.ten_cn} | {"Đã duyệt (demo)" if approved else "Chưa có PDI"}')
        self.stdout.write(self.style.SUCCESS(f'Đã tạo phiếu đặt xe {request.request_number} với 10 xe.'))
