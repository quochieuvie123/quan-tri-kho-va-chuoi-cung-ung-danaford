"""Dữ liệu minh họa nghiệp vụ, chạy lặp không ghi đè dữ liệu đã tạo."""
from datetime import date
from decimal import Decimal
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from database.models import ChiNhanh, Kho, Xe, NhaCungCap, DonViVanChuyen, HoaDonNhap, ChiTietNhap
from warehouse.models import PhieuNhapKho
from warehouse import services


class Command(BaseCommand):
    help = 'Tạo 4 phiếu nhập minh họa tại Đà Nẵng; không tạo tài khoản hoặc ghi đè phiếu cũ.'

    def add_arguments(self, parser):
        parser.add_argument('--user', required=True, help='Tài khoản superuser có sẵn để ghi nhận thao tác mẫu')

    @transaction.atomic
    def handle(self, *args, **options):
        user = get_user_model().objects.filter(username=options['user'], is_active=True, is_superuser=True).first()
        if user is None:
            raise CommandError('Chọn tài khoản superuser đang có; lệnh không tạo tài khoản mới.')
        branch = ChiNhanh.objects.filter(pk='CN01', ten_cn__icontains='Đà Nẵng').first()
        if branch is None:
            branch = ChiNhanh.objects.filter(ten_cn__icontains='Đà Nẵng').first()
        if branch is None:
            raise CommandError('Chưa có chi nhánh Đà Nẵng. Không tự tạo kho thay thế.')
        kho = Kho.objects.filter(chi_nhanh=branch).first()
        if kho is None:
            raise CommandError('Chi nhánh Đà Nẵng chưa có kho.')
        supplier, _ = NhaCungCap.objects.get_or_create(ma_ncc='MAU-FVL', defaults={
            'ten_ncc': 'Ford Việt Nam (dữ liệu mô phỏng)', 'mst': 'MO-PHONG-FVL'})
        carrier, _ = DonViVanChuyen.objects.get_or_create(ma_dvvc='MAU-VC', defaults={
            'ten_dvvc': 'Đơn vị vận chuyển minh họa'})
        scenarios = [
            ('01', 'Ford Ranger', 'XLS 2.0L 4x2 AT', 'Trắng', 'NHAP'),
            ('02', 'Ford Everest', 'Titanium 2.0L', 'Đen', 'LOI'),
            ('03', 'Ford Territory', 'Titanium 1.5L', 'Trắng', 'CHO_DUYET'),
            ('04', 'Ford Ranger', 'Wildtrak 2.0L 4x4 AT', 'Xám', 'DA_DUYET'),
        ]
        for suffix, model, version, color, state in scenarios:
            number = 'MAU-PN-' + suffix
            if PhieuNhapKho.objects.filter(ma_phieu=number).exists():
                self.stdout.write(number + ': đã có, giữ nguyên.')
                continue
            vin = 'MAU-VIN-' + suffix
            if Xe.objects.filter(pk=vin).exists() or HoaDonNhap.objects.filter(pk='MAU-HDN-' + suffix).exists():
                raise CommandError('Mã mẫu đã được dùng ngoài bộ phiếu: ' + vin)
            car = Xe.objects.create(vin=vin, ten_xe=model, phien_ban=version,
                loai_xe='Xe minh họa', so_may='MAU-MAY-' + suffix, mau_sac=color)
            invoice = HoaDonNhap.objects.create(ma_hdn='MAU-HDN-' + suffix,
                nha_cung_cap=supplier, chi_nhanh=branch, don_vi_van_chuyen=carrier,
                ngay_nhap=timezone.now(), so_hoa_don='MO-PHONG-' + suffix)
            line = ChiTietNhap.objects.create(hoa_don_nhap=invoice, xe=car,
                so_luong_nhap=1, don_gia=Decimal('700000000'))
            receipt = services.create_receipt(user, ma_phieu=number,
                chi_tiet_nhap_id=line.pk, kho_id=kho.pk, ngay_nhap=timezone.localdate())
            if state != 'NHAP':
                result = 'KHONG_DAT' if state == 'LOI' else 'DAT'
                items = [{'hang_muc': label, 'tinh_trang': 'Trầy xước cần xử lý' if state == 'LOI' and label == 'Ngoại thất' else 'Kiểm tra bình thường',
                    'ket_qua': 'KHONG_DAT' if state == 'LOI' and label == 'Ngoại thất' else 'DAT',
                    'ghi_chu': 'Dữ liệu mô phỏng phục vụ chạy thử'} for label in ['Ngoại thất', 'Nội thất', 'Vận hành']]
                pdi = services.record_pdi(user, receipt.pk,
                    tinh_trang='Trầy xước ngoại thất' if state == 'LOI' else 'Xe đã kiểm tra đầy đủ',
                    ket_qua=result, hang_muc=items, ghi_chu='Dữ liệu mô phỏng, không phải hồ sơ xe thật')
                if state != 'LOI':
                    services.approve_pdi(user, receipt.pk, pdi_id=pdi.pk)
                    services.submit_receipt(user, receipt.pk, pdi_id=pdi.pk)
                    if state == 'DA_DUYET':
                        services.approve_receipt(user, receipt.pk, pdi_id=pdi.pk)
            self.stdout.write(number + ': ' + state)
        self.stdout.write(self.style.SUCCESS('Đã tạo bộ phiếu minh họa. VIN MAU-* là mã giả, không phải VIN lưu hành. Chỉ phiếu Đã duyệt tăng tồn một xe.'))
