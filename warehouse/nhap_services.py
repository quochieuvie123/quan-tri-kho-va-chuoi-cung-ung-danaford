"""Mọi thay đổi nhập kho đi qua dịch vụ để kiểm tra và lưu nguyên tử."""
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone
from database.models import Xe, Kho, ChiTietNhap, TonKho, BienBanPDI, TrangThaiXe
from core.iii_iv_access import require_role, can_write_warehouse, is_da_nang_branch, SALE_ADMIN, WAREHOUSE
from .models import PhieuNhapKho, KetQuaPDI, LichSuNhapKho
from .validation import validate_pdi_items


def require_permission(user, codename):
    from core.roles import get_user_role_info
    role = get_user_role_info(user)
    if not user.is_authenticated or not user.is_active or (role and role.get('is_read_only')) or not user.has_perm(codename):
        raise PermissionDenied('Bạn không có quyền thực hiện thao tác này.')


def require_branch(user, kho):
    if not is_da_nang_branch(kho.chi_nhanh):
        raise ValidationError('Kho nhận phải là Dana Ford Đà Nẵng.')
    if not can_write_warehouse(user, kho):
        raise PermissionDenied('Tài khoản chưa được gắn nhân viên tại chi nhánh của kho này.')


def incident_rows(receipt):
    if getattr(receipt, 'loai_nguon', None) == PhieuNhapKho.LoaiNguon.LUU_CHUYEN or receipt.lenh_luu_chuyen_id:
        return BienBanPDI.objects.filter(lenh_luu_chuyen_id=receipt.lenh_luu_chuyen_id, xe_id=receipt.xe_id)
    if receipt.chi_tiet_nhap_id:
        return BienBanPDI.objects.filter(hoa_don_nhap_id=receipt.chi_tiet_nhap.hoa_don_nhap_id, xe_id=receipt.xe_id)
    return BienBanPDI.objects.filter(xe_id=receipt.xe_id)


def lock_receipt(pk):
    vin = PhieuNhapKho.objects.values_list('xe_id', flat=True).get(pk=pk)
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
    if BienBanPDI.objects.filter(xe_id=receipt.xe_id).exclude(trang_thai_claim='Đã xử lý').exists():
        return ['VIN còn sự cố chưa đóng; cần hoàn tất hồ sơ xử lý sự cố trước khi duyệt PDI lại.']
    failures = receipt.cac_lan_pdi.filter(ket_qua='KHONG_DAT')
    if not failures.exists():
        return []
    first_failure = failures.order_by('thoi_gian_kiem_tra').first()
    incidents = incident_rows(receipt).filter(ngay_ghi_nhan__gte=first_failure.thoi_gian_kiem_tra)
    if not incidents.exists() or incidents.exclude(trang_thai_claim='Đã xử lý').exists():
        return ['PDI không đạt: cần hoàn tất hồ sơ xử lý sự cố vận chuyển trước khi duyệt PDI lại.']
    if pdi is None or pdi.ket_qua != 'DAT':
        return ['Cần kiểm tra PDI lại và có kết quả Đạt sau khi xử lý sự cố.']
    # Ngày đóng trong hồ sơ và thời điểm nhật ký đều phải trước lần kiểm tra lại.
    if incidents.filter(ho_so__ngay_xac_nhan__gt=timezone.localtime(pdi.thoi_gian_kiem_tra).date()).exists() or incidents.filter(
        lich_su__hanh_dong='Cập nhật kết quả xử lý, đóng sự cố',
        lich_su__thoi_gian__gte=pdi.thoi_gian_kiem_tra,
    ).exists():
        return ['PDI phải được kiểm tra lại sau khi sự cố hoàn tất.']
    return []


def check_pdi_version(pdi, expected_id):
    if expected_id is None or str(pdi.pk) != str(expected_id):
        raise ValidationError('PDI đã thay đổi hoặc chưa xác nhận PDI đang xem; tải lại PDI mới nhất.')


def hoan_tat_lenh_tu_nhap_kho(lenh, user):
    """Chuyển trạng thái Lệnh lưu chuyển sang HOAN_TAT khi phiếu nhập kho được hoàn tất."""
    if not lenh:
        return None
    from transfers.models import LenhLuuChuyen
    from transfers.services import ghi_thong_bao

    lenh_obj = LenhLuuChuyen.objects.select_for_update().get(pk=lenh.pk)
    expected_vins = set(lenh_obj.chi_tiet.values_list('xe_id', flat=True))
    approved_vins = set(PhieuNhapKho.objects.filter(
        lenh_luu_chuyen=lenh_obj, trang_thai=PhieuNhapKho.TrangThai.DA_DUYET,
    ).values_list('xe_id', flat=True))
    if not expected_vins or not expected_vins.issubset(approved_vins):
        return lenh_obj
    if lenh_obj.trang_thai != LenhLuuChuyen.TrangThai.HOAN_TAT:
        lenh_obj.trang_thai = LenhLuuChuyen.TrangThai.HOAN_TAT
        lenh_obj.save(update_fields=['trang_thai'])
        ghi_thong_bao(
            user,
            "Hoàn tất lưu chuyển xe",
            f"Phiếu nhập kho cho xe thuộc lệnh {lenh_obj.ma_lenh} đã hoàn tất kiểm định và nhập kho Đà Nẵng.",
            loai="THANH_CONG"
        )
    return lenh_obj


