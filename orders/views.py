from .availability import (
    release_expired_draft_requests,
    get_allocations_availability_map,
    get_allocation_status,
    AllocationAvailabilityStatus
)

from django.utils import timezone
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from .models import Allocation
from .forms import AllocationUploadForm
from openpyxl import load_workbook
from datetime import datetime, date
from django.db import transaction
from django.db.models import Q


from io import BytesIO

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.mail import EmailMessage
from django.db.models import Sum
from django.http import HttpResponse
from django.template.loader import render_to_string
from xhtml2pdf import pisa

from .models import Allocation, VehicleRequest, VehicleRequestItem
from database.models import ChiNhanh
from core.roles import get_user_role_info

import os
from django.contrib.staticfiles import finders

MONTH_EN_MAP = {
    'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
    'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12
}

def chuyen_ngay(value):
    if value is None or value == "" or value == 0 or value == "0":
        return None

    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, date):
        return value

    if isinstance(value, str):
        val_str = value.strip()
        if not val_str or val_str.startswith("1899-12-31") or val_str == "0":
            return None

        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d", "%d-%m-%Y"):
            try:
                return datetime.strptime(val_str, fmt).date()
            except ValueError:
                continue

    return None

import re

def chuyen_thang(value, default_date=None):
    if value is None or value == "":
        return default_date

    if isinstance(value, datetime):
        return value.date().replace(day=1)

    if isinstance(value, date):
        return value.replace(day=1)

    if isinstance(value, str):
        val_str = value.strip()

        # Tiếng Việt: "Tháng 10 năm 2026", "Tháng 10/2026"
        m_vn = re.search(r"Tháng\s+(\d{1,2})(?:\s+năm|\s*[/.-])\s*(\d{2,4})", val_str, flags=re.IGNORECASE)
        if m_vn:
            nam = int(m_vn.group(2))
            if nam < 100:
                nam += 2000
            return date(nam, int(m_vn.group(1)), 1)

        # Dạng MM/YYYY hoặc MM-YYYY hoặc MM/YY
        m_slash = re.search(r"(?:^|[^\d])(\d{1,2})[/.-](\d{2,4})(?:$|[^\d])", val_str)
        if m_slash:
            nam = int(m_slash.group(2))
            if nam < 100:
                nam += 2000
            return date(nam, int(m_slash.group(1)), 1)

        # Dạng YYYY-MM
        m_dash = re.search(r"(?:^|[^\d])(\d{4})[/.-](\d{1,2})(?:$|[^\d])", val_str)
        if m_dash:
            return date(int(m_dash.group(1)), int(m_dash.group(2)), 1)

        # Tiếng Anh: "Oct 2026 Allocation", "OCT 26 DEFER FROM SEP", "Sep 2026"
        m_en = re.search(r"(?:\b|_)(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*[\s_-]+(?:20)?(\d{2,4})(?:\b|_)", val_str, flags=re.IGNORECASE)
        if m_en:
            thang = MONTH_EN_MAP.get(m_en.group(1).lower()[:3], 1)
            nam = int(m_en.group(2))
            if nam < 100:
                nam += 2000
            return date(nam, thang, 1)

    return default_date

def chuyen_chuoi(value):
    if value is None:
        return ""

    if isinstance(value, str):
        return value.strip()

    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return str(value)

    if isinstance(value, (int, date, datetime)):
        return str(value)

    return str(value).strip()

def chuyen_so_luong(value, default=1):
    if value is None or isinstance(value, bool):
        return default

    try:
        so_luong = int(str(value).strip())
        return so_luong if so_luong > 0 else default
    except (ValueError, TypeError, OverflowError):
        return default

@login_required
def order_index(request):
    """Điều hướng Quản lý đặt xe: Admin vào Phân bổ, Sale vào Đặt xe"""
    from core.roles import get_user_role_info
    role_info = get_user_role_info(request.user)
    if request.user.is_superuser or (role_info and role_info.get('code') == 'ADMIN'):
        return redirect('orders:allocation_list')
    return redirect('orders:vehicle_orders')


def lay_danh_sach_thang_phan_bo(current_cn="ALL"):
    qs = Allocation.objects.filter(allocation_month__isnull=False)
    if current_cn and current_cn != "ALL":
        qs = qs.filter(chi_nhanh__ma_cn=current_cn)
    
    months = qs.values_list("allocation_month", flat=True).distinct().order_by("-allocation_month")
    res = []
    seen = set()
    for m in months:
        val = m.strftime("%Y-%m")
        if val not in seen:
            seen.add(val)
            cnt = qs.filter(allocation_month__year=m.year, allocation_month__month=m.month).count()
            res.append({
                "value": val,
                "label": f"Tháng {m.month:02d}/{m.year} ({cnt} xe)",
                "year": m.year,
                "month": m.month
            })
    return res

def xu_ly_loc_phan_bo(request):
    current_cn = request.session.get("current_cn", "ALL")
    allocations = Allocation.objects.all().select_related("chi_nhanh").order_by("-allocation_month", "id")

    # Lọc theo chi nhánh từ Header
    if current_cn and current_cn != "ALL":
        allocations = allocations.filter(chi_nhanh__ma_cn=current_cn)

    month_options = lay_danh_sach_thang_phan_bo(current_cn)
    selected_month = request.GET.get("month", "").strip()

    if selected_month == "ALL":
        # Xem tất cả các tháng
        pass
    elif selected_month and "-" in selected_month:
        try:
            y, m = map(int, selected_month.split("-"))
            allocations = allocations.filter(allocation_month__year=y, allocation_month__month=m)
        except ValueError:
            pass
    else:
        # Nếu chưa chọn tháng: ưu tiên tháng hiện tại nếu có xe, nếu không thì lấy tháng gần nhất
        today = timezone.localdate()
        cur_key = f"{today.year}-{today.month:02d}"
        has_cur = any(opt["value"] == cur_key for opt in month_options)
        if has_cur:
            selected_month = cur_key
            allocations = allocations.filter(allocation_month__year=today.year, allocation_month__month=today.month)
        elif month_options:
            selected_month = month_options[0]["value"]
            allocations = allocations.filter(allocation_month__year=month_options[0]["year"], allocation_month__month=month_options[0]["month"])
        else:
            selected_month = "ALL"

    return allocations, selected_month, month_options, current_cn

