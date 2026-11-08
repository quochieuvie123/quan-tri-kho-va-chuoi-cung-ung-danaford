from django.db import models
from django.conf import settings
from database.models import Kho, Xe


class LenhLuuChuyen(models.Model):

    TRANG_THAI = [
        ("NHAP", "Bản nháp"),
        ("DA_GUI", "Đã gửi"),
        ("DA_XAC_NHAN", "Đã xác nhận"),
    ]

    ma_lenh = models.CharField(
        max_length=30,
        unique=True,
        blank=True,
        null=True
    )

    kho_xuat = models.ForeignKey(
        Kho,
        on_delete=models.PROTECT,
        related_name="lenh_xuat"
    )

    kho_nhap = models.ForeignKey(
        Kho,
        on_delete=models.PROTECT,
        related_name="lenh_nhap"
    )

    nguoi_lap = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="lenh_luu_chuyen_da_lap"
    )

    ngay_lap = models.DateTimeField(auto_now_add=True)

    trang_thai = models.CharField(
        max_length=20,
        choices=TRANG_THAI,
        default="NHAP"
    )

    ngay_gui = models.DateTimeField(
        null=True,
        blank=True
    )

    ngay_xac_nhan = models.DateTimeField(
        null=True,
        blank=True
    )

    nguoi_xac_nhan = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="lenh_luu_chuyen_da_xac_nhan"
    )

    class Meta:
        verbose_name = "Lệnh lưu chuyển"
        verbose_name_plural = "Lệnh lưu chuyển"
        ordering = ["-ngay_lap"]

    def __str__(self):
        return self.ma_lenh or f"Lệnh lưu chuyển #{self.pk}"


class ChiTietLenhLuuChuyen(models.Model):

    lenh = models.ForeignKey(
        LenhLuuChuyen,
        on_delete=models.CASCADE,
        related_name="chi_tiet"
    )

    xe = models.ForeignKey(
        Xe,
        on_delete=models.PROTECT
    )

    so_luong = models.PositiveIntegerField(default=1)

    class Meta:
        verbose_name = "Chi tiết lệnh lưu chuyển"
        verbose_name_plural = "Chi tiết lệnh lưu chuyển"

    def __str__(self):
        return f"{self.xe} - SL: {self.so_luong}"
