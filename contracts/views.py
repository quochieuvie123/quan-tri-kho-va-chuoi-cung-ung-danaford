from .matching import car_matches_criterion, matches_contract_smart, get_model, get_trim, colors_match
from database.models import PhieuXuatKho, LichSuXuatKho, NhanVien, TrangThaiPhieuXuat, Kho
from django.utils import timezone
"""Backend III; GET chỉ tra cứu, không gán VIN hoặc giữ xe."""
from datetime import date
from django.conf import settings
from django.contrib.auth.decorators import login_required, permission_required
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET
from django.views.decorators.http import require_POST
from django.shortcuts import redirect
from django.contrib import messages
from django.core.exceptions import ValidationError
from core.iii_iv_api import api_errors
from core.iii_iv_access import role_required, has_role, is_da_nang_branch, SALE_ADMIN, WAREHOUSE
from database.models import HopDong, ChiTietHopDong, TonKho, HoaDonBan, TrangThaiHopDong, TrangThaiXe, Xe
from .presentation import stock_data


def wants_html(request):
    return 'text/html' in request.headers.get('Accept', '') and request.GET.get('format') != 'json'


def criteria_for(hd):
    """Lấy yêu cầu độc lập; hỗ trợ hợp đồng cũ chỉ khi xe mẫu có đủ phiên bản."""
    values = [hd.dong_xe_yeu_cau, hd.phien_ban_yeu_cau, hd.mau_sac_yeu_cau]
    values = [value.strip() if isinstance(value, str) else '' for value in values]
    if any(values):
        warning = None if all(values) else 'Tiêu chí hợp đồng chưa đủ dòng xe, phiên bản và màu sắc.'
        return [dict(dong_xe=values[0], phien_ban=values[1], mau_sac=values[2])], warning
    lines = list(hd.chitiethopdong_set.all())
    if not lines:
        return [], 'Chưa đủ dữ liệu để đề xuất xe.'
    criteria = []
    warning = None
    for line in lines:
        car = line.xe
        values = [(value or '').strip() for value in (car.ten_xe, car.phien_ban, car.mau_sac)]
        if not all(values):
            warning = 'Xe của hợp đồng cũ chưa đủ dòng xe, phiên bản và màu sắc.'
        criteria.append(dict(dong_xe=values[0], phien_ban=values[1], mau_sac=values[2]))
    return criteria, warning


def contract_summary(hd, user):
    criteria, warning = criteria_for(hd)
    first = criteria[0] if len(criteria) == 1 else {}
    source_confirmed = hd.trang_thai in (
        TrangThaiHopDong.CHO_XE_VE_KHO, TrangThaiHopDong.DU_DIEU_KIEN_XUAT,
        TrangThaiHopDong.DANG_XUAT_KHO, TrangThaiHopDong.HOAN_TAT,
    )
    can_propose = (
        not warning
        and not source_confirmed
        and bool(criteria)
        and hd.trang_thai in (TrangThaiHopDong.CHO_XU_LY, TrangThaiHopDong.CHO_PHAN_BO, TrangThaiHopDong.CHO_XE_VE_KHO)
        and has_role(user, SALE_ADMIN)
        and (user.is_superuser or user.has_perms(['database.view_hopdong', 'database.view_tonkho']))
    )
    return {
        'ma_hd': hd.pk, 'khach_hang_id': hd.khach_hang_id,
        'khach_hang__ten_kh': hd.khach_hang.ten_kh, 'chi_nhanh_id': hd.chi_nhanh_id,
        'ngay_ky': hd.ngay_ky, 'so_tien_coc': hd.so_tien_coc,
        'dong_xe_yeu_cau': (hd.dong_xe_yeu_cau or '').strip() or first.get('dong_xe'),
        'phien_ban_yeu_cau': (hd.phien_ban_yeu_cau or '').strip() or first.get('phien_ban'),
        'mau_sac_yeu_cau': (hd.mau_sac_yeu_cau or '').strip() or first.get('mau_sac'),
        'ngay_du_kien_giao': hd.ngay_du_kien_giao, 'trang_thai': hd.trang_thai,
        'trang_thai_hien_thi': ('Hoàn tất' if source_confirmed else 'Chờ lịch phân bổ' if hd.trang_thai == TrangThaiHopDong.CHO_PHAN_BO else 'Chờ xử lý'),
        'tieu_chi_xe': criteria, 'canh_bao': warning,
        'thao_tac': {'xem_chi_tiet': has_role(user, SALE_ADMIN) and user.has_perm('database.view_hopdong'),
                    'de_xuat_xe': can_propose},
    }