@login_required
def allocation_list(request):
    today = timezone.localdate()

    if request.method == "POST":
        form = AllocationUploadForm(request.POST, request.FILES)

        if form.is_valid():
            file = form.cleaned_data["file"]

            if not file.name.lower().endswith(".xlsx"):
                messages.error(request, "Chỉ chấp nhận file định dạng Excel (.xlsx)")
            else:
                workbook = None

                try:
                    workbook = load_workbook(
                        file,
                        read_only=True,
                        data_only=True
                    )

                    sheet = workbook.active

                    if sheet is None:
                        raise ValueError("File Excel không có sheet dữ liệu hợp lệ")

                    all_rows = list(sheet.iter_rows(values_only=True))
                    if not all_rows:
                        raise ValueError("File Excel hoàn toàn trống dữ liệu")

                    # ==============================================================
                    # TỰ ĐỘNG NHẬN DIỆN TIÊU ĐỀ CỘT (HEADER MAPPING TỰ ĐỘNG)
                    # ==============================================================
                    header_row_idx = None
                    col_map = {}

                    # Duyệt qua tối đa 10 dòng đầu để tìm dòng chứa tiêu đề 'VIN'
                    for idx, r in enumerate(all_rows[:10]):
                        if r and any(isinstance(c, str) and c.strip().upper() in ("VIN", "SỐ KHUNG", "VIN/CHASSIS") for c in r if c is not None):
                            header_row_idx = idx
                            break

                    if header_row_idx is not None:
                        # Ánh xạ theo tên cột thực tế trong file
                        for c_idx, cell_val in enumerate(all_rows[header_row_idx]):
                            if cell_val is None:
                                continue
                            c_name = str(cell_val).strip().upper()

                            if c_name in ("VIN", "SỐ KHUNG", "CHASSIS NUMBER", "CHASSIS_NO") and "vin" not in col_map:
                                col_map["vin"] = c_idx
                            elif c_name in ("ORDER_NO", "ORDER NO", "ORDER NUMBER", "ORDER_NUMBER", "SỐ ĐƠN ĐẶT HÀNG", "SỐ ĐƠN HÀNG", "SO DON HANG", "ORDER", "PO", "PO NO", "PO_NO", "PO NUMBER", "PO_NUMBER", "P/O", "MÃ ĐƠN", "MA DON", "MÃ ĐƠN HÀNG", "MA DON HANG", "MÃ ĐẶT HÀNG", "MA DAT HANG") and "order_number" not in col_map:
                                col_map["order_number"] = c_idx
                            elif c_name in ("MODEL CODE", "MODEL_CODE", "MÃ DÒNG XE", "MÃ XE", "MA DONG XE", "VEHICLE CODE", "VEHICLE_CODE") and "vehicle_code" not in col_map:
                                col_map["vehicle_code"] = c_idx
                            elif c_name in ("DESCRIPTION", "MODEL DESC", "MODEL_DESC", "MÔ TẢ", "MO TA", "TÊN XE", "TEN XE") and "description" not in col_map:
                                col_map["description"] = c_idx
                            elif c_name in ("COLOR CODE", "COLOR_CODE", "COLOUR CODE", "COLOUR_CODE", "MÃ MÀU", "MA MAU") and "color_code" not in col_map:
                                col_map["color_code"] = c_idx
                            elif c_name in ("EXTERIOR COLOUR", "EXTERIOR COLOR", "MÀU NGOẠI THẤT", "MAU NGOAI THAT", "COLOUR (FN)") and "exterior_color" not in col_map:
                                col_map["exterior_color"] = c_idx
                            elif c_name in ("MÀU SẮC", "MAU SAC", "MÀU", "MAU", "COLOR", "COLOUR") and "mau_sac" not in col_map:
                                col_map["mau_sac"] = c_idx
                            elif c_name in ("ENGINE_NUMBER", "ENGINE NUMBER", "ENGINE NO", "SỐ MÁY", "SO MAY") and "engine_number" not in col_map:
                                col_map["engine_number"] = c_idx
                            elif c_name in ("QUANTITY", "SỐ LƯỢNG", "SO LUONG", "QTY") and "quantity" not in col_map:
                                col_map["quantity"] = c_idx
                            elif c_name in ("NGÀY DỰ KIẾN SHIP", "NGAY DU KIEN SHIP", "EXPECTED SHIP DATE", "EXPECTED_SHIP_DATE", "ESTIMATED SHIP DATE", "SHIP DATE") and "expected_ship_date" not in col_map:
                                col_map["expected_ship_date"] = c_idx
                            elif c_name in ("NGÀY DỰ KIẾN GIAO THEO HỢP ĐỒNG", "NGAY DU KIEN GIAO THEO HOP DONG", "NGÀY DỰ KIẾN GIAO", "NGAY DU KIEN GIAO", "CONTRACTUAL DELIVERY DATE", "CONTRACTUAL_DELIVERY_DATE") and "contractual_delivery_date" not in col_map:
                                col_map["contractual_delivery_date"] = c_idx
                            elif c_name in ("ALLOCATION MONTH", "ALLOCATION_MONTH", "THÁNG PHÂN BỔ", "THANG PHAN BO", "ALLOCATION") and "allocation_month" not in col_map:
                                col_map["allocation_month"] = c_idx
                            elif c_name in ("DEALER NAME", "DEALER_NAME", "DEALER", "TÊN ĐẠI LÝ", "TEN DAI LY", "ĐẠI LÝ", "DAI LY", "CHI NHÁNH", "CHI NHANH") and "dealer_name" not in col_map:
                                col_map["dealer_name"] = c_idx
                            elif c_name in ("DEALER CODE", "DEALER_CODE", "MÃ ĐẠI LÝ", "MA DAI LY", "MÃ ĐL", "MA DL") and "dealer_code" not in col_map:
                                col_map["dealer_code"] = c_idx
                            elif c_name in ("SHIP TO", "SHIP_TO", "NƠI GIAO", "NOI GIAO", "ĐIỂM GIAO", "DIEM GIAO") and "ship_to" not in col_map:
                                col_map["ship_to"] = c_idx

                        start_data_idx = header_row_idx + 1
                    else:
                        # Fallback tương thích cấu trúc 12 cột cũ
                        col_map = {
                            "order_number": 1,
                            "vehicle_code": 2,
                            "description": 3,
                            "vin": 4,
                            "color_code": 5,
                            "exterior_color": 6,
                            "engine_number": 7,
                            "quantity": 8,
                            "expected_ship_date": 9,
                            "contractual_delivery_date": 10,
                            "allocation_month": 11,
                        }
                        start_data_idx = 1

                    if "vin" not in col_map:
                        raise ValueError("Không tìm thấy cột Số khung (VIN) trong file Excel")

                    data = []
                    qty_warnings = []
                    vin_seen_counts = defaultdict(int)
                    default_month = today.replace(day=1)

                    for row_number, row in enumerate(all_rows[start_data_idx:], start=start_data_idx + 1):
                        if not any(value is not None for value in row):
                            continue

                        vin_idx = col_map["vin"]
                        vin = chuyen_chuoi(row[vin_idx]) if vin_idx < len(row) else ""

                        # Bỏ qua dòng rỗng hoặc dòng header lặp lại
                        if not vin or len(vin) < 5 or vin.upper() == "VIN":
                            continue

                        def get_col(fld):
                            idx = col_map.get(fld)
                            return row[idx] if idx is not None and idx < len(row) else None

                        alloc_month = chuyen_thang(get_col("allocation_month"), default_date=default_month)

                        d_name_val = chuyen_chuoi(get_col("dealer_name"))
                        d_code_val = chuyen_chuoi(get_col("dealer_code"))
                        shipto_val = chuyen_chuoi(get_col("ship_to"))

                        combined_br = f"{d_name_val} {d_code_val} {shipto_val}".upper()
                        if any(k in combined_br for k in ("GIA LAI", "GL")):
                            target_ma_cn = "CN03"
                            d_lbl = "Dana Ford Gia Lai"
                        elif any(k in combined_br for k in ("BINH DINH", "BÌNH ĐỊNH", "V20011")):
                            target_ma_cn = "CN02"
                            d_lbl = "Dana Ford Bình Định"
                        else:
                            target_ma_cn = "CN01"
                            d_lbl = "Dana Ford Đà Nẵng"

                        cn_obj = ChiNhanh.objects.filter(ma_cn=target_ma_cn).first()

                        raw_qty = chuyen_so_luong(get_col("quantity"), default=1)
                        if raw_qty and raw_qty > 1:
                            qty_warnings.append(f"{vin} (x{raw_qty})")

                        # Đảm bảo mỗi 1 xe có 1 mã số VIN riêng biệt (thêm hậu tố -1, -2... nếu số lượng > 1 hoặc trùng VIN)
                        for q_idx in range(raw_qty):
                            vin_seen_counts[vin] += 1
                            if raw_qty > 1 or vin_seen_counts[vin] > 1:
                                unique_vin = f"{vin}-{vin_seen_counts[vin]}"
                            else:
                                unique_vin = vin

                            data.append({
                                "vin": unique_vin,
                                "order_number": chuyen_chuoi(get_col("order_number")),
                                "vehicle_code": chuyen_chuoi(get_col("vehicle_code")),
                                "description": chuyen_chuoi(get_col("description")),
                                "color_code": chuyen_chuoi(get_col("color_code")),
                                "exterior_color": chuyen_chuoi(get_col("exterior_color")),
                                "mau_sac": chuyen_chuoi(get_col("mau_sac")) or chuyen_chuoi(get_col("exterior_color")),
                                "engine_number": chuyen_chuoi(get_col("engine_number")),
                                "quantity": 1,
                                "expected_ship_date": chuyen_ngay(get_col("expected_ship_date")),
                                "contractual_delivery_date": chuyen_ngay(get_col("contractual_delivery_date")),
                                "allocation_month": alloc_month,
                                "dealer_name": d_name_val or d_lbl,
                                "dealer_code": d_code_val or ("V20011" if target_ma_cn == "CN02" else ("V20012" if target_ma_cn == "CN03" else "VD2001")),
                                "chi_nhanh": cn_obj,
                            })

                    if not data:
                        raise ValueError("Không đọc được dòng dữ liệu xe phân bổ hợp lệ nào từ file Excel")

                    with transaction.atomic():
                        for item in data:
                            vin_val = item.pop("vin")
                            Allocation.objects.update_or_create(
                                vin=vin_val,
                                defaults=item
                            )

                    # TỰ ĐỘNG ĐỒNG BỘ CHỈ TIÊU PHÂN BỔ SANG MODULE DỰ BÁO NHU CẦU (ANALYTICS)
                    try:
                        from analytics.models import ChiTieuPhanBo
                        summary_pbs = (
                            Allocation.objects
                            .filter(allocation_month__isnull=False)
                            .values("allocation_month__year", "allocation_month__month", "description")
                            .annotate(tong_pb=Sum("quantity"))
                        )
                        for pb in summary_pbs:
                            desc = pb["description"]
                            if desc:
                                ChiTieuPhanBo.objects.update_or_create(
                                    nam=pb["allocation_month__year"],
                                    thang=pb["allocation_month__month"],
                                    ten_xe=desc,
                                    defaults={"so_luong": pb["tong_pb"]}
                                )
                    except Exception:
                        pass

                    if qty_warnings:
                        messages.warning(
                            request,
                            f"Thông báo: Có {len(qty_warnings)} dòng xe có số lượng > 1 trong file Excel đã được tách thành từng xe riêng biệt với mã số VIN độc lập (hậu tố -1, -2, -3...): {', '.join(qty_warnings[:5])}{'...' if len(qty_warnings) > 5 else ''}."
                        )
                    messages.success(
                        request,
                        f"Tải danh sách phân bổ thành công! Đã nạp {len(data)} xe vào hệ thống."
                    )
                    return redirect("orders:allocation_list")

                except Exception as e:
                    messages.error(
                        request,
                        f"Không thể nhập dữ liệu: {e}"
                    )

                finally:
                    if workbook is not None:
                        workbook.close()

    else:
        form = AllocationUploadForm()

    allocations, selected_month, month_options, current_cn = xu_ly_loc_phan_bo(request)

    cn_name = "Tất cả các chi nhánh"
    if current_cn and current_cn != "ALL":
        cn_obj = ChiNhanh.objects.filter(ma_cn=current_cn).first()
        if cn_obj:
            cn_name = cn_obj.ten_cn

    release_expired_draft_requests()
    avail_map = get_allocations_availability_map(allocations)
    for a_item in allocations:
        a_item.availability_info = avail_map.get(a_item.id)

    tong_so_xe = allocations.aggregate(total=Sum("quantity"))["total"] or 0
    return render(request, "danh_sach_pb.html", {
        "form": form,
        "allocations": allocations,
        "tong_so_xe": tong_so_xe,
        "selected_month": selected_month,
        "month_options": month_options,
        "current_cn": current_cn,
        "current_cn_name": cn_name,
    })

