
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
                            elif c_name in ("ORDER_NO", "ORDER NO", "ORDER NUMBER", "ORDER_NUMBER", "SỐ ĐƠN ĐẶT HÀNG", "SỐ ĐƠN HÀNG", "SO DON HANG", "ORDER") and "order_number" not in col_map:
                                col_map["order_number"] = c_idx
                            elif c_name in ("MODEL CODE", "MODEL_CODE", "MÃ DÒNG XE", "MÃ XE", "MA DONG XE", "VEHICLE CODE", "VEHICLE_CODE") and "vehicle_code" not in col_map:
                                col_map["vehicle_code"] = c_idx
                            elif c_name in ("DESCRIPTION", "MODEL DESC", "MODEL_DESC", "MÔ TẢ", "MO TA", "TÊN XE", "TEN XE") and "description" not in col_map:
                                col_map["description"] = c_idx
                            elif c_name in ("COLOR CODE", "COLOR_CODE", "COLOUR CODE", "COLOUR_CODE", "MÃ MÀU", "MA MAU") and "color_code" not in col_map:
                                col_map["color_code"] = c_idx
                            elif c_name in ("EXTERIOR COLOUR", "EXTERIOR COLOR", "MÀU NGOẠI THẤT", "MAU NGOAI THAT", "MÀU SẮC", "MAU SAC", "COLOUR (FN)") and "exterior_color" not in col_map:
                                col_map["exterior_color"] = c_idx
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

                        data.append({
                            "vin": vin,
                            "order_number": chuyen_chuoi(get_col("order_number")),
                            "vehicle_code": chuyen_chuoi(get_col("vehicle_code")),
                            "description": chuyen_chuoi(get_col("description")),
                            "color_code": chuyen_chuoi(get_col("color_code")),
                            "exterior_color": chuyen_chuoi(get_col("exterior_color")),
                            "engine_number": chuyen_chuoi(get_col("engine_number")),
                            "quantity": chuyen_so_luong(get_col("quantity"), default=1),
                            "expected_ship_date": chuyen_ngay(get_col("expected_ship_date")),
                            "contractual_delivery_date": chuyen_ngay(get_col("contractual_delivery_date")),
                            "allocation_month": alloc_month,
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
                        from django.db.models import Sum
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

    # Hiển thị danh sách phân bổ: Ưu tiên tháng hiện tại, nếu chưa có thì lấy tháng phân bổ gần nhất
    allocations = Allocation.objects.filter(
        allocation_month__year=today.year,
        allocation_month__month=today.month
    ).order_by("id")

    if not allocations.exists():
        latest_allocation = Allocation.objects.order_by("-allocation_month").first()
        if latest_allocation and latest_allocation.allocation_month:
            allocations = Allocation.objects.filter(
                allocation_month__year=latest_allocation.allocation_month.year,
                allocation_month__month=latest_allocation.allocation_month.month
            ).order_by("id")

    return render(request, "danh_sach_pb.html", {
        "form": form,
        "allocations": allocations
    })

# Đặt xe

@login_required
def dat_xe(request):
        keyword = request.GET.get("keyword", "").strip()

        # Lấy ngày hiện tại theo múi giờ Django
        today = timezone.localdate()

        # Ưu tiên lấy xe thuộc tháng hiện tại, nếu chưa có thì lấy tháng phân bổ gần nhất
        allocations = Allocation.objects.filter(
            allocation_month__year=today.year,
            allocation_month__month=today.month
        ).order_by("id")

        if not allocations.exists():
            latest_alloc = Allocation.objects.order_by("-allocation_month").first()
            if latest_alloc and latest_alloc.allocation_month:
                allocations = Allocation.objects.filter(
                    allocation_month__year=latest_alloc.allocation_month.year,
                    allocation_month__month=latest_alloc.allocation_month.month
                ).order_by("id")

        # Tìm kiếm theo VIN, mô tả, mã xe, màu sắc
        if keyword:
            allocations = Allocation.objects.filter(
                Q(vin__icontains=keyword) |
                Q(description__icontains=keyword) |
                Q(vehicle_code__icontains=keyword) |
                Q(exterior_color__icontains=keyword)
            ).order_by("-allocation_month", "id")

        context = {
            "keyword": keyword,
            "allocations": allocations
        }
        # Lấy danh sách xe đã chọn trong Session
        danh_sach = request.session.get("selected_vehicles", {})

        xe_da_chon = []

        for ma_xe, so_luong in danh_sach.items():
            xe = Allocation.objects.filter(id=ma_xe).first()

            if xe:
                xe_da_chon.append({
                    "xe": xe,
                    "quantity": so_luong
                })
                context = {
                    "keyword": keyword,
                    "allocations": allocations,
                    "xe_da_chon": xe_da_chon
                }
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
        try:
            so_luong = int(request.POST.get("quantity", ""))
        except (ValueError, TypeError):
            messages.error(request, "Số lượng phải là số nguyên.")
        else:
            if so_luong <= 0:
                messages.error(request, "Số lượng phải lớn hơn 0.")

            else:
                # Lấy danh sách xe đã chọn từ Session
                danh_sach = request.session.get("selected_vehicles", {})

                ma_xe = str(xe.id)

                # Số lượng đã chọn trước đó
                so_luong_cu = danh_sach.get(ma_xe, 0)

                tong_so_luong = so_luong_cu + so_luong

                if tong_so_luong > xe.quantity:
                    messages.error(
                        request,
                        f"Số lượng yêu cầu không được vượt quá "
                        f"{xe.quantity} xe phân bổ."
                    )
                else:
                    danh_sach[ma_xe] = tong_so_luong

                    request.session["selected_vehicles"] = danh_sach

                    messages.success(
                        request,
                        "Đã thêm xe vào danh sách."
                    )

                    return redirect("orders:vehicle_orders")

    return render(request, "chi_tiet_xe.html", {
        "xe": xe
    })

from django.views.decorators.http import require_POST

@login_required
@require_POST
def xoa_xe_da_chon(request, xe_id):
    # Lấy danh sách xe đã chọn từ Session
    danh_sach = request.session.get("selected_vehicles", {})

    # ID trong Session được lưu dưới dạng chuỗi
    ma_xe = str(xe_id)

    if ma_xe in danh_sach:
        del danh_sach[ma_xe]

        # Cập nhật lại Session
        request.session["selected_vehicles"] = danh_sach

        messages.success(request, "Đã xóa xe khỏi danh sách.")
    else:
        messages.error(request, "Xe không tồn tại trong danh sách đã chọn.")

    return redirect("orders:vehicle_orders")


@login_required
def lap_phieu_yeu_cau(request):

    # 1. Lấy danh sách xe đã chọn từ Session
    danh_sach = request.session.get("selected_vehicles", {})

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

        phieu = VehicleRequest.objects.create(
            created_by=request.user,
            status=VehicleRequest.Status.DRAFT
        )

        for item in xe_trong_phieu:
            VehicleRequestItem.objects.create(
                vehicle_request=phieu,
                allocation=item["xe"],
                quantity=item["quantity"]
            )

    # 4. Chuyển sang trang xem phiếu
    return redirect(
        "orders:phieu_yeu_cau",
        id=phieu.id
    )

@login_required
def phieu_yeu_cau(request, id):

    phieu = get_object_or_404(
        VehicleRequest.objects.prefetch_related("items__allocation"),
        id=id,
        created_by=request.user
    )

    tong_so_luong = (
        phieu.items.aggregate(total=Sum("quantity"))["total"] or 0
    )

    context = {
        "phieu": phieu,
        "tong_so_luong": tong_so_luong
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
    print("===== ĐÃ VÀO HÀM GỬI PHIẾU =====", flush=True)
    # 1. Chỉ cho phép gửi phiếu bằng phương thức POST
    if request.method != "POST":
        return HttpResponse(status=405)

    # 2. Lấy phiếu yêu cầu đặt xe
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

    # 6. Tạo nội dung HTML cho PDF
    html = render_to_string(
        "phieu_yc_pdf.html",
        {
            "phieu": phieu,
            "tong_so_luong": tong_so_luong,
        },
    )

    # 7. Chuyển HTML thành PDF
    pdf_buffer = BytesIO()

    result = pisa.CreatePDF(
        html,
        dest=pdf_buffer,
        link_callback=link_callback
    )

    if result.err:
        messages.error(
            request,
            "Không thể tạo file PDF."
        )
        return redirect(
            "orders:phieu_yeu_cau",
            id=phieu.id
        )
    # 8. Tạo email gửi đến Ford Việt Nam
    email = EmailMessage(
        subject=f"Phiếu yêu cầu đặt xe {phieu.request_number}",

        body=(
            "Kính gửi Công ty TNHH FORD Việt Nam,\n\n"
            "DanaFord gửi phiếu yêu cầu đặt xe đính kèm.\n\n"
            "Trân trọng."
        ),

        from_email=settings.DEFAULT_FROM_EMAIL,

        to=["fordvn04@gmail.com"],
    )


    # 9. Đính kèm file PDF
    email.attach(
        f"Phieu_yeu_cau_{phieu.request_number}.pdf",
        pdf_buffer.getvalue(),
        "application/pdf",
    )

    # 10. Thực hiện gửi email
    try:
        print("===== BẮT ĐẦU GỬI EMAIL =====", flush=True)
        print("Email gửi:", settings.DEFAULT_FROM_EMAIL)

        print(
            "SMTP username:",
            settings.MAILERS["default"]["OPTIONS"]["username"]
        )

        print(
            "Có mật khẩu:",
            bool(settings.MAILERS["default"]["OPTIONS"]["password"])
        )
        so_email = email.send(fail_silently=False)

        print("Số email gửi thành công:", so_email)

        if so_email != 1:
            raise RuntimeError(
                "Máy chủ email chưa xác nhận gửi."
            )

    except Exception as e:
        print("LỖI GỬI EMAIL:", repr(e))

        messages.error(
            request,
            "Gửi email thất bại."
        )

        return redirect(
            "orders:phieu_yeu_cau",
            id=phieu.id
        )


    # 11. Cập nhật trạng thái sau khi gửi thành công
    phieu.status = VehicleRequest.Status.PENDING
    phieu.sent_at = timezone.now()

    phieu.save(
        update_fields=["status", "sent_at"]
    )

    # 12. Làm trống danh sách xe đang chọn trong Session
    request.session.pop("selected_vehicles", None)

    # 13. Thông báo gửi thành công
    messages.success(
        request,
        "Đã gửi phiếu yêu cầu đặt xe thành công! "
        "Bạn có thể chọn xe để lập phiếu mới."
    )

    # 14. Quay về giao diện tìm kiếm xe
    return redirect("orders:vehicle_orders")

@login_required
def danh_sach_yeu_cau(request):
    phieu_yeu_cau = (
        VehicleRequest.objects
        .filter(created_by=request.user)
        .order_by("-created_at")
    )

    return render(
        request,
        "danh_sach_yc.html",
        {
            "phieu_yeu_cau": phieu_yeu_cau
        }
    )


@login_required
@require_POST
def xac_nhan_phieu(request, id):

    # Chỉ người thuộc nhóm Sale Admin được xác nhận
    if not request.user.groups.filter(
        name="Sale Admin"
    ).exists() and not request.user.is_superuser:
        return HttpResponse(status=403)

    phieu = get_object_or_404(
        VehicleRequest,
        id=id,
        created_by=request.user
    )

    # Chỉ cho phép xác nhận phiếu đã gửi
    if phieu.status != VehicleRequest.Status.PENDING:
        messages.error(
            request,
            "Chỉ có thể xác nhận phiếu đã gửi."
        )
        return redirect(
            "orders:phieu_yeu_cau",
            id=phieu.id
        )

    phieu.status = VehicleRequest.Status.ACCEPTED
    phieu.save(update_fields=["status"])

    messages.success(
        request,
        "Phiếu yêu cầu đã được xác nhận tiếp nhận."
    )

    return redirect(
        "orders:phieu_yeu_cau",
        id=phieu.id
    )



from collections import defaultdict
from database.models import ChiTietBan, TonKho


@login_required
def danh_sach_de_xuat(request):
    today = timezone.localdate()

    # 1. Lấy danh sách phân bổ (ưu tiên tháng hiện tại, nếu chưa có thì lấy tháng gần nhất)
    allocations = Allocation.objects.filter(
        allocation_month__year=today.year,
        allocation_month__month=today.month
    )
    if not allocations.exists():
        latest_pb = Allocation.objects.order_by("-allocation_month").first()
        if latest_pb and latest_pb.allocation_month:
            allocations = Allocation.objects.filter(
                allocation_month__year=latest_pb.allocation_month.year,
                allocation_month__month=latest_pb.allocation_month.month
            )

    # 2. Tính tổng số xe bán theo dòng xe
    doanh_so = (
        ChiTietBan.objects
        .filter(
            hoa_don_ban__ngay_ban__year=today.year,
            hoa_don_ban__ngay_ban__month=today.month
        )
        .values("xe__ten_xe")
        .annotate(tong_ban=Sum("so_luong_ban"))
    )

    doanh_so_map = {
        item["xe__ten_xe"]: item["tong_ban"]
        for item in doanh_so
    }

    # 3. Tính tổng số xe tồn kho theo dòng xe
    ton_kho = (
        TonKho.objects
        .values("xe__ten_xe")
        .annotate(tong_ton=Sum("so_luong_ton"))
    )

    ton_kho_map = {
        item["xe__ten_xe"]: item["tong_ton"]
        for item in ton_kho
    }

    # 4. Gom phân bổ theo dòng xe, bỏ mã màu
    phan_bo_map = defaultdict(lambda: {
        "so_phan_bo": 0,
        "allocation_id": None
    })

    for xe in allocations:
        ten_xe = xe.description

        phan_bo_map[ten_xe]["so_phan_bo"] += xe.quantity
        phan_bo_map[ten_xe]["allocation_id"] = xe.id

    # 5. Tính số lượng đề xuất nhập
    danh_sach = []

    for ten_xe, thong_tin in phan_bo_map.items():
        so_ban = doanh_so_map.get(ten_xe, 0)
        so_ton = ton_kho_map.get(ten_xe, 0)
        so_phan_bo = thong_tin["so_phan_bo"]

        nhu_cau = max(0, so_ban - so_ton)
        de_xuat_nhap = min(nhu_cau, so_phan_bo)

        danh_sach.append({
            "allocation_id": thong_tin["allocation_id"],
            "ten_xe": ten_xe,
            "so_ban": so_ban,
            "so_ton": so_ton,
            "so_phan_bo": so_phan_bo,
            "de_xuat_nhap": de_xuat_nhap
        })

    return render(
        request,
        "ds_de_xuat.html",
        {"danh_sach": danh_sach}
    )



@login_required
def chi_tiet_de_xuat(request, id):

    # 1. Lấy ngày hiện tại
    today = timezone.localdate()

    # 2. Lấy xe từ danh sách phân bổ
    allocation = get_object_or_404(
        Allocation,
        id=id
    )

    # 3. Xác định dòng xe
    ten_xe = allocation.description

    # 4. Tính tổng số xe đã bán trong tháng
    so_ban = (
        ChiTietBan.objects
        .filter(
            xe__ten_xe=ten_xe,
            hoa_don_ban__ngay_ban__year=today.year,
            hoa_don_ban__ngay_ban__month=today.month
        )
        .aggregate(
            total=Sum("so_luong_ban")
        )["total"] or 0
    )

    # 5. Tính tổng số lượng tồn kho
    so_ton = (
        TonKho.objects
        .filter(
            xe__ten_xe=ten_xe
        )
        .aggregate(
            total=Sum("so_luong_ton")
        )["total"] or 0
    )

    # 6. Tính tổng số lượng phân bổ theo dòng xe
    # Không phân biệt mã màu
    so_phan_bo = (
        Allocation.objects
        .filter(
            description=ten_xe,
            allocation_month=allocation.allocation_month
        )
        .aggregate(
            total=Sum("quantity")
        )["total"] or 0
    )

    # 7. Tính nhu cầu nhập xe
    nhu_cau = max(0, so_ban - so_ton)

    # 8. Số lượng đề xuất không vượt quá phân bổ
    de_xuat_nhap = min(nhu_cau, so_phan_bo)

    # 9. Truyền dữ liệu sang HTML
    context = {
        "allocation": allocation,
        "ten_xe": ten_xe,
        "so_ban": so_ban,
        "so_ton": so_ton,
        "so_phan_bo": so_phan_bo,
        "nhu_cau": nhu_cau,
        "de_xuat_nhap": de_xuat_nhap,
    }

    # 10. Hiển thị trang chi tiết
    return render(
        request,
        "chi_tiet_de_xuat.html",
        context
    )
