"""Tra cứu chứng từ nhập hiện có. Hóa đơn nhập không được coi là phiếu đã duyệt."""
from django.contrib.auth.decorators import login_required, permission_required
from django.db.models import Q, Prefetch
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib import messages
from django.utils import timezone
from django.views.decorators.http import require_GET
from core.iii_iv_api import api_errors
from core.iii_iv_access import role_required, has_role, can_write_warehouse, is_da_nang_branch, SALE_ADMIN, WAREHOUSE
from database.models import HoaDonNhap, ChiTietNhap, BienBanPDI, Kho, Xe, NhaCungCap, NhanVien


def wants_html(request):
    return 'text/html' in request.headers.get('Accept', '') and request.GET.get('format') != 'json'


@login_required
@api_errors
@role_required(SALE_ADMIN, WAREHOUSE)
@permission_required('database.view_hoadonnhap', raise_exception=True)
@require_GET
def nhap(request):
    rows = HoaDonNhap.objects.order_by('-ngay_nhap', 'ma_hdn')
    keyword = request.GET.get('q', '').strip()
    if keyword:
        rows = rows.filter(Q(ma_hdn__icontains=keyword) | Q(chitietnhap__xe__vin__icontains=keyword)).distinct()
    sess = getattr(request, 'session', {})
    current_cn = sess.get('current_cn') if hasattr(sess, 'get') else None
    if current_cn and current_cn != 'ALL':
        rows = rows.filter(chi_nhanh_id=current_cn)
    return JsonResponse({'hoa_don_nhap': list(rows.values('ma_hdn', 'nha_cung_cap_id', 'chi_nhanh_id', 'ngay_nhap', 'so_hoa_don')),
                         'luu_y': 'Đây là hóa đơn nhập theo model hiện có, chưa có trạng thái duyệt phiếu nhập.'})


@login_required
@api_errors
@role_required(SALE_ADMIN, WAREHOUSE)
@permission_required(['database.view_hoadonnhap', 'database.view_chitietnhap', 'database.view_bienbanpdi'], raise_exception=True)
@require_GET
def nhap_detail(request, ma_hdn):
    hd = get_object_or_404(HoaDonNhap, pk=ma_hdn)
    return JsonResponse({'ma_hdn': hd.pk, 'ngay_nhap': hd.ngay_nhap,
        'chi_nhanh': hd.chi_nhanh_id, 'nha_cung_cap': hd.nha_cung_cap_id,
        'chi_tiet': list(ChiTietNhap.objects.filter(hoa_don_nhap=hd).order_by('xe_id').values('xe_id', 'so_luong_nhap', 'don_gia', 'thanh_tien')),
        'bien_ban_su_co_pdi': list(BienBanPDI.objects.filter(hoa_don_nhap=hd).order_by('-ngay_ghi_nhan', 'ma_pdi').values('ma_pdi', 'xe_id', 'loai_su_co', 'mo_ta_chi_tiet', 'trang_thai_claim'))})

# API nghiệp vụ mới: không thay thế hóa đơn nhập cũ.
import json
from uuid import uuid4
from datetime import date
from django.core.exceptions import PermissionDenied, ValidationError
from django.views.decorators.http import require_POST
from openpyxl import load_workbook
from .models import PhieuNhapKho, KetQuaPDI
from . import nhap_services as services
from .presentation import receipt_data, pdi_data, user_name


