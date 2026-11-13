"""Create the receiving draft for every car saved on a PYC order."""
from decimal import Decimal
from django.db import transaction
from django.utils import timezone

from database.models import ChiNhanh, ChiTietNhap, DonViVanChuyen, HoaDonNhap, Kho, NhaCungCap, Xe
from orders.models import VehicleRequest
from .models import PhieuNhapKho


def _da_nang_receiving_data():
    """Default PYC destination until a transfer is planned."""
    branch, _ = ChiNhanh.objects.get_or_create(ma_cn='CN01', defaults={'ten_cn': 'Dana Ford Đà Nẵng', 'dia_chi_cn': 'Đà Nẵng'})
    warehouse, _ = Kho.objects.get_or_create(ma_kho='KHO01', defaults={'chi_nhanh': branch})
    supplier, _ = NhaCungCap.objects.get_or_create(ma_ncc='NCC_FORD_VN', defaults={'ten_ncc': 'Ford Việt Nam', 'dia_chi_ncc': 'Hà Nội', 'mst': '0100109998'})
    carrier, _ = DonViVanChuyen.objects.get_or_create(ma_dvvc='DVVC_FORD_VN', defaults={'ten_dvvc': 'Ford Việt Nam', 'dia_chi_dvvc': 'Việt Nam'})
    return branch, warehouse, supplier, carrier


@transaction.atomic
def sync_request(request_id):
    """Make one real NHAP receipt per VIN as soon as a PYC is saved."""
    order = VehicleRequest.objects.select_for_update().get(pk=request_id)
    branch, warehouse, supplier, carrier = _da_nang_receiving_data()
    invoice, _ = HoaDonNhap.objects.get_or_create(
        ma_hdn=f'HDN-PYC-{order.pk}',
        defaults={'nha_cung_cap': supplier, 'chi_nhanh': branch, 'don_vi_van_chuyen': carrier,
                  'ngay_nhap': timezone.now(), 'so_hoa_don': order.request_number,
                  'ky_hieu': 'PYC', 'ten_tai_xe': 'Chờ dữ liệu PDI'},
    )
    created = 0
    for item in order.items.select_related('allocation').order_by('pk'):
        allocation = item.allocation
        ma_phieu = f'PN-PYC-{order.pk}-{item.pk}'
        if PhieuNhapKho.objects.filter(ma_phieu=ma_phieu).exists():
            continue

        # Nếu xe đang có phiếu nhập nháp cũ chưa hoàn tất (từ bản nháp cũ chưa duyệt, không có PDI)
        active_pnk = PhieuNhapKho.objects.filter(
            xe_id=allocation.vin,
            trang_thai__in=['NHAP', 'CHO_DUYET']
        ).exclude(ma_phieu=ma_phieu).first()

        if active_pnk:
            if not active_pnk.cac_lan_pdi.exists():
                active_pnk.delete()
            else:
                continue

        engine = (allocation.engine_number or f'DEMO-{allocation.vin}')[:50]
        car, _ = Xe.objects.get_or_create(
            vin=allocation.vin,
            defaults={'ten_xe': allocation.description or allocation.vehicle_code,
                      'loai_xe': allocation.vehicle_code, 'phien_ban': allocation.description or '',
                      'so_may': engine, 'mau_sac': allocation.exterior_color or ''},
        )
        if car.trang_thai == 'DA_XUAT':
            car.trang_thai = 'SAN_SANG'
            car.save(update_fields=['trang_thai'])

        line, _ = ChiTietNhap.objects.get_or_create(
            hoa_don_nhap=invoice, xe=car, defaults={'so_luong_nhap': 1, 'don_gia': Decimal('0')},
        )
        _, was_created = PhieuNhapKho.objects.get_or_create(
            ma_phieu=ma_phieu,
            defaults={'chi_tiet_nhap': line, 'xe': car, 'kho': warehouse,
                      'ngay_nhap': timezone.localdate(), 'nguoi_lap': order.created_by,
                      'trang_thai': PhieuNhapKho.TrangThai.NHAP})
        created += was_created
    return created