@login_required
@api_errors
@role_required(SALE_ADMIN, WAREHOUSE)
@permission_required('database.view_hopdong', raise_exception=True)
@require_GET
def index(request):
    rows = HopDong.objects.select_related('khach_hang', 'chi_nhanh').prefetch_related('chitiethopdong_set__xe').order_by('ma_hd')
    keyword = request.GET.get('q', '').strip()
    if keyword:
        rows = rows.filter(Q(ma_hd__icontains=keyword) | Q(khach_hang__ten_kh__icontains=keyword))
    for param, field in [('trang_thai', 'trang_thai'), ('chi_nhanh_id', 'chi_nhanh_id')]:
        if request.GET.get(param):
            value = request.GET[param].strip()
            if param == 'trang_thai' and value == TrangThaiHopDong.CHO_XU_LY:
                rows = rows.filter(trang_thai=TrangThaiHopDong.CHO_XU_LY)
            elif param == 'trang_thai' and value == TrangThaiHopDong.HOAN_TAT:
                rows = rows.filter(trang_thai__in=[TrangThaiHopDong.CHO_XE_VE_KHO,
                    TrangThaiHopDong.DU_DIEU_KIEN_XUAT, TrangThaiHopDong.DANG_XUAT_KHO,
                    TrangThaiHopDong.HOAN_TAT])
            else:
                rows = rows.filter(**{field: value})
    sess = getattr(request, 'session', {})
    current_cn = sess.get('current_cn') if hasattr(sess, 'get') else None
    if not request.GET.get('chi_nhanh_id') and current_cn and current_cn != 'ALL':
        rows = rows.filter(chi_nhanh_id=current_cn)
    if request.GET.get('ngay_du_kien_giao'):
        try:
            day = date.fromisoformat(request.GET['ngay_du_kien_giao'])
        except ValueError:
            return JsonResponse({'error': 'Ngày phải theo YYYY-MM-DD.'}, status=400)
        rows = rows.filter(ngay_du_kien_giao=day)
    filters = {key: request.GET[key].strip().casefold() for key in ('dong_xe', 'phien_ban', 'mau_sac') if request.GET.get(key, '').strip()}
    data = []
    for hd in rows:
        if current_cn and current_cn != 'ALL':
            if hd.chi_nhanh_id != current_cn:
                continue
        elif not current_cn and not request.GET.get('chi_nhanh_id'):
            if not is_da_nang_branch(hd.chi_nhanh):
                continue
        summary = contract_summary(hd, request.user)
        # Cùng bộ tiêu chí dùng cho hiển thị và lọc, kể cả hợp đồng cũ.
        # Một xe phải đáp ứng toàn bộ bộ lọc; không ghép dòng của hai xe khác nhau.
        if filters and not any(all(item[key].casefold() == value for key, value in filters.items()) for item in summary['tieu_chi_xe']):
            continue
        data.append(summary)
    message = '' if data else ('Không có hợp đồng phù hợp.' if HopDong.objects.exists() else 'Chưa có hợp đồng xe bán.')
    payload = {'hop_dong': data, 'message': message}
    if wants_html(request):
        payload.update(page_title='Quản lý hợp đồng xe bán', trang_thai_options=[
            (TrangThaiHopDong.CHO_XU_LY, 'Chờ xử lý'),
            (TrangThaiHopDong.CHO_PHAN_BO, 'Chờ lịch phân bổ'),
            (TrangThaiHopDong.HOAN_TAT, 'Hoàn tất'),
        ])
        return render(request, 'contracts/index.html', payload)
    return JsonResponse(payload)


