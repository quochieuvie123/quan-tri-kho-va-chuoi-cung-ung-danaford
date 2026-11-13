"""Bổ sung: phiếu nhập, kết quả PDI và lịch sử nhập.
Các bảng database hiện có giữ nguyên. Mỗi phiếu xử lý một VIN.
"""
from django.conf import settings
from django.db import models
from django.core.exceptions import ValidationError
from .validation import validate_pdi_items


class PhieuNhapKho(models.Model):
    class TrangThai(models.TextChoices):
        NHAP = 'NHAP', 'Nháp'
        CHO_DUYET = 'CHO_DUYET', 'Chờ duyệt'
        DA_DUYET = 'DA_DUYET', 'Đã duyệt'

    class LoaiNguon(models.TextChoices):
        HOA_DON = 'HOA_DON', 'Hóa đơn nhập'
        LUU_CHUYEN = 'LUU_CHUYEN', 'Lệnh lưu chuyển'

    ma_phieu = models.CharField(max_length=50, unique=True)
    loai_nguon = models.CharField(max_length=20, choices=LoaiNguon.choices, default=LoaiNguon.HOA_DON)
    # Nguồn 1: ChiTietNhap (MaHDN, MaSP) từ nhà máy/hóa đơn nhập
    chi_tiet_nhap = models.ForeignKey('database.ChiTietNhap', on_delete=models.PROTECT, null=True, blank=True)
    # Nguồn 2: LenhLuuChuyen đã giao đến Đà Nẵng
    lenh_luu_chuyen = models.ForeignKey('transfers.LenhLuuChuyen', on_delete=models.PROTECT, null=True, blank=True, related_name='phieu_nhap_kho')
    xe = models.ForeignKey('database.Xe', on_delete=models.PROTECT)
    kho = models.ForeignKey('database.Kho', on_delete=models.PROTECT)
    ngay_nhap = models.DateField()
    trang_thai = models.CharField(max_length=12, choices=TrangThai.choices, default=TrangThai.NHAP)
    nguoi_lap = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='phieu_nhap_da_lap')
    ngay_lap = models.DateTimeField(auto_now_add=True)
    nguoi_duyet = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name='phieu_nhap_da_duyet')
    thoi_gian_duyet = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = verbose_name_plural = 'Phiếu nhập kho'
        permissions = [('approve_phieunhapkho', 'Được duyệt phiếu nhập kho')]
        constraints = [
            models.UniqueConstraint(fields=['xe'], condition=models.Q(trang_thai__in=['NHAP', 'CHO_DUYET']), name='warehouse_active_receipt_vin'),
            models.CheckConstraint(condition=models.Q(trang_thai__in=['NHAP', 'CHO_DUYET', 'DA_DUYET']), name='warehouse_receipt_state'),
            models.CheckConstraint(condition=(models.Q(trang_thai='DA_DUYET', nguoi_duyet__isnull=False, thoi_gian_duyet__isnull=False) | models.Q(trang_thai__in=['NHAP', 'CHO_DUYET'], nguoi_duyet__isnull=True, thoi_gian_duyet__isnull=True)), name='warehouse_approval_audit'),
            models.CheckConstraint(
                condition=(
                    (models.Q(loai_nguon='HOA_DON') & models.Q(chi_tiet_nhap__isnull=False) & models.Q(lenh_luu_chuyen__isnull=True)) |
                    (models.Q(loai_nguon='LUU_CHUYEN') & models.Q(chi_tiet_nhap__isnull=True) & models.Q(lenh_luu_chuyen__isnull=False))
                ),
                name='warehouse_receipt_single_source'
            ),
        ]

    def clean(self):
        super().clean()
        if not isinstance(self.ma_phieu, str) or not self.ma_phieu.strip():
            raise ValidationError('Mã phiếu không được rỗng.')
        if self.loai_nguon == self.LoaiNguon.HOA_DON:
            if not self.chi_tiet_nhap or self.lenh_luu_chuyen:
                raise ValidationError('Phiếu nhập từ hóa đơn phải có chi tiết nhập và không có lệnh lưu chuyển.')
            line = self.chi_tiet_nhap
            if line.xe_id != self.xe_id or line.so_luong_nhap != 1:
                raise ValidationError('Chi tiết nhập phải đúng một chiếc và đúng VIN.')
        elif self.loai_nguon == self.LoaiNguon.LUU_CHUYEN:
            if not self.lenh_luu_chuyen or self.chi_tiet_nhap:
                raise ValidationError('Phiếu nhập từ lưu chuyển phải có lệnh lưu chuyển và không có chi tiết nhập.')
            if self.lenh_luu_chuyen_id and not self.lenh_luu_chuyen.chi_tiet.filter(xe_id=self.xe_id).exists():
                raise ValidationError('Xe không thuộc lệnh lưu chuyển này.')
        else:
            raise ValidationError('Nguồn nhập không hợp lệ.')

    @property
    def hoa_don_nhap(self):
        if self.chi_tiet_nhap:
            return self.chi_tiet_nhap.hoa_don_nhap
        return None

    @property
    def ten_nguon_giao(self):
        if self.chi_tiet_nhap:
            return f"Hóa đơn {self.chi_tiet_nhap.hoa_don_nhap_id}"
        if self.lenh_luu_chuyen:
            return f"Lệnh lưu chuyển {self.lenh_luu_chuyen.ma_lenh}"
        return ""

    def __str__(self):
        return self.ma_phieu


