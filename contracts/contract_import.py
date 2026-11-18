"""Excel import for contract and customer data using existing database columns only."""
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO
import re

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from openpyxl import load_workbook

from database.models import ChiNhanh, HopDong, KhachHang, TrangThaiHopDong

HEADERS = ('ma_hop_dong', 'ma_khach_hang', 'ten_khach_hang', 'sdt_khach_hang', 'mst_khach_hang',
           'ma_chi_nhanh', 'ngay_ky', 'so_tien_coc', 'dong_xe_yeu_cau', 'phien_ban_yeu_cau',
           'mau_sac_yeu_cau')

HEADER_ALIASES = {
    'ma_hop_dong': {'ma_hop_dong', 'ma hop dong', 'ma_hd', 'ma hd', 'mã hợp đồng', 'mã hđ'},
    'ma_khach_hang': {'ma_khach_hang', 'ma khach hang', 'ma_kh', 'ma kh', 'mã khách hàng'},
    'ten_khach_hang': {'ten_khach_hang', 'ten khach hang', 'ten_kh', 'tên khách hàng'},
    'sdt_khach_hang': {'sdt_khach_hang', 'sdt khach hang', 'sdt', 'so dien thoai', 'số điện thoại', 'sđt'},
    'mst_khach_hang': {'mst_khach_hang', 'mst khach hang', 'mst', 'ma so thue', 'mã số thuế'},
    'ma_chi_nhanh': {'ma_chi_nhanh', 'ma chi nhanh', 'ma_cn', 'mã chi nhánh', 'chi nhánh'},
    'ngay_ky': {'ngay_ky', 'ngay ky', 'ngày ký', 'ngày ký hợp đồng'},
    'so_tien_coc': {'so_tien_coc', 'so tien coc', 'tien coc', 'số tiền cọc', 'tiền đặt cọc'},
    'dong_xe_yeu_cau': {'dong_xe_yeu_cau', 'dong xe yeu cau', 'dong xe', 'dòng xe', 'dòng xe yêu cầu'},
    'phien_ban_yeu_cau': {'phien_ban_yeu_cau', 'phien ban yeu cau', 'phien ban', 'phiên bản', 'phiên bản yêu cầu'},
    'mau_sac_yeu_cau': {'mau_sac_yeu_cau', 'mau sac yeu cau', 'mau sac', 'màu sắc', 'màu sắc yêu cầu'},
}


def _norm_header(val):
    return re.sub(r'\s+', ' ', str(val or '').strip().lower())


def _day(value, number, label):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        text = value.strip()
        for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y', '%Y/%m/%d'):
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                continue
    raise ValidationError(f'Dòng {number}: {label} phải là ngày Excel hợp lệ.')


def _parse_money(value, number):
    if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
        return Decimal(str(value))
    text = str(value or '').strip().replace(' ', '')
    if not text:
        raise InvalidOperation('empty')
    # Hỗ trợ nhập chuỗi kiểu 600.000.000 hoặc 600,000,000
    if re.fullmatch(r'-?\d{1,3}(\.\d{3})+', text):
        text = text.replace('.', '')
    elif re.fullmatch(r'-?\d{1,3}(,\d{3})+', text):
        text = text.replace(',', '')
    return Decimal(text)


def read_file(content):
    try:
        workbook = load_workbook(BytesIO(content), read_only=True, data_only=True)
        try:
            rows = list(workbook.active.iter_rows(max_row=502, values_only=True))
        finally:
            workbook.close()
    except Exception as exc:
        raise ValidationError('Không đọc được file Excel .xlsx hợp lệ.') from exc
    if not rows:
        raise ValidationError('Tên cột hoặc thứ tự cột không đúng file mẫu hợp đồng.')

    header_row = rows[0]
    col_map = {}
    if tuple(header_row[:len(HEADERS)]) == HEADERS:
        col_map = {h: idx for idx, h in enumerate(HEADERS)}
    else:
        for idx, raw_cell in enumerate(header_row):
            norm = _norm_header(raw_cell)
            for canonical, aliases in HEADER_ALIASES.items():
                if canonical not in col_map and norm in aliases:
                    col_map[canonical] = idx
                    break

    if len(col_map) != len(HEADERS):
        raise ValidationError('Tên cột hoặc thứ tự cột không đúng file mẫu hợp đồng.')
    if len(rows) > 501:
        raise ValidationError('File tối đa 500 hợp đồng.')

    output, codes = [], set()
    for number, values in enumerate(rows[1:], 2):
        if not any(value is not None for value in values):
            continue
        row = {key: (values[idx] if idx < len(values) else None) for key, idx in col_map.items()}
        for key in HEADERS:
            if key not in ('ngay_ky', 'ngay_du_kien_giao', 'so_tien_coc'):
                row[key] = str(row[key] or '').strip()
        row['ngay_ky'] = _day(row['ngay_ky'], number, 'ngày ký')
        try:
            row['so_tien_coc'] = _parse_money(row['so_tien_coc'], number)
        except (InvalidOperation, ValueError):
            raise ValidationError(f'Dòng {number}: số tiền cọc không hợp lệ.')
        required = ('ma_hop_dong', 'ma_khach_hang', 'ten_khach_hang', 'sdt_khach_hang', 'ma_chi_nhanh',
                    'dong_xe_yeu_cau', 'phien_ban_yeu_cau', 'mau_sac_yeu_cau')
        if not all(row[key] for key in required) or row['so_tien_coc'] < 0:
            raise ValidationError(f'Dòng {number}: thiếu dữ liệu bắt buộc hoặc số tiền cọc âm.')
        if len(row['sdt_khach_hang']) != 10 or not row['sdt_khach_hang'].isdigit():
            raise ValidationError(f'Dòng {number}: số điện thoại khách hàng phải gồm 10 chữ số.')
        if row['ma_hop_dong'] in codes:
            raise ValidationError(f'Dòng {number}: mã hợp đồng trùng trong file.')
        codes.add(row['ma_hop_dong'])
        row['dong'] = number
        output.append(row)
    if not output:
        raise ValidationError('File không có dữ liệu hợp đồng.')
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
