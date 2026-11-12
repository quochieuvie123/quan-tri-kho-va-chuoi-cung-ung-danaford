"""Dịch vụ nghiệp vụ Lệnh lưu chuyển xe nội bộ (Dana Ford).
Mỗi chuyển trạng thái thực hiện nguyên tử qua một hàm service duy nhất.
Tồn kho nguồn chỉ bị trừ khi kho nguồn xác nhận xuất xe.
Transfers TUYỆT ĐỐI KHÔNG cộng tồn tại kho đích (việc cộng tồn chỉ thực hiện ở module warehouse nhập kho).
"""
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from database.models import TonKho, Xe, TrangThaiXe, DonViVanChuyen, ChiTietHopDong
from dashboard.models import ThongBaoHoatDong
from .models import LenhLuuChuyen, ChiTietLenhLuuChuyen

ACTIVE_TRANSFER_STATUSES = [
    LenhLuuChuyen.TrangThai.NHAP,
    LenhLuuChuyen.TrangThai.CHO_DUYET,
    LenhLuuChuyen.TrangThai.DA_GUI,
    LenhLuuChuyen.TrangThai.DA_DUYET,
    LenhLuuChuyen.TrangThai.DANG_VAN_CHUYEN,
    LenhLuuChuyen.TrangThai.DA_GIAO_DEN_DA_NANG,
]


def is_admin_or_sale_admin(user):
    """Kiểm tra người dùng có vai trò Quản trị viên / Sale Admin."""
    if not user or not user.is_authenticated or not user.is_active:
        return False
    if user.is_superuser or user.is_staff:
        return True
    try:
        from core.roles import get_user_role_info
        role_info = get_user_role_info(user)
        if role_info and role_info.get("code") in ("ADMIN", "SALE_ADMIN"):
            return True
    except Exception:
        pass
    return user.groups.filter(name__in=["Sale Admin", "Quản trị viên", "Quản lý"]).exists()


def kiem_tra_quyen_chi_nhanh(user, kho):
    """Kiểm tra người dùng có quyền thao tác trên kho chi nhánh."""
    if is_admin_or_sale_admin(user):
        return True
    nv = getattr(user, "nhan_vien", None)
    if nv and kho and nv.chi_nhanh_id == kho.chi_nhanh_id:
        return True
    raise PermissionDenied(f"Tài khoản không thuộc chi nhánh quản lý kho {kho.ma_kho if kho else ''}.")


def kiem_tra_quyen_sale_admin(user):
    """Bắt buộc vai trò Sale Admin."""
    if not is_admin_or_sale_admin(user):
        raise PermissionDenied("Chỉ Quản trị viên (Sale Admin) mới có quyền duyệt thao tác này.")


def kiem_tra_vin_trong_lenh_mo(xe, exclude_order_id=None):
    """Một VIN chỉ được nằm trong duy nhất một lệnh lưu chuyển đang mở."""
    qs = ChiTietLenhLuuChuyen.objects.filter(
        xe=xe,
        lenh__trang_thai__in=ACTIVE_TRANSFER_STATUSES
    )
    if exclude_order_id:
        qs = qs.exclude(lenh_id=exclude_order_id)
    existing = qs.select_related("lenh").first()
    if existing:
        raise ValidationError(
            f"Xe {xe.vin} đang nằm trong lệnh lưu chuyển '{existing.lenh.ma_lenh or existing.lenh_id}' chưa hoàn tất."
        )


def ghi_thong_bao(user, hanh_dong, chi_tiet, loai="THONG_TIN"):
    """Ghi nhận thông báo hoạt động hệ thống minh bạch, không nuốt lỗi."""
    ten = user.get_full_name() or user.username if user and user.is_authenticated else "Hệ thống"
    chuc_vu = "Quản trị viên (Sale Admin)" if is_admin_or_sale_admin(user) else "Sale Chi Nhánh / Nhân viên kho"
    ThongBaoHoatDong.objects.create(
        user=user if user and user.is_authenticated else None,
        ten_nhan_vien=ten,
        chuc_vu=chuc_vu,
        hanh_dong=hanh_dong,
        chi_tiet=chi_tiet,
        module="transfers",
        loai=loai
    )