@login_required
@role_required(WAREHOUSE)
@permission_required('warehouse.add_ketquapdi', raise_exception=True)
def import_pdi_excel(request):
    """Import PDI của xưởng theo mã phiếu nhập và VIN, có bước xem trước."""
    from django.db import IntegrityError
    from . import pdi_import
    preview = None
    if request.method == 'POST':
        try:
            if request.POST.get('confirm') == '1':
                preview = request.session.get('pdi_import_preview')
                if not preview:
                    raise ValidationError('Dữ liệu xem trước đã hết hạn; hãy chọn file lại.')
                pdi_import.import_rows(request.user, preview, request.session.get('pdi_import_employee'))
                request.session.pop('pdi_import_preview', None)
                request.session.pop('pdi_import_employee', None)
                messages.success(request, f'Đã nhập {len(preview)} PDI; xe đạt đã nhập kho, xe lỗi đã chuyển sang sự cố.')
                return redirect('warehouse:nhap')
            request.session.pop('pdi_import_preview', None)
            request.session.pop('pdi_import_employee', None)
            upload = request.FILES.get('file')
            if not upload or not upload.name.lower().endswith('.xlsx') or upload.size > 2_000_000:
                raise ValidationError('Chọn file .xlsx tối đa 2 MB.')
            preview = pdi_import.read_file(upload.read())
            employee = pdi_import.employee_for(request.user, request.POST.get('nhan_vien'))
            pdi_import.validate_rows(request.user, preview, employee.pk)
            request.session['pdi_import_preview'] = preview
            request.session['pdi_import_employee'] = employee.pk
        except ValidationError as exc:
            messages.error(request, ' '.join(exc.messages))
            preview = None
        except IntegrityError:
            messages.error(request, 'Dữ liệu đã thay đổi hoặc bị trùng. Không có dòng nào được nhập; hãy kiểm tra lại.')
            preview = None
    employees = NhanVien.objects.select_related('chi_nhanh').order_by('ten_nv') if request.user.is_superuser and not getattr(request.user, 'nhan_vien', None) else []
    return render(request, 'warehouse/import_pdi.html', {'page_title': 'Import PDI xưởng', 'preview': preview, 'employees': employees})


def receipt_rows():
    from django.conf import settings
    branch_ids = list(getattr(settings, 'III_IV_DA_NANG_BRANCH_IDS', ['CN01'])) + list(getattr(settings, 'III_IV_TRANSFER_BRANCH_IDS', ['CN02', 'CN03']))
    return PhieuNhapKho.objects.filter(kho__chi_nhanh_id__in=branch_ids).select_related(
        'xe', 'kho__chi_nhanh', 'chi_tiet_nhap__hoa_don_nhap__nha_cung_cap',
        'lenh_luu_chuyen__kho_xuat__chi_nhanh', 'lenh_luu_chuyen__don_vi_van_chuyen',
        'nguoi_lap__nhan_vien', 'nguoi_duyet__nhan_vien',
    ).prefetch_related(Prefetch('cac_lan_pdi', queryset=KetQuaPDI.objects.select_related(
        'phieu_nhap', 'nguoi_kiem_tra__nhan_vien', 'nguoi_duyet__nhan_vien',
    ).order_by('-thoi_gian_kiem_tra', '-pk'), to_attr='pdi_records'))


