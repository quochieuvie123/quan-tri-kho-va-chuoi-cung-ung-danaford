"""Backend III; GET chỉ tra cứu, không gán VIN hoặc giữ xe."""
from datetime import date
from django.contrib.auth.decorators import login_required, permission_required
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET
from core.iii_iv_api import api_errors
from core.iii_iv_access import role_required, has_role, is_da_nang_branch, SALE_ADMIN, WAREHOUSE
from database.models import HopDong, ChiTietHopDong, TonKho, HoaDonBan
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
    return {
        'ma_hd': hd.pk, 'khach_hang_id': hd.khach_hang_id,
        'khach_hang__ten_kh': hd.khach_hang.ten_kh, 'chi_nhanh_id': hd.chi_nhanh_id,
        'ngay_ky': hd.ngay_ky, 'so_tien_coc': hd.so_tien_coc,
        'dong_xe_yeu_cau': (hd.dong_xe_yeu_cau or '').strip() or first.get('dong_xe'),
        'phien_ban_yeu_cau': (hd.phien_ban_yeu_cau or '').strip() or first.get('phien_ban'),
        'mau_sac_yeu_cau': (hd.mau_sac_yeu_cau or '').strip() or first.get('mau_sac'),
        'ngay_du_kien_giao': hd.ngay_du_kien_giao, 'trang_thai': hd.trang_thai,
        'tieu_chi_xe': criteria, 'canh_bao': warning,
        'thao_tac': {'xem_chi_tiet': has_role(user, SALE_ADMIN) and user.has_perm('database.view_hopdong'),
                    'de_xuat_xe': has_role(user, WAREHOUSE) and user.has_perms(['database.view_hopdong', 'database.view_tonkho'])},
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
            rows = rows.filter(**{field: request.GET[param].strip()})
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
        payload.update(page_title='Quản lý hợp đồng xe bán')
        return render(request, 'contracts/index.html', payload)
    return JsonResponse(payload)


@login_required
@api_errors
@role_required(SALE_ADMIN)
@permission_required('database.view_hopdong', raise_exception=True)
@require_GET
def detail(request, ma_hd):
    hd = get_object_or_404(HopDong.objects.select_related('khach_hang'), pk=ma_hd)
    result = contract_summary(hd, request.user)
    result.update({
        'khach_hang': hd.khach_hang_id, 'ten_khach_hang': hd.khach_hang.ten_kh,
        'sdt_khach_hang': hd.khach_hang.sdt_kh, 'chi_nhanh': hd.chi_nhanh_id,
        'dong_xe': result['dong_xe_yeu_cau'], 'phien_ban': result['phien_ban_yeu_cau'],
        'mau_sac': result['mau_sac_yeu_cau'],
        'xe': list(ChiTietHopDong.objects.filter(hop_dong=hd).order_by('xe_id').values('xe_id', 'xe__ten_xe', 'xe__phien_ban', 'xe__loai_xe', 'xe__mau_sac')),
        # Chỉ lấy hóa đơn có liên kết thực qua phiếu xuất, không ghép theo khách hàng.
        'hoa_don': list(HoaDonBan.objects.filter(phieu_xuat_kho__chi_tiet_hop_dong__hop_dong=hd).order_by('ma_hdb').values('ma_hdb', 'so_hoa_don')),
    })
    result['vin_hien_thi'] = [line['xe_id'] for line in result['xe']]
    result['hoa_don_canh_bao'] = None if result['hoa_don'] else 'Chưa có hóa đơn liên kết qua phiếu xuất kho.'
    if wants_html(request):
        return render(request, 'contracts/detail.html', {'page_title': f'Hợp đồng {hd.pk}', 'hop_dong': result})
    return JsonResponse(result)


def find_suitable(hd):
    criteria, warning = criteria_for(hd)
    if warning:
        return criteria, [], warning
    query = Q()
    for item in criteria:
        query |= Q(xe__ten_xe__iexact=item['dong_xe'], xe__phien_ban__iexact=item['phien_ban'], xe__mau_sac__iexact=item['mau_sac'])
    stocks = TonKho.objects.filter(query, so_luong_ton__gt=0).select_related('xe', 'kho__chi_nhanh').order_by('kho_id', 'xe_id')
    results = []
    for row in stocks:
        if ChiTietHopDong.objects.filter(xe_id=row.xe_id).exclude(hop_dong=hd).exists():
            continue
        from database.models import BienBanPDI
        if BienBanPDI.objects.filter(xe_id=row.xe_id).exclude(trang_thai_claim='Đã xử lý').exists():
            continue
        item = stock_data(row)
        local = is_da_nang_branch(row.kho.chi_nhanh)
        item['phuong_an'] = 'Xe tại Đà Nẵng' if local else 'Cần lưu chuyển về Đà Nẵng'
        item['uu_tien'] = 0 if local else 1
        results.append(item)
    results.sort(key=lambda item: (item['uu_tien'], item['kho_id'], item['vin']))
    return criteria, results, None


@login_required
@api_errors
@role_required(WAREHOUSE)
@permission_required(['database.view_hopdong', 'database.view_tonkho'], raise_exception=True)
@require_GET
def suitable_vehicles(request, ma_hd):
    hd = get_object_or_404(HopDong, pk=ma_hd)
    criteria, results, error = find_suitable(hd)
    if error:
        if wants_html(request):
            return render(request, 'contracts/suitable.html', {
                'page_title': f'Xe phù hợp hợp đồng {hd.pk}',
                'ma_hd': hd.pk,
                'tieu_chi_xac_nhan': criteria,
                'xe_phu_hop': [],
                'message': error,
                'canh_bao_du_lieu': error,
                'canh_bao': '',
            })
        return JsonResponse({'error': error}, status=400)
    payload = {'ma_hd': hd.pk, 'tieu_chi_xac_nhan': criteria,
                         'canh_bao_du_lieu': 'Chỉ đối chiếu xe có đủ dòng xe, phiên bản và màu sắc; dữ liệu thiếu có thể làm kết quả chưa đầy đủ.',
                         'canh_bao': 'Kết quả chỉ tra cứu tồn kho; chưa xác minh giữ chỗ hoặc sẵn sàng bán.',
                         'xe_phu_hop': results, 'message': '' if results else 'Cả ba kho chưa có xe phù hợp. Hợp đồng chờ xe; nhu cầu được dùng để đối chiếu kỳ phân bổ tiếp theo.'}
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
    criteria, results, error = find_suitable(hd)
    if error:
        return JsonResponse({'error': error}, status=400)
    selected = [row for row in results if row['vin'] == vin]
    if not selected:
        return JsonResponse({'error': 'Xe không còn nằm trong kết quả đề xuất.'}, status=404)
    if wants_html(request):
        return render(request, 'contracts/vehicle_detail.html', {'page_title': 'Thông tin xe được đề xuất', 'ma_hd': hd.pk, 'xe': selected[0]})
    return JsonResponse({'ma_hd': hd.pk, 'xe': selected})
