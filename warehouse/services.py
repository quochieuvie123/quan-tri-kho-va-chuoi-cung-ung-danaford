"""Mọi thay đổi nhập kho đi qua dịch vụ để kiểm tra và lưu nguyên tử."""
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone
from database.models import Xe, Kho, ChiTietNhap, TonKho, BienBanPDI
from core.iii_iv_access import require_role, can_write_warehouse, is_da_nang_branch, SALE_ADMIN, WAREHOUSE
from .models import PhieuNhapKho, KetQuaPDI, LichSuNhapKho
from .validation import validate_pdi_items


def require_permission(user, codename):
    if not user.is_authenticated or not user.has_perm(codename):
        raise PermissionDenied('Bạn không có quyền thực hiện thao tác này.')


def require_branch(user, kho):
    # Giới hạn ghi theo chi nhánh nhân viên hiện có, không tạo trường kho mới.
    if not can_write_warehouse(user, kho):
        raise PermissionDenied('Tài khoản chưa được gắn nhân viên tại chi nhánh của kho này.')


def incident_rows(receipt):
    return BienBanPDI.objects.filter(xe_id=receipt.xe_id,
        hoa_don_nhap_id=receipt.chi_tiet_nhap.hoa_don_nhap_id)


def lock_receipt(pk):
    vin = PhieuNhapKho.objects.values_list('xe_id', flat=True).get(pk=pk)
    # Luôn khóa VIN trước chứng từ để các thao tác cùng xe dùng một thứ tự.
    Xe.objects.select_for_update().get(pk=vin)
    receipt = PhieuNhapKho.objects.select_for_update().get(pk=pk)
    if receipt.xe_id != vin:
        raise ValidationError('VIN của phiếu đã thay đổi; vui lòng tải lại.')
    return receipt


def latest_pdi(receipt):
    if hasattr(receipt, 'pdi_records'):
        return receipt.pdi_records[0] if receipt.pdi_records else None
    return receipt.cac_lan_pdi.order_by('-thoi_gian_kiem_tra', '-pk').first()


def pdi_warnings(pdi):
    if pdi is None:
        return ['Chưa có kết quả kiểm tra PDI.']
    warnings = []
    if not pdi.hang_muc:
        warnings.append('Chưa có hạng mục kiểm tra; chưa đủ điều kiện duyệt PDI.')
    try:
        validate_pdi_items(pdi.hang_muc)
    except ValidationError as exc:
        warnings.extend(exc.messages)
    if not isinstance(pdi.tinh_trang, str) or not pdi.tinh_trang.strip():
        warnings.append('Thiếu tình trạng kiểm tra thực tế.')
    if pdi.ket_qua not in KetQuaPDI.KetQua.values:
        warnings.append('Kết quả PDI không hợp lệ.')
    if not warnings and pdi.ket_qua == 'DAT' and any(item['ket_qua'] != 'DAT' for item in pdi.hang_muc):
        warnings.append('Không kết luận Đạt khi còn hạng mục Không đạt.')
    if bool(pdi.nguoi_duyet_id) != bool(pdi.thoi_gian_duyet):
        warnings.append('Thông tin người duyệt và thời gian duyệt chưa đầy đủ.')
    return warnings


def ready_pdi(receipt, pdi=None):
    pdi = pdi or latest_pdi(receipt)
    if incident_warnings(receipt, pdi):
        return False
    return bool(pdi and pdi.ket_qua == 'DAT' and pdi.nguoi_duyet_id and pdi.thoi_gian_duyet and not pdi_warnings(pdi))


def incident_warnings(receipt, pdi):
    """PDI lỗi phải qua hồ sơ sự cố và có lần kiểm tra lại sau xử lý."""
    failures = receipt.cac_lan_pdi.filter(ket_qua='KHONG_DAT')
    if not failures.exists():
        return []
    first_failure = failures.order_by('thoi_gian_kiem_tra').first()
    incidents = BienBanPDI.objects.filter(
        xe_id=receipt.xe_id,
        hoa_don_nhap_id=receipt.chi_tiet_nhap.hoa_don_nhap_id,
        ngay_ghi_nhan__gte=first_failure.thoi_gian_kiem_tra,
    )
    if not incidents.exists() or incidents.exclude(trang_thai_claim='Đã xử lý').exists():
        return ['PDI không đạt: cần hoàn tất hồ sơ xử lý sự cố vận chuyển trước khi duyệt PDI lại.']
    if pdi is None or pdi.ket_qua != 'DAT':
        return ['Cần kiểm tra PDI lại và có kết quả Đạt sau khi xử lý sự cố.']
    return []