@login_required
@api_errors
@role_required(SALE_ADMIN, WAREHOUSE)
@permission_required('warehouse.view_phieunhapkho', raise_exception=True)
@require_GET
def receipt_list(request):
    from orders.models import Allocation
    rows = receipt_rows().order_by('-ngay_lap', '-pk')
    keyword = request.GET.get('q', '').strip()
    if keyword:
        rows = rows.filter(Q(ma_phieu__icontains=keyword) | Q(xe__vin__icontains=keyword))
    if request.GET.get('kho_id'):
        rows = rows.filter(kho_id=request.GET['kho_id'].strip())
    if request.GET.get('ngay_lap'):
        try:
            day = date.fromisoformat(request.GET['ngay_lap'])
        except ValueError:
            return JsonResponse({'error': 'Ngày lập phải theo YYYY-MM-DD.'}, status=400)
        rows = rows.filter(ngay_lap__date=day)
    data = [receipt_data(row, request.user) for row in rows]
    tt_filter = request.GET.get('trang_thai', '').strip()
    if tt_filter:
        if tt_filter in ('DA_XU_LY', 'DA_DUYET'):
            data = [d for d in data if d.get('trang_thai_code') == 'DA_XU_LY']
        elif tt_filter in ('DANG_XU_LY', 'CHO_DUYET'):
            data = [d for d in data if d.get('trang_thai_code') == 'DANG_XU_LY']
        elif tt_filter in ('CHUA_XU_LY', 'NHAP'):
            data = [d for d in data if d.get('trang_thai_code') == 'CHUA_XU_LY']
    display_rows = list(data)
    if not any(request.GET.get(key) for key in ('trang_thai', 'kho_id', 'ngay_lap')):
        known_vins = {row['vin'] for row in display_rows}
        selected_ids = list(request.session.get('selected_vehicles', {}))
        selected = Allocation.objects.filter(pk__in=selected_ids)
        for allocation in selected:
            if allocation.vin not in known_vins and (not keyword or keyword.lower() in allocation.vin.lower()):
                display_rows.insert(0, {'vin': allocation.vin, 'dong_xe': allocation.description,
                    'mau_sac': allocation.exterior_color, 'ma_phieu': 'Đang chọn đặt xe',
                    'trang_thai_hien_thi': '—', 'pending_order': True})
                known_vins.add(allocation.vin)

        from transfers.models import ChiTietLenhLuuChuyen, LenhLuuChuyen
        arrived_transfers = ChiTietLenhLuuChuyen.objects.filter(
            lenh__trang_thai__in=[
                LenhLuuChuyen.TrangThai.DA_DUYET,
                LenhLuuChuyen.TrangThai.DANG_VAN_CHUYEN,
                LenhLuuChuyen.TrangThai.DA_GIAO_DEN_DA_NANG,
            ],
            lenh__kho_nhap__chi_nhanh_id='CN01'
        ).exclude(
            xe_id__in=known_vins
        ).exclude(
            xe__tonkho__so_luong_ton__gt=0
        ).select_related('xe', 'lenh__kho_nhap__chi_nhanh', 'lenh__kho_xuat__chi_nhanh')
        for ct in arrived_transfers:
            if not keyword or keyword.lower() in ct.xe_id.lower() or keyword.lower() in ct.lenh.ma_lenh.lower():
                display_rows.insert(0, {
                    'vin': ct.xe_id,
                    'dong_xe': ct.xe.ten_xe,
                    'phien_ban': getattr(ct.xe, 'phien_ban', '') or '',
                    'mau_sac': ct.xe.mau_sac,
                    'ma_phieu': f'Lệnh {ct.lenh.ma_lenh}',
                    'ten_kho': ct.lenh.kho_nhap.chi_nhanh.ten_cn if ct.lenh.kho_nhap and ct.lenh.kho_nhap.chi_nhanh else 'Đà Nẵng',
                    'ngay_lap': ct.lenh.ngay_giao or ct.lenh.ngay_duyet or ct.lenh.ngay_lap,
                    'nguoi_lap': (ct.lenh.nguoi_duyet.get_full_name() if ct.lenh.nguoi_duyet else None) or (ct.lenh.nguoi_giao.get_full_name() if ct.lenh.nguoi_giao else 'Sale Admin đã duyệt'),
                    'trang_thai_hien_thi': 'Chờ lập phiếu nhập',
                    'badge_class': 'badge--CHO_DUYET',
                    'pending_order': True,
                    'is_transfer_pending': True,
                    'transfer_line_id': ct.pk,
                })
                known_vins.add(ct.xe_id)
    message = '' if data else ('Không có phiếu phù hợp.' if PhieuNhapKho.objects.exists() else 'Chưa có phiếu nhập kho.')
    payload = {'phieu_nhap': data, 'message': message,
               'thao_tac': {'lap_phieu': has_role(request.user, WAREHOUSE) and request.user.has_perm('warehouse.add_phieunhapkho')}}
    if wants_html(request):
        payload.update(page_title='Quản lý nhập kho', display_rows=display_rows,
                       kho=Kho.objects.select_related('chi_nhanh').order_by('ma_kho'),
                       trang_thai=[('CHUA_XU_LY', 'Chưa xử lý'), ('DANG_XU_LY', 'Đang xử lý'), ('DA_XU_LY', 'Đã xử lý')])
        return render(request, 'warehouse/receipt_list.html', payload)
    return JsonResponse(payload)


