"""Dữ liệu cho các ô và hộp thoại Figma; không tạo dữ liệu nghiệp vụ giả."""
from warehouse.models import LichSuNhapKho


def stock_data(stock):
    car = stock.xe
    latest = LichSuNhapKho.objects.filter(xe=car, kho=stock.kho).select_related('phieu_nhap').order_by('-thoi_gian', '-pk').first()
    # Tồn cũ chỉ chứng minh còn xe, không tự chứng minh PDI/giữ chỗ.
    state = 'CON_TON_CAN_KIEM_TRA'
    label = 'Còn tồn — cần kiểm tra trạng thái'
    if latest and latest.phieu_nhap.trang_thai == 'DA_DUYET':
        state, label = 'DA_NHAP_KHO', 'Đã nhập kho'
    return {
        'xe_id': car.pk, 'vin': car.pk, 'xe__ten_xe': car.ten_xe,
        'xe__phien_ban': car.phien_ban, 'xe__loai_xe': car.loai_xe,
        'xe__mau_sac': car.mau_sac, 'so_may': car.so_may,
        'kho_id': stock.kho_id, 'vi_tri_kho': stock.kho.chi_nhanh.ten_cn,
        'so_luong_ton': stock.so_luong_ton, 'trang_thai_xe': state,
        'trang_thai_hien_thi': label,
    }