@transaction.atomic
def tao_lenh_luu_chuyen(user, kho_xuat, kho_nhap, ds_xe=None):
    """Tạo lệnh lưu chuyển ở trạng thái bản nháp (NHAP)."""
    if kho_xuat == kho_nhap or kho_xuat.pk == kho_nhap.pk:
        raise ValidationError("Kho xuất và kho tiếp nhận không được trùng nhau.")
    kiem_tra_quyen_chi_nhanh(user, kho_xuat)

    now = timezone.now()
    thang_nam = now.strftime("%Y%m")
    prefix = f"LC-{thang_nam}-"
    so_hien_tai = LenhLuuChuyen.objects.filter(ma_lenh__startswith=prefix).count() + 1
    ma_lenh = f"{prefix}{so_hien_tai:03d}"

    lenh = LenhLuuChuyen.objects.create(
        ma_lenh=ma_lenh,
        kho_xuat=kho_xuat,
        kho_nhap=kho_nhap,
        nguoi_lap=user,
        trang_thai=LenhLuuChuyen.TrangThai.NHAP,
    )

    if ds_xe:
        for car in ds_xe:
            kiem_tra_vin_trong_lenh_mo(car, exclude_order_id=lenh.pk)
            # Kiểm tra tồn kho tại kho xuất
            ton = TonKho.objects.filter(kho=kho_xuat, xe=car, so_luong_ton__gt=0).first()
            if not ton:
                raise ValidationError(f"Xe {car.vin} không có tồn kho tại {kho_xuat.ma_kho}.")
            ChiTietLenhLuuChuyen.objects.create(lenh=lenh, xe=car, so_luong=1)

    ghi_thong_bao(
        user,
        f"Lập lệnh lưu chuyển {lenh.ma_lenh}",
        f"Khởi tạo lệnh lưu chuyển bản nháp {lenh.ma_lenh} từ {kho_xuat.ma_kho} về {kho_nhap.ma_kho}.",
        loai="THONG_TIN"
    )
    return lenh


@transaction.atomic
def them_xe_vao_lenh(user, order_id, xe):
    """Thêm một VIN vào lệnh bản nháp."""
    order = LenhLuuChuyen.objects.select_for_update().select_related("kho_xuat").get(pk=order_id)
    if order.trang_thai != LenhLuuChuyen.TrangThai.NHAP:
        raise ValidationError("Chỉ có thể thêm xe vào lệnh đang ở trạng thái bản nháp.")
    kiem_tra_quyen_chi_nhanh(user, order.kho_xuat)
    kiem_tra_vin_trong_lenh_mo(xe, exclude_order_id=order.pk)

    ton = TonKho.objects.filter(kho=order.kho_xuat, xe=xe, so_luong_ton__gt=0).first()
    if not ton:
        raise ValidationError(f"Xe {xe.vin} không có tồn tại kho xuất {order.kho_xuat.ma_kho}.")

    ct, created = ChiTietLenhLuuChuyen.objects.get_or_create(lenh=order, xe=xe, defaults={"so_luong": 1})
    if not created:
        raise ValidationError(f"Xe {xe.vin} đã có trong lệnh lưu chuyển này.")
    return ct


@transaction.atomic
def xoa_xe_khoi_lenh(user, order_id, xe_id):
    """Xóa một VIN khỏi lệnh bản nháp."""
    order = LenhLuuChuyen.objects.select_for_update().select_related("kho_xuat").get(pk=order_id)
    if order.trang_thai != LenhLuuChuyen.TrangThai.NHAP:
        raise ValidationError("Chỉ có thể xóa xe khỏi lệnh đang ở trạng thái bản nháp.")
    kiem_tra_quyen_chi_nhanh(user, order.kho_xuat)
    ChiTietLenhLuuChuyen.objects.filter(lenh=order, xe_id=xe_id).delete()