@login_required
@api_errors
@role_required(SALE_ADMIN, WAREHOUSE)
@permission_required(['warehouse.view_phieunhapkho', 'warehouse.view_ketquapdi'], raise_exception=True)
@require_GET
def receipt_detail(request, pk):
    row = get_object_or_404(receipt_rows(), pk=pk)
    payload = {'phieu_nhap': receipt_data(row, request.user),
               'pdi': [dict(pdi_data(pdi), la_moi_nhat=(i == 0)) for i, pdi in enumerate(row.pdi_records)]}
    if wants_html(request):
        payload['page_title'] = f'Phiếu nhập {row.ma_phieu}'
        return render(request, 'warehouse/receipt_detail.html', payload)
    return JsonResponse(payload)


@login_required
@api_errors
@role_required(SALE_ADMIN, WAREHOUSE)
@permission_required('warehouse.view_phieunhapkho', raise_exception=True)
@require_GET
def receipt_options(request):
    worker = has_role(request.user, WAREHOUSE) and request.user.has_perm('warehouse.add_phieunhapkho')
    return JsonResponse({
        'kho': [dict(kho_id=kho.pk, ten_kho=kho.chi_nhanh.ten_cn,
                     co_the_lap=worker and can_write_warehouse(request.user, kho))
                for kho in Kho.objects.select_related('chi_nhanh').order_by('ma_kho')],
        'trang_thai': [dict(value=value, label=label) for value, label in PhieuNhapKho.TrangThai.choices],
        'nguon_xe': list(NhaCungCap.objects.filter(hoadonnhap__chitietnhap__isnull=False).distinct().order_by('ma_ncc').values('ma_ncc', 'ten_ncc')),
    })


@login_required
@api_errors
@require_POST
def receipt_action(request, action, pk=None):
    # Giữ CSRF middleware mặc định; quyền kiểm tra trong từng dịch vụ.
    permissions = {
        'tao': 'warehouse.add_phieunhapkho',
        'pdi': 'warehouse.add_ketquapdi',
        'duyet-pdi': 'warehouse.approve_ketquapdi',
        'gui-duyet': 'warehouse.change_phieunhapkho',
        'duyet': 'warehouse.approve_phieunhapkho',
    }
    if action not in permissions:
        return JsonResponse({'error': 'Thao tác không tồn tại.'}, status=404)
    services.require_permission(request.user, permissions[action])
    try:
        data = json.loads(request.body or b'{}')
        if not isinstance(data, dict):
            raise ValueError('Nội dung phải là JSON object.')
        if action == 'tao':
            source = {}
            for key in ('chi_tiet_nhap_id', 'lenh_luu_chuyen_id', 'xe_id'):
                value = data.get(key)
                if value is not None:
                    if key == 'xe_id':
                        source[key] = str(value).strip()
                    else:
                        if isinstance(value, bool) or not str(value).isascii() or not str(value).isdigit() or int(value) < 1:
                            raise ValueError('Mã chứng từ phải là số nguyên dương.')
                        source[key] = int(value)
            obj = services.create_receipt(request.user, ma_phieu=data.get('ma_phieu') or 'PN-' + uuid4().hex[:12].upper(),
                kho_id=data['kho_id'], ngay_nhap=date.fromisoformat(data['ngay_nhap']) if data.get('ngay_nhap') else timezone.localdate(), **source)
        elif action == 'pdi':
            obj = services.record_pdi(request.user, pk, tinh_trang=data['tinh_trang'],
                        ket_qua=data['ket_qua'], ghi_chu=data.get('ghi_chu', ''), hang_muc=data.get('hang_muc'), pdi_id=data.get('pdi_id'))
        elif action == 'duyet-pdi':
            obj = services.approve_pdi(request.user, pk, pdi_id=data['pdi_id'])
        elif action == 'gui-duyet':
            obj = services.submit_receipt(request.user, pk, pdi_id=data['pdi_id'])
        else:
            obj = services.approve_receipt(request.user, pk, pdi_id=data['pdi_id'])
        receipt = obj.phieu_nhap if isinstance(obj, KetQuaPDI) else obj
        return JsonResponse({'id': obj.pk, 'message': 'Thành công.',
                             'phieu_nhap': receipt_data(receipt, request.user),
                             'pdi': pdi_data(obj) if isinstance(obj, KetQuaPDI) else None},
                            status=201 if action == 'tao' else 200)
    except (PhieuNhapKho.DoesNotExist, ChiTietNhap.DoesNotExist, Kho.DoesNotExist, Xe.DoesNotExist):
        return JsonResponse({'error': 'Không tìm thấy phiếu hoặc chi tiết nhập.'}, status=404)
    except ValidationError as exc:
        return JsonResponse({'error': exc.messages}, status=400)
    except (KeyError, ValueError, TypeError):
        return JsonResponse({'error': 'Thiếu trường bắt buộc hoặc sai định dạng dữ liệu.'}, status=400)


