from django.shortcuts import render
from django.db.models import Q
from database.models import Kho, TonKho
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.db import transaction
from .models import LenhLuuChuyen, ChiTietLenhLuuChuyen
from django.http import HttpResponse
from django.conf import settings
from io import BytesIO
import logging
from django.core.mail import EmailMessage
from django.template.loader import render_to_string
from xhtml2pdf import pisa
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
FONT_DIR = settings.BASE_DIR / "transfers" / "static" / "fonts"

pdfmetrics.registerFont(
    TTFont(
        "DejaVuSans",
        str(FONT_DIR / "DejaVuSans.ttf")
    )
)

pdfmetrics.registerFont(
    TTFont(
        "DejaVuSans-Bold",
        str(FONT_DIR / "DejaVuSans-Bold.ttf")
    )
)

pdfmetrics.registerFontFamily(
    "DejaVuSans",
    normal="DejaVuSans",
    bold="DejaVuSans-Bold",
)

def link_callback(uri, rel):
    font_files = {
        "DejaVuSans.ttf": "DejaVuSans.ttf",
        "DejaVuSans-Bold.ttf": "DejaVuSans-Bold.ttf",
    }

    if uri in font_files:
        return str(FONT_DIR / font_files[uri])

    return uri
@login_required
def danh_sach_ton_kho(request):

    # 1. Lấy danh sách các kho và thông tin chi nhánh
    ds_kho = Kho.objects.select_related(
        'chi_nhanh'
    ).all()

    # 2. Lấy danh sách xe đang tồn kho
    ds_ton_kho = TonKho.objects.select_related(
        'kho',
        'kho__chi_nhanh',
        'xe'
    ).filter(
        so_luong_ton__gt=0
    )
    sess = getattr(request, 'session', {})
    current_kho = sess.get('current_kho') if hasattr(sess, 'get') else None
    if current_kho and current_kho != "ALL":
        ds_ton_kho = ds_ton_kho.filter(kho_id=current_kho)

    # 3. Lấy từ khóa tìm kiếm từ URL
    tu_khoa = request.GET.get('q', '').strip()

    # 4. Tìm kiếm xe
    if tu_khoa:
        ds_ton_kho = ds_ton_kho.filter(
            Q(xe__ten_xe__icontains=tu_khoa) |
            Q(kho__ma_kho__icontains=tu_khoa)
        )

    # 5. Sắp xếp theo mã kho
    ds_ton_kho = ds_ton_kho.order_by(
        'kho__ma_kho'
    )

    # 6. Truyền dữ liệu sang HTML
    context = {
        'ds_kho': ds_kho,
        'ds_ton_kho': ds_ton_kho,
        'tu_khoa': tu_khoa,
    }
    ds_da_chon = request.session.get("ds_xe_luu_chuyen", [])

    danh_sach_da_chon = []

    for index, item in enumerate(ds_da_chon):
        ton_kho = TonKho.objects.select_related(
            "xe", "kho", "kho__chi_nhanh"
        ).filter(pk=item["ton_kho_id"]).first()

        kho_nhan = Kho.objects.select_related(
            "chi_nhanh"
        ).filter(pk=item["kho_nhan_id"]).first()

        if ton_kho and kho_nhan:
            danh_sach_da_chon.append({
                "index": index,  # THÊM DÒNG NÀY
                "ton_kho": ton_kho,
                "kho_nhan": kho_nhan,
                "so_luong": item["so_luong"]
            })
    context['danh_sach_da_chon'] = danh_sach_da_chon
    return render(
        request,
        'danh_sach_ton_kho.html',
        context
    )