@login_required
@api_errors
@role_required(SALE_ADMIN)
@permission_required('database.view_hopdong', raise_exception=True)
@require_GET
def detail(request, ma_hd):
    hd = get_object_or_404(HopDong.objects.select_related('khach_hang'), pk=ma_hd)
    if not is_da_nang_branch(hd.chi_nhanh):
        from django.http import Http404
        raise Http404
    result = contract_summary(hd, request.user)
    result.update({
        'khach_hang': hd.khach_hang_id, 'ten_khach_hang': hd.khach_hang.ten_kh,
        'sdt_khach_hang': hd.khach_hang.sdt_kh, 'chi_nhanh': hd.chi_nhanh.ten_cn,
        'dong_xe': result['dong_xe_yeu_cau'], 'phien_ban': result['phien_ban_yeu_cau'],
        'mau_sac': result['mau_sac_yeu_cau'],
        'xe': list(ChiTietHopDong.objects.filter(hop_dong=hd).order_by('xe_id').values('xe_id', 'xe__ten_xe', 'xe__phien_ban', 'xe__loai_xe', 'xe__mau_sac')),
        # Chỉ lấy hóa đơn có liên kết thực qua phiếu xuất, không ghép theo khách hàng.
        'hoa_don': list(HoaDonBan.objects.filter(phieu_xuat_kho__chi_tiet_hop_dong__hop_dong=hd).distinct().order_by('ma_hdb').values('ma_hdb', 'so_hoa_don')),
    })
    result['vin_hien_thi'] = [line['xe_id'] for line in result['xe']]
    result['hoa_don_canh_bao'] = None if result['hoa_don'] else 'Chưa có hóa đơn liên kết trực tiếp với hợp đồng hoặc phiếu xuất kho.'
    if wants_html(request):
        ctx = dict(result)
        ctx['phieu_xuat'] = PhieuXuatKho.objects.filter(chi_tiet_hop_dong__hop_dong=hd).select_related('kho', 'nguoi_lap', 'nguoi_duyet').first()
        try:
            from transfers.models import LenhLuuChuyen
            ctx['lenh_luu_chuyen'] = LenhLuuChuyen.objects.filter(chi_tiet__xe__chitiethopdong__hop_dong=hd).select_related('kho_xuat__chi_nhanh', 'kho_nhap__chi_nhanh').first()
        except Exception:
            ctx['lenh_luu_chuyen'] = None
        can_edit = has_role(request.user, SALE_ADMIN) or request.user.is_superuser
        return render(request, 'contracts/detail.html', {'page_title': f'Hợp đồng {hd.pk}', 'hop_dong': ctx, 'co_the_chinh_sua': can_edit})
    return JsonResponse(result)


@login_required
@role_required(SALE_ADMIN)
@permission_required('database.change_hopdong', raise_exception=True)
@require_POST
def cap_nhat_ngay_giao(request, ma_hd):
    """Cập nhật ngày dự kiến giao xe cho hợp đồng bán."""
    hd = get_object_or_404(HopDong, pk=ma_hd)
    val = request.POST.get('ngay_du_kien_giao', '').strip()
    if not val:
        hd.ngay_du_kien_giao = None
        hd.save(update_fields=['ngay_du_kien_giao'])
        messages.success(request, f'Đã xóa ngày giao dự kiến của hợp đồng {hd.ma_hd}.')
    else:
        try:
            d = date.fromisoformat(val)
            hd.ngay_du_kien_giao = d
            hd.save(update_fields=['ngay_du_kien_giao'])
            messages.success(request, f'Đã cập nhật ngày giao dự kiến cho hợp đồng {hd.ma_hd}: {d.strftime("%d/%m/%Y")}.')
        except (ValueError, TypeError):
            messages.error(request, 'Định dạng ngày giao dự kiến không hợp lệ. Vui lòng chọn lại.')
    return redirect('contracts:detail', ma_hd=ma_hd)


