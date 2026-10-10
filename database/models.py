from django.core.validators import MinValueValidator, RegexValidator
from django.db import models

# SĐT phải gồm đúng 10 chữ số (len = 10 theo tài liệu thiết kế)
sdt_validator = RegexValidator(r"^\d{10}$", "Số điện thoại phải gồm đúng 10 chữ số.")


def tien():
    """DECIMAL(18,2) theo tài liệu thiết kế."""
    return dict(max_digits=18, decimal_places=2)


class NhaCungCap(models.Model):
    ma_ncc = models.CharField(max_length=50, primary_key=True)
    ten_ncc = models.CharField(max_length=255)
    dia_chi_ncc = models.CharField(max_length=255, null=True, blank=True)
    mst = models.CharField(max_length=20, unique=True)

    def __str__(self):
        return self.ten_ncc


class DonViVanChuyen(models.Model):
    ma_dvvc = models.CharField(max_length=50, primary_key=True)
    ten_dvvc = models.CharField(max_length=255)
    sdt_dvvc = models.CharField(max_length=20, null=True, blank=True, validators=[sdt_validator])
    dia_chi_dvvc = models.CharField(max_length=255, null=True, blank=True)

    def __str__(self):
        return self.ten_dvvc


class KhachHang(models.Model):
    ma_kh = models.CharField(max_length=50, primary_key=True)
    ten_kh = models.CharField(max_length=255)
    sdt_kh = models.CharField(max_length=20, validators=[sdt_validator])
    # UNIQUE + NULL: nhiều khách không có MST vẫn hợp lệ (NULL không bị coi là trùng)
    mst_kh = models.CharField(max_length=50, unique=True, null=True, blank=True)

    def __str__(self):
        return self.ten_kh


class ChiNhanh(models.Model):
    ma_cn = models.CharField(max_length=50, primary_key=True)
    ten_cn = models.CharField(max_length=255)
    dia_chi_cn = models.CharField(max_length=255, null=True, blank=True)

    def __str__(self):
        return self.ten_cn


class NhanVien(models.Model):
    ma_nv = models.CharField(max_length=50, primary_key=True)
    chi_nhanh = models.ForeignKey(ChiNhanh, on_delete=models.CASCADE, db_column="MaCN")
    ten_nv = models.CharField(max_length=255)
    # Tên đăng nhập mới là trường UNIQUE (tài liệu gốc đặt UNIQUE nhầm cho mật khẩu)
    dn_nv = models.CharField(max_length=50, unique=True)
    # Lưu mật khẩu ĐÃ BĂM (dùng make_password), không lưu mật khẩu thô.
    # Chuỗi băm dài hơn 50 ký tự nên để 128.
    mn_nv = models.CharField(max_length=128)
    sdt_nv = models.CharField(max_length=20, null=True, blank=True, validators=[sdt_validator])
    vai_tro = models.CharField(max_length=100)

    def __str__(self):
        return self.ten_nv


class Kho(models.Model):
    ma_kho = models.CharField(max_length=50, primary_key=True)
    # FK + UK = OneToOneField (mỗi chi nhánh 1 kho)
    chi_nhanh = models.OneToOneField(ChiNhanh, on_delete=models.CASCADE, db_column="MaCN")

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

    def __str__(self):
        return self.ten_xe


class HoaDonNhap(models.Model):
    ma_hdn = models.CharField(max_length=50, primary_key=True)
    nha_cung_cap = models.ForeignKey(NhaCungCap, on_delete=models.CASCADE, db_column="MaNCC")
    chi_nhanh = models.ForeignKey(ChiNhanh, on_delete=models.CASCADE, db_column="MaCN")
    don_vi_van_chuyen = models.ForeignKey(DonViVanChuyen, on_delete=models.CASCADE, db_column="MaDVVC")
    ngay_nhap = models.DateTimeField()
    so_hoa_don = models.CharField(max_length=50, null=True, blank=True)
    ky_hieu = models.CharField(max_length=50, null=True, blank=True)
    bien_so_xe = models.CharField(max_length=20, null=True, blank=True)
    ten_tai_xe = models.CharField(max_length=100, null=True, blank=True)

    def __str__(self):
        return self.ma_hdn


class HoaDonBan(models.Model):
    ma_hdb = models.CharField(max_length=50, primary_key=True)
    khach_hang = models.ForeignKey(KhachHang, on_delete=models.CASCADE, db_column="MaKH")
    chi_nhanh = models.ForeignKey(ChiNhanh, on_delete=models.CASCADE, db_column="MaCN")
    ngay_ban = models.DateTimeField()
    so_hoa_don = models.CharField(max_length=50, null=True, blank=True)
    hinh_thuc_tt = models.CharField(max_length=50, null=True, blank=True)

    def __str__(self):
        return self.ma_hdb