def chi_tiet_xe(request, id):

    ton_kho = get_object_or_404(
        TonKho.objects.select_related(
            'xe',
            'kho',
            'kho__chi_nhanh'
        ),
        pk=id,
        so_luong_ton__gt=0
    )

    ds_kho_nhan = Kho.objects.select_related(
        'chi_nhanh'
    ).exclude(
        pk=ton_kho.kho_id
    )

    if request.method == 'POST':

        so_luong_nhap = request.POST.get('so_luong', '')
        kho_nhan_id = request.POST.get('kho_nhan', '')

        try:
            so_luong = int(so_luong_nhap)
        except (ValueError, TypeError):
            so_luong = 0

        kho_nhan = Kho.objects.filter(
            pk=kho_nhan_id
        ).exclude(
            pk=ton_kho.kho_id
        ).first()

        if so_luong <= 0:
            messages.error(
                request,
                "Số lượng lưu chuyển phải lớn hơn 0."
            )

        elif not kho_nhan:
            messages.error(
                request,
                "Vui lòng chọn kho nhận hợp lệ."
            )

        else:
            danh_sach = request.session.get(
                'ds_xe_luu_chuyen', []
            )

            # Kiểm tra kho xuất của TẤT CẢ xe đã chọn
            for item in danh_sach:
                xe_da_chon = TonKho.objects.filter(
                    pk=item['ton_kho_id']
                ).first()

                if xe_da_chon and xe_da_chon.kho_id != ton_kho.kho_id:
                    messages.error(
                        request,
                        f"Danh sách đã có xe từ kho {xe_da_chon.kho_id}. "
                        f"Không thể thêm xe từ kho {ton_kho.kho_id}."
                    )

                    return redirect(
                        reverse('transfers:index') + '?tab=da-chon'
                    )

            # Kiểm tra tổng số lượng đã chọn
            so_luong_da_chon = sum(
                item['so_luong']
                for item in danh_sach
                if item['ton_kho_id'] == ton_kho.pk
            )

            if so_luong + so_luong_da_chon > ton_kho.so_luong_ton:
                messages.error(
                    request,
                    "Số lượng lưu chuyển vượt quá tồn kho."
                )

            else:
                danh_sach.append({
                    'ton_kho_id': ton_kho.pk,
                    'kho_nhan_id': kho_nhan.pk,
                    'so_luong': so_luong,
                })

                request.session['ds_xe_luu_chuyen'] = danh_sach

                messages.success(
                    request,
                    "Đã thêm xe vào danh sách lưu chuyển."
                )

                return redirect(
                    reverse('transfers:index') + '?tab=da-chon'
                )
            if so_luong + so_luong_da_chon > ton_kho.so_luong_ton:
                messages.error(
                    request,
                    "Số lượng lưu chuyển vượt quá tồn kho."
                )

            else:
                danh_sach.append({
                    'ton_kho_id': ton_kho.pk,
                    'kho_nhan_id': kho_nhan.pk,
                    'so_luong': so_luong,
                })

                request.session['ds_xe_luu_chuyen'] = danh_sach

                messages.success(
                    request,
                    "Đã thêm xe vào danh sách lưu chuyển."
                )

                return redirect(
                    reverse('transfers:index') + '?tab=da-chon'
                )

    return render(
        request,
        'chi_tiet_xe.html',
        {
            'ton_kho': ton_kho,
            'ds_kho_nhan': ds_kho_nhan,
        }
    )

def xoa_xe_da_chon(request, index):

    if request.method == "POST":

        danh_sach = request.session.get(
            "ds_xe_luu_chuyen", []
        )

        if 0 <= index < len(danh_sach):

            danh_sach.pop(index)

            request.session["ds_xe_luu_chuyen"] = danh_sach

            messages.success(
                request,
                "Đã xóa xe khỏi danh sách lưu chuyển."
            )

        else:
            messages.error(
                request,
                "Không tìm thấy xe cần xóa."
            )

    return redirect(
        reverse("transfers:index") + "?tab=da-chon"
    )