def find_suitable(hd):
    criteria, warning = criteria_for(hd)
    if not is_da_nang_branch(hd.chi_nhanh):
        return criteria, [], 'Chỉ tra cứu hợp đồng tại Đà Nẵng.'
    if hd.trang_thai not in (TrangThaiHopDong.CHO_XU_LY, TrangThaiHopDong.CHO_PHAN_BO, TrangThaiHopDong.CHO_XE_VE_KHO, TrangThaiHopDong.DU_DIEU_KIEN_XUAT, TrangThaiHopDong.DANG_XUAT_KHO):
        return criteria, [], 'Hợp đồng đã hoàn tất hoặc đang xuất kho; không cần đề xuất xe mới.'
    if warning:
        return criteria, [], warning
    from .demand import remaining_requirements
    if hd.chitiethopdong_set.exists():
        criteria = remaining_requirements(hd, include_reserved=True)
    if not criteria:
        return [], [], 'Các yêu cầu xe đã được giao hoặc đang có phiếu giữ xe.'

    stocks = TonKho.objects.filter(so_luong_ton__gt=0, xe__trang_thai=TrangThaiXe.SAN_SANG).select_related('xe', 'kho__chi_nhanh').order_by('kho_id', 'xe_id')
    results = []
    for row in stocks:
        if ChiTietHopDong.objects.filter(xe_id=row.xe_id).exclude(hop_dong=hd).exists():
            continue
        from database.models import BienBanPDI
        if BienBanPDI.objects.filter(xe_id=row.xe_id).exclude(trang_thai_claim='Đã xử lý').exists():
            continue
        local = is_da_nang_branch(row.kho.chi_nhanh)
        if not local and row.kho.chi_nhanh_id not in getattr(settings, 'III_IV_TRANSFER_BRANCH_IDS', ['CN02', 'CN03']):
            continue

        matched_criteria = []
        is_exact_color_any = False
        for i, criterion in enumerate(criteria):
            match_mt, match_c = car_matches_criterion(row.xe, criterion)
            if match_mt:
                matched_criteria.append(i)
                if match_c:
                    is_exact_color_any = True

        if not matched_criteria:
            continue

        item = stock_data(row)
        item['tieu_chi_chi_so'] = matched_criteria
        if local:
            if is_exact_color_any:
                item['phuong_an'] = 'Xe tại Đà Nẵng (Khớp màu)'
                item['uu_tien'] = 0
            else:
                item['phuong_an'] = f'Xe tại Đà Nẵng (Màu: {row.xe.mau_sac or "Khác"})'
                item['uu_tien'] = 2
        else:
            if is_exact_color_any:
                item['phuong_an'] = 'Cần lưu chuyển về Đà Nẵng'
                item['uu_tien'] = 1
            else:
                item['phuong_an'] = f'Lưu chuyển về ĐN (Màu: {row.xe.mau_sac or "Khác"})'
                item['uu_tien'] = 3
        results.append(item)

    # Không lọc bỏ xe ở chi nhánh để hiển thị đầy đủ số lượng xe ở Đà Nẵng và Bình Định / Gia Lai
    results.sort(key=lambda item: (item['uu_tien'], item['kho_id'], item['vin']))

    # PYC đã sinh phiếu nhập nháp cũng là nguồn xe dự kiến, chưa phải tồn kho.
    from warehouse.models import PhieuNhapKho
    from .workflow import matches_contract
    pending = PhieuNhapKho.objects.filter(trang_thai='NHAP', kho__chi_nhanh_id='CN01').select_related('xe', 'kho__chi_nhanh')
    for receipt in pending:
        if ChiTietHopDong.objects.filter(xe_id=receipt.xe_id).exclude(hop_dong=hd).exists() or not matches_contract(receipt.xe, hd):
            continue
        results.append({'vin': receipt.xe_id, 'xe__ten_xe': receipt.xe.ten_xe, 'xe__phien_ban': receipt.xe.phien_ban or '',
                        'xe__mau_sac': receipt.xe.mau_sac or '', 'kho_id': receipt.kho_id,
                        'vi_tri_kho': 'PYC / chờ PDI', 'chat_luong': 'Chưa có PDI', 'tinh_trang_gan': 'Chưa gán hợp đồng',
                        'trang_thai_hien_thi': 'Chờ PDI', 'phuong_an': 'Xe từ PYC - chờ PDI', 'uu_tien': 4,
                        'tieu_chi_chi_so': list(range(len(criteria))), 'nguon_pyc': True})
    return criteria, results, None


@login_required
@role_required(SALE_ADMIN)
@permission_required('database.change_hopdong', raise_exception=True)
@require_POST
def choose_suggested_vehicle(request, ma_hd, vin):
    from .workflow import choose_vehicle
    try:
        contract = choose_vehicle(ma_hd, vin, request.user)
        pxk = PhieuXuatKho.objects.filter(chi_tiet_hop_dong__hop_dong=contract, chi_tiet_hop_dong__xe_id=vin).first()
        if pxk and pxk.trang_thai == TrangThaiPhieuXuat.CHO_DUYET:
            messages.success(request, f'Đã chốt xe VIN {vin} tại Kho Đà Nẵng. Đã gửi yêu cầu xuất kho ({pxk.ma_pxk}) sang Quản lý xuất kho để Sale Admin phê duyệt.')
        elif contract.trang_thai == TrangThaiHopDong.CHO_XE_VE_KHO:
            messages.success(request, f'Đã chốt xe VIN {vin} tại chi nhánh. Đã tạo lệnh lưu chuyển xe về Đà Nẵng (trạng thái: Chờ duyệt), chờ Sale Admin duyệt.')
        else:
            messages.success(request, f'Đã chốt VIN {vin}; hợp đồng chuyển sang {contract.get_trang_thai_display()}.')
    except (ValidationError, HopDong.DoesNotExist) as e:
        messages.error(request, str(e) if isinstance(e, ValidationError) else 'VIN không thể được chốt cho hợp đồng ở thời điểm này.')
    return redirect('contracts:detail', ma_hd=ma_hd)


