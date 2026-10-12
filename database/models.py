from django.core.validators import MinValueValidator, RegexValidator
from django.db import models

# SĐT phải gồm đúng 10 chữ số (len = 10 theo tài liệu thiết kế)
sdt_validator = RegexValidator(r"^\d{10}\Z", "Số điện thoại phải gồm đúng 10 chữ số.")


def tien():
    """DECIMAL(18,2) theo tài liệu thiết kế."""
    return dict(max_digits=18, decimal_places=2)


class NhaCungCap(models.Model):
    ma_ncc = models.CharField(max_length=50, primary_key=True)
    ten_ncc = models.CharField(max_length=255)
    dia_chi_ncc = models.CharField(max_length=255, null=True, blank=True)
    mst = models.CharField(max_length=20, unique=True)

    class Meta:
        verbose_name = verbose_name_plural = "Nhà cung cấp"
    def __str__(self):
        return self.ten_ncc


class DonViVanChuyen(models.Model):
    ma_dvvc = models.CharField(max_length=50, primary_key=True)
    ten_dvvc = models.CharField(max_length=255)
    sdt_dvvc = models.CharField(max_length=10, null=True, blank=True, validators=[sdt_validator])
    dia_chi_dvvc = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        verbose_name = verbose_name_plural = "Đơn vị vận chuyển "
    def __str__(self):
        return self.ten_dvvc


class KhachHang(models.Model):
    ma_kh = models.CharField(max_length=50, primary_key=True)
    ten_kh = models.CharField(max_length=255)
    sdt_kh = models.CharField(max_length=10, validators=[sdt_validator])
    # UNIQUE + NULL: nhiều khách không có MST vẫn hợp lệ (NULL không bị coi là trùng)
    mst_kh = models.CharField(max_length=50, unique=True, null=True, blank=True)

    class Meta:
        verbose_name = verbose_name_plural = "Khách Hàng"
    def __str__(self):
        return self.ten_kh


class ChiNhanh(models.Model):
    ma_cn = models.CharField(max_length=50, primary_key=True)
    ten_cn = models.CharField(max_length=255)
    dia_chi_cn = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        verbose_name = verbose_name_plural = "Chi nhánh"
    def __str__(self):
        return self.ten_cn


class NhanVien(models.Model):
    ma_nv = models.CharField(max_length=50, primary_key=True)
    chi_nhanh = models.ForeignKey(ChiNhanh, on_delete=models.PROTECT, db_column="MaCN")
    ten_nv = models.CharField(max_length=255)
    sdt_nv = models.CharField(max_length=10, null=True, blank=True, validators=[sdt_validator])

    class Meta:
        verbose_name = verbose_name_plural = "Nhân viên"
    def __str__(self):
        return self.ten_nv


class Kho(models.Model):
    ma_kho = models.CharField(max_length=50, primary_key=True)
    # FK + UK = OneToOneField (mỗi chi nhánh 1 kho)
    chi_nhanh = models.OneToOneField(ChiNhanh, on_delete=models.PROTECT, db_column="MaCN")

    class Meta:
        verbose_name = verbose_name_plural = "Kho"
    def __str__(self):
        return self.ma_kho


class Xe(models.Model):
    vin = models.CharField(max_length=50, primary_key=True)
    ten_xe = models.CharField(max_length=255)
    loai_xe = models.CharField(max_length=50)
    so_may = models.CharField(max_length=50, unique=True)
    mau_sac = models.CharField(max_length=50, null=True, blank=True)
    nam_sx = models.IntegerField(null=True, blank=True)
    hop_so = models.CharField(max_length=50, null=True, blank=True)
    nhien_lieu = models.CharField(max_length=50, null=True, blank=True)
    dung_tich = models.IntegerField(null=True, blank=True, validators=[MinValueValidator(1)])

    class Meta:
        verbose_name = verbose_name_plural = "Xe"
    def __str__(self):
        return self.ten_xe