@login_required
@api_errors
@role_required(WAREHOUSE)
@permission_required(['database.view_xe', 'database.view_chitietnhap'], raise_exception=True)
@require_GET
def eligible_vehicles(request):
    """Các dòng chứng từ có VIN chưa nằm trong kho; trả cảnh báo phiếu đang xử lý."""
    from transfers.models import ChiTietLenhLuuChuyen, LenhLuuChuyen
    rows = ChiTietNhap.objects.exclude(xe__tonkho__so_luong_ton__gt=0).select_related('xe', 'hoa_don_nhap__nha_cung_cap').order_by('pk')
    for query_key, field in [('vin', 'xe__vin__icontains'), ('ten_xe', 'xe__ten_xe__icontains'), ('dong_xe', 'xe__ten_xe__icontains'),
                             ('phien_ban', 'xe__phien_ban__iexact'), ('loai_xe', 'xe__loai_xe__iexact'), ('mau_sac', 'xe__mau_sac__iexact'),
                             ('nguon_xe', 'hoa_don_nhap__nha_cung_cap_id')]:
        if request.GET.get(query_key):
            rows = rows.filter(**{field: request.GET[query_key].strip()})
    rows = rows.exclude(phieunhapkho__trang_thai='DA_DUYET')
    active = {row.xe_id: row for row in receipt_rows().filter(trang_thai__in=['NHAP', 'CHO_DUYET'])}
    state_filter = request.GET.get('trang_thai', '').strip()
    if state_filter and state_filter not in ('CHUA_NHAP_KHO', 'DANG_CO_PHIEU'):
        return JsonResponse({'error': 'Trạng thái lọc không hợp lệ.'}, status=400)
    data = []
    for row in rows:
        current = active.get(row.xe_id)
        state = 'DANG_CO_PHIEU' if current else 'CHUA_NHAP_KHO'
        if state_filter and state_filter != state:
            continue
        warnings = []
        if current:
            warnings.append('VIN đang thuộc một phiếu nhập kho; mở phiếu hiện có để xử lý tiếp.')
        if row.so_luong_nhap != 1:
            warnings.append('Chi tiết nhập theo VIN phải có số lượng đúng một chiếc.')
        data.append(dict(id=row.pk, vin=row.xe_id, ten_xe=row.xe.ten_xe, dong_xe=row.xe.ten_xe,
            loai_xe=row.xe.loai_xe, phien_ban=row.xe.phien_ban, mau_sac=row.xe.mau_sac,
            so_may=row.xe.so_may, ma_hdn=row.hoa_don_nhap_id,
            nguon_xe_id=row.hoa_don_nhap.nha_cung_cap_id,
            nguon_xe=row.hoa_don_nhap.nha_cung_cap.ten_ncc,
            trang_thai=state, trang_thai_hien_thi='Đang có phiếu nhập' if current else 'Chưa nhập kho', dang_co_phieu=current is not None,
            phieu_hien_co_id=current.pk if current else None,
            pdi_moi_nhat=pdi_data(services.latest_pdi(current)) if current and current.chi_tiet_nhap_id == row.pk and request.user.has_perm('warehouse.view_ketquapdi') else None,
            canh_bao=warnings, co_the_tao=current is None and row.so_luong_nhap == 1 and request.user.has_perm('warehouse.add_phieunhapkho')))

    # Bổ sung xe từ lệnh lưu chuyển đã giao đến Đà Nẵng
    transfer_rows = ChiTietLenhLuuChuyen.objects.filter(
        lenh__trang_thai__in=[
            LenhLuuChuyen.TrangThai.DA_DUYET,
            LenhLuuChuyen.TrangThai.DANG_VAN_CHUYEN,
            LenhLuuChuyen.TrangThai.DA_GIAO_DEN_DA_NANG,
        ],
        lenh__kho_nhap__chi_nhanh_id='CN01'
    ).exclude(
        xe__tonkho__so_luong_ton__gt=0
    ).exclude(
        xe__phieunhapkho__trang_thai='DA_DUYET'
    ).select_related('xe', 'lenh__kho_xuat__chi_nhanh')
    for query_key, field in [('vin', 'xe__vin__icontains'), ('ten_xe', 'xe__ten_xe__icontains'), ('dong_xe', 'xe__ten_xe__icontains'),
                             ('phien_ban', 'xe__phien_ban__iexact'), ('loai_xe', 'xe__loai_xe__iexact'), ('mau_sac', 'xe__mau_sac__iexact')]:
        if request.GET.get(query_key):
            transfer_rows = transfer_rows.filter(**{field: request.GET[query_key].strip()})
    for t_row in transfer_rows:
        current = active.get(t_row.xe_id)
        state = 'DANG_CO_PHIEU' if current else 'CHUA_NHAP_KHO'
        if state_filter and state_filter != state:
            continue
        warnings = []
        if current:
            warnings.append('VIN đang thuộc một phiếu nhập kho; mở phiếu hiện có để xử lý tiếp.')
        data.append(dict(
            id=t_row.pk, vin=t_row.xe_id, ten_xe=t_row.xe.ten_xe, dong_xe=t_row.xe.ten_xe,
            loai_xe=t_row.xe.loai_xe, phien_ban=t_row.xe.phien_ban, mau_sac=t_row.xe.mau_sac,
            so_may=t_row.xe.so_may, ma_hdn=None, ma_lenh=t_row.lenh.ma_lenh,
            nguon_xe_id=f"TRANSFER_{t_row.lenh_id}",
            nguon_xe=f"Lệnh {t_row.lenh.ma_lenh} ({t_row.lenh.kho_xuat.chi_nhanh.ten_cn if t_row.lenh.kho_xuat and t_row.lenh.kho_xuat.chi_nhanh else 'Lưu chuyển'})",
            trang_thai=state, trang_thai_hien_thi='Đang có phiếu nhập' if current else 'Chưa nhập kho (Chờ tiếp nhận lưu chuyển)',
            dang_co_phieu=current is not None,
            phieu_hien_co_id=current.pk if current else None,
            pdi_moi_nhat=pdi_data(services.latest_pdi(current)) if current and current.lenh_luu_chuyen_id == t_row.lenh_id and request.user.has_perm('warehouse.view_ketquapdi') else None,
            canh_bao=warnings,
            co_the_tao=current is None and request.user.has_perm('warehouse.add_phieunhapkho'),
            loai_nguon='LUU_CHUYEN',
        ))

    payload = {'xe': data, 'message': '' if data else 'Không tìm thấy xe phù hợp.',
               'luu_y': 'Danh sách lấy từ chi tiết chứng từ nhập hiện có; xe chưa có chứng từ cần được bổ sung hồ sơ trước.'}
    if wants_html(request):
        payload['page_title'] = 'Xe có thể nhập kho'
        return render(request, 'warehouse/eligible_vehicles.html', payload)
    return JsonResponse(payload)


