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
from database.models import HopDong, ChiTietHopDong, TonKho, HoaDonBan, TrangThaiHopDong, TrangThaiXe
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
    if request.GET.get('ngay_du_kien_giao'):
        try:
            day = date.fromisoformat(request.GET['ngay_du_kien_giao'])
        except ValueError:
            return JsonResponse({'error': 'Ngày phải theo YYYY-MM-DD.'}, status=400)
        rows = rows.filter(ngay_du_kien_giao=day)
    filters = {key: request.GET[key].strip().casefold() for key in ('dong_xe', 'phien_ban', 'mau_sac') if request.GET.get(key, '').strip()}
    data = []
    for hd in rows:
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
        return render(request, 'contracts/detail.html', {'page_title': f'Hợp đồng {hd.pk}', 'hop_dong': result})
    return JsonResponse(result)


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
    query = Q()
    for item in criteria:
        q_item = Q()
        if item.get('dong_xe'):
            q_item &= Q(xe__ten_xe__iexact=item['dong_xe'])
        if item.get('phien_ban'):
            q_item &= Q(xe__phien_ban__iexact=item['phien_ban'])
        if item.get('mau_sac'):
            q_item &= Q(xe__mau_sac__iexact=item['mau_sac'])
        if q_item:
            query |= q_item
    stocks = TonKho.objects.filter(query, so_luong_ton__gt=0, xe__trang_thai=TrangThaiXe.SAN_SANG).select_related('xe', 'kho__chi_nhanh').order_by('kho_id', 'xe_id')
    results = []
    for row in stocks:
        if ChiTietHopDong.objects.filter(xe_id=row.xe_id).exclude(hop_dong=hd).exists():
            continue
        from database.models import BienBanPDI
        if BienBanPDI.objects.filter(xe_id=row.xe_id).exclude(trang_thai_claim='Đã xử lý').exists():
            continue
        item = stock_data(row)
        local = is_da_nang_branch(row.kho.chi_nhanh)
        if not local and row.kho.chi_nhanh_id not in getattr(settings, 'III_IV_TRANSFER_BRANCH_IDS', ['CN02', 'CN03']):
            continue
        from .demand import matches
        item['tieu_chi_chi_so'] = [i for i, criterion in enumerate(criteria) if matches(row.xe, criterion)]
        item['phuong_an'] = 'Xe tại Đà Nẵng' if local else 'Cần lưu chuyển về Đà Nẵng'
        item['uu_tien'] = 0 if local else 1
        results.append(item)
    local_counts = {i: sum(row['uu_tien'] == 0 and i in row['tieu_chi_chi_so'] for row in results) for i in range(len(criteria))}
    results = [row for row in results if row['uu_tien'] == 0 or any(
        local_counts[i] < criteria[i].get('so_luong', 1) for i in row['tieu_chi_chi_so'])]
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
                        'trang_thai_hien_thi': 'Chờ PDI', 'phuong_an': 'Xe từ PYC - chờ PDI', 'uu_tien': 2,
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
        messages.success(request, f'Đã chốt VIN {vin}; hợp đồng chuyển sang {contract.get_trang_thai_display()}.')
    except (ValidationError, HopDong.DoesNotExist):
        messages.error(request, 'VIN không thể được chốt cho hợp đồng ở thời điểm này.')
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
                ],
                'message': error,
                'canh_bao_du_lieu': error,
                'canh_bao': '',
            })
        return JsonResponse({'error': error}, status=400)
    payload = {'ma_hd': hd.pk, 'co_the_xem_hop_dong': has_role(request.user, SALE_ADMIN), 'tieu_chi_xac_nhan': criteria,
                         'xe_phu_hop': results, 'message': '' if results else 'Cả ba kho chưa có xe phù hợp. Hợp đồng chờ xe; nhu cầu được dùng để đối chiếu kỳ phân bổ tiếp theo.'}
    payload['xe_da_nang'] = [row for row in results if row['uu_tien'] == 0]
    payload['xe_chi_nhanh'] = [row for row in results if row['uu_tien'] == 1]
    payload['nhom_xe'] = [
        {'id': 'xe-da-nang', 'tieu_de': 'Xe tại kho Đà Nẵng', 'xe': payload['xe_da_nang']},
        {'id': 'xe-chi-nhanh', 'tieu_de': 'Xe tại kho Bình Định / Gia Lai', 'xe': payload['xe_chi_nhanh']},
        {'id': 'xe-pyc', 'tieu_de': 'Xe đang chờ PDI', 'xe': [row for row in results if row.get('nguon_pyc')]},
    ]
    payload['co_the_cho_phan_bo'] = not results and has_role(request.user, SALE_ADMIN)
    if wants_html(request):
        payload['page_title'] = f'Xe phù hợp hợp đồng {hd.pk}'
        return render(request, 'contracts/suitable.html', payload)
    return JsonResponse(payload)


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
