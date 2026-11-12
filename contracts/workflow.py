"""State changes caused by a manager explicitly choosing a proposed VIN."""
from django.core.exceptions import ValidationError
from django.db import transaction

from core.iii_iv_access import is_da_nang_branch
from database.models import ChiTietHopDong, HopDong, TonKho, TrangThaiHopDong, TrangThaiXe, Xe


def matches_contract(car, contract):
    return all((actual or '').strip().casefold() == (expected or '').strip().casefold() for actual, expected in (
        (car.ten_xe, contract.dong_xe_yeu_cau),
        (car.phien_ban, contract.phien_ban_yeu_cau),
        (car.mau_sac, contract.mau_sac_yeu_cau),
    ))


@transaction.atomic
def choose_vehicle(contract_id, vin, user):
    """Reserve one suggested VIN and calculate the next contract state."""
    contract = HopDong.objects.select_for_update().select_related('chi_nhanh').get(pk=contract_id)
    car = Xe.objects.select_for_update().get(pk=vin)
    if contract.trang_thai in (TrangThaiHopDong.DANG_XUAT_KHO, TrangThaiHopDong.HOAN_TAT):
        raise ValidationError('Hợp đồng đang xuất kho hoặc đã hoàn tất.')
    if not matches_contract(car, contract):
        raise ValidationError('VIN không khớp dòng xe, phiên bản và màu sắc của hợp đồng.')
    other = ChiTietHopDong.objects.filter(xe=car).exclude(hop_dong=contract).exists()
    if other:
        raise ValidationError('VIN đã được giữ cho hợp đồng khác.')
    ChiTietHopDong.objects.get_or_create(hop_dong=contract, xe=car)
    available_here = TonKho.objects.filter(
        xe=car, so_luong_ton__gt=0, xe__trang_thai=TrangThaiXe.SAN_SANG,
    ).select_related('kho__chi_nhanh').first()
    if available_here and is_da_nang_branch(available_here.kho.chi_nhanh):
        contract.trang_thai = TrangThaiHopDong.DU_DIEU_KIEN_XUAT
    elif available_here:
        # Xe ở Bình Định/Gia Lai: chốt là tạo sẵn lệnh lưu chuyển về Đà Nẵng.
        from transfers.models import ChiTietLenhLuuChuyen, LenhLuuChuyen
        from database.models import Kho
        target_warehouse = Kho.objects.get(pk='KHO01')
        code = f'LC-{contract.pk}-{car.pk[-10:]}'[:30]
        transfer, _ = LenhLuuChuyen.objects.get_or_create(
            ma_lenh=code,
            defaults={'kho_xuat': available_here.kho, 'kho_nhap': target_warehouse, 'nguoi_lap': user},
        )
        ChiTietLenhLuuChuyen.objects.get_or_create(lenh=transfer, xe=car, defaults={'so_luong': 1})
        contract.trang_thai = TrangThaiHopDong.CHO_XE_VE_KHO
    else:
        contract.trang_thai = TrangThaiHopDong.CHO_XE_VE_KHO
    contract.save(update_fields=['trang_thai'])
    return contract


@transaction.atomic
def sync_contract_for_vin(vin):
    """After PDI/receipt puts a chosen VIN in Đà Nẵng stock, enable export."""
    car = Xe.objects.select_for_update().get(pk=vin)
    if not TonKho.objects.filter(xe=car, so_luong_ton__gt=0, xe__trang_thai=TrangThaiXe.SAN_SANG,
                                  kho__chi_nhanh_id='CN01').exists():
        return 0
    updated = 0
    for contract in HopDong.objects.select_for_update().filter(chitiethopdong__xe=car,
        trang_thai__in=[TrangThaiHopDong.CHO_XE_VE_KHO, TrangThaiHopDong.CHO_PHAN_BO]).distinct():
        contract.trang_thai = TrangThaiHopDong.DU_DIEU_KIEN_XUAT
        contract.save(update_fields=['trang_thai'])
        updated += 1
    return updated
