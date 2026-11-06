from django.db import models
from django.conf import settings
from django.utils import timezone


class SuKienNoiBat(models.Model):
    LOAI_CHOICES = [
        ("thong_bao", "Thông báo nội bộ"),
        ("kiem_ke", "Lịch kiểm kê kho"),
        ("van_chuyen", "Kế hoạch vận chuyển"),
        ("hop_giao_ban", "Họp giao ban"),
        ("khan_cap", "Khẩn cấp / Lưu ý"),
    ]

    tieu_de = models.CharField(max_length=255, verbose_name="Tiêu đề sự kiện")
    noi_dung = models.TextField(verbose_name="Nội dung chi tiết")
    loai_su_kien = models.CharField(
        max_length=50,
        choices=LOAI_CHOICES,
        default="thong_bao",
        verbose_name="Loại sự kiện"
    )
    dia_diem = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name="Địa điểm / Phạm vi"
    )
    thoi_gian_dien_ra = models.DateTimeField(
        default=timezone.now,
        verbose_name="Thời gian diễn ra"
    )
    nguoi_tao = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="su_kien_da_tao",
        verbose_name="Người tạo"
    )
    ngay_tao = models.DateTimeField(auto_now_add=True, verbose_name="Ngày tạo")
    is_active = models.BooleanField(default=True, verbose_name="Đang hiển thị")

    class Meta:
        verbose_name = "Sự kiện nổi bật"
        verbose_name_plural = "Danh sách sự kiện nổi bật"
        ordering = ["-thoi_gian_dien_ra", "-ngay_tao"]

    def __str__(self):
        return self.tieu_de


class ThongBaoHoatDong(models.Model):
    MODULE_CHOICES = [
        ("warehouse", "Quản lý Kho (Xuất/Nhập/Tồn)"),
        ("transfers", "Lưu chuyển xe"),
        ("contracts", "Hợp đồng xe bán"),
        ("orders", "Đặt xe & Phân bổ"),
        ("incidents", "Sự cố vận chuyển"),
        ("analytics", "Dự báo nhu cầu"),
        ("alerts", "Cảnh báo hệ thống"),
        ("reports", "Báo cáo thống kê"),
        ("he_thong", "Hệ thống chung"),
    ]

    LOAI_CHOICES = [
        ("tu_dong", "Tự động ghi nhận"),
        ("thu_cong", "Thông báo tạo thủ công"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="hoat_dong_da_thuc_hien",
        verbose_name="Người thực hiện"
    )
    ten_nhan_vien = models.CharField(max_length=255, verbose_name="Tên nhân viên")
    chuc_vu = models.CharField(max_length=100, blank=True, default="", verbose_name="Chức vụ")
    hanh_dong = models.CharField(max_length=255, verbose_name="Hành động / Cập nhật")
    chi_tiet = models.TextField(blank=True, default="", verbose_name="Chi tiết cập nhật")
    module = models.CharField(
        max_length=50,
        choices=MODULE_CHOICES,
        default="he_thong",
        verbose_name="Phân hệ / Module"
    )
    loai = models.CharField(
        max_length=20,
        choices=LOAI_CHOICES,
        default="tu_dong",
        verbose_name="Loại thông báo"
    )
    thoi_gian = models.DateTimeField(auto_now_add=True, verbose_name="Thời gian")
    da_doc = models.BooleanField(default=False, verbose_name="Đã đọc")
    is_active = models.BooleanField(default=True, verbose_name="Còn hiệu lực")

    class Meta:
        verbose_name = "Thông báo hoạt động"
        verbose_name_plural = "Nhật ký hoạt động & Cập nhật"
        ordering = ["-thoi_gian"]

    def __str__(self):
        return f"[{self.ten_nhan_vien}] {self.hanh_dong}"
