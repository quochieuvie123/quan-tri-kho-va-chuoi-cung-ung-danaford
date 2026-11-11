"""Đọc và nhập file PDI xưởng; mỗi lô được áp dụng nguyên tử."""
from datetime import date, datetime
from io import BytesIO

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from openpyxl import load_workbook

from database.models import BienBanPDI, NhanVien, TonKho, TrangThaiXe, Xe
from incidents.models import LOAI_SU_CO
from .models import KetQuaPDI, LichSuNhapKho, PhieuNhapKho
from . import nhap_services as services

HEADERS = ('ma_phieu', 'vin', 'ma_pdi', 'ngay_kiem_dinh', 'nguoi_kiem_dinh',
           'ngoai_that', 'noi_that', 'van_hanh', 'ket_qua', 'loai_su_co', 'mo_ta_su_co', 'ghi_chu')


def read_file(content):
    try:
        book = load_workbook(BytesIO(content), read_only=True, data_only=True)
        try:
            rows = list(book.active.iter_rows(max_row=502, max_col=12, values_only=True))
        finally:
            book.close()
    except Exception as exc:
        raise ValidationError('Không đọc được file Excel .xlsx hợp lệ.') from exc
    if not rows or tuple(rows[0]) != HEADERS:
        raise ValidationError('Tên cột hoặc thứ tự cột không khớp file PDI mẫu.')
    if len(rows) > 501:
        raise ValidationError('File tối đa 500 dòng xe.')
    output, seen_vin, seen_code, seen_pdi = [], set(), set(), set()
    for number, values in enumerate(rows[1:], 2):
        if not any(value is not None for value in values):
            continue
        row = dict(zip(HEADERS, values))
        for key in HEADERS:
            if key != 'ngay_kiem_dinh':
                row[key] = str(row[key] or '').strip()
        day = row['ngay_kiem_dinh']
        if isinstance(day, datetime):
            day = day.date()
        if not isinstance(day, date):
            raise ValidationError(f'Dòng {number}: ngày kiểm định phải là ngày Excel hợp lệ.')
        row['ngay_kiem_dinh'] = day.isoformat()
        if not all(row[key] for key in ('ma_phieu', 'vin', 'ma_pdi', 'nguoi_kiem_dinh')):
            raise ValidationError(f'Dòng {number}: thiếu mã phiếu, VIN, mã PDI hoặc người kiểm định.')
        if len(row['ma_pdi']) > 50 or row['vin'] in seen_vin or row['ma_phieu'] in seen_code or row['ma_pdi'] in seen_pdi:
            raise ValidationError(f'Dòng {number}: VIN, mã phiếu hoặc mã PDI trùng/không hợp lệ.')
        seen_vin.add(row['vin']); seen_code.add(row['ma_phieu']); seen_pdi.add(row['ma_pdi'])
        results = [row[key] for key in ('ngoai_that', 'noi_that', 'van_hanh')]
        if any(value not in ('DAT', 'KHONG_DAT') for value in results + [row['ket_qua']]):
            raise ValidationError(f'Dòng {number}: kết quả chỉ được là DAT hoặc KHONG_DAT.')
        if (row['ket_qua'] == 'DAT') != all(value == 'DAT' for value in results):
            raise ValidationError(f'Dòng {number}: kết quả tổng không khớp các hạng mục.')
        if row['ket_qua'] == 'KHONG_DAT' and (row['loai_su_co'] not in LOAI_SU_CO or not row['mo_ta_su_co']):
            raise ValidationError(f'Dòng {number}: xe không đạt cần loại sự cố hợp lệ và mô tả.')
        row['dong'] = number
        output.append(row)
    if not output:
        raise ValidationError('File không có dữ liệu PDI.')
    return output


def employee_for(user, employee_id=None):
    employee = getattr(user, 'nhan_vien', None)
    if employee is None and user.is_superuser and employee_id:
        employee = NhanVien.objects.filter(pk=employee_id).first()
    if employee is None:
        raise ValidationError('Hãy chọn nhân viên kho ghi nhận PDI; hoặc dùng tài khoản đã liên kết nhân viên.')
    return employee


