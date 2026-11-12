"""Excel import for contract and customer data using existing database columns only."""
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from openpyxl import load_workbook

from database.models import ChiNhanh, HopDong, KhachHang, TrangThaiHopDong

HEADERS = ('ma_hop_dong', 'ma_khach_hang', 'ten_khach_hang', 'sdt_khach_hang', 'mst_khach_hang',
           'ma_chi_nhanh', 'ngay_ky', 'so_tien_coc', 'dong_xe_yeu_cau', 'phien_ban_yeu_cau',
           'mau_sac_yeu_cau')


def _day(value, number, label):
    if isinstance(value, datetime): return value.date()
    if isinstance(value, date): return value
    raise ValidationError(f'Dòng {number}: {label} phải là ngày Excel hợp lệ.')


def read_file(content):
    try:
        workbook = load_workbook(BytesIO(content), read_only=True, data_only=True)
        try: rows = list(workbook.active.iter_rows(max_row=502, max_col=len(HEADERS), values_only=True))
        finally: workbook.close()
    except Exception as exc:
        raise ValidationError('Không đọc được file Excel .xlsx hợp lệ.') from exc
    if not rows or tuple(rows[0]) != HEADERS:
        raise ValidationError('Tên cột hoặc thứ tự cột không đúng file mẫu hợp đồng.')
    if len(rows) > 501: raise ValidationError('File tối đa 500 hợp đồng.')
    output, codes = [], set()
    for number, values in enumerate(rows[1:], 2):
        if not any(value is not None for value in values): continue
        row = dict(zip(HEADERS, values))
        for key in HEADERS:
            if key not in ('ngay_ky', 'ngay_du_kien_giao', 'so_tien_coc'):
                row[key] = str(row[key] or '').strip()
        row['ngay_ky'] = _day(row['ngay_ky'], number, 'ngày ký')
        try: row['so_tien_coc'] = Decimal(str(row['so_tien_coc']))
        except (InvalidOperation, ValueError): raise ValidationError(f'Dòng {number}: số tiền cọc không hợp lệ.')
        required = ('ma_hop_dong', 'ma_khach_hang', 'ten_khach_hang', 'sdt_khach_hang', 'ma_chi_nhanh',
                    'dong_xe_yeu_cau', 'phien_ban_yeu_cau', 'mau_sac_yeu_cau')
        if not all(row[key] for key in required) or row['so_tien_coc'] < 0:
            raise ValidationError(f'Dòng {number}: thiếu dữ liệu bắt buộc hoặc số tiền cọc âm.')
        if len(row['sdt_khach_hang']) != 10 or not row['sdt_khach_hang'].isdigit():
            raise ValidationError(f'Dòng {number}: số điện thoại khách hàng phải gồm 10 chữ số.')
        if row['ma_hop_dong'] in codes: raise ValidationError(f'Dòng {number}: mã hợp đồng trùng trong file.')
        codes.add(row['ma_hop_dong']); row['dong'] = number; output.append(row)
    if not output: raise ValidationError('File không có dữ liệu hợp đồng.')
    return output


def validate_rows(rows):
    for row in rows:
        if HopDong.objects.filter(pk=row['ma_hop_dong']).exists(): raise ValidationError(f"Dòng {row['dong']}: mã hợp đồng đã tồn tại.")
        if not ChiNhanh.objects.filter(pk=row['ma_chi_nhanh']).exists(): raise ValidationError(f"Dòng {row['dong']}: chi nhánh không tồn tại.")
        if row['mst_khach_hang'] and KhachHang.objects.filter(mst_kh=row['mst_khach_hang']).exclude(ma_kh=row['ma_khach_hang']).exists():
            raise ValidationError(f"Dòng {row['dong']}: mã số thuế đã thuộc về khách hàng khác; hãy để trống hoặc dùng mã khách hàng tương ứng.")


@transaction.atomic
def import_rows(rows):
    validate_rows(rows)
    for row in rows:
        customer, created = KhachHang.objects.get_or_create(
            ma_kh=row['ma_khach_hang'],
            defaults={'ten_kh': row['ten_khach_hang'], 'sdt_kh': row['sdt_khach_hang'], 'mst_kh': row['mst_khach_hang'] or None},
        )
        if not created and (customer.ten_kh != row['ten_khach_hang'] or customer.sdt_kh != row['sdt_khach_hang']):
            raise ValidationError(f"Dòng {row['dong']}: mã khách hàng đã có nhưng tên hoặc số điện thoại không khớp.")
        HopDong.objects.create(ma_hd=row['ma_hop_dong'], khach_hang=customer, chi_nhanh_id=row['ma_chi_nhanh'],
            ngay_ky=timezone.make_aware(datetime.combine(row['ngay_ky'], datetime.min.time())),
            so_tien_coc=row['so_tien_coc'], trang_thai=TrangThaiHopDong.CHO_XU_LY,
            dong_xe_yeu_cau=row['dong_xe_yeu_cau'], phien_ban_yeu_cau=row['phien_ban_yeu_cau'],
            mau_sac_yeu_cau=row['mau_sac_yeu_cau'])