@login_required
@role_required(WAREHOUSE)
@permission_required('warehouse.add_phieunhapkho', raise_exception=True)
def receipt_create_page(request):
    from transfers.models import ChiTietLenhLuuChuyen, LenhLuuChuyen
    lines = ChiTietNhap.objects.exclude(xe__tonkho__so_luong_ton__gt=0).filter(
        so_luong_nhap=1, phieunhapkho__isnull=True,
    ).select_related('xe', 'hoa_don_nhap__nha_cung_cap').order_by('pk')

    xe_luu_chuyen = ChiTietLenhLuuChuyen.objects.filter(
        lenh__trang_thai__in=[
            LenhLuuChuyen.TrangThai.DA_DUYET,
            LenhLuuChuyen.TrangThai.DANG_VAN_CHUYEN,
            LenhLuuChuyen.TrangThai.DA_GIAO_DEN_DA_NANG,
        ],
        lenh__kho_nhap__chi_nhanh_id='CN01'
    ).exclude(
        xe__phieunhapkho__trang_thai__in=['NHAP', 'CHO_DUYET', 'DA_DUYET']
    ).exclude(
        xe__tonkho__so_luong_ton__gt=0
    ).select_related('xe', 'lenh').order_by('pk')

    warehouses = [kho for kho in Kho.objects.select_related('chi_nhanh').order_by('ma_kho')
                  if can_write_warehouse(request.user, kho) and is_da_nang_branch(kho.chi_nhanh)]
    keyword = request.GET.get('q', '').strip()
    if keyword:
        lines = lines.filter(Q(xe__vin__icontains=keyword) | Q(xe__ten_xe__icontains=keyword) | Q(xe__phien_ban__icontains=keyword) | Q(xe__mau_sac__icontains=keyword))
        xe_luu_chuyen = xe_luu_chuyen.filter(Q(xe__vin__icontains=keyword) | Q(xe__ten_xe__icontains=keyword) | Q(xe__phien_ban__icontains=keyword) | Q(xe__mau_sac__icontains=keyword) | Q(lenh__ma_lenh__icontains=keyword))

    if request.method == 'POST':
        try:
            source = request.POST['nguon_xe']
            kind, line_id = source.split(':', 1)
            ma_phieu = request.POST.get('ma_phieu', '').strip() or 'PN-' + uuid4().hex[:12].upper()
            kho_id = request.POST['kho_id']
            ngay_nhap = date.fromisoformat(request.POST['ngay_nhap']) if request.POST.get('ngay_nhap') else timezone.localdate()

            if kind == 'hang':
                if not line_id.isdigit():
                    raise ValueError('Mã chi tiết nhập không hợp lệ.')
                obj = services.create_receipt(
                    request.user,
                    ma_phieu=ma_phieu,
                    chi_tiet_nhap_id=int(line_id),
                    kho_id=kho_id,
                    ngay_nhap=ngay_nhap,
                )
            elif kind == 'luu-chuyen':
                if not line_id.isdigit():
                    raise ValueError('Mã chi tiết lệnh lưu chuyển không hợp lệ.')
                ct = ChiTietLenhLuuChuyen.objects.select_related('lenh').get(pk=int(line_id))
                obj = services.create_receipt(
                    request.user,
                    ma_phieu=ma_phieu,
                    lenh_luu_chuyen_id=ct.lenh_id,
                    xe_id=ct.xe_id,
                    kho_id=kho_id,
                    ngay_nhap=ngay_nhap,
                )
            else:
                raise ValueError('Nguồn xe không hợp lệ.')

            messages.success(request, 'Đã lưu phiếu nhập ở trạng thái Nháp.')
            return redirect('warehouse:receipt_detail', pk=obj.pk)
        except (KeyError, ValueError, TypeError) as err:
            messages.error(request, f'Vui lòng nhập đầy đủ và đúng định dạng: {err}')
        except (ChiTietNhap.DoesNotExist, ChiTietLenhLuuChuyen.DoesNotExist, Kho.DoesNotExist):
            messages.error(request, 'Chứng từ hoặc kho không còn tồn tại.')
        except ValidationError as exc:
            messages.error(request, ' '.join(exc.messages))

    return render(request, 'warehouse/receipt_form.html', {
        'page_title': 'Lập phiếu nhập kho', 'xe_co_the_nhap': lines, 'kho': warehouses, 'xe_luu_chuyen': xe_luu_chuyen,
        'form_data': request.POST if request.method == 'POST' else {'nguon_xe': request.GET.get('nguon_xe', '')},
        'ngay_nhap_mac_dinh': request.POST.get('ngay_nhap', '') if request.method == 'POST' else timezone.localdate().isoformat(),
    })