def validate_rows(user, rows, employee_id=None):
    services.require_permission(user, 'warehouse.add_ketquapdi')
    services.require_permission(user, 'warehouse.approve_ketquapdi')
    employee = employee_for(user, employee_id)
    for row in rows:
        receipt = PhieuNhapKho.objects.select_related('kho__chi_nhanh', 'chi_tiet_nhap').filter(
            ma_phieu=row['ma_phieu'], xe_id=row['vin']).first()
        if not receipt:
            raise ValidationError(f"Dòng {row['dong']}: mã phiếu và VIN không khớp.")
        services.require_branch(user, receipt.kho)
        if employee.chi_nhanh_id != receipt.kho.chi_nhanh_id:
            raise ValidationError(f"Dòng {row['dong']}: nhân viên ghi nhận phải thuộc chi nhánh kho nhận.")
        if receipt.trang_thai != 'NHAP' or receipt.cac_lan_pdi.exists():
            raise ValidationError(f"Dòng {row['dong']}: phiếu đã có PDI hoặc không còn ở trạng thái chờ.")
        if BienBanPDI.objects.filter(pk=row['ma_pdi']).exists():
            raise ValidationError(f"Dòng {row['dong']}: mã PDI đã được sử dụng.")
        if BienBanPDI.objects.filter(xe_id=row['vin']).exclude(trang_thai_claim='Đã xử lý').exists():
            raise ValidationError(f"Dòng {row['dong']}: xe còn sự cố chưa đóng.")
        if TonKho.objects.filter(xe_id=row['vin'], so_luong_ton__gt=0).exists():
            raise ValidationError(f"Dòng {row['dong']}: xe đã có tồn kho.")


@transaction.atomic
def import_rows(user, rows, employee_id=None):
    # Lock xe và phiếu trước khi kiểm tra lại, bao gồm các thay đổi từ lần xem trước.
    list(Xe.objects.select_for_update().filter(pk__in=sorted(row['vin'] for row in rows)).order_by('pk'))
    list(PhieuNhapKho.objects.select_for_update().filter(ma_phieu__in=[row['ma_phieu'] for row in rows]).order_by('pk'))
    validate_rows(user, rows, employee_id)
    employee = employee_for(user, employee_id)
    for row in rows:
        receipt = PhieuNhapKho.objects.select_related('chi_tiet_nhap').get(ma_phieu=row['ma_phieu'], xe_id=row['vin'])
        items = [dict(hang_muc=label, tinh_trang='Đạt' if row[key] == 'DAT' else 'Không đạt',
                      ket_qua=row[key], ghi_chu='') for key, label in
                 [('ngoai_that', 'Ngoại thất'), ('noi_that', 'Nội thất'), ('van_hanh', 'Vận hành')]]
        note = f"Mã PDI xưởng: {row['ma_pdi']}; ngày kiểm định: {row['ngay_kiem_dinh']}; người kiểm định: {row['nguoi_kiem_dinh']}. {row['ghi_chu']}"
        pdi = services.record_pdi(user, receipt.pk, tinh_trang='Đạt' if row['ket_qua'] == 'DAT' else row['mo_ta_su_co'],
                                  ket_qua=row['ket_qua'], ghi_chu=note, hang_muc=items)
        services.approve_pdi(user, receipt.pk, pdi_id=pdi.pk)
        if row['ket_qua'] == 'KHONG_DAT':
            BienBanPDI.objects.create(ma_pdi=row['ma_pdi'], hoa_don_nhap_id=receipt.chi_tiet_nhap.hoa_don_nhap_id,
                xe_id=row['vin'], nhan_vien=employee, ngay_ghi_nhan=timezone.now(), loai_su_co=row['loai_su_co'],
                mo_ta_chi_tiet=row['mo_ta_su_co'], trang_thai_claim='Chưa xử lý')
            continue
        services.validate_receipt_data(receipt)
        stock, _ = TonKho.objects.get_or_create(kho=receipt.kho, xe_id=row['vin'], defaults={
            'ngay_vao_kho': receipt.ngay_nhap, 'so_luong_ton': 0})
        if TonKho.objects.filter(pk=stock.pk, so_luong_ton=0).update(so_luong_ton=1, ngay_vao_kho=receipt.ngay_nhap) != 1:
            raise ValidationError(f"VIN {row['vin']} đã có tồn kho.")
        now = timezone.now()
        LichSuNhapKho.objects.create(phieu_nhap=receipt, xe_id=row['vin'], kho=receipt.kho, nguoi_thuc_hien=user, thoi_gian=now)
        receipt.trang_thai = 'DA_DUYET'; receipt.nguoi_duyet = user; receipt.thoi_gian_duyet = now
        receipt.save(update_fields=['trang_thai', 'nguoi_duyet', 'thoi_gian_duyet'])
        Xe.objects.filter(pk=row['vin']).update(trang_thai=TrangThaiXe.SAN_SANG)
        from contracts.workflow import sync_contract_for_vin
        sync_contract_for_vin(row['vin'])