@transaction.atomic
def gui_lenh_luu_chuyen(user, order_id):
    """Chuyển trạng thái: NHAP -> CHO_DUYET.
    Giữ chỗ xe (GIU_CHO_XUAT), KHÔNG trừ tồn kho nguồn.
    """
    order = LenhLuuChuyen.objects.select_for_update().select_related("kho_xuat", "kho_nhap").get(pk=order_id)
    if order.trang_thai != LenhLuuChuyen.TrangThai.NHAP:
        raise ValidationError("Chỉ có thể gửi lệnh đang ở trạng thái bản nháp.")

    # Cho phép người lập lệnh hoặc nhân viên thuộc chi nhánh kho xuất hoặc admin gửi
    if order.nguoi_lap_id != user.pk:
        kiem_tra_quyen_chi_nhanh(user, order.kho_xuat)

    lines = list(order.chi_tiet.select_related("xe").all())
    if not lines:
        raise ValidationError("Lệnh lưu chuyển chưa có xe nào.")

    for item in lines:
        car = Xe.objects.select_for_update().get(pk=item.xe_id)
        kiem_tra_vin_trong_lenh_mo(car, exclude_order_id=order.pk)

        stock = TonKho.objects.select_for_update().filter(kho=order.kho_xuat, xe=car, so_luong_ton__gt=0).first()
        if not stock:
            raise ValidationError(f"Xe {car.vin} không còn tồn tại kho {order.kho_xuat.ma_kho}.")

        # Giữ chỗ xe để không bị bán hoặc xuất ở nơi khác
        if car.trang_thai == TrangThaiXe.SAN_SANG:
            car.trang_thai = TrangThaiXe.GIU_CHO_XUAT
            car.save(update_fields=["trang_thai"])

    order.trang_thai = LenhLuuChuyen.TrangThai.CHO_DUYET
    order.ngay_gui = timezone.now()
    order.save(update_fields=["trang_thai", "ngay_gui"])

    ghi_thong_bao(
        user,
        f"Gửi lệnh lưu chuyển {order.ma_lenh}",
        f"Đã gửi lệnh lưu chuyển {order.ma_lenh} từ {order.kho_xuat.ma_kho} về {order.kho_nhap.ma_kho}. Chờ Sale Admin phê duyệt.",
        loai="THONG_TIN"
    )
    return order


@transaction.atomic
def duyet_lenh_luu_chuyen(user, order_id):
    """Chuyển trạng thái: CHO_DUYET (hoặc DA_GUI) -> DA_DUYET.
    Chỉ Sale Admin được duyệt. KHÔNG trừ tồn kho nguồn.
    """
    kiem_tra_quyen_sale_admin(user)
    order = LenhLuuChuyen.objects.select_for_update().select_related("kho_xuat", "kho_nhap").get(pk=order_id)
    if order.trang_thai not in (LenhLuuChuyen.TrangThai.CHO_DUYET, LenhLuuChuyen.TrangThai.DA_GUI):
        raise ValidationError("Chỉ có thể phê duyệt lệnh đang ở trạng thái chờ duyệt.")

    lines = list(order.chi_tiet.select_related("xe").all())
    if not lines:
        raise ValidationError("Lệnh lưu chuyển chưa có xe nào.")

    for item in lines:
        car = Xe.objects.select_for_update().get(pk=item.xe_id)
        stock = TonKho.objects.select_for_update().filter(kho=order.kho_xuat, xe=car, so_luong_ton__gt=0).first()
        if not stock:
            raise ValidationError(f"Xe {car.vin} không còn tồn tại kho {order.kho_xuat.ma_kho}.")

    order.trang_thai = LenhLuuChuyen.TrangThai.DA_DUYET
    order.nguoi_duyet = user
    order.ngay_duyet = timezone.now()
    order.save(update_fields=["trang_thai", "nguoi_duyet", "ngay_duyet"])

    ghi_thong_bao(
        user,
        f"Phê duyệt lệnh lưu chuyển {order.ma_lenh}",
        f"Sale Admin đã phê duyệt lệnh lưu chuyển {order.ma_lenh}. Kho nguồn {order.kho_xuat.ma_kho} chuẩn bị xuất xe.",
        loai="THANH_CONG"
    )
    return order