# Đặt xe

def _get_pending_contract_alloc_map():
    """Trả về dict {alloc_id: ma_hd} cho các xe phân bổ đã chốt từ Hợp đồng nhưng chưa lập PYC."""
    from database.models import ChiTietHopDong, TrangThaiHopDong, TonKho
    from transfers.models import ChiTietLenhLuuChuyen
    from warehouse.models import PhieuNhapKho

    pending_cts = ChiTietHopDong.objects.filter(
        hop_dong__trang_thai=TrangThaiHopDong.CHO_XE_VE_KHO,
    ).select_related("xe", "hop_dong")

    vin_to_hd = {}
    for ct in pending_cts:
        vin = ct.xe_id
        if TonKho.objects.filter(xe_id=vin, so_luong_ton__gt=0).exists():
            continue
        if PhieuNhapKho.objects.filter(xe_id=vin).exists():
            continue
        if ChiTietLenhLuuChuyen.objects.filter(xe_id=vin).exists():
            continue
        if VehicleRequestItem.objects.filter(
            allocation__vin=vin
        ).exclude(vehicle_request__status=VehicleRequest.Status.REJECTED).exists():
            continue
        vin_to_hd[vin] = ct.hop_dong_id

    if not vin_to_hd:
        return {}

    res = {}
    for alloc in Allocation.objects.filter(vin__in=list(vin_to_hd.keys())).order_by("id"):
        res[str(alloc.id)] = vin_to_hd[alloc.vin]
    return res


