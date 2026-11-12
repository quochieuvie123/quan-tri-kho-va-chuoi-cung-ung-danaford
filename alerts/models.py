from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models


class NguongCanhBao(models.Model):
    ten_xe = models.CharField("Dòng xe", max_length=255)
    mau_sac = models.CharField("Màu sắc", max_length=50, blank=True)

    ton_toi_thieu = models.PositiveIntegerField(
        "Tồn tối thiểu",
        validators=[MinValueValidator(1)],
    )

    dang_theo_doi = models.BooleanField(
        "Đang theo dõi",
        default=True,
    )

    class Meta:
        verbose_name = "Ngưỡng cảnh báo"
        verbose_name_plural = "Ngưỡng cảnh báo"

        constraints = [
            models.UniqueConstraint(
                fields=["ten_xe", "mau_sac"],
                name="alerts_nguong_dong_mau_unique",
            ),
            models.CheckConstraint(
                condition=models.Q(ton_toi_thieu__gte=1),
                name="alerts_ton_toi_thieu_gte_1",
            ),
        ]

    def __str__(self):
        return f"{self.ten_xe} ({self.mau_sac or 'Chưa có màu'})"


class CanhBao(models.Model):
    class Loai(models.TextChoices):
        HET_HANG = "HET_HANG", "Hết hàng"
        DUOI_NGUONG = "DUOI_NGUONG", "Tồn dưới ngưỡng"
        TON_LAU = "TON_LAU", "Xe tồn lâu"

    class TrangThai(models.TextChoices):
        CHUA_XU_LY = "CHUA_XU_LY", "Chưa xử lý"
        DANG_XU_LY = "DANG_XU_LY", "Đang xử lý"
        DA_XU_LY = "DA_XU_LY", "Đã xử lý"

    kho = models.ForeignKey(
        "database.Kho",
        on_delete=models.PROTECT,
        verbose_name="Kho của cảnh báo tồn lâu",
        null=True,
        blank=True,
    )

    cac_kho = models.ManyToManyField(
        "database.Kho",
        blank=True,
        related_name="canh_bao_lien_quan",
        verbose_name="Các kho liên quan",
    )

    loai = models.CharField(
        "Loại cảnh báo",
        max_length=20,
        choices=Loai.choices,
    )

    nguong = models.ForeignKey(
        NguongCanhBao,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        verbose_name="Nhóm xe theo dõi",
    )

    xe = models.ForeignKey(
        "database.Xe",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        verbose_name="Xe",
    )

    so_luong_hien_tai = models.PositiveIntegerField(
        "Số lượng hiện tại",
        null=True,
        blank=True,
    )

    so_ngay_ton = models.PositiveIntegerField(
        "Số ngày tồn",
        null=True,
        blank=True,
    )

    con_hieu_luc = models.BooleanField(
        "Còn hiệu lực",
        default=True,
    )

    trang_thai = models.CharField(
        "Trạng thái xử lý",
        max_length=20,
        choices=TrangThai.choices,
        default=TrangThai.CHUA_XU_LY,
    )

    ngay_phat_sinh = models.DateTimeField(
        "Ngày phát sinh",
        auto_now_add=True,
    )

    ngay_cap_nhat = models.DateTimeField(
        "Lần cập nhật gần nhất",
        auto_now=True,
    )

    nguoi_xu_ly = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Người cập nhật trạng thái",
    )

    thoi_diem_xu_ly = models.DateTimeField(
        "Thời điểm cập nhật trạng thái",
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = "Cảnh báo"
        verbose_name_plural = "Cảnh báo"
        ordering = ["-ngay_phat_sinh"]
        constraints = [
            models.UniqueConstraint(
                fields=["nguong"],
                condition=models.Q(
                    con_hieu_luc=True,
                    loai__in=["HET_HANG", "DUOI_NGUONG"],
                ),
                name="alerts_thieu_hang_hien_hanh_unique",
            ),
            models.UniqueConstraint(
                fields=["kho", "xe"],
                condition=models.Q(
                    con_hieu_luc=True,
                    loai="TON_LAU",
                ),
                name="alerts_ton_lau_hien_hanh_unique",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        loai__in=["HET_HANG", "DUOI_NGUONG"],
                        nguong__isnull=False,
                        xe__isnull=True,
                    )
                    | models.Q(
                        loai="TON_LAU",
                        nguong__isnull=True,
                        xe__isnull=False,
                    )
                ),
                name="alerts_doi_tuong_dung_loai",
            ),
        ]
    @property
    def kho_hien_thi(self):
        if self.loai == self.Loai.TON_LAU:
            return str(self.kho)

        if self.so_luong_hien_tai == 0:
            return "Tổng ba kho"

        danh_sach = []

        for kho in self.cac_kho.all():
            danh_sach.append(str(kho.pk))

        return " và ".join(sorted(danh_sach))

    def __str__(self):
        return f"CB{self.pk} ({self.get_loai_display()})"
