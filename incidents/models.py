"""Module 10 - Quản lý sự cố vận chuyển.

Nguyên tắc: KHÔNG sửa app `database`. Biên bản sự cố vẫn lưu ở `database.BienBanPDI`
(trạng thái nằm ở trường `trang_thai_claim`). Các dữ liệu mà BienBanPDI chưa có
(nhiều ảnh, email ĐVVC, kết quả bồi thường, lịch sử phản hồi) lưu ở các bảng dưới đây.
"""
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.storage import FileSystemStorage
from django.core.validators import FileExtensionValidator, MinValueValidator
from django.db import models

from database.models import BienBanPDI, DonViVanChuyen, tien

# File tải lên được lưu trong incidents/uploads/ (đã có .gitignore, không đẩy lên GitHub)
UPLOAD_DIR = Path(__file__).resolve().parent / "uploads"


def kho_luu_tru():
    """Callable để migration không lưu đường dẫn tuyệt đối của từng máy."""
    return FileSystemStorage(location=str(UPLOAD_DIR))

# Giá trị lưu ở BienBanPDI.trang_thai_claim
CHUA_XU_LY = "Chưa xử lý"          # mới ghi nhận
DA_GUI_YEU_CAU = "Đã gửi yêu cầu"
DA_XU_LY = "Đã xử lý"              # = Đã đóng
# Dữ liệu mẫu cũ còn có "Đang xử lý" -> coi như đang xử lý.

LOAI_SU_CO = ["Giao sai VIN", "Trầy xước sơn", "Móp méo thân vỏ", "Hư hỏng linh kiện"]

PHAM_VI_LOI_ANH = ["jpg", "jpeg", "png", "webp"]
PHAM_VI_TAI_LIEU = ["pdf", "jpg", "jpeg", "png", "doc", "docx"]


def dang_xu_ly(trang_thai):
    return trang_thai != DA_XU_LY


def nhan_trang_thai(trang_thai):
    """Nhãn hiển thị: Đang xử lý / Đã đóng."""
    return "Đã đóng" if trang_thai == DA_XU_LY else "Đang xử lý"


class DvvcLienHe(models.Model):
    """Email liên hệ của ĐVVC (bảng DonViVanChuyen chưa có cột email)."""
    dvvc = models.OneToOneField(DonViVanChuyen, on_delete=models.CASCADE, related_name="lien_he")
    email = models.EmailField("Email liên hệ")

    class Meta:
        verbose_name = verbose_name_plural = "Email liên hệ ĐVVC"

    def __str__(self):
        return f"{self.dvvc_id} - {self.email}"


class HoSoSuCo(models.Model):
    """Thông tin mở rộng của một biên bản PDI có sự cố (tạo khi cần)."""
    HINH_THUC = [
        ("TIEN", "ĐVVC bồi thường tiền"),
        ("SUA", "ĐVVC tự sửa chữa"),
        ("GIAM_TRU", "Giảm trừ công nợ"),
    ]
    bien_ban = models.OneToOneField(BienBanPDI, on_delete=models.CASCADE, related_name="ho_so")
    han_phan_hoi = models.DateField("Hạn phản hồi", null=True, blank=True)
    hinh_thuc_khac_phuc = models.CharField(max_length=10, choices=HINH_THUC, blank=True)
    so_tien_boi_thuong = models.DecimalField(
        "Số tiền bồi thường", null=True, blank=True, validators=[MinValueValidator(0)], **tien())
    ngay_xac_nhan = models.DateField("Ngày xác nhận", null=True, blank=True)
    bien_ban_thoa_thuan = models.FileField(
        "Biên bản thỏa thuận", storage=kho_luu_tru, upload_to="thoa_thuan/", null=True, blank=True,
        validators=[FileExtensionValidator(PHAM_VI_TAI_LIEU)])

    class Meta:
        verbose_name = verbose_name_plural = "Hồ sơ xử lý sự cố"

    def __str__(self):
        return self.bien_ban_id

    def clean(self):
        if self.so_tien_boi_thuong is not None and self.so_tien_boi_thuong < 0:
            raise ValidationError("Số tiền bồi thường không được âm.")


class AnhSuCo(models.Model):
    bien_ban = models.ForeignKey(BienBanPDI, on_delete=models.CASCADE, related_name="anh_su_co")
    tep = models.FileField(storage=kho_luu_tru, upload_to="anh/",
                           validators=[FileExtensionValidator(PHAM_VI_LOI_ANH)])
    ngay_tai_len = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = verbose_name_plural = "Ảnh sự cố"
        ordering = ["id"]

    def __str__(self):
        return f"{self.bien_ban_id} - {Path(self.tep.name).name}"


class LichSuPhanHoi(models.Model):
    """Nhật ký: ghi nhận, gửi yêu cầu cho ĐVVC, cập nhật kết quả."""
    bien_ban = models.ForeignKey(BienBanPDI, on_delete=models.CASCADE, related_name="lich_su")
    thoi_gian = models.DateTimeField(auto_now_add=True)
    nguoi_thuc_hien = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    hanh_dong = models.CharField(max_length=100)
    noi_dung = models.TextField(blank=True)

    class Meta:
        verbose_name = verbose_name_plural = "Lịch sử phản hồi"
        ordering = ["-thoi_gian", "-id"]

    def __str__(self):
        return f"{self.bien_ban_id} - {self.hanh_dong}"