def _merge_selected_vehicles(request):
    from database.models import ChiTietHopDong
    danh_sach = dict(request.session.get("selected_vehicles", {}))
    selected_contracts = dict(request.session.get("selected_vehicle_contracts", {}))
    db_pending = _get_pending_contract_alloc_map()
    for alloc_id_str, ma_hd in db_pending.items():
        if alloc_id_str not in danh_sach:
            danh_sach[alloc_id_str] = 1
        if alloc_id_str not in selected_contracts:
            selected_contracts[alloc_id_str] = ma_hd
    return danh_sach, selected_contracts


@login_required
def dat_xe(request):
        keyword = request.GET.get("keyword", "").strip()

        # Lấy ngày hiện tại theo múi giờ Django
        today = timezone.localdate()

        allocations, selected_month, month_options, current_cn = xu_ly_loc_phan_bo(request)

        # Tìm kiếm theo VIN, mô tả, mã xe, màu sắc
        if keyword:
            allocations = allocations.filter(
                Q(vin__icontains=keyword) |
                Q(description__icontains=keyword) |
                Q(vehicle_code__icontains=keyword) |
                Q(exterior_color__icontains=keyword)
            )

        cn_name = "Tất cả các chi nhánh"
        if current_cn and current_cn != "ALL":
            cn_obj = ChiNhanh.objects.filter(ma_cn=current_cn).first()
            if cn_obj:
                cn_name = cn_obj.ten_cn

        release_expired_draft_requests()
        avail_map = get_allocations_availability_map(allocations)
        for xe_item in allocations:
            xe_item.availability_info = avail_map.get(xe_item.id)

        context = {
            "keyword": keyword,
            "allocations": allocations,
            "selected_month": selected_month,
            "month_options": month_options,
            "current_cn": current_cn,
            "current_cn_name": cn_name,
        }
        # Lấy danh sách xe đã chọn trong Session kết hợp từ DB (không mất khi đổi tài khoản / trình duyệt)
        from database.models import ChiTietHopDong
        danh_sach, selected_contracts = _merge_selected_vehicles(request)

        xe_da_chon = []

        for ma_xe, so_luong in danh_sach.items():
            xe = Allocation.objects.filter(id=ma_xe).first()

            if xe:
                ma_hd_link = selected_contracts.get(str(ma_xe)) or ChiTietHopDong.objects.filter(xe__vin=xe.vin).values_list("hop_dong_id", flat=True).first()
                xe_da_chon.append({
                    "xe": xe,
                    "quantity": so_luong,
                    "ma_hd": ma_hd_link,
                })
        context["xe_da_chon"] = xe_da_chon
        return render(request, "tim_kiem_xe.html", context)



@login_required
def chi_tiet_xe(request, id):
    today = timezone.localdate()

    # Lấy thông tin xe phân bổ theo id
    xe = get_object_or_404(
        Allocation,
        id=id
    )

    if request.method == "POST":
        danh_sach = request.session.get("selected_vehicles", {})
        ma_xe = str(xe.id)

        # Kiểm tra nếu VIN đã có trong danh sách đã chọn thì báo "Xe đã có trong phiếu"
        selected_ids = [int(k) for k in danh_sach.keys() if str(k).isdigit()]
        existing_vins = set(Allocation.objects.filter(id__in=selected_ids).values_list("vin", flat=True))

        if ma_xe in danh_sach or xe.vin in existing_vins:
            messages.error(request, "Xe đã có trong phiếu.")
            return redirect("orders:vehicle_orders")

        with transaction.atomic():
            locked_alloc = Allocation.objects.select_for_update().filter(id=xe.id).first()
            status_info = get_allocation_status(locked_alloc)
            if not status_info["is_available"]:
                messages.error(request, f"Xe VIN {xe.vin} không khả dụng ({status_info['label']}).")
                return redirect("orders:vehicle_orders")

            danh_sach[ma_xe] = 1
            request.session["selected_vehicles"] = danh_sach
            messages.success(request, "Đã thêm xe vào danh sách.")
            return redirect("orders:vehicle_orders")

    return render(request, "chi_tiet_xe.html", {
        "xe": xe
    })

from django.views.decorators.http import require_POST

@login_required
@require_POST
def xoa_xe_da_chon(request, xe_id):
    # Lấy danh sách xe đã chọn từ Session
    danh_sach = dict(request.session.get("selected_vehicles", {}))
    selected_contracts = dict(request.session.get("selected_vehicle_contracts", {}))

    # ID trong Session được lưu dưới dạng chuỗi
    ma_xe = str(xe_id)
    removed = False

    if ma_xe in danh_sach:
        del danh_sach[ma_xe]
        selected_contracts.pop(ma_xe, None)
        request.session["selected_vehicles"] = danh_sach
        request.session["selected_vehicle_contracts"] = selected_contracts
        removed = True

    db_pending = _get_pending_contract_alloc_map()
    if ma_xe in db_pending:
        from database.models import ChiTietHopDong, HopDong, TrangThaiHopDong
        alloc_obj = Allocation.objects.filter(pk=xe_id).first()
        if alloc_obj:
            ma_hd = db_pending[ma_xe]
            ChiTietHopDong.objects.filter(hop_dong_id=ma_hd, xe__vin=alloc_obj.vin).delete()
            HopDong.objects.filter(pk=ma_hd, trang_thai=TrangThaiHopDong.CHO_XE_VE_KHO).update(
                trang_thai=TrangThaiHopDong.CHO_XU_LY
            )
            removed = True

    if removed:
        messages.success(request, "Đã xóa xe khỏi danh sách.")
    else:
        messages.error(request, "Xe không tồn tại trong danh sách đã chọn.")

    return redirect("orders:vehicle_orders")


