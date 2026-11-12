from django.db import models
from django.conf import settings
from database.models import Kho, Xe, DonViVanChuyen


class LenhLuuChuyen(models.Model):

    class TrangThai(models.TextChoices):
        NHAP = "NHAP", "Bản nháp"
        CHO_DUYET = "CHO_DUYET", "Chờ duyệt"
        DA_GUI = "DA_GUI", "Đã gửi"  # Tương thích ngược (tương đương Chờ duyệt)
        DA_DUYET = "DA_DUYET", "Đã duyệt - Chờ xuất kho"
        DANG_VAN_CHUYEN = "DANG_VAN_CHUYEN", "Đang vận chuyển"
        DA_GIAO_DEN_DA_NANG = "DA_GIAO_DEN_DA_NANG", "Đã giao đến Đà Nẵng - chờ nhập kho"
        HOAN_TAT = "HOAN_TAT", "Hoàn tất"
        DA_XAC_NHAN = "DA_XAC_NHAN", "Đã xác nhận"  # Tương thích ngược
        TU_CHOI = "TU_CHOI", "Từ chối"
        HUY = "HUY", "Đã hủy"

    TRANG_THAI = TrangThai.choices

    ma_lenh = models.CharField(
        max_length=50,
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
        max_length=30,
        choices=TrangThai.choices,
        default=TrangThai.NHAP,
        db_index=True
    )

    ngay_gui = models.DateTimeField(
        null=True,
        blank=True
    )

    # Phê duyệt / Từ chối (Sale Admin)
    nguoi_duyet = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="lenh_luu_chuyen_da_duyet"
    )
    ngay_duyet = models.DateTimeField(null=True, blank=True)
    ly_do_tu_choi = models.TextField(blank=True, null=True)

    # Thông tin vận chuyển (Kho nguồn nhập khi xuất xe)
    don_vi_van_chuyen = models.ForeignKey(
        DonViVanChuyen,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="lenh_luu_chuyen"
    )
    bien_so_xe = models.CharField(max_length=50, blank=True, null=True, help_text="Biển số xe vận chuyển")
    tai_xe = models.CharField(max_length=100, blank=True, null=True, help_text="Họ tên tài xế")
    sdt_tai_xe = models.CharField(max_length=20, blank=True, null=True, help_text="Số điện thoại tài xế")
    ngay_du_kien_den = models.DateField(null=True, blank=True, help_text="Ngày dự kiến đến Đà Nẵng")

    # Người và ngày xuất kho nguồn
    nguoi_xuat = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="lenh_luu_chuyen_da_xuat"
    )
    ngay_xuat = models.DateTimeField(null=True, blank=True)

    # Người và ngày tiếp nhận giao tại Đà Nẵng
    nguoi_giao = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="lenh_luu_chuyen_da_giao"
    )
    ngay_giao = models.DateTimeField(null=True, blank=True)

    # Ghi chú khi hủy lệnh
    ghi_chu_huy = models.TextField(blank=True, null=True)

    # Tương thích ngược với các trường cũ
    ngay_xac_nhan = models.DateTimeField(null=True, blank=True)
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

    @property
    def is_open(self):
        """Lệnh đang mở nếu chưa hoàn tất hoặc chưa hủy/từ chối."""
        return self.trang_thai in [
            self.TrangThai.NHAP,
            self.TrangThai.CHO_DUYET,
            self.TrangThai.DA_GUI,
            self.TrangThai.DA_DUYET,
            self.TrangThai.DANG_VAN_CHUYEN,
            self.TrangThai.DA_GIAO_DEN_DA_NANG,
        ]


class ChiTietLenhLuuChuyen(models.Model):

    lenh = models.ForeignKey(
        LenhLuuChuyen,
        on_delete=models.CASCADE,
        related_name="chi_tiet"
    )

    xe = models.ForeignKey(
        Xe,
        on_delete=models.PROTECT,
        related_name="chi_tiet_luu_chuyen"
    )

    so_luong = models.PositiveIntegerField(default=1)

    class Meta:
        verbose_name = "Chi tiết lệnh lưu chuyển"
        verbose_name_plural = "Chi tiết lệnh lưu chuyển"
        constraints = [
            models.UniqueConstraint(fields=["lenh", "xe"], name="uniq_chitietlenh_lenh_xe"),
        ]

    def __str__(self):
        return f"{self.xe} - SL: {self.so_luong}"