def receipt_warnings(receipt):
    car = receipt.xe
    if getattr(receipt, 'loai_nguon', None) == PhieuNhapKho.LoaiNguon.LUU_CHUYEN or receipt.lenh_luu_chuyen_id:
        lenh = receipt.lenh_luu_chuyen
        source_name = lenh.kho_xuat.chi_nhanh.ten_cn if (lenh and lenh.kho_xuat and lenh.kho_xuat.chi_nhanh) else (lenh.kho_xuat.ten_kho if (lenh and lenh.kho_xuat) else "Lưu chuyển nội bộ")
    else:
        source_name = receipt.chi_tiet_nhap.hoa_don_nhap.nha_cung_cap.ten_ncc if receipt.chi_tiet_nhap else ""
    required = [car.ten_xe, car.mau_sac, car.so_may, source_name]
    if not all(isinstance(value, str) and value.strip() for value in required):
        return ['Thiếu dòng xe, màu sắc, số máy hoặc nguồn xe; cần bổ sung trước khi gửi/duyệt nhập.']
    return []


def validate_receipt_data(receipt):
    receipt.full_clean()
    warnings = receipt_warnings(receipt)
    if warnings:
        raise ValidationError(warnings)


@transaction.atomic
def create_receipt(user, *, ma_phieu, kho_id, ngay_nhap, chi_tiet_nhap_id=None, lenh_luu_chuyen_id=None, xe_id=None):
    require_role(user, WAREHOUSE)
    require_permission(user, 'warehouse.add_phieunhapkho')
    if not isinstance(ma_phieu, str):
        raise ValidationError('Mã phiếu phải là chuỗi.')
    kho = Kho.objects.select_related('chi_nhanh').get(pk=kho_id)
    require_branch(user, kho)

    # Đảm bảo XOR: nhận chi_tiet_nhap HOẶC lenh_luu_chuyen, không được cả hai, không được thiếu cả hai
    has_hdn = bool(chi_tiet_nhap_id)
    has_lenh = bool(lenh_luu_chuyen_id)
    if has_hdn == has_lenh:
        raise ValidationError('Phải chọn chính xác một nguồn nhập: Chi tiết hóa đơn nhập HOẶC Lệnh lưu chuyển.')

    if has_hdn:
        line = ChiTietNhap.objects.select_for_update().select_related('hoa_don_nhap').get(pk=chi_tiet_nhap_id)
        if line.so_luong_nhap != 1 or line.hoa_don_nhap.chi_nhanh_id != kho.chi_nhanh_id:
            raise ValidationError('Chứng từ phải đúng chi nhánh và một xe theo VIN.')
        if PhieuNhapKho.objects.filter(chi_tiet_nhap=line).exists():
            raise ValidationError('Chứng từ nguồn đã được dùng; mở phiếu hiện có.')
        target_vin = line.xe_id
        loai_nguon = PhieuNhapKho.LoaiNguon.HOA_DON
        lenh = None
    else:
        from transfers.models import LenhLuuChuyen
        lenh = LenhLuuChuyen.objects.select_for_update().select_related('kho_nhap__chi_nhanh').get(pk=lenh_luu_chuyen_id)
        if lenh.trang_thai not in (
            LenhLuuChuyen.TrangThai.DA_DUYET,
            LenhLuuChuyen.TrangThai.DANG_VAN_CHUYEN,
            LenhLuuChuyen.TrangThai.DA_GIAO_DEN_DA_NANG,
        ):
            raise ValidationError('Chỉ được tạo phiếu nhập cho lệnh lưu chuyển đã được phê duyệt.')
        if lenh.kho_nhap_id != kho.pk and lenh.kho_nhap.chi_nhanh_id != kho.chi_nhanh_id:
            raise ValidationError('Lệnh lưu chuyển không có điểm đến tại kho nhận này.')
        if not xe_id:
            raise ValidationError('Phải chọn số khung VIN cần nhập từ lệnh lưu chuyển.')
        target_vin = str(xe_id).strip()
        if not lenh.chi_tiet.filter(xe_id=target_vin).exists():
            raise ValidationError('Xe không thuộc lệnh lưu chuyển này.')
        if PhieuNhapKho.objects.filter(lenh_luu_chuyen=lenh, xe_id=target_vin).exists():
            raise ValidationError('Xe này trong lệnh lưu chuyển đã có phiếu nhập; mở phiếu hiện có.')
        loai_nguon = PhieuNhapKho.LoaiNguon.LUU_CHUYEN
        line = None

    car = Xe.objects.select_for_update().get(pk=target_vin)
    if has_hdn:
        if car.trang_thai in (TrangThaiXe.DA_XUAT, TrangThaiXe.GIU_CHO_XUAT):
            raise ValidationError('Xe đã xuất hoặc đang giữ cho phiếu xuất.')
    else:
        if car.trang_thai == TrangThaiXe.DA_XUAT:
            raise ValidationError('Xe đã xuất.')
    if PhieuNhapKho.objects.filter(xe_id=target_vin, trang_thai__in=['NHAP', 'CHO_DUYET']).exists():
        raise ValidationError('VIN này đang có phiếu nhập chưa hoàn tất.')
    if TonKho.objects.filter(xe_id=target_vin, so_luong_ton__gt=0).exists():
        raise ValidationError('VIN đã có tồn kho; không được nhập trùng.')

    receipt = PhieuNhapKho(ma_phieu=ma_phieu.strip(), xe_id=target_vin,
                           kho=kho, ngay_nhap=ngay_nhap, nguoi_lap=user,
                           loai_nguon=loai_nguon, chi_tiet_nhap=line, lenh_luu_chuyen=lenh)
    validate_receipt_data(receipt)
    receipt.save()
    return receipt