class HoaDonNhap(models.Model):
    ma_hdn = models.CharField(max_length=50, primary_key=True)
    nha_cung_cap = models.ForeignKey(NhaCungCap, on_delete=models.PROTECT, db_column="MaNCC")
    chi_nhanh = models.ForeignKey(ChiNhanh, on_delete=models.PROTECT, db_column="MaCN")
    don_vi_van_chuyen = models.ForeignKey(DonViVanChuyen, on_delete=models.PROTECT, db_column="MaDVVC")
    ngay_nhap = models.DateTimeField()
    so_hoa_don = models.CharField(max_length=50, null=True, blank=True)
    ky_hieu = models.CharField(max_length=50, null=True, blank=True)
    bien_so_xe = models.CharField(max_length=20, null=True, blank=True)
    ten_tai_xe = models.CharField(max_length=100, null=True, blank=True)

    class Meta:
        verbose_name = verbose_name_plural = "Hóa Đơn Nhập Kho"
    def __str__(self):
        return self.ma_hdn


class HoaDonBan(models.Model):
    ma_hdb = models.CharField(max_length=50, primary_key=True)
    khach_hang = models.ForeignKey(KhachHang, on_delete=models.PROTECT, db_column="MaKH")
    chi_nhanh = models.ForeignKey(ChiNhanh, on_delete=models.PROTECT, db_column="MaCN")
    ngay_ban = models.DateTimeField()
    so_hoa_don = models.CharField(max_length=50, null=True, blank=True)
    hinh_thuc_tt = models.CharField(max_length=50, null=True, blank=True)

    class Meta:
        verbose_name = verbose_name_plural = "Hóa Đơn Bán Hàng"
    def __str__(self):
        return self.ma_hdb


# ---- Các bảng có khóa chính kép theo tài liệu ----
# Dùng id tự tăng + UniqueConstraint trên cặp khóa ngoại để vẫn đăng ký được trong Django admin
# (CompositePrimaryKey chưa được admin hỗ trợ). Về dữ liệu, cặp khóa vẫn không thể trùng.

class TonKho(models.Model):
    kho = models.ForeignKey(Kho, on_delete=models.PROTECT, db_column="MaKho")
    xe = models.ForeignKey(Xe, on_delete=models.PROTECT, db_column="MaSP")
    ngay_vao_kho = models.DateField()
    so_luong_ton = models.IntegerField(default=1, validators=[MinValueValidator(0)])

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["kho", "xe"], name="uniq_tonkho_kho_xe"),
            models.CheckConstraint(condition=models.Q(so_luong_ton__gte=0), name="chk_tonkho_so_luong_ton_gte_0"),
        ]
        verbose_name = verbose_name_plural = "Tồn Kho"

    def __str__(self):
        return f"Tồn kho {self.xe} tại {self.kho}"


class ChiTietNhap(models.Model):
    hoa_don_nhap = models.ForeignKey(HoaDonNhap, on_delete=models.CASCADE, db_column="MaHDN")
    xe = models.ForeignKey(Xe, on_delete=models.PROTECT, db_column="MaSP")
    so_luong_nhap = models.IntegerField(default=1, validators=[MinValueValidator(1)])
    don_gia = models.DecimalField(validators=[MinValueValidator(0)], **tien())
    # Tự tính trong save() = so_luong_nhap * don_gia, không cho nhập tay để khỏi lệch số
    thanh_tien = models.DecimalField(editable=False, **tien())

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["hoa_don_nhap", "xe"], name="uniq_chitietnhap_hdn_xe"),
            models.CheckConstraint(condition=models.Q(so_luong_nhap__gte=1), name="chk_chitietnhap_so_luong_gte_1"),
        ]
        verbose_name = verbose_name_plural = "Chi Tiết Nhập Kho"

    def save(self, *args, **kwargs):
        if self.so_luong_nhap is not None and self.don_gia is not None:
            self.thanh_tien = self.so_luong_nhap * self.don_gia
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.hoa_don_nhap_id} - {self.xe_id}"


class ChiTietBan(models.Model):
    hoa_don_ban = models.ForeignKey(HoaDonBan, on_delete=models.CASCADE, db_column="MaHDB")
    xe = models.ForeignKey(Xe, on_delete=models.PROTECT, db_column="MaSP")
    so_luong_ban = models.IntegerField(default=1, validators=[MinValueValidator(1)])
    gia_ban = models.DecimalField(validators=[MinValueValidator(0)], **tien())
    tien_vat = models.DecimalField(validators=[MinValueValidator(0)], **tien())
    tong_thanh_toan = models.DecimalField(validators=[MinValueValidator(0)], **tien())

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["hoa_don_ban", "xe"], name="uniq_chitietban_hdb_xe"),
            models.CheckConstraint(condition=models.Q(so_luong_ban__gte=1), name="chk_chitietban_so_luong_gte_1"),
        ]
        verbose_name = verbose_name_plural = "Chi Tiết Bán Hàng"

    def __str__(self):
        return f"{self.hoa_don_ban_id} - {self.xe_id}"


