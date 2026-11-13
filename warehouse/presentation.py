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
    invoice = receipt.chi_tiet_nhap.hoa_don_nhap if receipt.chi_tiet_nhap else None
    lenh = receipt.lenh_luu_chuyen if getattr(receipt, 'lenh_luu_chuyen_id', None) else None
    pdi = services.latest_pdi(receipt)
    local = is_da_nang_branch(warehouse.chi_nhanh)
    worker = local and has_role(user, WAREHOUSE) and can_write_warehouse(user, warehouse)
    can_pdi = worker and (user.has_perm('warehouse.add_ketquapdi') or user.is_superuser)
    ready = services.ready_pdi(receipt, pdi=pdi)

    # 3 trạng thái chuẩn nghiệp vụ: Chưa xử lý, Đang xử lý, Đã xử lý
    from database.models import BienBanPDI
    incidents = BienBanPDI.objects.filter(xe_id=receipt.xe_id).order_by('-ngay_ghi_nhan', '-pk')
    latest_incident = incidents.first()
    has_incident = latest_incident is not None
    open_incident = has_incident and (latest_incident.trang_thai_claim != 'Đã xử lý')
    closed_incident = has_incident and (latest_incident.trang_thai_claim == 'Đã xử lý')

    if receipt.trang_thai == 'DA_DUYET' or closed_incident:
        status_code = 'DA_XU_LY'
        label = 'Đã xử lý'
        badge_class = 'badge--DA_DUYET'
    elif open_incident:
        status_code = 'DANG_XU_LY'
        label = 'Đang xử lý'
        badge_class = 'badge--CHO_DUYET'
    elif receipt.trang_thai == 'CHO_DUYET':
        status_code = 'DANG_XU_LY'
        label = 'Đang xử lý'
        badge_class = 'badge--CHO_DUYET'
    else:
        status_code = 'CHUA_XU_LY'
        label = 'Chưa xử lý'
        badge_class = 'badge--NHAP'

    incident_info = None
    if latest_incident:
        incident_info = {
            'ma_pdi': latest_incident.ma_pdi,
            'trang_thai_claim': latest_incident.trang_thai_claim,
            'is_open': open_incident,
            'is_closed': closed_incident,
        }

    warnings = services.receipt_warnings(receipt)
    warnings.extend(services.incident_warnings(receipt, pdi))
    stock_exists = receipt.trang_thai != 'DA_DUYET' and car.tonkho_set.filter(so_luong_ton__gt=0).exists()
    if stock_exists:
        warnings.append('VIN đã có trong tồn kho; không được nhập trùng.')
    from core.roles import get_user_role_info
    read_only = (get_user_role_info(user) or {}).get('is_read_only', False)
    if read_only:
        worker = can_pdi = False

    if invoice:
        don_vi_van_chuyen = invoice.don_vi_van_chuyen.ten_dvvc if invoice.don_vi_van_chuyen else ''
        bien_so_xe = invoice.bien_so_xe or ''
        ten_tai_xe = invoice.ten_tai_xe or ''
        nguon_xe = invoice.nha_cung_cap.ten_ncc if invoice.nha_cung_cap else ''
    elif lenh:
        don_vi_van_chuyen = lenh.don_vi_van_chuyen.ten_dvvc if lenh.don_vi_van_chuyen else ''
        bien_so_xe = lenh.bien_so_xe or ''
        ten_tai_xe = lenh.tai_xe or ''
        nguon_xe = f"Lưu chuyển từ {lenh.kho_xuat.chi_nhanh.ten_cn if (lenh.kho_xuat and lenh.kho_xuat.chi_nhanh) else (lenh.kho_xuat.ten_kho if lenh.kho_xuat else 'Kho chi nhánh')}"
    else:
        don_vi_van_chuyen = ''
        bien_so_xe = ''
        ten_tai_xe = ''
        nguon_xe = ''

    return {
        'id': receipt.pk, 'ma_phieu': receipt.ma_phieu,
        'loai_nguon': getattr(receipt, 'loai_nguon', 'HOA_DON'),
        'lenh_luu_chuyen_id': receipt.lenh_luu_chuyen_id if getattr(receipt, 'lenh_luu_chuyen_id', None) else None,
        'ma_lenh': lenh.ma_lenh if lenh else None,
        'kho_xuat_ten': lenh.kho_xuat.chi_nhanh.ten_cn if (lenh and lenh.kho_xuat and lenh.kho_xuat.chi_nhanh) else (lenh.kho_xuat.ten_kho if (lenh and lenh.kho_xuat) else ''),
        'chi_tiet_nhap_id': receipt.chi_tiet_nhap_id, 'xe_id': receipt.xe_id,
        'vin': receipt.xe_id, 'dong_xe': car.ten_xe, 'phien_ban': getattr(car, 'phien_ban', '') or '',
        'mau_sac': car.mau_sac, 'so_may': car.so_may,
        'ma_hdn': invoice.pk if invoice else None,
        'so_hoa_don': invoice.so_hoa_don if invoice else None,
        'don_vi_van_chuyen': don_vi_van_chuyen,
        'bien_so_xe': bien_so_xe,
        'ten_tai_xe': ten_tai_xe,
        'nguon_xe': nguon_xe,
        'kho_id': receipt.kho_id, 'ten_kho': warehouse.chi_nhanh.ten_cn if warehouse.chi_nhanh else warehouse.ma_kho,
        'ngay_lap': receipt.ngay_lap, 'ngay_nhap': receipt.ngay_nhap,
        'nguoi_lap_id': receipt.nguoi_lap_id, 'nguoi_lap': user_name(receipt.nguoi_lap),
        'trang_thai': receipt.trang_thai, 'trang_thai_hien_thi': label, 'trang_thai_code': status_code, 'badge_class': badge_class, 'incident_info': incident_info,
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