def check_pdi_version(pdi, expected_id):
    if expected_id is None or str(pdi.pk) != str(expected_id):
        raise ValidationError('PDI đã thay đổi hoặc chưa xác nhận PDI đang xem; tải lại PDI mới nhất.')


def receipt_warnings(receipt):
    car = receipt.xe
    required = [car.ten_xe, car.phien_ban, car.mau_sac, car.so_may,
                receipt.chi_tiet_nhap.hoa_don_nhap.nha_cung_cap.ten_ncc]
    if not all(isinstance(value, str) and value.strip() for value in required):
        return ['Thiếu dòng xe, phiên bản, màu sắc, số máy hoặc nguồn xe; cần bổ sung trước khi gửi/duyệt nhập.']
    return []


def validate_receipt_data(receipt):
    receipt.full_clean()
    warnings = receipt_warnings(receipt)
    if warnings:
        raise ValidationError(warnings)


@transaction.atomic
def create_receipt(user, *, ma_phieu, chi_tiet_nhap_id, kho_id, ngay_nhap):
    require_role(user, WAREHOUSE)
    require_permission(user, 'warehouse.add_phieunhapkho')
    vin = ChiTietNhap.objects.values_list('xe_id', flat=True).get(pk=chi_tiet_nhap_id)
    Xe.objects.select_for_update().get(pk=vin)
    line = ChiTietNhap.objects.select_for_update().select_related('hoa_don_nhap').get(pk=chi_tiet_nhap_id)
    if line.xe_id != vin:
        raise ValidationError('VIN của chứng từ đã thay đổi; vui lòng tải lại.')
    kho = Kho.objects.get(pk=kho_id)
    require_branch(user, kho)
    if line.so_luong_nhap != 1:
        raise ValidationError('Phiếu theo VIN chỉ tiếp nhận đúng một chiếc xe.')
    if TonKho.objects.filter(xe_id=line.xe_id, so_luong_ton__gt=0).exists():
        raise ValidationError('VIN đã có trong tồn kho.')
    if PhieuNhapKho.objects.filter(chi_tiet_nhap=line).exists():
        raise ValidationError('Chi tiết nhập đã có phiếu tiếp nhận.')
    receipt = PhieuNhapKho(ma_phieu=ma_phieu, chi_tiet_nhap=line, xe_id=line.xe_id,
                          kho=kho, ngay_nhap=ngay_nhap, nguoi_lap=user)
    receipt.full_clean()
    receipt.save()
    return receipt


@transaction.atomic
def record_pdi(user, receipt_id, *, tinh_trang, ket_qua, ghi_chu='', hang_muc=None, pdi_id=None):
    require_role(user, WAREHOUSE)
    require_permission(user, 'warehouse.add_ketquapdi')
    receipt = lock_receipt(receipt_id)
    require_branch(user, receipt.kho)
    if receipt.trang_thai == 'DA_DUYET':
        raise ValidationError('Không cập nhật PDI sau khi đã duyệt nhập kho.')
    current = latest_pdi(receipt)
    if current:
        check_pdi_version(current, pdi_id)
    elif pdi_id is not None:
        raise ValidationError('Chưa có PDI tương ứng để cập nhật.')
    if not all(isinstance(value, str) for value in (tinh_trang, ket_qua, ghi_chu)):
        raise ValidationError('Tình trạng, kết quả và ghi chú PDI phải là chuỗi.')
    if ket_qua == 'DAT' and receipt.cac_lan_pdi.filter(ket_qua='KHONG_DAT').exists():
        errors = incident_warnings(receipt, current)
        # Kiểm tra hồ sơ trước khi cho ghi lần kiểm tra lại đạt.
        if errors and 'hoàn tất hồ sơ' in errors[0]:
            raise ValidationError(errors)
    pdi = KetQuaPDI(phieu_nhap=receipt, tinh_trang=tinh_trang, ket_qua=ket_qua,
                   ghi_chu=ghi_chu, nguoi_kiem_tra=user, hang_muc=[] if hang_muc is None else hang_muc)
    pdi.full_clean()
    pdi.save()
    # Mỗi lần kiểm tra mới cần duyệt lại, không ghi đè lịch sử cũ.
    receipt.trang_thai = 'NHAP'
    receipt.save(update_fields=['trang_thai'])
    return pdi


