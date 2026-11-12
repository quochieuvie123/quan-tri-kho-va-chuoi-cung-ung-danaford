"""Hợp đồng dữ liệu cho giao diện; ID nội bộ và nhãn hiển thị tách biệt."""
from core.iii_iv_access import has_role, can_write_warehouse, is_da_nang_branch, SALE_ADMIN, WAREHOUSE
from . import nhap_services as services


def user_name(user):
    if user is None:
        return None
    employee = getattr(user, 'nhan_vien', None)
    return user.get_full_name() or (employee.ten_nv if employee else user.username)


def pdi_data(pdi):
    if pdi is None:
        return None
    return {
        'id': pdi.pk, 'ma_pdi_hien_thi': f'PDI-{pdi.pk:03d}',
        'phieu_nhap_id': pdi.phieu_nhap_id, 'vin': pdi.phieu_nhap.xe_id,
        'tinh_trang': pdi.tinh_trang, 'ket_qua': pdi.ket_qua,
        'ket_qua_hien_thi': pdi.get_ket_qua_display(), 'hang_muc': pdi.hang_muc,
        'ghi_chu': pdi.ghi_chu, 'nguoi_kiem_tra_id': pdi.nguoi_kiem_tra_id,
        'nguoi_kiem_tra': user_name(pdi.nguoi_kiem_tra),
        'thoi_gian_kiem_tra': pdi.thoi_gian_kiem_tra,
        'nguoi_duyet_id': pdi.nguoi_duyet_id, 'nguoi_duyet': user_name(pdi.nguoi_duyet),
        'thoi_gian_duyet': pdi.thoi_gian_duyet,
        'trang_thai_hien_thi': 'Đã duyệt' if pdi.nguoi_duyet_id else 'Chưa duyệt',
        'canh_bao': services.pdi_warnings(pdi),
    }


def receipt_data(receipt, user):
    car, warehouse = receipt.xe, receipt.kho
    invoice = receipt.chi_tiet_nhap.hoa_don_nhap
    pdi = services.latest_pdi(receipt)
    local = is_da_nang_branch(warehouse.chi_nhanh)
    worker = local and has_role(user, WAREHOUSE) and can_write_warehouse(user, warehouse)
    can_pdi = worker and (user.has_perm('warehouse.add_ketquapdi') or user.is_superuser)
    ready = services.ready_pdi(receipt, pdi=pdi)
    label = receipt.get_trang_thai_display()
    if receipt.trang_thai == 'NHAP' and pdi is None:
        label = '—'
    elif receipt.trang_thai == 'NHAP' and not ready:
        label = 'Nháp — chờ xử lý PDI'
    warnings = services.receipt_warnings(receipt)
    warnings.extend(services.incident_warnings(receipt, pdi))
    stock_exists = receipt.trang_thai != 'DA_DUYET' and car.tonkho_set.filter(so_luong_ton__gt=0).exists()
    if stock_exists:
        warnings.append('VIN đã có trong tồn kho; không được nhập trùng.')
    from core.roles import get_user_role_info
    read_only = (get_user_role_info(user) or {}).get('is_read_only', False)
    if read_only:
        worker = can_pdi = False
    return {
        'id': receipt.pk, 'ma_phieu': receipt.ma_phieu,
        'chi_tiet_nhap_id': receipt.chi_tiet_nhap_id, 'xe_id': receipt.xe_id,
        'vin': receipt.xe_id, 'dong_xe': car.ten_xe, 'phien_ban': getattr(car, 'phien_ban', '') or '',
        'mau_sac': car.mau_sac, 'so_may': car.so_may,
        'ma_hdn': invoice.pk if invoice else None,
        'so_hoa_don': invoice.so_hoa_don if invoice else None,
        'don_vi_van_chuyen': invoice.don_vi_van_chuyen.ten_dvvc if invoice else '',
        'bien_so_xe': invoice.bien_so_xe if invoice else '',
        'ten_tai_xe': invoice.ten_tai_xe if invoice else '',
        'nguon_xe': invoice.nha_cung_cap.ten_ncc,
        'kho_id': receipt.kho_id, 'ten_kho': warehouse.chi_nhanh.ten_cn if warehouse.chi_nhanh else warehouse.ma_kho,
        'ngay_lap': receipt.ngay_lap, 'ngay_nhap': receipt.ngay_nhap,
        'nguoi_lap_id': receipt.nguoi_lap_id, 'nguoi_lap': user_name(receipt.nguoi_lap),
        'trang_thai': receipt.trang_thai, 'trang_thai_hien_thi': label,
        'trang_thai_danh_sach_hien_thi': 'Đã nhập kho' if receipt.trang_thai == 'DA_DUYET' else label,
        'nguoi_duyet_id': receipt.nguoi_duyet_id, 'nguoi_duyet': user_name(receipt.nguoi_duyet),
        'thoi_gian_duyet': receipt.thoi_gian_duyet,
        'pdi_moi_nhat': pdi_data(pdi) if (user.has_perm('warehouse.view_ketquapdi') or user.is_superuser) else None,
        'trang_thai_xe_hien_thi': 'Đã nhập kho' if receipt.trang_thai == 'DA_DUYET' else 'Chưa nhập kho theo phiếu này',
        'canh_bao': warnings,
        'thao_tac': {
            'xem_chi_tiet': user.has_perms(['warehouse.view_phieunhapkho', 'warehouse.view_ketquapdi']) or user.is_superuser,
            'cap_nhat_pdi': can_pdi and receipt.trang_thai != 'DA_DUYET',
            'duyet_pdi': (worker and (user.has_perm('warehouse.approve_ketquapdi') or user.is_superuser) and pdi is not None and (pdi.ket_qua == 'KHONG_DAT' or not services.incident_warnings(receipt, pdi)) and not services.pdi_warnings(pdi) and pdi.nguoi_duyet_id is None and receipt.trang_thai != 'DA_DUYET'),
            'gui_duyet': (worker and (user.has_perm('warehouse.change_phieunhapkho') or user.is_superuser) and receipt.trang_thai == 'NHAP' and ready and not warnings),
            'duyet_nhap': (local and not read_only and (has_role(user, SALE_ADMIN) or user.is_superuser) and (user.has_perm('warehouse.approve_phieunhapkho') or user.is_superuser) and receipt.trang_thai == 'CHO_DUYET' and ready and not warnings),
        },
    }