# ---- Các bảng có khóa chính kép theo tài liệu ----
# Dùng id tự tăng + UniqueConstraint trên cặp khóa ngoại để vẫn đăng ký được trong Django admin
# (CompositePrimaryKey chưa được admin hỗ trợ). Về dữ liệu, cặp khóa vẫn không thể trùng.

class TonKho(models.Model):
    kho = models.ForeignKey(Kho, on_delete=models.CASCADE, db_column="MaKho")
    xe = models.ForeignKey(Xe, on_delete=models.CASCADE, db_column="MaSP")
    ngay_vao_kho = models.DateField()
    so_luong_ton = models.IntegerField(default=1)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["kho", "xe"], name="uniq_tonkho_kho_xe"),
        ]

    def __str__(self):
        return f"Tồn kho {self.xe} tại {self.kho}"


class ChiTietNhap(models.Model):
    hoa_don_nhap = models.ForeignKey(HoaDonNhap, on_delete=models.CASCADE, db_column="MaHDN")
    xe = models.ForeignKey(Xe, on_delete=models.CASCADE, db_column="MaSP")
    so_luong_nhap = models.IntegerField(default=1)
    don_gia = models.DecimalField(**tien())
    thanh_tien = models.DecimalField(**tien())

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["hoa_don_nhap", "xe"], name="uniq_chitietnhap_hdn_xe"),
        ]


class ChiTietBan(models.Model):
    hoa_don_ban = models.ForeignKey(HoaDonBan, on_delete=models.CASCADE, db_column="MaHDB")
    xe = models.ForeignKey(Xe, on_delete=models.CASCADE, db_column="MaSP")
    so_luong_ban = models.IntegerField(default=1)
    gia_ban = models.DecimalField(**tien())
    tien_vat = models.DecimalField(**tien())
    tong_thanh_toan = models.DecimalField(**tien())

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["hoa_don_ban", "xe"], name="uniq_chitietban_hdb_xe"),
        ]


class BienBanPDI(models.Model):
    ma_pdi = models.CharField(max_length=50, primary_key=True)
    hoa_don_nhap = models.ForeignKey(HoaDonNhap, on_delete=models.CASCADE, db_column="MaHDN")
    xe = models.ForeignKey(Xe, on_delete=models.CASCADE, db_column="MaSP")
    nhan_vien = models.ForeignKey(NhanVien, on_delete=models.CASCADE, db_column="MaNV")
    ngay_ghi_nhan = models.DateTimeField()
    loai_su_co = models.CharField(max_length=100)
    mo_ta_chi_tiet = models.TextField(null=True, blank=True)
    hinh_anh_url = models.URLField(max_length=500, null=True, blank=True)
    trang_thai_claim = models.CharField(max_length=50, default="Chưa xử lý")

    def __str__(self):
        return self.ma_pdi


class HopDong(models.Model):
    ma_hd = models.CharField(max_length=50, primary_key=True)
    chi_nhanh = models.ForeignKey(ChiNhanh, on_delete=models.CASCADE, db_column="MaCN")
    khach_hang = models.ForeignKey(KhachHang, on_delete=models.CASCADE, db_column="MaKH")
    xe = models.ForeignKey(Xe, on_delete=models.CASCADE, db_column="MaSP")
    ngay_ky = models.DateTimeField()
    so_tien_coc = models.DecimalField(default=0, **tien())

    def __str__(self):
        return self.ma_hd


class PhieuXuatKho(models.Model):
    ma_pxk = models.CharField(max_length=50, primary_key=True)
    # FK + UK = OneToOneField (mỗi hợp đồng 1 phiếu xuất)
    hop_dong = models.OneToOneField(HopDong, on_delete=models.CASCADE, db_column="MaHD")
    kho = models.ForeignKey(Kho, on_delete=models.CASCADE, db_column="MaKho")
    ngay_xuat = models.DateTimeField()

    def __str__(self):
        return self.ma_pxk


class PhieuKiemKe(models.Model):
    ma_pkk = models.CharField(max_length=50, primary_key=True)
    kho = models.ForeignKey(Kho, on_delete=models.CASCADE, db_column="MaKho")
    nhan_vien = models.ForeignKey(NhanVien, on_delete=models.CASCADE, db_column="MaNV")
    ngay_kiem_ke = models.DateTimeField()
    ghi_chu = models.CharField(max_length=255, null=True, blank=True)

    def __str__(self):
        return self.ma_pkk


class ChiTietKiemKe(models.Model):
    phieu_kiem_ke = models.ForeignKey(PhieuKiemKe, on_delete=models.CASCADE, db_column="MaPKK")
    xe = models.ForeignKey(Xe, on_delete=models.CASCADE, db_column="MaSP")
    ton_he_thong = models.IntegerField(default=1)
    ton_thuc_te = models.IntegerField(default=1)  # 1: còn, 0: mất
    tinh_trang = models.CharField(max_length=100, null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["phieu_kiem_ke", "xe"], name="uniq_chitietkiemke_pkk_xe"),
        ]