@transaction.atomic
def approve_pdi(user, receipt_id, *, pdi_id):
    require_role(user, WAREHOUSE)
    require_permission(user, 'warehouse.approve_ketquapdi')
    receipt = lock_receipt(receipt_id)
    require_branch(user, receipt.kho)
    if receipt.trang_thai == 'DA_DUYET':
        raise ValidationError('Phiếu nhập đã duyệt.')
    pdi = latest_pdi(receipt)
    if pdi is None or pdi.nguoi_duyet_id is not None:
        raise ValidationError('Không có PDI mới chờ duyệt.')
    check_pdi_version(pdi, pdi_id)
    if pdi.ket_qua != 'DAT':
        raise ValidationError('PDI không đạt: giữ phiếu Nháp và chuyển xử lý sự cố vận chuyển.')
    incident_errors = incident_warnings(receipt, pdi)
    if incident_errors:
        raise ValidationError(incident_errors)
    warnings = pdi_warnings(pdi)
    if warnings:
        raise ValidationError(warnings)
    pdi.full_clean()
    pdi.nguoi_duyet = user
    pdi.thoi_gian_duyet = timezone.now()
    pdi.save(update_fields=['nguoi_duyet', 'thoi_gian_duyet'])
    return pdi


@transaction.atomic
def submit_receipt(user, receipt_id, *, pdi_id):
    require_role(user, WAREHOUSE)
    require_permission(user, 'warehouse.change_phieunhapkho')
    receipt = lock_receipt(receipt_id)
    require_branch(user, receipt.kho)
    if receipt.trang_thai != 'NHAP' or not ready_pdi(receipt):
        raise ValidationError('Chỉ gửi phiếu nháp có PDI mới nhất đạt và đã duyệt.')
    check_pdi_version(latest_pdi(receipt), pdi_id)
    validate_receipt_data(receipt)
    receipt.trang_thai = 'CHO_DUYET'
    receipt.save(update_fields=['trang_thai'])
    return receipt


@transaction.atomic
def approve_receipt(user, receipt_id, *, pdi_id):
    require_role(user, SALE_ADMIN)
    require_permission(user, 'warehouse.approve_phieunhapkho')
    receipt = lock_receipt(receipt_id)
    if not is_da_nang_branch(receipt.kho.chi_nhanh):
        raise ValidationError('Kho nhận phải là Dana Ford Đà Nẵng.')
    if receipt.trang_thai != 'CHO_DUYET' or not ready_pdi(receipt):
        raise ValidationError('Phiếu chưa đủ điều kiện duyệt hoặc đã duyệt.')
    check_pdi_version(latest_pdi(receipt), pdi_id)
    validate_receipt_data(receipt)
    line = ChiTietNhap.objects.select_for_update().select_related('hoa_don_nhap').get(pk=receipt.chi_tiet_nhap_id)
    if line.xe_id != receipt.xe_id or line.so_luong_nhap != 1:
        raise ValidationError('Dữ liệu hóa đơn, VIN hoặc kho không còn khớp.')
    if TonKho.objects.filter(xe_id=receipt.xe_id, so_luong_ton__gt=0).exists():
        raise ValidationError('VIN đã tồn tại trong kho, không thể nhập trùng.')
    stock, _ = TonKho.objects.get_or_create(kho_id=receipt.kho_id, xe_id=receipt.xe_id,
                   defaults={'ngay_vao_kho': receipt.ngay_nhap, 'so_luong_ton': 0})
    # Điều kiện cập nhật cũng bảo vệ trước yêu cầu đồng thời trên SQLite.
    if TonKho.objects.filter(pk=stock.pk, so_luong_ton=0).update(so_luong_ton=1, ngay_vao_kho=receipt.ngay_nhap) != 1:
        raise ValidationError('Tồn kho vừa thay đổi, vui lòng kiểm tra lại.')
    now = timezone.now()
    LichSuNhapKho.objects.create(phieu_nhap=receipt, xe_id=receipt.xe_id, kho_id=receipt.kho_id,
                                 nguoi_thuc_hien=user, thoi_gian=now)
    receipt.trang_thai = 'DA_DUYET'
    receipt.nguoi_duyet = user
    receipt.thoi_gian_duyet = now
    receipt.save(update_fields=['trang_thai', 'nguoi_duyet', 'thoi_gian_duyet'])
    return receipt