class KetQuaPDI(models.Model):
    class KetQua(models.TextChoices):
        DAT = 'DAT', 'Đạt'
        KHONG_DAT = 'KHONG_DAT', 'Không đạt'

    phieu_nhap = models.ForeignKey(PhieuNhapKho, on_delete=models.PROTECT, related_name='cac_lan_pdi')
    hang_muc = models.JSONField(default=list, blank=True, validators=[validate_pdi_items])
    tinh_trang = models.TextField()
    ket_qua = models.CharField(max_length=10, choices=KetQua.choices)
    ghi_chu = models.TextField(blank=True)
    nguoi_kiem_tra = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')
    thoi_gian_kiem_tra = models.DateTimeField(auto_now_add=True)
    nguoi_duyet = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name='+')
    thoi_gian_duyet = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = verbose_name_plural = 'Kết quả PDI'
        permissions = [('approve_ketquapdi', 'Được duyệt kết quả PDI')]
        constraints = [
            models.CheckConstraint(condition=models.Q(ket_qua__in=['DAT', 'KHONG_DAT']), name='warehouse_pdi_result'),
            models.CheckConstraint(condition=(models.Q(nguoi_duyet__isnull=True, thoi_gian_duyet__isnull=True) | models.Q(nguoi_duyet__isnull=False, thoi_gian_duyet__isnull=False)), name='warehouse_pdi_audit'),
        ]

    def clean(self):
        super().clean()
        validate_pdi_items(self.hang_muc)
        if not isinstance(self.tinh_trang, str) or not self.tinh_trang.strip():
            raise ValidationError('Phải ghi tình trạng kiểm tra thực tế.')
        if self.ket_qua == 'DAT' and any(item['ket_qua'] != 'DAT' for item in self.hang_muc):
            raise ValidationError('Không kết luận Đạt khi còn hạng mục Không đạt.')


class LichSuNhapKho(models.Model):
    phieu_nhap = models.OneToOneField(PhieuNhapKho, on_delete=models.PROTECT)
    xe = models.ForeignKey('database.Xe', on_delete=models.PROTECT)
    kho = models.ForeignKey('database.Kho', on_delete=models.PROTECT)
    nguoi_thuc_hien = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    thoi_gian = models.DateTimeField()

    class Meta:
        verbose_name = verbose_name_plural = 'Lịch sử nhập kho'
