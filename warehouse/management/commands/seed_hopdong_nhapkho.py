from datetime import date
from decimal import Decimal
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from database.models import ChiNhanh, Kho, Xe, KhachHang, HopDong, NhaCungCap, DonViVanChuyen, HoaDonNhap, ChiTietNhap


class Command(BaseCommand):
    help = 'Chỉ tạo mẫu trên config.iii_iv_demo_settings; không tạo PDI giả đạt hoặc cộng tồn.'

    @transaction.atomic
    def handle(self, **options):
        if not getattr(settings, 'III_IV_DEMO', False):
            raise CommandError('Chỉ chạy với --settings=config.iii_iv_demo_settings')
        cn, _ = ChiNhanh.objects.get_or_create(ma_cn='DEMO-DN', defaults={'ten_cn': 'Đà Nẵng (DEMO)'})
        Kho.objects.get_or_create(ma_kho='DEMO-KHO', defaults={'chi_nhanh': cn})
        customer, _ = KhachHang.objects.get_or_create(ma_kh='DEMO-KH', defaults={'ten_kh': 'Khách hàng mô phỏng', 'sdt_kh': '0900000000'})
        supplier, _ = NhaCungCap.objects.get_or_create(ma_ncc='DEMO-NCC', defaults={'ten_ncc': 'Nhà cung cấp mô phỏng', 'mst': 'DEMO-MST'})
        carrier, _ = DonViVanChuyen.objects.get_or_create(ma_dvvc='DEMO-DV', defaults={'ten_dvvc': 'Vận chuyển mô phỏng'})
        # Mọi định danh đều là DEMO; không nhập dữ liệu cá nhân từ Drive.
        car, _ = Xe.objects.get_or_create(vin='DEMO0000000000001', defaults={
            'ten_xe': 'FORD RANGER', 'loai_xe': 'PICKUP', 'phien_ban': 'XLS',
            'so_may': 'DEMO-ENGINE-01', 'mau_sac': 'Đỏ', 'nam_sx': 2026})
        hd, _ = HoaDonNhap.objects.get_or_create(ma_hdn='DEMO-HDN', defaults={
            'nha_cung_cap': supplier, 'chi_nhanh': cn, 'don_vi_van_chuyen': carrier,
            'ngay_nhap': timezone.now(), 'so_hoa_don': 'DEMO-INVOICE'})
        line, _ = ChiTietNhap.objects.get_or_create(hoa_don_nhap=hd, xe=car, defaults={'don_gia': Decimal('488800000')})
        HopDong.objects.get_or_create(ma_hd='DEMO-HD', defaults={
            'chi_nhanh': cn, 'khach_hang': customer, 'ngay_ky': timezone.now(),
            'dong_xe_yeu_cau': 'FORD RANGER', 'phien_ban_yeu_cau': 'XLS',
            'mau_sac_yeu_cau': 'Đỏ', 'trang_thai': 'Chờ giao', 'ngay_du_kien_giao': date.today()})
        self.stdout.write(f'DEMO: kho=DEMO-KHO, chi_tiet_nhap_id={line.pk}, hợp đồng=DEMO-HD')
        self.stdout.write('Lệnh không tạo PDI hoặc cộng tồn; dữ liệu demo đã tồn tại được giữ nguyên. Dùng API để kiểm tra luồng nhập.')