@login_required
def lap_phieu_yeu_cau(request):

    # 1. Lấy danh sách xe đã chọn từ Session + Hợp đồng phân bổ đang chờ lập PYC
    danh_sach, selected_contracts = _merge_selected_vehicles(request)

    if not danh_sach:
        messages.error(
            request,
            "Bạn chưa chọn xe nào để lập phiếu."
        )
        return redirect("orders:vehicle_orders")

    today = timezone.localdate()

    xe_trong_phieu = []

    # 2. Kiểm tra tất cả xe trước khi tạo phiếu
    for ma_xe, so_luong in danh_sach.items():

        xe = Allocation.objects.filter(
            pk=ma_xe
        ).first()

        if xe is None:
            messages.error(
                request,
                "Không tìm thấy thông tin xe trong danh sách phân bổ."
            )
            return redirect("orders:vehicle_orders")

        if (
            type(so_luong) is not int
            or so_luong <= 0
            or so_luong > xe.quantity
        ):
            messages.error(
                request,
                f"Số lượng yêu cầu của xe {xe.vin} không hợp lệ."
            )
            return redirect("orders:vehicle_orders")

        xe_trong_phieu.append({
            "xe": xe,
            "quantity": so_luong
        })

    # 3. Lưu phiếu và danh sách xe vào database
    with transaction.atomic():
        release_expired_draft_requests()
        from datetime import timedelta
        hold_minutes = getattr(settings, "ORDER_DRAFT_HOLD_MINUTES", 10)
        hold_until = timezone.now() + timedelta(minutes=hold_minutes)

        from database.models import ChiTietHopDong, HopDong
        alloc_ids = [item["xe"].id for item in xe_trong_phieu]
        locked_allocs = list(Allocation.objects.select_for_update().filter(id__in=alloc_ids))

        matched_hd = None
        for alloc in locked_allocs:
            ma_hd_link = selected_contracts.get(str(alloc.id)) or ChiTietHopDong.objects.filter(xe__vin=alloc.vin).values_list("hop_dong_id", flat=True).first()
            target_hd = HopDong.objects.filter(pk=ma_hd_link).first() if ma_hd_link else None
            if target_hd and not matched_hd:
                matched_hd = target_hd
            status_info = get_allocation_status(alloc, target_hd=target_hd)
            if not status_info["is_available"]:
                messages.error(request, f"Xe VIN {alloc.vin} không còn trống: {status_info['label']}.")
                return redirect("orders:vehicle_orders")

        phieu = VehicleRequest.objects.create(
            created_by=request.user,
            status=VehicleRequest.Status.DRAFT,
            hold_until=hold_until,
            hop_dong=matched_hd,
        )

        for alloc in locked_allocs:
            VehicleRequestItem.objects.create(
                vehicle_request=phieu,
                allocation=alloc,
                quantity=1
            )
        request.session["selected_vehicles"] = {}
        request.session["selected_vehicle_contracts"] = {}

        # Ghi nhận phiếu nháp thành công, chờ người dùng gửi để Sale Admin duyệt trước khi chuyển sang kho.

    # 4. Chuyển sang trang xem phiếu
    return redirect(
        "orders:phieu_yeu_cau",
        id=phieu.id
    )

@login_required
def phieu_yeu_cau(request, id):
    role_info = get_user_role_info(request.user)
    is_admin = request.user.is_superuser or (role_info and role_info.get("code") == "ADMIN")

    if is_admin:
        phieu = get_object_or_404(
            VehicleRequest.objects.prefetch_related("items__allocation", "created_by"),
            id=id
        )
    else:
        phieu = get_object_or_404(
            VehicleRequest.objects.prefetch_related("items__allocation", "created_by"),
            id=id,
            created_by=request.user
        )

    tong_so_luong = (
        phieu.items.aggregate(total=Sum("quantity"))["total"] or 0
    )

    context = {
        "phieu": phieu,
        "tong_so_luong": tong_so_luong,
        "is_sale_admin": is_admin,
    }

    return render(request, "phieu_yc.html", context)

def link_callback(uri, rel):
    if uri.startswith(settings.STATIC_URL):
        relative_path = uri[len(settings.STATIC_URL):]
        file_path = finders.find(relative_path)

        if file_path:
            return os.path.abspath(file_path)

    return uri