@login_required
@role_required(SALE_ADMIN)
@permission_required('database.add_hopdong', raise_exception=True)
def import_contracts_excel(request):
    """Preview then import contracts from the agreed xlsx schema."""
    from django.core.exceptions import ValidationError
    from . import contract_import
    preview = None
    if request.method == 'POST':
        try:
            if request.POST.get('confirm') == '1':
                preview = request.session.get('contract_import_preview')
                if not preview: raise ValidationError('Dữ liệu xem trước đã hết hạn; hãy chọn file lại.')
                for row in preview:
                    row['ngay_ky'] = date.fromisoformat(row['ngay_ky'])
                    from decimal import Decimal
                    row['so_tien_coc'] = Decimal(row['so_tien_coc'])
                contract_import.import_rows(preview)
                request.session.pop('contract_import_preview', None)
                messages.success(request, f'Đã nhập {len(preview)} hợp đồng.')
                return redirect('contracts:index')
            upload = request.FILES.get('file')
            if not upload or not upload.name.lower().endswith('.xlsx') or upload.size > 2_000_000:
                raise ValidationError('Chọn file .xlsx tối đa 2 MB.')
            preview = contract_import.read_file(upload.read())
            contract_import.validate_rows(preview)
            request.session['contract_import_preview'] = [dict(row, ngay_ky=row['ngay_ky'].isoformat(), so_tien_coc=str(row['so_tien_coc'])) for row in preview]
        except ValidationError as exc:
            messages.error(request, ' '.join(exc.messages)); preview = None
        except Exception as exc:
            if 'UNIQUE constraint failed' in str(exc):
                messages.error(request, 'Dữ liệu bị trùng mã khách hàng hoặc mã số thuế; hãy kiểm tra file rồi import lại.')
            else:
                messages.error(request, 'Không thể import file hợp đồng. Hãy kiểm tra lại dữ liệu.')
            preview = None
    return render(request, 'contracts/import.html', {'page_title': 'Import hợp đồng xe bán', 'preview': preview})


@login_required
@role_required(SALE_ADMIN)
@permission_required('database.change_hopdong', raise_exception=True)
@require_POST
def wait_allocation(request, ma_hd):
    hd = get_object_or_404(HopDong, pk=ma_hd)
    criteria, results, error = find_suitable(hd)
    if not is_da_nang_branch(hd.chi_nhanh) or error or results:
        messages.error(request, 'Chỉ chọn chờ phân bổ khi không còn xe phù hợp tại ba kho.')
    else:
        hd.trang_thai = TrangThaiHopDong.CHO_PHAN_BO
        hd.save(update_fields=['trang_thai'])
        messages.success(request, 'Hợp đồng đã chuyển sang chờ lịch phân bổ.')
    return redirect('contracts:xe_phu_hop', ma_hd=ma_hd)


def find_allocation_vehicles(hd, criteria):
    """
    Tra cứu danh sách xe phân bổ từ nhà máy của các tháng tiếp theo (demo kỳ Tháng 11/2026),
    so khớp với tiêu chí dòng xe, phiên bản và màu sắc của hợp đồng.
    """
    from orders.models import Allocation
    alloc_qs = Allocation.objects.filter(
        Q(allocation_month__gte=date(2026, 11, 1)) | Q(allocation_month=date(2026, 11, 1))
    ).order_by('allocation_month', 'id')

    matched_allocs = []
    for alloc in alloc_qs:
        if ChiTietHopDong.objects.filter(xe__vin=alloc.vin).exclude(hop_dong=hd).exists():
            continue

        m_car = get_model(alloc.description) or get_model(alloc.vehicle_code)
        tr_car = get_trim(alloc.description) or get_trim(alloc.vehicle_code)

        matched_any = False
        is_exact_color = False
        for crit in criteria:
            m_req = get_model(crit.get('dong_xe', ''))
            tr_req = get_trim(crit.get('phien_ban', '')) or get_trim(crit.get('dong_xe', ''))
            req_mau = crit.get('mau_sac', '')

            if m_req and m_car and m_req != m_car:
                continue
            if tr_req and tr_car and tr_req != tr_car:
                continue

            matched_any = True
            c_match = colors_match(req_mau, alloc.mau_sac or alloc.exterior_color)
            if c_match:
                is_exact_color = True

        if matched_any:
            matched_allocs.append({
                'id': alloc.id,
                'order_number': alloc.order_number or f'ORD-{alloc.id}',
                'vin': alloc.vin,
                'vehicle_code': alloc.vehicle_code,
                'description': alloc.description,
                'mau_sac': alloc.mau_sac or alloc.exterior_color or 'Tiêu chuẩn',
                'color_code': alloc.color_code or '',
                'allocation_month': alloc.allocation_month,
                'ky_phan_bo': alloc.allocation_month.strftime('Tháng %m/%Y') if alloc.allocation_month else 'Tháng 11/2026',
                'expected_ship_date': alloc.expected_ship_date,
                'contractual_delivery_date': alloc.contractual_delivery_date,
                'dealer_name': alloc.dealer_name or alloc.chi_nhanh or 'Dana Ford',
                'is_exact_color': is_exact_color,
                'phuong_an': 'Xe theo lịch phân bổ (Khớp màu)' if is_exact_color else f'Xe theo lịch phân bổ (Màu: {alloc.mau_sac or alloc.exterior_color})',
            })

    matched_allocs.sort(key=lambda x: (not x['is_exact_color'], x['allocation_month'], x['order_number']))
    return matched_allocs