@transaction.atomic
def tu_choi_lenh_luu_chuyen(user, order_id, ly_do=""):
    """Chuyển trạng thái: CHO_DUYET -> TU_CHOI.
    Chỉ Sale Admin được từ chối. Nhả giữ chỗ xe về SẴN SÀNG.
    """
    kiem_tra_quyen_sale_admin(user)
    order = LenhLuuChuyen.objects.select_for_update().select_related("kho_xuat").get(pk=order_id)
    if order.trang_thai not in (LenhLuuChuyen.TrangThai.CHO_DUYET, LenhLuuChuyen.TrangThai.DA_GUI):
        raise ValidationError("Chỉ có thể từ chối lệnh đang ở trạng thái chờ duyệt.")

    # Nhả giữ chỗ xe nếu không bị ràng buộc bởi hợp đồng bán
    for item in order.chi_tiet.select_related("xe").all():
        car = Xe.objects.select_for_update().get(pk=item.xe_id)
        has_active_contract = ChiTietHopDong.objects.filter(
            xe=car,
            hop_dong__trang_thai__in=["CHO_XU_LY", "CHO_PHAN_BO", "CHO_XE_VE_KHO", "DANG_XUAT_KHO"]
        ).exists()
        if not has_active_contract and car.trang_thai == TrangThaiXe.GIU_CHO_XUAT:
            car.trang_thai = TrangThaiXe.SAN_SANG
            car.save(update_fields=["trang_thai"])

    order.trang_thai = LenhLuuChuyen.TrangThai.TU_CHOI
    order.nguoi_duyet = user
    order.ngay_duyet = timezone.now()
    order.ly_do_tu_choi = (ly_do or "").strip()
    order.save(update_fields=["trang_thai", "nguoi_duyet", "ngay_duyet", "ly_do_tu_choi"])

    ghi_thong_bao(
        user,
        f"Từ chối lệnh lưu chuyển {order.ma_lenh}",
        f"Sale Admin đã từ chối lệnh {order.ma_lenh}. Lý do: {order.ly_do_tu_choi or 'Không nêu lý do'}.",
        loai="CANH_BAO"
    )
    return order