@login_required
def gui_phieu_yeu_cau(request, id):
    # 1. Chỉ cho phép gửi phiếu bằng phương thức POST
    if request.method != "POST":
        return HttpResponse(status=405)

    role_info = get_user_role_info(request.user)
    is_admin = request.user.is_superuser or (role_info and role_info.get("code") == "ADMIN")

    # 2. Lấy phiếu yêu cầu đặt xe (Người tạo hoặc Sale Admin)
    if is_admin:
        phieu = get_object_or_404(
            VehicleRequest.objects.prefetch_related("items__allocation"),
            id=id
        )
    else:
        phieu = get_object_or_404(
            VehicleRequest.objects.prefetch_related("items__allocation"),
            id=id,
            created_by=request.user,
        )

    # 3. Chỉ cho phép gửi phiếu ở trạng thái DRAFT
    if phieu.status != VehicleRequest.Status.DRAFT:
        messages.warning(
            request,
            "Phiếu này không còn ở trạng thái bản nháp."
        )
        return redirect(
            "orders:phieu_yeu_cau",
            id=phieu.id
        )

    # Kiểm tra nếu phiếu nháp đã hết hạn giữ chỗ
    if phieu.hold_until and phieu.hold_until < timezone.now():
        phieu.items.all().delete()
        phieu.status = VehicleRequest.Status.REJECTED
        phieu.rejection_reason = "Phiếu nháp đã quá thời hạn giữ chỗ."
        phieu.save(update_fields=["status", "rejection_reason"])
        messages.error(request, "Phiếu nháp đã hết thời hạn giữ chỗ và đã tự động giải phóng xe.")
        return redirect("orders:danh_sach_yeu_cau")

    # Kiểm tra xe có bị chiếm bởi giao dịch khác hay không
    from database.models import ChiTietHopDong
    for item in phieu.items.select_related("allocation").all():
        target_hd = phieu.hop_dong
        if not target_hd:
            ct_hd = ChiTietHopDong.objects.filter(xe__vin=item.allocation.vin).select_related("hop_dong").first()
            target_hd = ct_hd.hop_dong if ct_hd else None
        status_info = get_allocation_status(item.allocation, target_hd=target_hd, exclude_request_id=phieu.id)
        if not status_info["is_available"]:
            messages.error(request, f"Xe VIN {item.allocation.vin} không khả dụng để gửi: {status_info['label']}.")
            return redirect("orders:phieu_yeu_cau", id=phieu.id)

    # 4. Tính tổng số lượng xe
    tong_so_luong = (
        phieu.items.aggregate(total=Sum("quantity"))["total"] or 0
    )

    # 5. Kiểm tra phiếu có xe hay chưa
    if tong_so_luong == 0:
        messages.error(
            request,
            "Phiếu chưa có xe để gửi."
        )
        return redirect(
            "orders:phieu_yeu_cau",
            id=phieu.id
        )

    # 6. Tạo file PDF đính kèm (nếu môi trường hỗ trợ pisa)
    pdf_data = None
    try:
        html = render_to_string(
            "phieu_yc_pdf.html",
            {
                "phieu": phieu,
                "tong_so_luong": tong_so_luong,
            },
        )
        pdf_buffer = BytesIO()
        result = pisa.CreatePDF(
            html,
            dest=pdf_buffer,
            link_callback=link_callback
        )
        if not result.err:
            pdf_data = pdf_buffer.getvalue()
    except Exception as e:
        print("Lưu ý: Không tạo được PDF phiếu yêu cầu:", repr(e))

    # 7. Thử gửi email nhưng không chặn workflow nếu chưa cấu hình SMTP
    try:
        email = EmailMessage(
            subject=f"Phiếu yêu cầu đặt xe {phieu.request_number}",
            body=(
                "Kính gửi Công ty TNHH FORD Việt Nam,\n\n"
                f"DanaFord gửi phiếu yêu cầu đặt xe {phieu.request_number} đính kèm.\n\n"
                "Trân trọng."
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=getattr(settings, "ORDER_RECEIVER_EMAILS", []) or ["fordvn04@gmail.com"],
        )
        if pdf_data:
            email.attach(
                f"Phieu_yeu_cau_{phieu.request_number}.pdf",
                pdf_data,
                "application/pdf",
            )
        email.send(fail_silently=True)
    except Exception as e:
        print("Lưu ý: Không thể gửi email (tiếp tục quy trình nội bộ):", repr(e))

    # 8. Cập nhật trạng thái sang PENDING (Chờ Quốc Hiếu / Sale Admin duyệt)
    phieu.status = VehicleRequest.Status.PENDING
    phieu.sent_at = timezone.now()
    phieu.hold_until = None
    phieu.save(
        update_fields=["status", "sent_at", "hold_until"]
    )

    # 9. Làm trống danh sách xe đang chọn trong Session
    request.session.pop("selected_vehicles", None)

    # 10. Tạo thông báo toàn hệ thống & gửi tới Quốc Hiếu (Sale Admin)
    try:
        from dashboard.models import ThongBaoHoatDong
        ten_sender = request.user.get_full_name() or request.user.username
        chuc_vu_sender = "Sale Chi Nhánh"
        ThongBaoHoatDong.objects.create(
            user=request.user,
            ten_nhan_vien=ten_sender,
            chuc_vu=chuc_vu_sender,
            hanh_dong=f"Đã gửi Phiếu yêu cầu đặt xe {phieu.request_number} — Chờ Quốc Hiếu duyệt",
            chi_tiet=f"{ten_sender} đã tạo và gửi phiếu đặt {tong_so_luong} xe lên hệ thống. Đang chờ Sale Admin (Quốc Hiếu Phan) kiểm tra, xác nhận và phê duyệt sang quy trình kho.",
            module="orders",
            loai="tu_dong",
            is_active=True,
        )
    except Exception as e:
        print("Lỗi tạo thông báo hoạt động:", repr(e))

    # 11. Thông báo gửi thành công trên giao diện
    messages.success(
        request,
        f"Đã gửi phiếu yêu cầu {phieu.request_number} thành công! Hệ thống đã phát thông báo và gửi đến Sale Admin (Quốc Hiếu) để kiểm tra, xác nhận tiếp nhận."
    )

    # 12. Xem chi tiết phiếu
    return redirect("orders:phieu_yeu_cau", id=phieu.id)

@login_required
def danh_sach_yeu_cau(request):
    role_info = get_user_role_info(request.user)
    is_admin = request.user.is_superuser or (role_info and role_info.get("code") == "ADMIN")

    if is_admin:
        phieu_yeu_cau = (
            VehicleRequest.objects
            .select_related("created_by")
            .order_by("-created_at")
        )
    else:
        phieu_yeu_cau = (
            VehicleRequest.objects
            .filter(created_by=request.user)
            .select_related("created_by")
            .order_by("-created_at")
        )

    thang = (request.GET.get("thang") or request.GET.get("month") or "").strip()
    trang_thai = (request.GET.get("trang_thai") or "").strip()
    if thang and thang != "ALL" and "-" in thang:
        try:
            y_val, m_val = map(int, thang.split("-", 1))
            phieu_yeu_cau = phieu_yeu_cau.filter(created_at__year=y_val, created_at__month=m_val)
        except ValueError:
            pass
    if trang_thai:
        phieu_yeu_cau = phieu_yeu_cau.filter(status=trang_thai)

    thang_options = [
        ("2026-11", "Tháng 11/2026"),
        ("2026-10", "Tháng 10/2026"),
        ("2026-09", "Tháng 09/2026"),
        ("2026-08", "Tháng 08/2026"),
    ]

    return render(
        request,
        "danh_sach_yc.html",
        {
            "phieu_yeu_cau": phieu_yeu_cau,
            "is_sale_admin": is_admin,
            "thang": thang,
            "trang_thai": trang_thai,
            "thang_options": thang_options,
        }
    )


@login_required
@require_POST
def xac_nhan_phieu(request, id):
    role_info = get_user_role_info(request.user)
    is_admin = (
        request.user.is_superuser
        or (role_info and role_info.get("code") == "ADMIN")
        or request.user.groups.filter(name__in=["Sale Admin", "Quản lý"]).exists()
    )

    # Chỉ người thuộc nhóm Sale Admin (Quốc Hiếu) được xác nhận
    if not is_admin:
        messages.error(
            request,
            "Chỉ Quản trị viên (Sale Admin - Quốc Hiếu) mới có quyền xác nhận phê duyệt phiếu yêu cầu đặt xe."
        )
        return redirect("orders:phieu_yeu_cau", id=id)

    phieu = get_object_or_404(
        VehicleRequest.objects.prefetch_related("items__allocation"),
        id=id
    )

    # Chỉ cho phép xác nhận phiếu đã gửi
    if phieu.status != VehicleRequest.Status.PENDING:
        messages.error(
            request,
            "Chỉ có thể xác nhận phiếu đang ở trạng thái chờ duyệt."
        )
        return redirect(
            "orders:phieu_yeu_cau",
            id=phieu.id
        )

    phieu.status = VehicleRequest.Status.ACCEPTED
    phieu.save(update_fields=["status"])

    # Đồng bộ sang Kho và tạo chứng từ nhập kho cho từng VIN
    try:
        from warehouse.order_intake import sync_request
        sync_request(phieu.pk)
    except Exception as e:
        print("Lỗi sync_request sang kho:", repr(e))

    # Phát thông báo toàn hệ thống đã phê duyệt
    try:
        from dashboard.models import ThongBaoHoatDong
        ten_admin = request.user.get_full_name() or request.user.username
        creator_name = phieu.created_by.get_full_name() or phieu.created_by.username if phieu.created_by else "Chi nhánh"
        ThongBaoHoatDong.objects.create(
            user=request.user,
            ten_nhan_vien=ten_admin,
            chuc_vu="Quản trị viên (Sale Admin)",
            hanh_dong=f"Đã xác nhận & phê duyệt Phiếu yêu cầu {phieu.request_number}",
            chi_tiet=f"Sale Admin {ten_admin} đã phê duyệt phiếu đặt xe của {creator_name}. Toàn bộ xe đã được chuyển sang Quản lý nhập kho và kiểm định PDI.",
            module="orders",
            loai="tu_dong",
            is_active=True,
        )
    except Exception as e:
        print("Lỗi tạo thông báo hoạt động khi duyệt:", repr(e))

    messages.success(
        request,
        f"Đã xác nhận & phê duyệt thành công phiếu yêu cầu {phieu.request_number}! Toàn bộ xe đã được chuyển sang Quản lý nhập kho."
    )

    return redirect(
        "orders:phieu_yeu_cau",
        id=phieu.id
    )



from collections import defaultdict
from database.models import ChiTietBan, TonKho


from analytics.models import PhienDuBao, DongDuBao, HOAN_TAT

@login_required
def danh_sach_de_xuat(request):
    allocations, selected_month, month_options, current_cn = xu_ly_loc_phan_bo(request)

    cn_name = "Tất cả các chi nhánh"
    if current_cn and current_cn != "ALL":
        cn_obj = ChiNhanh.objects.filter(ma_cn=current_cn).first()
        if cn_obj:
            cn_name = cn_obj.ten_cn

    today = timezone.localdate()

    # 1. Tìm phiên dự báo hoàn tất tương ứng với kỳ được chọn
    phien_qs = PhienDuBao.objects.filter(trang_thai=HOAN_TAT)
    if selected_month and selected_month != "ALL" and "-" in selected_month:
        try:
            y, m = map(int, selected_month.split("-"))
            phien_qs = phien_qs.filter(nam=y, thang=m)
        except ValueError:
            pass
    else:
        phien_qs = phien_qs.filter(nam=today.year, thang=today.month)

    phien = phien_qs.order_by("-tao_luc", "-id").first()
    danh_sach = []

    # Ưu tiên lấy theo kết quả phân tích POQ của Module Dự báo nhu cầu nếu có
    if phien and phien.san_sang and phien.dong.exists():
        for dong in phien.dong.all().order_by("ten_xe"):
            xe_phu_hop = allocations.filter(
                Q(description__icontains=dong.ten_xe) |
                Q(vehicle_code__iexact=getattr(dong, "ma_dong_xe", ""))
            )
            so_phan_bo_thuc_te = xe_phu_hop.aggregate(total=Sum("quantity"))["total"] or 0
            first_xe = xe_phu_hop.first()

            live_hd_cho_giao = tinh_hop_dong_cho_giao_thuc_te(dong.ten_xe, current_cn)
            danh_sach.append({
                "dong_id": dong.id,
                "allocation_id": first_xe.id if first_xe else None,
                "ten_xe": dong.ten_xe,
                "ma_dong_xe": getattr(dong, "ma_dong_xe", ""),
                "hop_dong_cho_giao": live_hd_cho_giao,
                "so_ton": dong.ton_kho,
                "chi_tieu": dong.chi_tieu,
                "so_phan_bo": so_phan_bo_thuc_te,
                "de_xuat_poq": dong.de_xuat_poq,
                "de_xuat_nhap": dong.so_luong_nhap,
            })
    else:
        # Dự phòng: Tự động tính toán theo Doanh số bán, Tồn kho và Phân bổ thực tế
        doanh_so_qs = ChiTietBan.objects.all()
        if selected_month and selected_month != "ALL" and "-" in selected_month:
            try:
                y, m = map(int, selected_month.split("-"))
                doanh_so_qs = doanh_so_qs.filter(hoa_don_ban__ngay_ban__year=y, hoa_don_ban__ngay_ban__month=m)
            except ValueError:
                pass
        if current_cn and current_cn != "ALL":
            doanh_so_qs = doanh_so_qs.filter(hoa_don_ban__chi_nhanh__ma_cn=current_cn)

        doanh_so = (
            doanh_so_qs
            .values("xe__ten_xe")
            .annotate(tong_ban=Sum("so_luong_ban"))
        )
        doanh_so_map = {item["xe__ten_xe"]: item["tong_ban"] for item in doanh_so}

        ton_kho_qs = TonKho.objects.all()
        if current_cn and current_cn != "ALL":
            ton_kho_qs = ton_kho_qs.filter(kho__chi_nhanh__ma_cn=current_cn)

        ton_kho = (
            ton_kho_qs
            .values("xe__ten_xe")
            .annotate(tong_ton=Sum("so_luong_ton"))
        )
        ton_kho_map = {item["xe__ten_xe"]: item["tong_ton"] for item in ton_kho}

        phan_bo_map = defaultdict(lambda: {"so_phan_bo": 0, "allocation_id": None})
        for xe in allocations:
            ten_xe = xe.description
            phan_bo_map[ten_xe]["so_phan_bo"] += xe.quantity
            phan_bo_map[ten_xe]["allocation_id"] = xe.id

        for ten_xe, thong_tin in phan_bo_map.items():
            so_ban = doanh_so_map.get(ten_xe, 0)
            so_ton = ton_kho_map.get(ten_xe, 0)
            so_phan_bo = thong_tin["so_phan_bo"]
            live_hd = tinh_hop_dong_cho_giao_thuc_te(ten_xe, current_cn)
            nhu_cau = max(0, so_ban + live_hd - so_ton)
            de_xuat_nhap = min(nhu_cau, so_phan_bo)

            danh_sach.append({
                "dong_id": None,
                "allocation_id": thong_tin["allocation_id"],
                "ten_xe": ten_xe,
                "hop_dong_cho_giao": live_hd,
                "so_ban": so_ban,
                "so_ton": so_ton,
                "so_phan_bo": so_phan_bo,
                "de_xuat_nhap": de_xuat_nhap
            })

    return render(
        request,
        "ds_de_xuat.html",
        {
            "danh_sach": danh_sach,
            "phien": phien,
            "selected_month": selected_month,
            "month_options": month_options,
            "current_cn": current_cn,
            "current_cn_name": cn_name,
        }
    )



@login_required
def chi_tiet_de_xuat(request, id):
    today = timezone.localdate()
    current_cn = request.session.get("current_cn", "ALL")

    # 1. Thử tìm kiếm theo DongDuBao (từ module dự báo POQ)
    dong = DongDuBao.objects.select_related("phien").filter(id=id).first()
    if dong:
        phien = dong.phien
        if not phien.san_sang:
            messages.warning(request, "Phiên dự báo này đã hết hạn hoặc đã bị hủy.")
            return redirect("orders:proposal_list")

        allocations = Allocation.objects.filter(
            allocation_month__year=phien.nam,
            allocation_month__month=phien.thang
        )
        if current_cn and current_cn != "ALL":
            allocations = allocations.filter(chi_nhanh__ma_cn=current_cn)

        xe_phu_hop = allocations.filter(
            Q(description__icontains=dong.ten_xe) |
            Q(vehicle_code__iexact=getattr(dong, "ma_dong_xe", ""))
        )
        so_phan_bo_thuc_te = xe_phu_hop.aggregate(total=Sum("quantity"))["total"] or 0

        live_hd = tinh_hop_dong_cho_giao_thuc_te(dong.ten_xe, current_cn)
        context = {
            "dong": dong,
            "phien": phien,
            "ten_xe": dong.ten_xe,
            "hop_dong_cho_giao": live_hd,
            "so_ton": dong.ton_kho,
            "chi_tieu": dong.chi_tieu,
            "so_phan_bo": so_phan_bo_thuc_te,
            "nhu_cau": dong.de_xuat_poq,
            "de_xuat_nhap": dong.so_luong_nhap,
            "xe_phu_hop": xe_phu_hop,
        }
        return render(request, "chi_tiet_de_xuat.html", context)

    # 2. Hoặc tìm theo Allocation ID (trực tiếp từ danh sách phân bổ)
    allocation = get_object_or_404(Allocation, id=id)
    ten_xe = allocation.description

    doanh_so_qs = ChiTietBan.objects.filter(xe__ten_xe=ten_xe)
    if allocation.allocation_month:
        doanh_so_qs = doanh_so_qs.filter(
            hoa_don_ban__ngay_ban__year=allocation.allocation_month.year,
            hoa_don_ban__ngay_ban__month=allocation.allocation_month.month
        )
    if current_cn and current_cn != "ALL":
        doanh_so_qs = doanh_so_qs.filter(hoa_don_ban__chi_nhanh__ma_cn=current_cn)
    so_ban = doanh_so_qs.aggregate(total=Sum("so_luong_ban"))["total"] or 0

    ton_kho_qs = TonKho.objects.filter(xe__ten_xe=ten_xe)
    if current_cn and current_cn != "ALL":
        ton_kho_qs = ton_kho_qs.filter(kho__chi_nhanh__ma_cn=current_cn)
    so_ton = ton_kho_qs.aggregate(total=Sum("so_luong_ton"))["total"] or 0

    alloc_qs = Allocation.objects.filter(description=ten_xe, allocation_month=allocation.allocation_month)
    if current_cn and current_cn != "ALL":
        alloc_qs = alloc_qs.filter(chi_nhanh__ma_cn=current_cn)
    so_phan_bo = alloc_qs.aggregate(total=Sum("quantity"))["total"] or 0

    nhu_cau = max(0, so_ban - so_ton)
    de_xuat_nhap = min(nhu_cau, so_phan_bo)

    context = {
        "allocation": allocation,
        "ten_xe": ten_xe,
        "so_ban": so_ban,
        "so_ton": so_ton,
        "so_phan_bo": so_phan_bo,
        "nhu_cau": nhu_cau,
        "de_xuat_nhap": de_xuat_nhap,
    }
    return render(request, "chi_tiet_de_xuat.html", context)


@login_required
@require_POST
def tu_choi_phieu(request, id):
    role_info = get_user_role_info(request.user)
    is_admin = (
        request.user.is_superuser
        or (role_info and role_info.get("code") == "ADMIN")
        or request.user.groups.filter(name__in=["Sale Admin", "Quản lý"]).exists()
    )

    if not is_admin:
        messages.error(request, "Chỉ Quản trị viên (Sale Admin) mới có quyền từ chối phiếu yêu cầu đặt xe.")
        return redirect("orders:phieu_yeu_cau", id=id)

    phieu = get_object_or_404(VehicleRequest, id=id)
    if phieu.status != VehicleRequest.Status.PENDING:
        messages.error(request, "Chỉ có thể từ chối phiếu đang ở trạng thái chờ duyệt.")
        return redirect("orders:phieu_yeu_cau", id=id)

    ly_do = request.POST.get("ly_do", "").strip() or "Sale Admin từ chối"
    phieu.status = VehicleRequest.Status.REJECTED
    phieu.rejection_reason = ly_do
    phieu.hold_until = None
    phieu.save(update_fields=["status", "rejection_reason", "hold_until"])

    messages.success(request, f"Đã từ chối phiếu {phieu.request_number}. Toàn bộ xe trong phiếu đã được nhả.")
    return redirect("orders:phieu_yeu_cau", id=id)


@login_required
@require_POST
def xoa_xe_phieu_nhap(request, id, item_id):
    phieu = get_object_or_404(VehicleRequest, id=id)
    if phieu.status != VehicleRequest.Status.DRAFT:
        messages.error(request, "Chỉ có thể xóa xe khỏi phiếu ở trạng thái Bản nháp.")
        return redirect("orders:phieu_yeu_cau", id=phieu.id)

    if not (request.user.is_superuser or phieu.created_by == request.user):
        messages.error(request, "Bạn không có quyền chỉnh sửa phiếu này.")
        return redirect("orders:phieu_yeu_cau", id=phieu.id)

    item = get_object_or_404(VehicleRequestItem, id=item_id, vehicle_request=phieu)
    vin = item.allocation.vin
    item.delete()

    messages.success(request, f"Đã xóa xe VIN {vin} khỏi phiếu nháp. Xe đã được nhả.")
    return redirect("orders:phieu_yeu_cau", id=phieu.id)


def tinh_hop_dong_cho_giao_thuc_te(ten_xe, chi_nhanh_id=None):
    """
    Tính số lượng hợp đồng đã ký đang chờ giao xe (chưa xuất kho hoàn tất)
    cho dòng xe `ten_xe` theo thời gian thực (real-time).
    """
    from database.models import HopDong, TrangThaiHopDong, TrangThaiPhieuXuat, ChiTietHopDong
    if not ten_xe:
        return 0

    ten_lower = ten_xe.strip().lower()
    main_keywords = [w for w in ["ranger", "everest", "territory", "explorer", "transit"] if w in ten_lower]

    active_states = [
        TrangThaiHopDong.CHO_XU_LY,
        TrangThaiHopDong.CHO_PHAN_BO,
        TrangThaiHopDong.CHO_XE_VE_KHO,
        TrangThaiHopDong.DU_DIEU_KIEN_XUAT,
        TrangThaiHopDong.DANG_XUAT_KHO,
    ]

    ct_qs = ChiTietHopDong.objects.filter(
        hop_dong__trang_thai__in=active_states
    ).exclude(
        phieuxuatkho__trang_thai=TrangThaiPhieuXuat.DA_DUYET
    ).select_related("hop_dong", "xe")

    if chi_nhanh_id and chi_nhanh_id != "ALL":
        ct_qs = ct_qs.filter(hop_dong__chi_nhanh__ma_cn=chi_nhanh_id)

    count = 0
    seen_hd_ids = set()
    for ct in ct_qs:
        xe = ct.xe
        hd = ct.hop_dong
        xe_name = f"{xe.ten_xe or ''} {getattr(xe, 'phien_ban', '') or ''} {xe.loai_xe or ''}".lower()
        hd_req = f"{hd.dong_xe_yeu_cau or ''} {hd.phien_ban_yeu_cau or ''}".lower()

        matched = (ten_lower in xe_name) or (ten_lower in hd_req)
        if not matched and main_keywords:
            matched = any(kw in xe_name or kw in hd_req for kw in main_keywords) and (
                any(token in xe_name or token in hd_req for token in ten_lower.split() if len(token) > 2)
            )

        if matched:
            count += 1
            seen_hd_ids.add(hd.pk)

    unassigned_hd_qs = HopDong.objects.filter(
        chitiethopdong__isnull=True,
        trang_thai__in=[TrangThaiHopDong.CHO_XU_LY, TrangThaiHopDong.CHO_PHAN_BO]
    )
    if chi_nhanh_id and chi_nhanh_id != "ALL":
        unassigned_hd_qs = unassigned_hd_qs.filter(chi_nhanh__ma_cn=chi_nhanh_id)

    for hd in unassigned_hd_qs:
        hd_req = f"{hd.dong_xe_yeu_cau or ''} {hd.phien_ban_yeu_cau or ''}".lower()
        matched = ten_lower in hd_req
        if not matched and main_keywords:
            matched = any(kw in hd_req for kw in main_keywords)
        if matched and hd.pk not in seen_hd_ids:
            count += 1
            seen_hd_ids.add(hd.pk)

    return count