@login_required
@api_errors
@role_required(SALE_ADMIN, WAREHOUSE)
@permission_required(['database.view_hopdong', 'database.view_tonkho'], raise_exception=True)
@require_GET
def suitable_vehicles(request, ma_hd):
    hd = get_object_or_404(HopDong, pk=ma_hd)
    if not is_da_nang_branch(hd.chi_nhanh):
        from django.http import Http404
        raise Http404
    criteria, results, error = find_suitable(hd)

    # Tra cứu xe theo lịch phân bổ cho kỳ tiếp theo (Tháng 11/2026)
    xe_phan_bo = find_allocation_vehicles(hd, criteria) if criteria else []

    if error:
        if wants_html(request):
            return render(request, 'contracts/suitable.html', {
                'page_title': f'Xe phù hợp hợp đồng {hd.pk}',
                'ma_hd': hd.pk,
                'co_the_xem_hop_dong': has_role(request.user, SALE_ADMIN),
                'tieu_chi_xac_nhan': criteria,
                'xe_phu_hop': [],
                'nhom_xe': [
                    {'id': 'xe-da-nang', 'tieu_de': 'Xe tại kho Đà Nẵng', 'xe': []},
                    {'id': 'xe-chi-nhanh', 'tieu_de': 'Xe tại kho Bình Định / Gia Lai', 'xe': []},
                    {'id': 'xe-phan-bo', 'tieu_de': 'Xe theo lịch phân bổ', 'xe': xe_phan_bo},
                ],
                'xe_da_nang': [],
                'xe_chi_nhanh': [],
                'xe_phan_bo': xe_phan_bo,
                'message': error,
                'canh_bao_du_lieu': error,
                'canh_bao': '',
            })
        return JsonResponse({'error': error}, status=400)

    # Thông báo tình trạng xe
    if not results and xe_phan_bo:
        info_msg = f'Cả ba kho hiện không có xe sẵn sàng. Hệ thống đã tự động đối chiếu và tìm thấy {len(xe_phan_bo)} xe phù hợp trong lịch phân bổ kỳ tiếp theo (Tháng 11/2026).'
    elif not results and not xe_phan_bo:
        info_msg = 'Cả ba kho và lịch phân bổ kỳ tiếp theo đều chưa có xe phù hợp. Hợp đồng tiếp tục chờ phân bổ các đợt tiếp theo.'
    else:
        info_msg = ''

    payload = {
        'ma_hd': hd.pk,
        'co_the_xem_hop_dong': has_role(request.user, SALE_ADMIN),
        'tieu_chi_xac_nhan': criteria,
        'xe_phu_hop': results,
        'message': info_msg,
    }
    payload['xe_da_nang'] = [row for row in results if row['uu_tien'] in (0, 2)]
    payload['xe_chi_nhanh'] = [row for row in results if row['uu_tien'] in (1, 3)]
    payload['xe_phan_bo'] = xe_phan_bo
    payload['nhom_xe'] = [
        {'id': 'xe-da-nang', 'tieu_de': 'Xe tại kho Đà Nẵng', 'xe': payload['xe_da_nang']},
        {'id': 'xe-chi-nhanh', 'tieu_de': 'Xe tại kho Bình Định / Gia Lai', 'xe': payload['xe_chi_nhanh']},
        {'id': 'xe-phan-bo', 'tieu_de': 'Xe theo lịch phân bổ', 'xe': xe_phan_bo},
        {'id': 'xe-pyc', 'tieu_de': 'Xe đang chờ PDI', 'xe': [row for row in results if row.get('nguon_pyc')]},
    ]
    payload['co_the_cho_phan_bo'] = not results and has_role(request.user, SALE_ADMIN)
    if wants_html(request):
        payload['page_title'] = f'Xe phù hợp hợp đồng {hd.pk}'
        return render(request, 'contracts/suitable.html', payload)
    return JsonResponse(payload)