@transaction.atomic
def huy_lenh_luu_chuyen(user, order_id, ly_do=""):
    """Hủy lệnh lưu chuyển (trước khi xuất xe).
    Cho phép khi lệnh ở NHAP, CHO_DUYET, DA_GUI, DA_DUYET.
    Nhả giữ chỗ xe về SẴN SÀNG.
    """
    order = LenhLuuChuyen.objects.select_for_update().select_related("kho_xuat").get(pk=order_id)
    allowed_states = (
        LenhLuuChuyen.TrangThai.NHAP,
        LenhLuuChuyen.TrangThai.CHO_DUYET,
        LenhLuuChuyen.TrangThai.DA_GUI,
        LenhLuuChuyen.TrangThai.DA_DUYET,
    )
    if order.trang_thai not in allowed_states:
        raise ValidationError(f"Không thể hủy lệnh đang ở trạng thái {order.get_trang_thai_display()}. Xe đã hoặc đang vận chuyển.")

    # Quyền: người lập, nhân viên kho xuất hoặc Sale Admin
    if order.nguoi_lap_id != user.pk and not is_admin_or_sale_admin(user):
        kiem_tra_quyen_chi_nhanh(user, order.kho_xuat)

    for item in order.chi_tiet.select_related("xe").all():
        car = Xe.objects.select_for_update().get(pk=item.xe_id)
        has_active_contract = ChiTietHopDong.objects.filter(
            xe=car,
            hop_dong__trang_thai__in=["CHO_XU_LY", "CHO_PHAN_BO", "CHO_XE_VE_KHO", "DANG_XUAT_KHO"]
        ).exists()
        if not has_active_contract and car.trang_thai == TrangThaiXe.GIU_CHO_XUAT:
            car.trang_thai = TrangThaiXe.SAN_SANG
            car.save(update_fields=["trang_thai"])

    order.trang_thai = LenhLuuChuyen.TrangThai.HUY
    order.ghi_chu_huy = (ly_do or "").strip()
    order.save(update_fields=["trang_thai", "ghi_chu_huy"])

    ghi_thong_bao(
        user,
        f"Hủy lệnh lưu chuyển {order.ma_lenh}",
        f"Lệnh lưu chuyển {order.ma_lenh} đã bị hủy bởi {user.get_full_name() or user.username}. Lý do: {order.ghi_chu_huy or 'Không nêu lý do'}.",
        loai="CANH_BAO"
    )
    return order


@transaction.atomic
def xac_nhan_xuat_kho_nguon(user, order_id, *, don_vi_van_chuyen_id, bien_so_xe, tai_xe, sdt_tai_xe=None, ngay_du_kien_den=None):
    """Chuyển trạng thái: DA_DUYET -> DANG_VAN_CHUYEN.
    Thủ kho nguồn xác nhận xuất xe:
    - Bắt buộc nhập: ĐVVC, Biển số xe, Tài xế, Ngày dự kiến đến Đà Nẵng.
    - TRỪ TỒN KHO NGUỒN (so_luong_ton = 0, đảm bảo không âm).
    - XE chuyển sang trạng thái DANG_LUU_CHUYEN.
    - TUYỆT ĐỐI KHÔNG CỘNG TỒN TẠI KHO ĐÍCH.
    """
    order = LenhLuuChuyen.objects.select_for_update().select_related("kho_xuat", "kho_nhap").get(pk=order_id)
    if order.trang_thai != LenhLuuChuyen.TrangThai.DA_DUYET:
        raise ValidationError("Lệnh phải ở trạng thái Đã duyệt để kho nguồn xác nhận xuất xe.")

    kiem_tra_quyen_chi_nhanh(user, order.kho_xuat)

    if not don_vi_van_chuyen_id:
        raise ValidationError("Vui lòng chọn đơn vị vận chuyển.")
    dvvc = DonViVanChuyen.objects.filter(pk=don_vi_van_chuyen_id).first()
    if not dvvc:
        raise ValidationError("Đơn vị vận chuyển không tồn tại.")

    bien_so = (bien_so_xe or "").strip()
    if not bien_so:
        raise ValidationError("Vui lòng nhập biển số xe chuyên chở.")

    ten_tai_xe = (tai_xe or "").strip()
    if not ten_tai_xe:
        raise ValidationError("Vui lòng nhập họ tên tài xế phụ trách.")

    if not ngay_du_kien_den:
        raise ValidationError("Vui lòng chọn ngày dự kiến xe đến Đà Nẵng.")

    lines = list(order.chi_tiet.select_related("xe").all())
    if not lines:
        raise ValidationError("Lệnh chưa có xe để xuất.")

    for item in lines:
        car = Xe.objects.select_for_update().get(pk=item.xe_id)
        stock = TonKho.objects.select_for_update().filter(kho=order.kho_xuat, xe=car).first()
        if not stock or stock.so_luong_ton < 1:
            raise ValidationError(f"Xe {car.vin} không còn tồn tại kho xuất {order.kho_xuat.ma_kho}.")

        # 1. TRỪ TỒN KHO NGUỒN (đảm bảo tồn không âm)
        stock.so_luong_ton = max(0, stock.so_luong_ton - 1)
        stock.save(update_fields=["so_luong_ton"])

        # 2. CHUYỂN TRẠNG THÁI XE SANG ĐANG LƯU CHUYỂN
        car.trang_thai = TrangThaiXe.DANG_LUU_CHUYEN
        car.save(update_fields=["trang_thai"])

    # 3. Cập nhật thông tin vận chuyển vào lệnh
    order.don_vi_van_chuyen = dvvc
    order.bien_so_xe = bien_so
    order.tai_xe = ten_tai_xe
    order.sdt_tai_xe = (sdt_tai_xe or "").strip()
    order.ngay_du_kien_den = ngay_du_kien_den
    order.nguoi_xuat = user
    order.ngay_xuat = timezone.now()
    order.trang_thai = LenhLuuChuyen.TrangThai.DANG_VAN_CHUYEN
    order.save(update_fields=[
        "don_vi_van_chuyen",
        "bien_so_xe",
        "tai_xe",
        "sdt_tai_xe",
        "ngay_du_kien_den",
        "nguoi_xuat",
        "ngay_xuat",
        "trang_thai"
    ])

    ghi_thong_bao(
        user,
        f"Xác nhận xuất xe lưu chuyển {order.ma_lenh}",
        f"Kho {order.kho_xuat.ma_kho} đã xuất xe giao cho ĐVVC {dvvc.ten_dvvc} (BS: {bien_so}, TX: {ten_tai_xe}). Dự kiến đến Đà Nẵng: {ngay_du_kien_den}.",
        loai="THONG_TIN"
    )
    return order


