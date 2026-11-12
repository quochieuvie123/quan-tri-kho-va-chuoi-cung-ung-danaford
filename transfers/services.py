"""Xuất nguồn và tiếp nhận lưu chuyển; tồn đích chỉ tăng khi duyệt phiếu nhập."""
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone
from database.models import TonKho, Xe, TrangThaiXe, BienBanPDI
from core.iii_iv_access import require_role, can_write_warehouse, WAREHOUSE
from warehouse.nhap_services import require_permission
from .models import LenhLuuChuyen


def check_actor(user, order, warehouse):
    require_role(user, WAREHOUSE)
    require_permission(user, 'transfers.change_lenhluuchuyen')
    if not can_write_warehouse(user, warehouse):
        raise PermissionDenied('Tài khoản không thuộc chi nhánh xử lý lệnh.')


@transaction.atomic
def dispatch_transfer(user, order_id):
    order = LenhLuuChuyen.objects.select_for_update().select_related('kho_xuat__chi_nhanh').get(pk=order_id)
    check_actor(user, order, order.kho_xuat)
    if order.trang_thai != 'NHAP':
        raise ValidationError('Chỉ có thể gửi lệnh đang ở trạng thái nháp.')
    lines = list(order.chi_tiet.order_by('xe_id'))
    if not lines or len({line.xe_id for line in lines}) != len(lines) or order.kho_xuat_id == order.kho_nhap_id:
        raise ValidationError('Lệnh trống, trùng VIN hoặc trùng kho xuất/nhận.')
    for line in lines:
        car = Xe.objects.select_for_update().get(pk=line.xe_id)
        if line.so_luong != 1 or car.trang_thai != TrangThaiXe.SAN_SANG:
            raise ValidationError('VIN phải sẵn sàng và số lượng bằng một.')
        if BienBanPDI.objects.filter(xe=car).exclude(trang_thai_claim='Đã xử lý').exists():
            raise ValidationError('Xe đang có sự cố chưa đóng.')
        stock = TonKho.objects.select_for_update().filter(xe=car, kho=order.kho_xuat, so_luong_ton=1).first()
        if stock is None or TonKho.objects.filter(xe=car, so_luong_ton__gt=0).exclude(pk=stock.pk).exists():
            raise ValidationError('Tồn nguồn không hợp lệ hoặc VIN nằm ở nhiều kho.')
        stock.so_luong_ton = 0
        stock.save(update_fields=['so_luong_ton'])
        car.trang_thai = TrangThaiXe.DANG_LUU_CHUYEN
        car.save(update_fields=['trang_thai'])
    order.trang_thai = 'DA_GUI'
    order.ngay_gui = timezone.now()
    order.save(update_fields=['trang_thai', 'ngay_gui'])
    return order


@transaction.atomic
def receive_transfer(user, order_id):
    order = LenhLuuChuyen.objects.select_for_update().select_related('kho_nhap__chi_nhanh').get(pk=order_id)
    check_actor(user, order, order.kho_nhap)
    if order.trang_thai != 'DA_GUI':
        raise ValidationError('Chỉ tiếp nhận lệnh đã gửi.')
    lines = list(order.chi_tiet.order_by('xe_id'))
    if not lines:
        raise ValidationError('Lệnh chưa có xe.')
    for line in lines:
        car = Xe.objects.select_for_update().get(pk=line.xe_id)
        if line.so_luong != 1 or car.trang_thai not in (TrangThaiXe.DANG_LUU_CHUYEN, TrangThaiXe.SU_CO_PDI):
            raise ValidationError('VIN không còn trong trạng thái vận chuyển hợp lệ.')
        if TonKho.objects.filter(xe=car, so_luong_ton__gt=0).exists():
            raise ValidationError('Xe vẫn có tồn dương; cần đối chiếu xuất kho nguồn trước khi tiếp nhận.')
        stock, _ = TonKho.objects.get_or_create(kho=order.kho_nhap, xe=car,
            defaults={'ngay_vao_kho': timezone.localdate(), 'so_luong_ton': 0})
        if TonKho.objects.filter(pk=stock.pk, so_luong_ton=0).update(
                so_luong_ton=1, ngay_vao_kho=timezone.localdate()) != 1:
            raise ValidationError('Tồn kho đích vừa thay đổi; hãy kiểm tra lại.')
        car.trang_thai = TrangThaiXe.SAN_SANG
        car.save(update_fields=['trang_thai'])
    order.trang_thai = 'DA_XAC_NHAN'
    order.ngay_xac_nhan = timezone.now()
    order.nguoi_xac_nhan = user
    order.save(update_fields=['trang_thai', 'ngay_xac_nhan', 'nguoi_xac_nhan'])
    from contracts.workflow import sync_contract_for_vin
    for line in lines:
        sync_contract_for_vin(line.xe_id)
    return order