@login_required
@require_POST
def receipt_web_action(request, pk, action):
    try:
        receipt = get_object_or_404(PhieuNhapKho, pk=pk)
        expected_id = request.POST.get('pdi_id') or None
        if action == 'ghi-pdi':
            items = []
            for key, label in [('ngoai_that', 'Ngoại thất'), ('noi_that', 'Nội thất'), ('van_hanh', 'Vận hành')]:
                items.append({'hang_muc': label, 'tinh_trang': request.POST.get(f'{key}_tinh_trang', '').strip(),
                              'ket_qua': request.POST.get(f'{key}_ket_qua', ''),
                              'ghi_chu': request.POST.get(f'{key}_ghi_chu', '').strip()})
            overall = 'DAT' if all(item['ket_qua'] == 'DAT' for item in items) else 'KHONG_DAT'
            services.record_pdi(request.user, pk, tinh_trang=request.POST.get('tinh_trang', '').strip(),
                ket_qua=overall, ghi_chu=request.POST.get('ghi_chu', '').strip(), hang_muc=items,
                pdi_id=expected_id)
            messages.success(request, 'Đã lưu kết quả kiểm tra PDI.')
        elif action == 'duyet-pdi':
            services.approve_pdi(request.user, pk, pdi_id=expected_id)
            messages.success(request, 'Đã duyệt kết quả PDI.')
        elif action == 'gui-duyet':
            services.submit_receipt(request.user, pk, pdi_id=expected_id)
            messages.success(request, 'Đã gửi phiếu sang trạng thái Chờ duyệt.')
        elif action == 'duyet':
            services.approve_receipt(request.user, pk, pdi_id=expected_id)
            messages.success(request, 'Đã duyệt nhập kho và cập nhật tồn kho.')
        else:
            messages.error(request, 'Thao tác không tồn tại.')
    except ValidationError as exc:
        messages.error(request, ' '.join(exc.messages))
    except PermissionDenied:
        messages.error(request, 'Bạn không có quyền thực hiện thao tác này.')
    return redirect('warehouse:receipt_detail', pk=pk)


