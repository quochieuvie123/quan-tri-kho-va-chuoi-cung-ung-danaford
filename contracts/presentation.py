"""Dữ liệu cho các ô và hộp thoại Figma; không tạo dữ liệu nghiệp vụ giả."""
def stock_data(stock):
    car = stock.xe
    latest = None
    try:
        from warehouse.models import LichSuNhapKho
        latest = LichSuNhapKho.objects.filter(xe=car, kho=stock.kho).select_related('phieu_nhap').order_by('-thoi_gian', '-pk').first()
    except Exception:
        pass
    # Tồn cũ chỉ chứng minh còn xe, không tự chứng minh PDI/giữ chỗ.
    state = 'CON_TON_CAN_KIEM_TRA'
    label = 'Còn tồn — cần kiểm tra trạng thái'
    if latest and latest.phieu_nhap.trang_thai == 'DA_DUYET':
        state, label = 'DA_NHAP_KHO', 'Đã nhập kho'
    return {
        'xe_id': car.pk, 'vin': car.pk, 'xe__ten_xe': car.ten_xe,
        'xe__phien_ban': getattr(car, 'phien_ban', '') or '',
        'xe__loai_xe': getattr(car, 'loai_xe', '') or '',
        'xe__mau_sac': car.mau_sac, 'so_may': car.so_may,
        'kho_id': stock.kho_id, 'vi_tri_kho': stock.kho.chi_nhanh.ten_cn if stock.kho and stock.kho.chi_nhanh else '',
        'so_luong_ton': stock.so_luong_ton, 'trang_thai_xe': state,
        'trang_thai_hien_thi': label,
    }