@transaction.atomic
def record_pdi(user, receipt_id, *, tinh_trang, ket_qua, ghi_chu, hang_muc=None, pdi_id=None):
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
        if errors and 'hoàn tất hồ sơ' in errors[0]:
            raise ValidationError(errors)
    pdi = KetQuaPDI(phieu_nhap=receipt, tinh_trang=tinh_trang, ket_qua=ket_qua,
                   ghi_chu=ghi_chu, nguoi_kiem_tra=user, hang_muc=[] if hang_muc is None else hang_muc)
    pdi.full_clean()
    pdi.save()
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
    incident_errors = incident_warnings(receipt, pdi) if pdi.ket_qua == 'DAT' else []
    if incident_errors:
        raise ValidationError(incident_errors)
    warnings = pdi_warnings(pdi)
    if warnings:
        raise ValidationError(warnings)
    pdi.full_clean()
    pdi.nguoi_duyet = user
    pdi.thoi_gian_duyet = timezone.now()
    pdi.save(update_fields=['nguoi_duyet', 'thoi_gian_duyet'])
    if pdi.ket_qua == 'KHONG_DAT':
        Xe.objects.filter(pk=receipt.xe_id).update(trang_thai=TrangThaiXe.SU_CO_PDI)
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
    if receipt.loai_nguon == PhieuNhapKho.LoaiNguon.HOA_DON:
        line = ChiTietNhap.objects.select_for_update().get(pk=receipt.chi_tiet_nhap_id)
        if line.xe_id != receipt.xe_id or line.so_luong_nhap != 1:
            raise ValidationError('Chứng từ nguồn không còn khớp VIN.')
    elif receipt.loai_nguon == PhieuNhapKho.LoaiNguon.LUU_CHUYEN:
        lenh = receipt.lenh_luu_chuyen
        if not lenh or not lenh.chi_tiet.filter(xe_id=receipt.xe_id).exists():
            raise ValidationError('Chứng từ nguồn không còn khớp VIN.')
    if receipt.loai_nguon == PhieuNhapKho.LoaiNguon.HOA_DON:
        if receipt.xe.trang_thai in (TrangThaiXe.DA_XUAT, TrangThaiXe.GIU_CHO_XUAT):
            raise ValidationError('Trạng thái xe không cho phép nhập kho.')
    else:
        if receipt.xe.trang_thai == TrangThaiXe.DA_XUAT:
            raise ValidationError('Trạng thái xe không cho phép nhập kho.')
    if BienBanPDI.objects.filter(xe_id=receipt.xe_id).exclude(trang_thai_claim='Đã xử lý').exists():
        raise ValidationError('VIN còn sự cố chưa hoàn tất.')
    if TonKho.objects.filter(xe_id=receipt.xe_id, so_luong_ton__gt=0).exists():
        raise ValidationError('VIN đã tồn tại trong kho, không thể nhập trùng.')
    stock, _ = TonKho.objects.get_or_create(kho_id=receipt.kho_id, xe_id=receipt.xe_id,
                   defaults={'ngay_vao_kho': receipt.ngay_nhap, 'so_luong_ton': 0})
    if TonKho.objects.filter(pk=stock.pk, so_luong_ton=0).update(so_luong_ton=1, ngay_vao_kho=receipt.ngay_nhap) != 1:
        raise ValidationError('Tồn kho vừa thay đổi, vui lòng kiểm tra lại.')
    Xe.objects.filter(pk=receipt.xe_id).update(trang_thai=TrangThaiXe.SAN_SANG)
    now = timezone.now()
    LichSuNhapKho.objects.create(phieu_nhap=receipt, xe_id=receipt.xe_id, kho_id=receipt.kho_id,
                                 nguoi_thuc_hien=user, thoi_gian=now)
    receipt.trang_thai = 'DA_DUYET'
    receipt.nguoi_duyet = user
    receipt.thoi_gian_duyet = now
    receipt.save(update_fields=['trang_thai', 'nguoi_duyet', 'thoi_gian_duyet'])
    if receipt.loai_nguon == PhieuNhapKho.LoaiNguon.LUU_CHUYEN and receipt.lenh_luu_chuyen:
        hoan_tat_lenh_tu_nhap_kho(receipt.lenh_luu_chuyen, user)
    from contracts.workflow import sync_contract_for_vin
    sync_contract_for_vin(receipt.xe_id)
    return receipt