@login_required
@role_required(SALE_ADMIN)
@permission_required('database.change_hopdong', raise_exception=True)
@require_POST
def choose_allocation_vehicle(request, ma_hd, alloc_id):
    """
    Chọn xe đề xuất từ lịch phân bổ nhà máy cho hợp đồng bán.
    Gán số khung VIN, cập nhật ngày giao dự kiến và chuyển hợp đồng sang CHO_XE_VE_KHO.
    """
    from orders.models import Allocation
    hd = get_object_or_404(HopDong, pk=ma_hd)
    alloc = get_object_or_404(Allocation, pk=alloc_id)

    if ChiTietHopDong.objects.filter(xe__vin=alloc.vin).exclude(hop_dong=hd).exists():
        messages.error(request, f'Xe VIN {alloc.vin} từ lịch phân bổ đã được gán cho một hợp đồng khác.')
        return redirect('contracts:xe_phu_hop', ma_hd=ma_hd)

    ten_xe = alloc.description or alloc.vehicle_code
    car, created = Xe.objects.get_or_create(
        vin=alloc.vin,
        defaults={
            'ten_xe': ten_xe,
            'loai_xe': alloc.vehicle_code or ten_xe,
            'phien_ban': alloc.description or '',
            'mau_sac': alloc.mau_sac or alloc.exterior_color or 'Tiêu chuẩn',
            'so_may': alloc.engine_number or f"ENG-{alloc.vin[-8:]}",
            'nam_sx': 2026,
            'trang_thai': TrangThaiXe.GIU_CHO_XUAT,
        }
    )

    ct_hd, ct_created = ChiTietHopDong.objects.get_or_create(hop_dong=hd, xe=car)

    update_fields = ['trang_thai']
    if alloc.contractual_delivery_date:
        hd.ngay_du_kien_giao = alloc.contractual_delivery_date
        update_fields.append('ngay_du_kien_giao')
    elif alloc.expected_ship_date:
        hd.ngay_du_kien_giao = alloc.expected_ship_date
        update_fields.append('ngay_du_kien_giao')

    hd.trang_thai = TrangThaiHopDong.CHO_XE_VE_KHO
    hd.save(update_fields=update_fields)

    ky_str = alloc.allocation_month.strftime('%m/%Y') if alloc.allocation_month else '11/2026'
    messages.success(
        request,
        f'Đã chọn xe VIN {alloc.vin} ({alloc.description}) từ lịch phân bổ Kỳ Tháng {ky_str} cho hợp đồng {hd.ma_hd}. '
        f'Trạng thái hợp đồng: {hd.get_trang_thai_display()}.'
    )
    return redirect('contracts:detail', ma_hd=ma_hd)


@login_required
@api_errors
@role_required(WAREHOUSE)
@permission_required(['database.view_hopdong', 'database.view_tonkho'], raise_exception=True)
@require_GET
def suggested_vehicle_detail(request, ma_hd, vin):
    hd = get_object_or_404(HopDong, pk=ma_hd)
    if not is_da_nang_branch(hd.chi_nhanh):
        from django.http import Http404
        raise Http404
    criteria, results, error = find_suitable(hd)
    if error:
        return JsonResponse({'error': error}, status=400)
    selected = [row for row in results if row['vin'] == vin]
    if not selected:
        return JsonResponse({'error': 'Xe không còn nằm trong kết quả đề xuất.'}, status=404)
    if wants_html(request):
        return render(request, 'contracts/vehicle_detail.html', {'page_title': 'Thông tin xe được đề xuất', 'ma_hd': hd.pk, 'xe': selected[0]})
    return JsonResponse({'ma_hd': hd.pk, 'xe': selected})