def lay_du_lieu_lenh_tu_session(request):
    danh_sach = request.session.get("ds_xe_luu_chuyen", [])

    if not danh_sach:
        raise ValueError("Bạn chưa chọn xe để tạo lệnh lưu chuyển.")

    chi_tiet = []
    kho_xuat_id = None
    kho_nhap_id = None
    so_luong_theo_ton_kho = {}

    for item in danh_sach:
        try:
            ton_kho_id = int(item["ton_kho_id"])
            kho_nhan_id = item["kho_nhan_id"]
            so_luong = int(item["so_luong"])
        except (KeyError, TypeError, ValueError):
            raise ValueError("Dữ liệu xe đã chọn không hợp lệ.")

        ton_kho = TonKho.objects.select_related(
            "xe", "kho"
        ).filter(pk=ton_kho_id).first()

        kho_nhan = Kho.objects.filter(
            pk=kho_nhan_id
        ).first()

        if ton_kho is None or kho_nhan is None:
            raise ValueError("Xe hoặc kho nhận không còn tồn tại.")

        if so_luong <= 0:
            raise ValueError("Số lượng xe phải lớn hơn 0.")

        if ton_kho.kho_id == kho_nhan.pk:
            raise ValueError("Kho xuất và kho nhập phải khác nhau.")

        if kho_xuat_id is None:
            kho_xuat_id = ton_kho.kho_id
            kho_nhap_id = kho_nhan.pk
        elif (
            ton_kho.kho_id != kho_xuat_id
            or kho_nhan.pk != kho_nhap_id
        ):
            raise ValueError(
                "Các xe trong một lệnh phải có cùng kho xuất và kho nhập."
            )

        so_luong_theo_ton_kho[ton_kho_id] = (
            so_luong_theo_ton_kho.get(ton_kho_id, 0) + so_luong
        )

        if so_luong_theo_ton_kho[ton_kho_id] > ton_kho.so_luong_ton:
            raise ValueError(
                f"Số lượng xe vượt tồn kho tại {ton_kho.kho}."
            )

        chi_tiet.append({
            "ton_kho": ton_kho,
            "kho_nhan": kho_nhan,
            "so_luong": so_luong,
        })

    return (
        Kho.objects.get(pk=kho_xuat_id),
        Kho.objects.get(pk=kho_nhap_id),
        chi_tiet,
    )



@login_required
def tao_lenh_luu_chuyen(request):
    danh_sach = request.session.get("ds_xe_luu_chuyen", [])

    if not danh_sach:
        messages.error(request, "Chưa có xe nào được chọn.")
        return redirect(
            reverse("transfers:index") + "?tab=da-chon"
        )

    chi_tiet = []
    so_luong_theo_ton_kho = {}

    for item in danh_sach:
        try:
            ton_kho_id = int(item["ton_kho_id"])
            kho_nhan_id = item["kho_nhan_id"]
            so_luong = int(item["so_luong"])
        except (KeyError, TypeError, ValueError):
            messages.error(request, "Dữ liệu xe không hợp lệ.")
            return redirect(
                reverse("transfers:index") + "?tab=da-chon"
            )

        ton_kho = get_object_or_404(
            TonKho.objects.select_related(
                "xe", "kho", "kho__chi_nhanh"
            ),
            pk=ton_kho_id
        )

        kho_nhan = get_object_or_404(
            Kho.objects.select_related("chi_nhanh"),
            pk=kho_nhan_id
        )

        if so_luong <= 0:
            messages.error(
                request,
                "Số lượng xe phải lớn hơn 0."
            )
            return redirect(
                reverse("transfers:index") + "?tab=da-chon"
            )

        if ton_kho.kho_id == kho_nhan.pk:
            messages.error(
                request,
                "Kho xuất và kho nhập phải khác nhau."
            )
            return redirect(
                reverse("transfers:index") + "?tab=da-chon"
            )

        so_luong_theo_ton_kho[ton_kho_id] = (
            so_luong_theo_ton_kho.get(ton_kho_id, 0)
            + so_luong
        )

        if so_luong_theo_ton_kho[ton_kho_id] > ton_kho.so_luong_ton:
            messages.error(
                request,
                f"Số lượng xe vượt quá tồn kho của {ton_kho.xe}."
            )
            return redirect(
                reverse("transfers:index") + "?tab=da-chon"
            )

        chi_tiet.append({
            "ton_kho": ton_kho,
            "kho_nhan": kho_nhan,
            "so_luong": so_luong,
        })

    # Xác định kho xuất và kho nhập
    kho_xuat = chi_tiet[0]["ton_kho"].kho
    kho_nhap = chi_tiet[0]["kho_nhan"]

    # Kiểm tra các xe cùng kho xuất và kho nhập
    for item in chi_tiet:
        if (
            item["ton_kho"].kho_id != kho_xuat.pk
            or item["kho_nhan"].pk != kho_nhap.pk
        ):
            messages.error(
                request,
                "Một lệnh lưu chuyển phải có cùng kho xuất và kho nhập."
            )
            return redirect(
                reverse("transfers:index") + "?tab=da-chon"
            )

    # Lưu lệnh và danh sách xe vào database
    with transaction.atomic():
        lenh_id = request.session.get(
            "lenh_nhap_dang_sua_id"
        )

        if lenh_id:
            lenh = LenhLuuChuyen.objects.select_for_update().filter(
                pk=lenh_id,
                trang_thai="NHAP",
                nguoi_lap=request.user
            ).first()

            if lenh is None:
                messages.error(
                    request,
                    "Không tìm thấy bản nháp đang chỉnh sửa."
                )
                return redirect("transfers:danh_sach_lenh")

            lenh.kho_xuat = kho_xuat
            lenh.kho_nhap = kho_nhap
            lenh.save(update_fields=["kho_xuat", "kho_nhap"])

            # Xóa chi tiết cũ để thay bằng danh sách mới
            lenh.chi_tiet.all().delete()

        else:
            lenh = LenhLuuChuyen.objects.create(
                kho_xuat=kho_xuat,
                kho_nhap=kho_nhap,
                nguoi_lap=request.user,
                trang_thai="NHAP"
            )

            # Tự động tạo mã lệnh
            lenh.ma_lenh = f"LC{lenh.pk:05d}"
            lenh.save(update_fields=["ma_lenh"])

        # Lưu từng xe thuộc lệnh
        for item in chi_tiet:
            ChiTietLenhLuuChuyen.objects.create(
                lenh=lenh,
                xe=item["ton_kho"].xe,
                so_luong=item["so_luong"]
            )

    # Ghi nhớ bản nháp đang làm việc
    request.session["lenh_nhap_dang_sua_id"] = lenh.pk

    # Chuyển đến trang chi tiết bản nháp
    return redirect(
        "transfers:chi_tiet_lenh",
        id=lenh.pk
    )



