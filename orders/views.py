
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

def chuyen_ngay(value):
    if value is None or value == "":
        return None

    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, date):
        return value

    if isinstance(value, str):
        value = value.strip()

        for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(value, fmt).date()
            except ValueError:
                continue

    raise ValueError(f"Ngày không hợp lệ: {value}")
import re

def chuyen_thang(value):
    if isinstance(value, datetime):
        value = value.date()

    if isinstance(value, date):
        return value.replace(day=1)

    if isinstance(value, str):
        match = re.fullmatch(
            r"Tháng\s+(\d{1,2})\s+năm\s+(\d{4})",
            value.strip(),
            flags=re.IGNORECASE
        )

        if match:
            thang = int(match.group(1))
            nam = int(match.group(2))
            return date(nam, thang, 1)

    raise ValueError(f"Tháng phân bổ không hợp lệ: {value}")
def chuyen_chuoi(value):
    if value is None:
        return ""

    if isinstance(value, str):
        return value.strip()

    if isinstance(value, (int, float)):
        return str(value)

    raise ValueError(
        f"Kiểu dữ liệu Excel không hợp lệ: {type(value).__name__}"
    )
def chuyen_so_luong(value):
    if value is None or isinstance(value, bool):
        raise ValueError("Số lượng không hợp lệ")

    try:
        so_luong = int(str(value).strip())
    except (ValueError, TypeError, OverflowError):
        raise ValueError("Số lượng phải là số nguyên")

    if so_luong <= 0:
        raise ValueError("Số lượng phải lớn hơn 0")

    return so_luong
@login_required
def allocation_list(request):
    if request.method == "POST":
        form = AllocationUploadForm(request.POST, request.FILES)

        if form.is_valid():
            file = form.cleaned_data["file"]

            if not file.name.lower().endswith(".xlsx"):
                messages.error(request, "Chỉ chấp nhận file .xlsx")
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
                        raise ValueError(
                            "File Excel không có sheet hợp lệ"
                        )

                    rows = list(sheet.iter_rows(
                        min_row=2,
                        values_only=True
                    ))

                    # Kiểm tra toàn bộ dữ liệu trước khi lưu
                    data = []

                    today = timezone.localdate()

                    for row_number, row in enumerate(rows, start=2):
                        if not any(value is not None for value in row):
                            continue

                        if len(row) < 12:
                            raise ValueError(
                                f"Dòng {row_number}: Thiếu cột dữ liệu"
                            )

                        vin = chuyen_chuoi(row[4])

                        if not vin:
                            raise ValueError(
                                f"Dòng {row_number}: Thiếu VIN"
                            )

                        # Kiểm tra tháng và năm
                        allocation_month = chuyen_thang(row[11])
                        if (allocation_month.month != today.month
                                or allocation_month.year != today.year):
                            raise ValueError(
                                f"Dòng {row_number}: Tháng phân bổ "
                                f"{allocation_month.strftime('%m/%Y')} "
                                "không phải tháng hiện tại"
                            )

                        data.append({
                            "order_number": chuyen_chuoi(row[1]),
                            "vehicle_code": chuyen_chuoi(row[2]),
                            "description": chuyen_chuoi(row[3]),
                            "vin": vin,
                            "color_code": chuyen_chuoi(row[5]),
                            "exterior_color": chuyen_chuoi(row[6]),
                            "engine_number": chuyen_chuoi(row[7]),
                            "quantity": chuyen_so_luong(row[8]),
                            "expected_ship_date": chuyen_ngay(row[9]),
                            "contractual_delivery_date": chuyen_ngay(row[10]),
                            "allocation_month": allocation_month,
                        })

                    with transaction.atomic():
                        for item in data:
                            vin = item.pop("vin")

                            Allocation.objects.update_or_create(
                                vin=vin,
                                defaults=item
                            )

                    messages.success(
                        request,
                        "Tải danh sách phân bổ thành công!"
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

    today = timezone.localdate()

    allocations = Allocation.objects.filter(
        allocation_month__year=today.year,
        allocation_month__month=today.month
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

        # Chỉ lấy xe thuộc tháng và năm hiện tại
        allocations = Allocation.objects.filter(
            allocation_month__year=today.year,
            allocation_month__month=today.month
        )

        # Tìm kiếm theo VIN hoặc mô tả
        if keyword:
            allocations = allocations.filter(
                Q(vin__iexact=keyword) |
                Q(description__icontains=keyword)
            )
        else:
            allocations = allocations.none()

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

    # Chỉ cho phép chọn xe thuộc tháng hiện tại
    xe = get_object_or_404(
        Allocation,
        id=id,
        allocation_month__year=today.year,
        allocation_month__month=today.month
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
            pk=ma_xe,
            allocation_month__year=today.year,
            allocation_month__month=today.month
        ).first()

        if xe is None:
            messages.error(
                request,
                "Xe không thuộc danh sách phân bổ tháng hiện tại."
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

    # 1. Lấy danh sách phân bổ tháng hiện tại
    allocations = Allocation.objects.filter(
        allocation_month__year=today.year,
        allocation_month__month=today.month
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

    # 2. Lấy xe từ danh sách phân bổ tháng hiện tại
    allocation = get_object_or_404(
        Allocation,
        id=id,
        allocation_month__year=today.year,
        allocation_month__month=today.month
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
            allocation_month__year=today.year,
            allocation_month__month=today.month
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