class BienBanPDI(models.Model):
    ma_pdi = models.CharField(max_length=50, primary_key=True)
    hoa_don_nhap = models.ForeignKey(HoaDonNhap, on_delete=models.PROTECT, db_column="MaHDN")
    xe = models.ForeignKey(Xe, on_delete=models.PROTECT, db_column="MaSP")
    nhan_vien = models.ForeignKey(NhanVien, on_delete=models.PROTECT, db_column="MaNV")
    ngay_ghi_nhan = models.DateTimeField()
    loai_su_co = models.CharField(max_length=100)
    mo_ta_chi_tiet = models.TextField(null=True, blank=True)
    hinh_anh_url = models.URLField(max_length=500, null=True, blank=True)
    trang_thai_claim = models.CharField(max_length=50, default="Chưa xử lý")

    class Meta:
        verbose_name = verbose_name_plural = "Biên Bản PDI"

    def __str__(self):
        return self.ma_pdi


class HopDong(models.Model):
    ma_hd = models.CharField(max_length=50, primary_key=True)
    chi_nhanh = models.ForeignKey(ChiNhanh, on_delete=models.PROTECT, db_column="MaCN")
    khach_hang = models.ForeignKey(KhachHang, on_delete=models.PROTECT, db_column="MaKH")
    xe = models.ForeignKey(Xe, on_delete=models.PROTECT, db_column="MaSP")
    ngay_ky = models.DateTimeField()
    so_tien_coc = models.DecimalField(default=0, validators=[MinValueValidator(0)], **tien())

    class Meta:
        verbose_name = verbose_name_plural = "Hợp Đồng"
    def __str__(self):
        return self.ma_hd


class PhieuXuatKho(models.Model):
    ma_pxk = models.CharField(max_length=50, primary_key=True)
    # FK + UK = OneToOneField (mỗi hợp đồng 1 phiếu xuất)
    hop_dong = models.OneToOneField(HopDong, on_delete=models.PROTECT, db_column="MaHD")
    kho = models.ForeignKey(Kho, on_delete=models.PROTECT, db_column="MaKho")
    ngay_xuat = models.DateTimeField()

    class Meta:
        verbose_name = verbose_name_plural = "Phiếu Xuất Kho"
    def __str__(self):
        return self.ma_pxk


class PhieuKiemKe(models.Model):
    ma_pkk = models.CharField(max_length=50, primary_key=True)
    kho = models.ForeignKey(Kho, on_delete=models.PROTECT, db_column="MaKho")
    nhan_vien = models.ForeignKey(NhanVien, on_delete=models.PROTECT, db_column="MaNV")
    ngay_kiem_ke = models.DateTimeField()
    ghi_chu = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        verbose_name = verbose_name_plural = "Phiếu Kiểm Kê Hàng Hóa"
    def __str__(self):
        return self.ma_pkk


class ChiTietKiemKe(models.Model):
    class TonThucTe(models.IntegerChoices):
        MAT = 0, "Mất"
        CON = 1, "Còn"

    phieu_kiem_ke = models.ForeignKey(PhieuKiemKe, on_delete=models.CASCADE, db_column="MaPKK")
    xe = models.ForeignKey(Xe, on_delete=models.PROTECT, db_column="MaSP")
    ton_he_thong = models.IntegerField(default=1, validators=[MinValueValidator(0)])
    ton_thuc_te = models.IntegerField(choices=TonThucTe.choices, default=TonThucTe.CON)  # 1: còn, 0: mất
    tinh_trang = models.CharField(max_length=100, null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["phieu_kiem_ke", "xe"], name="uniq_chitietkiemke_pkk_xe"),
            models.CheckConstraint(condition=models.Q(ton_thuc_te__in=[0, 1]), name="chk_chitietkiemke_ton_thuc_te_0_1"),
            models.CheckConstraint(condition=models.Q(ton_he_thong__gte=0), name="chk_chitietkiemke_ton_he_thong_gte_0"),
        ]
        verbose_name = verbose_name_plural = "Chi Tiết Kiểm Kê"

    def __str__(self):
        return f"{self.phieu_kiem_ke_id} - {self.xe_id}"