@login_required
@require_POST
def xac_nhan_lenh_luu_chuyen(request):
    danh_sach = request.session.get("ds_xe_luu_chuyen", [])

    if not danh_sach:
        messages.error(request, "Chưa có xe nào được chọn.")
        return redirect("transfers:index")

    chi_tiet = []

    for item in danh_sach:
        ton_kho = get_object_or_404(
            TonKho.objects.select_related(
                "xe", "kho", "kho__chi_nhanh"
            ),
            pk=item["ton_kho_id"]
        )

        kho_nhan = get_object_or_404(
            Kho.objects.select_related("chi_nhanh"),
            pk=item["kho_nhan_id"]
        )

        try:
            so_luong = int(item["so_luong"])
        except (ValueError, TypeError, KeyError):
            messages.error(request, "Số lượng xe không hợp lệ.")
            return redirect("transfers:tao_lenh")

        if so_luong <= 0 or so_luong > ton_kho.so_luong_ton:
            messages.error(
                request,
                "Số lượng xe không hợp lệ hoặc vượt quá tồn kho."
            )
            return redirect("transfers:tao_lenh")

        if ton_kho.kho_id == kho_nhan.pk:
            messages.error(
                request,
                "Kho xuất và kho nhập không được trùng nhau."
            )
            return redirect("transfers:tao_lenh")

        chi_tiet.append({
            "ton_kho": ton_kho,
            "kho_nhan": kho_nhan,
            "so_luong": so_luong,
        })

    kho_xuat = chi_tiet[0]["ton_kho"].kho
    kho_nhap = chi_tiet[0]["kho_nhan"]

    for item in chi_tiet:
        if (
            item["ton_kho"].kho_id != kho_xuat.pk
            or item["kho_nhan"].pk != kho_nhap.pk
        ):
            messages.error(
                request,
                "Các xe phải có cùng kho xuất và kho nhập."
            )
            return redirect("transfers:tao_lenh")

    context = {
        "chi_tiet": chi_tiet,
        "kho_xuat": kho_xuat,
        "kho_nhap": kho_nhap,
        "tong_so_luong": sum(
            item["so_luong"] for item in chi_tiet
        ),
        "ngay_lap": timezone.localdate(),
        "nguoi_lap": request.user.username,
    }

    try:
        # Bước 1: Lấy nội dung HTML của phiếu PDF
        html = render_to_string(
            "lenh_luu_chuyen_pdf.html",
            context
        )

        # Bước 2: Chuyển HTML thành PDF
        pdf_buffer = BytesIO()

        ket_qua = pisa.CreatePDF(
            src=html,
            dest=pdf_buffer,
            encoding="utf-8",
            link_callback=link_callback
        )

        if ket_qua.err:
            messages.error(request, "Không thể tạo file PDF.")
            return redirect("transfers:tao_lenh")

        # Bước 3: Kiểm tra người nhận
        if not settings.TRANSFER_RECEIVER_EMAILS:
            messages.error(request, "Chưa cấu hình email người nhận.")
            return redirect("transfers:tao_lenh")

        # Bước 4: Tạo email
        email = EmailMessage(
            subject="Lệnh lưu chuyển xe - Dana Ford",
            body=(
                "Kính gửi bộ phận quản lý kho,\n\n"
                "Hệ thống gửi phiếu lệnh lưu chuyển xe.\n\n"
                f"Kho xuất: {kho_xuat.ma_kho}\n"
                f"Kho nhập: {kho_nhap.ma_kho}\n"
                f"Tổng số lượng: {context['tong_so_luong']}\n\n"
                "Vui lòng xem file PDF đính kèm.\n\n"
                "Trân trọng,\n"
                "Hệ thống Dana Ford"
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=settings.TRANSFER_RECEIVER_EMAILS,
        )

        # Bước 5: Đính kèm PDF
        email.attach(
            "Lenh_luu_chuyen.pdf",
            pdf_buffer.getvalue(),
            "application/pdf"
        )

        # Bước 6: Gửi email
        so_email = email.send(fail_silently=False)

        if so_email == 1:
            request.session.pop("ds_xe_luu_chuyen", None)

            messages.success(
                request,
                "Đã gửi phiếu lệnh lưu chuyển PDF thành công!"
            )
            return redirect("transfers:index")

        messages.error(request, "Không gửi được email.")
        return redirect("transfers:tao_lenh")

    except Exception:
        logging.getLogger(__name__).exception(
            "Lỗi tạo PDF hoặc gửi email lưu chuyển"
        )

        messages.error(
            request,
            "Có lỗi khi tạo PDF hoặc gửi email. "
            "Vui lòng kiểm tra Terminal."
        )
        return redirect("transfers:tao_lenh")


@login_required
def danh_sach_lenh_luu_chuyen(request):
    from .models import LenhLuuChuyen

    trang_thai = request.GET.get("trang_thai", "").strip()
    tu_khoa = request.GET.get("q", "").strip()

    ds_lenh = LenhLuuChuyen.objects.select_related(
        "kho_xuat",
        "kho_nhap",
        "nguoi_lap"
    ).order_by("-ngay_lap")
    sess = getattr(request, 'session', {})
    current_kho = sess.get('current_kho') if hasattr(sess, 'get') else None
    if current_kho and current_kho != "ALL":
        ds_lenh = ds_lenh.filter(Q(kho_xuat_id=current_kho) | Q(kho_nhap_id=current_kho))

    if trang_thai in ["NHAP", "DA_GUI", "DA_XAC_NHAN"]:
        ds_lenh = ds_lenh.filter(trang_thai=trang_thai)

    if tu_khoa:
        ds_lenh = ds_lenh.filter(
            Q(ma_lenh__icontains=tu_khoa)
            | Q(kho_xuat__ma_kho__icontains=tu_khoa)
            | Q(kho_nhap__ma_kho__icontains=tu_khoa)
        )

    return render(request, "danh_sach_lenh.html", {
        "ds_lenh": ds_lenh,
        "trang_thai": trang_thai,
        "tu_khoa": tu_khoa,
    })


@login_required
def chi_tiet_lenh_luu_chuyen(request, id):
    from .models import LenhLuuChuyen

    lenh = get_object_or_404(
        LenhLuuChuyen.objects.select_related(
            "kho_xuat",
            "kho_nhap",
            "nguoi_lap",
            "nguoi_xac_nhan"
        ).prefetch_related("chi_tiet__xe"),
        pk=id
    )

    tong_so_luong = sum(
        item.so_luong for item in lenh.chi_tiet.all()
    )

    return render(request, "chi_tiet_lenh.html", {
        "lenh": lenh,
        "tong_so_luong": tong_so_luong,
    })


@login_required
@require_POST
def cap_nhat_trang_thai_lenh(request, id):
    from django.core.exceptions import PermissionDenied, ValidationError
    from .services import receive_transfer
    try:
        receive_transfer(request.user, id)
        messages.success(request, 'Đã tiếp nhận xe. Lập phiếu nhập và kiểm tra PDI trước khi ghi tồn kho đích.')
    except (PermissionDenied, ValidationError) as exc:
        messages.error(request, str(exc))
    return redirect('transfers:chi_tiet_lenh', id=id)


@login_required
def chinh_sua_lenh_luu_chuyen(request, id):
    from .models import LenhLuuChuyen

    lenh = get_object_or_404(
        LenhLuuChuyen.objects.prefetch_related("chi_tiet__xe"),
        pk=id
    )

    # Chỉ cho phép chỉnh sửa bản nháp
    if lenh.trang_thai != "NHAP":
        messages.error(
            request,
            "Chỉ có thể chỉnh sửa lệnh ở trạng thái Bản nháp."
        )
        return redirect("transfers:chi_tiet_lenh", id=id)

    # Lấy danh sách xe từ bản nháp
    danh_sach = []

    for item in lenh.chi_tiet.all():

        ton_kho = TonKho.objects.filter(
            kho=lenh.kho_xuat,
            xe=item.xe
        ).first()

        if not ton_kho:
            messages.error(
                request,
                f"Không tìm thấy tồn kho của xe {item.xe.vin}."
            )
            return redirect("transfers:chi_tiet_lenh", id=id)

        danh_sach.append({
            "ton_kho_id": ton_kho.pk,
            "kho_nhan_id": lenh.kho_nhap_id,
            "so_luong": item.so_luong,
        })

    # Đưa danh sách xe vào session
    request.session["ds_xe_luu_chuyen"] = danh_sach

    # Ghi nhớ bản nháp đang chỉnh sửa
    request.session["lenh_nhap_dang_sua_id"] = lenh.pk

    messages.success(
        request,
        "Đã tải danh sách xe của bản nháp. "
        "Bạn có thể tiếp tục chỉnh sửa."
    )

    # Quay về tab Danh sách đã chọn
    return redirect(
        reverse("transfers:index") + "?tab=da-chon"
    )

@login_required
@require_POST
def luu_ban_nhap_lenh(request):
    danh_sach = request.session.get("ds_xe_luu_chuyen", [])

    if not danh_sach:
        messages.error(request, "Chưa có xe nào được chọn.")
        return redirect("transfers:index")

    chi_tiet = []

    for item in danh_sach:
        ton_kho = get_object_or_404(
            TonKho.objects.select_related("xe", "kho"),
            pk=item["ton_kho_id"]
        )

        kho_nhan = get_object_or_404(
            Kho,
            pk=item["kho_nhan_id"]
        )

        try:
            so_luong = int(item["so_luong"])
        except (ValueError, TypeError, KeyError):
            messages.error(request, "Số lượng xe không hợp lệ.")
            return redirect("transfers:tao_lenh")

        if so_luong <= 0 or so_luong > ton_kho.so_luong_ton:
            messages.error(request, "Số lượng xe vượt quá tồn kho.")
            return redirect("transfers:tao_lenh")

        if ton_kho.kho_id == kho_nhan.pk:
            messages.error(request, "Kho xuất và kho nhập phải khác nhau.")
            return redirect("transfers:tao_lenh")

        chi_tiet.append({
            "ton_kho": ton_kho,
            "kho_nhan": kho_nhan,
            "so_luong": so_luong,
        })

    kho_xuat = chi_tiet[0]["ton_kho"].kho
    kho_nhap = chi_tiet[0]["kho_nhan"]

    for item in chi_tiet:
        if (
            item["ton_kho"].kho_id != kho_xuat.pk
            or item["kho_nhan"].pk != kho_nhap.pk
        ):
            messages.error(
                request,
                "Các xe phải có cùng kho xuất và kho nhập."
            )
            return redirect("transfers:tao_lenh")

    # Lưu bản nháp và các xe trong cùng một giao dịch database
    with transaction.atomic():
        lenh_id = request.session.get("lenh_nhap_dang_sua_id")

        if lenh_id:
            lenh = get_object_or_404(
                LenhLuuChuyen.objects.select_for_update(),
                pk=lenh_id,
                trang_thai="NHAP"
            )

            # Chỉ cho phép người lập chỉnh sửa bản nháp của mình
            if lenh.nguoi_lap_id != request.user.pk:
                messages.error(request, "Bạn không có quyền sửa lệnh này.")
                return redirect("transfers:danh_sach_lenh")

            lenh.kho_xuat = kho_xuat
            lenh.kho_nhap = kho_nhap
            lenh.save(update_fields=["kho_xuat", "kho_nhap"])

            lenh.chi_tiet.all().delete()

        else:
            lenh = LenhLuuChuyen.objects.create(
                kho_xuat=kho_xuat,
                kho_nhap=kho_nhap,
                nguoi_lap=request.user,
                trang_thai="NHAP"
            )

            lenh.ma_lenh = f"LC{lenh.pk:05d}"
            lenh.save(update_fields=["ma_lenh"])

        for item in chi_tiet:
            ChiTietLenhLuuChuyen.objects.create(
                lenh=lenh,
                xe=item["ton_kho"].xe,
                so_luong=item["so_luong"]
            )

    request.session["lenh_nhap_dang_sua_id"] = lenh.pk

    messages.success(
        request,
        f"Đã lưu bản nháp {lenh.ma_lenh} thành công."
    )

    return redirect("transfers:chi_tiet_lenh", id=lenh.pk)



@login_required
@require_POST
def gui_lenh_luu_chuyen(request, id):
    lenh = get_object_or_404(
        LenhLuuChuyen.objects.select_related(
            "kho_xuat", "kho_nhap", "nguoi_lap"
        ).prefetch_related("chi_tiet__xe"),
        pk=id
    )

    if lenh.nguoi_lap_id != request.user.pk:
        messages.error(request, "Bạn không có quyền gửi lệnh này.")
        return redirect("transfers:danh_sach_lenh")

    if lenh.trang_thai != "NHAP":
        messages.warning(request, "Lệnh này không còn là bản nháp.")
        return redirect("transfers:chi_tiet_lenh", id=id)

    chi_tiet = list(lenh.chi_tiet.all())

    if not chi_tiet:
        messages.error(request, "Lệnh chưa có xe.")
        return redirect("transfers:chi_tiet_lenh", id=id)

    try:
        html = render_to_string(
            "lenh_luu_chuyen_pdf.html",
            {
                "lenh": lenh,
                "chi_tiet": chi_tiet,
                "kho_xuat": lenh.kho_xuat,
                "kho_nhap": lenh.kho_nhap,
                "nguoi_lap": lenh.nguoi_lap.username,
                "ngay_lap": timezone.localtime(lenh.ngay_lap).date(),
                "tong_so_luong": sum(
                    item.so_luong for item in chi_tiet
                ),
            },
            request=request
        )

        pdf_buffer = BytesIO()

        ket_qua = pisa.CreatePDF(
            src=html,
            dest=pdf_buffer,
            encoding="utf-8",
            link_callback=link_callback
        )

        if ket_qua.err:
            raise ValueError("Không thể tạo file PDF.")

        danh_sach_email = getattr(settings, "TRANSFER_RECEIVER_EMAILS", [])


        if isinstance(danh_sach_email, str):


            danh_sach_email = [dia_chi.strip() for dia_chi in danh_sach_email.split(",") if dia_chi.strip()]


        if danh_sach_email and getattr(settings, "DEFAULT_FROM_EMAIL", None):


            try:


                email = EmailMessage(


                    subject=f"Lệnh lưu chuyển {lenh.ma_lenh}",


                    body=f"Đính kèm lệnh lưu chuyển {lenh.ma_lenh}.",


                    from_email=settings.DEFAULT_FROM_EMAIL,


                    to=danh_sach_email


                )


                email.attach(


                    f"Lenh_luu_chuyen_{lenh.ma_lenh}.pdf",


                    pdf_buffer.getvalue(),


                    "application/pdf"


                )


                email.send(fail_silently=True)


            except Exception as mail_err:


                logging.warning(f"Không thể gửi email thông báo: {mail_err}")

    except Exception as e:
        messages.error(request, f"Lỗi gửi lệnh: {e}")
        return redirect("transfers:chi_tiet_lenh", id=id)

    from django.core.exceptions import PermissionDenied, ValidationError
    from .services import dispatch_transfer
    try:
        dispatch_transfer(request.user, lenh.pk)
    except (PermissionDenied, ValidationError) as exc:
        messages.error(request, str(exc))
        return redirect('transfers:chi_tiet_lenh', id=id)

    if request.session.get("lenh_nhap_dang_sua_id") == lenh.pk:
        request.session.pop("lenh_nhap_dang_sua_id", None)
        request.session.pop("ds_xe_luu_chuyen", None)

    messages.success(
        request,
        f"Đã gửi lệnh {lenh.ma_lenh} thành công!"
    )

    return redirect("transfers:chi_tiet_lenh", id=lenh.pk)