@login_required
@role_required(SALE_ADMIN)
@permission_required('database.change_hopdong', raise_exception=True)
@require_POST
def hoan_tat_hop_dong(request, ma_hd):
    """
    Xác nhận giao xe và hoàn tất hợp đồng:
    Ủy quyền qua XuatKhoService.duyet_phieu_xuat_kho để đảm bảo đồng bộ 100% nghiệp vụ xuất kho.
    """
    from warehouse.services import XuatKhoService, XuatKhoError
    hd = get_object_or_404(HopDong.objects.select_for_update(), pk=ma_hd)
    if hd.trang_thai == TrangThaiHopDong.HOAN_TAT:
        messages.info(request, f'Hợp đồng {ma_hd} đã ở trạng thái hoàn tất.')
        return redirect('contracts:detail', ma_hd=ma_hd)

    lines = list(hd.chitiethopdong_set.select_related('xe').all())
    if not lines:
        messages.error(request, f'Hợp đồng {ma_hd} chưa được chốt xe. Vui lòng chọn xe đề xuất trước khi hoàn tất.')
        return redirect('contracts:detail', ma_hd=ma_hd)

    nv = getattr(request.user, 'nhan_vien', None)
    if not nv and request.user.username in ('hieu', 'admin', 'phanquochieu'):
        nv = NhanVien.objects.filter(ma_nv='NV10').first()
    if not nv:
        nv = NhanVien.objects.first()

    pxk = PhieuXuatKho.objects.filter(chi_tiet_hop_dong__hop_dong=hd, trang_thai=TrangThaiPhieuXuat.CHO_DUYET).first()
    if pxk:
        try:
            XuatKhoService.duyet_phieu_xuat_kho(pxk.ma_pxk, nv.ma_nv)
            messages.success(request, f'Đã duyệt phiếu xuất kho {pxk.ma_pxk} và hoàn tất hợp đồng {ma_hd}. Tồn kho đã trừ và lưu báo cáo.')
            return redirect('contracts:detail', ma_hd=ma_hd)
        except XuatKhoError as e:
            messages.error(request, f'Không thể duyệt xuất kho: {e}')
            return redirect('contracts:detail', ma_hd=ma_hd)

    now = timezone.now()
    for line in lines:
        car = line.xe
        # 1. Trừ tồn kho (giữ lại bản ghi trong danh sách tồn kho với so_luong_ton = 0)
        tk = TonKho.objects.filter(xe=car, so_luong_ton__gt=0).first()
        if not tk:
            tk = TonKho.objects.filter(xe=car).first()

        if tk:
            tk.so_luong_ton = 0
            tk.save(update_fields=['so_luong_ton'])
            kho_xuat = tk.kho
        else:
            kho_xuat = Kho.objects.get(pk='KHO01')
            tk, _ = TonKho.objects.get_or_create(kho=kho_xuat, xe=car, defaults={'so_luong_ton': 0, 'ngay_vao_kho': now.date()})

        # 2. Cập nhật trạng thái xe sang DA_XUAT
        car.trang_thai = TrangThaiXe.DA_XUAT
        car.save(update_fields=['trang_thai'])

        # 3. Tạo/Cập nhật Phiếu xuất kho
        ma_pxk = f"PXK-{hd.ma_hd}-{car.vin[-6:]}"[:50]
        pxk, _ = PhieuXuatKho.objects.get_or_create(
            chi_tiet_hop_dong=line,
            defaults={
                'ma_pxk': ma_pxk,
                'kho': kho_xuat,
                'nguoi_nhan': hd.khach_hang.ten_kh,
                'nguoi_lap': nv,
                'nguoi_duyet': nv,
                'ngay_duyet': now,
                'ngay_xuat': now,
                'trang_thai': TrangThaiPhieuXuat.DA_DUYET,
                'ghi_chu': f"Xuất kho giao xe cho khách {hd.khach_hang.ten_kh} theo hợp đồng {hd.ma_hd}."
            }
        )
        if pxk.trang_thai != TrangThaiPhieuXuat.DA_DUYET:
            pxk.trang_thai = TrangThaiPhieuXuat.DA_DUYET
            pxk.nguoi_duyet = nv
            pxk.ngay_duyet = now
            pxk.ngay_xuat = now
            pxk.save(update_fields=['trang_thai', 'nguoi_duyet', 'ngay_duyet', 'ngay_xuat'])

        # 4. Ghi lịch sử xuất kho để phục vụ thống kê & báo cáo
        LichSuXuatKho.objects.create(
            phieu_xuat=pxk,
            xe=car,
            kho=kho_xuat,
            hanh_dong="DUYET_XUAT_KHO",
            nguoi_thuc_hien=nv,
            ghi_chu=f"Đã xuất bán xe {car.vin} cho hợp đồng {hd.ma_hd}. Tồn kho đã trừ và chuyển sang Đã xuất."
        )

    # 5. Cập nhật trạng thái hợp đồng thành HOAN_TAT
    hd.trang_thai = TrangThaiHopDong.HOAN_TAT
    hd.save(update_fields=['trang_thai'])

    # 6. Tạo thông báo toàn hệ thống
    try:
        from dashboard.models import ThongBaoHoatDong
        ten_admin = request.user.get_full_name() or request.user.username
        ThongBaoHoatDong.objects.create(
            user=request.user,
            ten_nhan_vien=ten_admin,
            chuc_vu="Quản trị viên (Sale Admin)",
            hanh_dong=f"Đã xuất kho & Hoàn tất hợp đồng {hd.ma_hd}",
            chi_tiet=f"Sale Admin {ten_admin} đã xác nhận giao xe và hoàn tất hợp đồng {hd.ma_hd} cho khách hàng {hd.khach_hang.ten_kh}. Xe đã xuất kho và tồn kho được cập nhật.",
            module="contracts",
            loai="tu_dong",
            is_active=True,
        )
    except Exception:
        pass

    messages.success(request, f'Hợp đồng {ma_hd} đã hoàn tất. Xe đã xuất kho và cập nhật báo cáo.')
    return redirect('contracts:detail', ma_hd=ma_hd)
