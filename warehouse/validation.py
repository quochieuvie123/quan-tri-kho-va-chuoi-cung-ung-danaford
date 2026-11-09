from django.core.exceptions import ValidationError


def validate_pdi_items(items):
    """Hạng mục tùy chọn; không coi danh sách rỗng là đã kiểm tra đạt."""
    if not isinstance(items, list) or len(items) > 100:
        raise ValidationError('Hạng mục PDI phải là danh sách tối đa 100 mục.')
    for item in items:
        if not isinstance(item, dict) or set(item) - {'hang_muc', 'tinh_trang', 'ket_qua', 'ghi_chu'}:
            raise ValidationError('Hạng mục PDI không đúng cấu trúc.')
        if any(not isinstance(item.get(key), str) or not item[key].strip() for key in ('hang_muc', 'tinh_trang')):
            raise ValidationError('Mỗi hạng mục cần tên và tình trạng thực tế.')
        if item.get('ket_qua') not in ('DAT', 'KHONG_DAT'):
            raise ValidationError('Kết quả hạng mục phải là DAT hoặc KHONG_DAT.')
        if not isinstance(item.get('ghi_chu', ''), str):
            raise ValidationError('Ghi chú phải là chuỗi.')