@transaction.atomic
def complete_after_incident_closed(incident):
    """Đóng sự cố là xác nhận xưởng đã khắc phục và nghiệm thu xe, tự động hoàn tất nhập kho."""
    receipt = None
    if incident.hoa_don_nhap_id:
        receipt = PhieuNhapKho.objects.select_for_update().filter(
            chi_tiet_nhap__hoa_don_nhap_id=incident.hoa_don_nhap_id,
            xe_id=incident.xe_id,
        ).first()
    if receipt is None and getattr(incident, 'lenh_luu_chuyen_id', None):
        receipt = PhieuNhapKho.objects.select_for_update().filter(
            lenh_luu_chuyen_id=incident.lenh_luu_chuyen_id,
            xe_id=incident.xe_id,
        ).first()
    if receipt is None:
        receipt = PhieuNhapKho.objects.select_for_update().filter(xe_id=incident.xe_id).first()
    if receipt is None:
        return None
    if receipt.trang_thai == 'DA_DUYET':
        return receipt

    # Lấy hoặc tự động phê duyệt lần PDI kỹ thuật sau khi đã xử lý xong sự cố
    pdi = latest_pdi(receipt)
    approver = getattr(getattr(incident, 'nhan_vien', None), 'user', None) or receipt.nguoi_lap
    if pdi and not pdi.nguoi_duyet_id:
        pdi.nguoi_duyet = approver
        pdi.thoi_gian_duyet = timezone.now()
        pdi.save(update_fields=['nguoi_duyet', 'thoi_gian_duyet'])

    # Cập nhật tồn kho xe
    stock, _ = TonKho.objects.get_or_create(kho=receipt.kho, xe=receipt.xe,
        defaults={'ngay_vao_kho': timezone.localdate(), 'so_luong_ton': 0})
    TonKho.objects.filter(pk=stock.pk).update(so_luong_ton=1, ngay_vao_kho=timezone.localdate())

    # Cập nhật phiếu nhập kho sang Đã duyệt (Đã xử lý)
    receipt.trang_thai = 'DA_DUYET'
    receipt.nguoi_duyet = (pdi.nguoi_duyet if pdi and pdi.nguoi_duyet else approver)
    receipt.thoi_gian_duyet = timezone.now()
    receipt.save(update_fields=['trang_thai', 'nguoi_duyet', 'thoi_gian_duyet'])

    # Lưu lịch sử nhập kho
    LichSuNhapKho.objects.get_or_create(
        phieu_nhap=receipt,
        defaults={
            'xe': receipt.xe,
            'kho': receipt.kho,
            'nguoi_thuc_hien': receipt.nguoi_duyet,
            'thoi_gian': receipt.thoi_gian_duyet,
        }
    )

    # Đưa trạng thái xe về Sẵn sàng
    Xe.objects.filter(pk=receipt.xe_id).update(trang_thai=TrangThaiXe.SAN_SANG)

    # Nếu nguồn là Lệnh lưu chuyển -> hoàn tất lệnh
    if getattr(receipt, 'loai_nguon', None) == PhieuNhapKho.LoaiNguon.LUU_CHUYEN and receipt.lenh_luu_chuyen:
        hoan_tat_lenh_tu_nhap_kho(receipt.lenh_luu_chuyen, receipt.nguoi_duyet)

    try:
        from contracts.workflow import sync_contract_for_vin
        sync_contract_for_vin(receipt.xe_id)
    except Exception:
        pass
    return receipt