@login_required
@api_errors
@role_required(WAREHOUSE)
@permission_required('warehouse.view_ketquapdi', raise_exception=True)
@require_GET
def pdi_detail(request, pk):
    row = get_object_or_404(KetQuaPDI.objects.select_related('phieu_nhap', 'nguoi_kiem_tra__nhan_vien', 'nguoi_duyet__nhan_vien'), pk=pk)
    current = services.latest_pdi(row.phieu_nhap)
    is_latest = current is not None and current.pk == row.pk
    actions = receipt_data(row.phieu_nhap, request.user)['thao_tac']
    result = pdi_data(row)
    if not is_latest:
        result['canh_bao'].append('Đây là lần kiểm tra cũ; chỉ PDI mới nhất được xử lý tiếp.')
    if wants_html(request):
        return render(request, 'warehouse/pdi_detail.html', {'page_title': 'Chi tiết kết quả PDI', 'pdi': result, 'thao_tac': actions, 'la_moi_nhat': is_latest})
    return JsonResponse({'pdi': result, 'la_moi_nhat': is_latest,
                         'thao_tac': {'cap_nhat': is_latest and actions['cap_nhat_pdi'],
                                     'duyet': is_latest and actions['duyet_pdi']}})


@login_required
@api_errors
@role_required(SALE_ADMIN, WAREHOUSE)
@permission_required('warehouse.view_lichsunhapkho', raise_exception=True)
@require_GET
def receipt_history(request, pk):
    from .models import LichSuNhapKho
    get_object_or_404(PhieuNhapKho, pk=pk)
    if wants_html(request):
        return render(request, 'warehouse/history.html', {'page_title': 'Lịch sử nhập kho theo VIN', 'pk': pk,
            'rows': LichSuNhapKho.objects.filter(phieu_nhap_id=pk).select_related('xe', 'kho__chi_nhanh', 'nguoi_thuc_hien')})
    return JsonResponse({'lich_su': [dict(id=row.pk, phieu_nhap_id=pk, vin=row.xe_id, su_kien='Nhập kho',
        kho_id=row.kho_id, ten_kho=row.kho.chi_nhanh.ten_cn,
        nguoi_thuc_hien=user_name(row.nguoi_thuc_hien), thoi_gian=row.thoi_gian)
        for row in LichSuNhapKho.objects.filter(phieu_nhap_id=pk).select_related('kho__chi_nhanh', 'nguoi_thuc_hien__nhan_vien')]})
