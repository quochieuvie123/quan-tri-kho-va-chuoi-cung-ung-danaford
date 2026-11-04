"""Module 9 - Dự báo nhu cầu và đề xuất nhập xe.

Không sửa app `database`. Các bảng riêng của module: chỉ tiêu phân bổ của hãng,
phiên dự báo, các dòng đề xuất theo dòng xe, nhật ký xuất file.
"""
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

THOI_HAN_PHIEN_NGAY = 7

HOAN_TAT = "Hoàn tất"
DA_HUY = "Đã hủy"
TU_DONG = "Tự động"
DA_DIEU_CHINH = "Đã điều chỉnh thủ công"


class ChiTieuPhanBo(models.Model):
    """Chỉ tiêu nhập xe Ford Việt Nam phân bổ cho đại lý, theo tháng và dòng xe."""
    nam = models.PositiveSmallIntegerField("Năm")
    thang = models.PositiveSmallIntegerField("Tháng", validators=[MinValueValidator(1), MaxValueValidator(12)])
    ten_xe = models.CharField("Dòng xe (tên đầy đủ như bảng Xe)", max_length=255)
    so_luong = models.PositiveIntegerField("Chỉ tiêu (xe)")

    class Meta:
        verbose_name = verbose_name_plural = "Chỉ tiêu phân bổ của hãng"
        constraints = [models.UniqueConstraint(fields=["nam", "thang", "ten_xe"], name="uniq_chitieu_ky_dongxe")]
        ordering = ["-nam", "-thang", "ten_xe"]

    def __str__(self):
        return f"{self.thang:02d}/{self.nam} - {self.ten_xe}: {self.so_luong}"


class PhienDuBao(models.Model):
    nam = models.PositiveSmallIntegerField("Năm dự báo")
    thang = models.PositiveSmallIntegerField("Tháng dự báo")
    nguoi_tao = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                  on_delete=models.SET_NULL, related_name="+")
    tao_luc = models.DateTimeField(default=timezone.now)
    het_han_luc = models.DateTimeField()
    trang_thai = models.CharField(max_length=20, default=HOAN_TAT)            # Hoàn tất / Đã hủy
    trang_thai_de_xuat = models.CharField(max_length=30, default=TU_DONG)     # Tự động / Đã điều chỉnh thủ công
    canh_bao = models.TextField("Nhật ký cảnh báo", blank=True)
    ly_do_ngoai_le = models.TextField("Lý do ngoại lệ (vượt chỉ tiêu)", blank=True)

    class Meta:
        verbose_name = verbose_name_plural = "Phiên dự báo"
        ordering = ["-tao_luc"]

    def __str__(self):
        return f"Dự báo {self.thang:02d}/{self.nam} ({self.tao_luc:%d/%m/%Y %H:%M})"

    def save(self, *args, **kwargs):
        if not self.het_han_luc:
            self.het_han_luc = self.tao_luc + timedelta(days=THOI_HAN_PHIEN_NGAY)
        super().save(*args, **kwargs)

    @property
    def san_sang(self):
        return self.trang_thai == HOAN_TAT and self.het_han_luc > timezone.now()


class DongDuBao(models.Model):
    phien = models.ForeignKey(PhienDuBao, on_delete=models.CASCADE, related_name="dong")
    ten_xe = models.CharField(max_length=255)
    loai_xe = models.CharField("Phân khúc", max_length=50)
    ma_dong_xe = models.CharField(max_length=60)
    ten_ngan = models.CharField("Tên xe", max_length=100)
    phien_ban = models.CharField("Phiên bản", max_length=150)
    du_bao_sarima = models.FloatField("Dự báo nhu cầu SARIMA")
    phuong_phap = models.CharField(max_length=80, blank=True)
    ky_truoc = models.PositiveIntegerField("Số xe bán tháng trước", default=0)
    ton_kho = models.IntegerField("Tồn kho khả dụng", default=0)
    hop_dong_cho_giao = models.IntegerField(default=0)
    dang_van_chuyen = models.IntegerField(default=0)
    chi_tieu = models.PositiveIntegerField("Chỉ tiêu phân bổ", null=True, blank=True)
    de_xuat_poq = models.PositiveIntegerField("Số lượng đề xuất theo POQ", default=0)
    so_luong_dieu_chinh = models.PositiveIntegerField("Số lượng nhập điều chỉnh", null=True, blank=True)
    ly_do_dieu_chinh = models.CharField(max_length=255, blank=True)
    don_gia_von = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"))
    ghi_chu = models.CharField("Chú thích", max_length=255, blank=True)

    class Meta:
        verbose_name = verbose_name_plural = "Dòng đề xuất nhập xe"
        ordering = ["loai_xe", "ten_xe"]
        constraints = [models.UniqueConstraint(fields=["phien", "ten_xe"], name="uniq_dongdubao_phien_xe")]

    def __str__(self):
        return f"{self.phien_id} - {self.ten_xe}"

    @property
    def so_luong_nhap(self):
        return self.de_xuat_poq if self.so_luong_dieu_chinh is None else self.so_luong_dieu_chinh

    @property
    def thanh_tien(self):
        return self.so_luong_nhap * self.don_gia_von


class NhatKyXuatFile(models.Model):
    phien = models.ForeignKey(PhienDuBao, on_delete=models.CASCADE, related_name="nhat_ky_xuat")
    nguoi_xuat = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                   on_delete=models.SET_NULL, related_name="+")
    thoi_gian = models.DateTimeField(auto_now_add=True)
    dinh_dang = models.CharField(max_length=10)
    ghi_chu = models.TextField(blank=True)

    class Meta:
        verbose_name = verbose_name_plural = "Nhật ký xuất danh sách đề xuất"
        ordering = ["-thoi_gian"]