@transaction.atomic
def xac_nhan_den_da_nang(user, order_id):
    """Chuyển trạng thái: DANG_VAN_CHUYEN -> DA_GIAO_DEN_DA_NANG.
    Xe đã đến bãi Đà Nẵng:
    - BƯỚC NÀY TUYỆT ĐỐI KHÔNG CỘNG TỒN (KHO01 vẫn chưa có tồn).
    - Trạng thái xe vẫn là DANG_LUU_CHUYEN (chờ tạo Phiếu nhập kho & kiểm tra PDI).
    - Quyền: Chi nhánh Đà Nẵng hoặc Sale Admin.
    """
    order = LenhLuuChuyen.objects.select_for_update().select_related("kho_nhap", "kho_xuat").get(pk=order_id)
    if order.trang_thai != LenhLuuChuyen.TrangThai.DANG_VAN_CHUYEN:
        raise ValidationError("Lệnh không ở trạng thái đang vận chuyển.")

    kiem_tra_quyen_chi_nhanh(user, order.kho_nhap)

    order.trang_thai = LenhLuuChuyen.TrangThai.DA_GIAO_DEN_DA_NANG
    order.nguoi_giao = user
    order.ngay_giao = timezone.now()
    order.save(update_fields=["trang_thai", "nguoi_giao", "ngay_giao"])

    ghi_thong_bao(
        user,
        f"Xe lưu chuyển đã đến Đà Nẵng {order.ma_lenh}",
        f"Lệnh {order.ma_lenh} đã giao đến kho Đà Nẵng ({order.kho_nhap.ma_kho}). Đang chờ Thủ kho lập Phiếu nhập kho và kiểm tra PDI.",
        loai="THANH_CONG"
    )
    return order


# Tương thích ngược với các service cũ
def dispatch_transfer(user, order_id):
    """Hàm wrapper cho luồng cũ: gửi duyệt lệnh."""
    return gui_lenh_luu_chuyen(user, order_id)


def receive_transfer(user, order_id):
    """Hàm wrapper cho luồng cũ: xác nhận xe đến Đà Nẵng (KHÔNG cộng tồn)."""
    return xac_nhan_den_da_nang(user, order_id)
