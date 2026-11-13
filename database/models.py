from decimal import ROUND_HALF_UP, Decimal, InvalidOperation, localcontext

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, RegexValidator
from django.db import models


class TrangThaiXe(models.TextChoices):
    SAN_SANG = "SAN_SANG", "Sẵn sàng"
    GIU_CHO_XUAT = "GIU_CHO_XUAT", "Giữ chỗ xuất kho"
    DANG_LUU_CHUYEN = "DANG_LUU_CHUYEN", "Đang lưu chuyển"
    SU_CO_PDI = "SU_CO_PDI", "Sự cố PDI - Khóa xuất"
    DA_XUAT = "DA_XUAT", "Đã xuất kho"

class TrangThaiHopDong(models.TextChoices):
    CHO_XU_LY = "CHO_XU_LY", "Chờ xử lý"
    CHO_PHAN_BO = "CHO_PHAN_BO", "Chờ lịch phân bổ"
    CHO_XE_VE_KHO = "CHO_XE_VE_KHO", "Đã phân bổ - chờ xe về kho"
    DU_DIEU_KIEN_XUAT = "DU_DIEU_KIEN_XUAT", "Đủ điều kiện xuất kho"
    DANG_XUAT_KHO = "DANG_XUAT_KHO", "Đang xuất kho"
    HOAN_TAT = "HOAN_TAT", "Hoàn tất"

class TrangThaiPhieuXuat(models.TextChoices):
    CHO_DUYET = "CHO_DUYET", "Chờ duyệt"
    DA_DUYET = "DA_DUYET", "Đã duyệt"
    DA_HUY = "DA_HUY", "Đã hủy"

class TrangThaiKiemKe(models.TextChoices):
    DANG_KIEM_KE = "DANG_KIEM_KE", "Đang kiểm kê"
    CHO_XU_LY = "CHO_XU_LY", "Chờ xử lý chênh lệch"
    HOAN_TAT = "HOAN_TAT", "Hoàn tất"
    DA_HUY = "DA_HUY", "Đã hủy"

class PhanLoaiKiemKe(models.TextChoices):
    KHOP = "KHOP", "Khớp"
    THIEU = "THIEU", "Thiếu"
    THUA = "THUA", "Thừa"
    SAI_VI_TRI = "SAI_VI_TRI", "Sai vị trí"
    DANG_XU_LY_NGHIEP_VU = "DANG_XU_LY_NGHIEP_VU", "Đang xử lý nghiệp vụ"

# SĐT phải gồm đúng 10 chữ số (len = 10 theo tài liệu thiết kế).
# Dùng [0-9] thay vì \d vì \d trong Python còn khớp cả chữ số Unicode (vd: chữ số Ả Rập).
sdt_validator = RegexValidator(r"^[0-9]{10}\Z", "Số điện thoại phải gồm đúng 10 chữ số.")

# ---- Quy ước tính tiền ----
TIEN_MAX_DIGITS = 18
TIEN_DECIMAL_PLACES = 2
TIEN_MAX = Decimal(10) ** (TIEN_MAX_DIGITS - TIEN_DECIMAL_PLACES) - Decimal("0.01")  # 9999999999999999.99
TIEN_LAM_TRON = Decimal("0.01")
VAT_RATE = Decimal("0.10")  # thuế suất VAT 10%
KIEU_LAM_TRON = ROUND_HALF_UP  # 0.005 -> 0.01 (cách làm tròn thông thường trong kế toán)


def tien():
    """DECIMAL(18,2) theo tài liệu thiết kế."""
    return dict(max_digits=TIEN_MAX_DIGITS, decimal_places=TIEN_DECIMAL_PLACES)


def lam_tron_tien(value):
    """Làm tròn về 2 chữ số thập phân, dùng KIEU_LAM_TRON."""
    return Decimal(value).quantize(TIEN_LAM_TRON, rounding=KIEU_LAM_TRON)


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
    phien_ban = models.CharField(max_length=150, null=True, blank=True, help_text="Phiên bản xe (VD: XLS, Wildtrak...)")
    ten_xe = models.CharField(max_length=255)
    loai_xe = models.CharField(max_length=50)
    so_may = models.CharField(max_length=50, unique=True)
    mau_sac = models.CharField(max_length=50, null=True, blank=True)
    nam_sx = models.IntegerField(null=True, blank=True)
    hop_so = models.CharField(max_length=50, null=True, blank=True)
    nhien_lieu = models.CharField(max_length=50, null=True, blank=True)
    dung_tich = models.IntegerField(null=True, blank=True, validators=[MinValueValidator(1)])

    trang_thai = models.CharField(max_length=30, choices=TrangThaiXe.choices, default=TrangThaiXe.SAN_SANG,
                                  db_index=True)
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
    phieu_xuat_kho = models.OneToOneField("PhieuXuatKho", on_delete=models.SET_NULL, null=True, blank=True)

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
    vi_tri = models.CharField(max_length=50, default="A01", blank=True, help_text="Vị trí đỗ trong bãi")

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
            models.CheckConstraint(condition=models.Q(don_gia__gte=0), name="chk_chitietnhap_don_gia_gte_0"),
            models.CheckConstraint(condition=models.Q(thanh_tien__gte=0), name="chk_chitietnhap_thanh_tien_gte_0"),
        ]
        verbose_name = verbose_name_plural = "Chi Tiết Nhập Kho"

    def tinh_tien(self):
        """thanh_tien = so_luong_nhap * don_gia. Trả về False nếu dữ liệu đầu vào chưa hợp lệ."""
        try:
            with localcontext() as ctx:
                ctx.prec = 50
                self.thanh_tien = lam_tron_tien(self.so_luong_nhap * self.don_gia)
        except (TypeError, InvalidOperation):
            return False
        return True

    def clean_fields(self, exclude=None):
        # Tính trước để thanh_tien (editable=False) luôn có giá trị khi validate
        self.tinh_tien()
        super().clean_fields(exclude=exclude)

    def clean(self):
        super().clean()
        # Admin/ModelForm không validate trường editable=False, nên kiểm tra tràn số ở đây
        if self.thanh_tien is not None and self.thanh_tien > TIEN_MAX:
            raise ValidationError({"don_gia": "Thành tiền vượt giới hạn cho phép (tối đa 18 chữ số, 2 số lẻ)."})

    def save(self, *args, **kwargs):
        # Lưu ý: bulk_create/bulk_update/QuerySet.update() không gọi save(); hiện dự án không dùng.
        self.tinh_tien()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.hoa_don_nhap_id} - {self.xe_id}"


class ChiTietBan(models.Model):
    hoa_don_ban = models.ForeignKey(HoaDonBan, on_delete=models.CASCADE, db_column="MaHDB")
    xe = models.ForeignKey(Xe, on_delete=models.PROTECT, db_column="MaSP")
    so_luong_ban = models.IntegerField(default=1, validators=[MinValueValidator(1)])
    # Đơn giá 1 xe, CHƯA gồm VAT
    gia_ban = models.DecimalField(validators=[MinValueValidator(0)], **tien())
    # Tự tính trong save(), không cho nhập tay:
    #   tien_hang       = so_luong_ban * gia_ban
    #   tien_vat        = tien_hang * 10%  (làm tròn 1 lần, ROUND_HALF_UP)
    #   tong_thanh_toan = tien_hang + tien_vat  (đã gồm VAT)
    tien_vat = models.DecimalField(editable=False, **tien())
    tong_thanh_toan = models.DecimalField(editable=False, **tien())

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["hoa_don_ban", "xe"], name="uniq_chitietban_hdb_xe"),
            models.CheckConstraint(condition=models.Q(so_luong_ban__gte=1), name="chk_chitietban_so_luong_gte_1"),
            models.CheckConstraint(condition=models.Q(gia_ban__gte=0), name="chk_chitietban_gia_ban_gte_0"),
            models.CheckConstraint(condition=models.Q(tien_vat__gte=0), name="chk_chitietban_tien_vat_gte_0"),
            models.CheckConstraint(condition=models.Q(tong_thanh_toan__gte=0), name="chk_chitietban_tong_thanh_toan_gte_0"),
            models.UniqueConstraint(fields=["hoa_don_ban"], name="uniq_chitietban_mot_xe_moi_hoa_don"),
        ]
        verbose_name = verbose_name_plural = "Chi Tiết Bán Hàng"

    @property
    def tien_hang(self):
        """Tiền hàng chưa VAT của dòng = so_luong_ban * gia_ban."""
        return self.so_luong_ban * self.gia_ban

    def tinh_tien(self):
        """Tính tien_vat và tong_thanh_toan. Trả về False nếu dữ liệu đầu vào chưa hợp lệ."""
        try:
            with localcontext() as ctx:
                ctx.prec = 50
                tien_hang = self.tien_hang
                # VAT tính từ tiền hàng gốc, chỉ làm tròn đúng 1 lần
                self.tien_vat = lam_tron_tien(tien_hang * VAT_RATE)
                self.tong_thanh_toan = lam_tron_tien(tien_hang) + self.tien_vat
        except (TypeError, InvalidOperation):
            return False
        return True

    def clean_fields(self, exclude=None):
        self.tinh_tien()
        super().clean_fields(exclude=exclude)

    def clean(self):
        super().clean()
        if self.tong_thanh_toan is not None and self.tong_thanh_toan > TIEN_MAX:
            raise ValidationError({"gia_ban": "Tổng thanh toán vượt giới hạn cho phép (tối đa 18 chữ số, 2 số lẻ)."})

    def save(self, *args, **kwargs):
        # Lưu ý: bulk_create/bulk_update/QuerySet.update() không gọi save(); hiện dự án không dùng.
        self.tinh_tien()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.hoa_don_ban_id} - {self.xe_id}"


class BienBanPDI(models.Model):
    ma_pdi = models.CharField(max_length=50, primary_key=True)
    hoa_don_nhap = models.ForeignKey(HoaDonNhap, on_delete=models.PROTECT, db_column="MaHDN", null=True, blank=True)
    lenh_luu_chuyen = models.ForeignKey(
        'transfers.LenhLuuChuyen', on_delete=models.PROTECT, null=True, blank=True,
        related_name="bien_ban_pdi", db_column="MaLenhLuuChuyen"
    )
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

    @property
    def don_vi_van_chuyen(self):
        if self.hoa_don_nhap and self.hoa_don_nhap.don_vi_van_chuyen:
            return self.hoa_don_nhap.don_vi_van_chuyen.ten_dvvc
        if self.lenh_luu_chuyen and self.lenh_luu_chuyen.don_vi_van_chuyen:
            return self.lenh_luu_chuyen.don_vi_van_chuyen.ten_dvvc
        return ""

    @property
    def don_vi_van_chuyen_obj(self):
        if self.hoa_don_nhap and self.hoa_don_nhap.don_vi_van_chuyen:
            return self.hoa_don_nhap.don_vi_van_chuyen
        if self.lenh_luu_chuyen and self.lenh_luu_chuyen.don_vi_van_chuyen:
            return self.lenh_luu_chuyen.don_vi_van_chuyen
        return None

    @property
    def bien_so_xe(self):
        if self.hoa_don_nhap:
            return self.hoa_don_nhap.bien_so_xe
        if self.lenh_luu_chuyen:
            return self.lenh_luu_chuyen.bien_so_xe
        return ""

    @property
    def chi_nhanh(self):
        if self.hoa_don_nhap and self.hoa_don_nhap.chi_nhanh:
            return self.hoa_don_nhap.chi_nhanh
        if self.lenh_luu_chuyen and self.lenh_luu_chuyen.kho_nhap:
            return self.lenh_luu_chuyen.kho_nhap.chi_nhanh
        return None


class HopDong(models.Model):
    ma_hd = models.CharField(max_length=50, primary_key=True)
    chi_nhanh = models.ForeignKey(ChiNhanh, on_delete=models.CASCADE, db_column="MaCN")
    khach_hang = models.ForeignKey(KhachHang, on_delete=models.CASCADE, db_column="MaKH")
    ngay_ky = models.DateTimeField()
    so_tien_coc = models.DecimalField(default=0, **tien())   # tiền cọc của cả hợp đồng
    trang_thai = models.CharField(max_length=30, choices=TrangThaiHopDong.choices, default=TrangThaiHopDong.CHO_XU_LY,
                                  db_index=True)
    dong_xe_yeu_cau = models.CharField(max_length=255, null=True, blank=True, help_text="Dòng xe yêu cầu")
    phien_ban_yeu_cau = models.CharField(max_length=150, null=True, blank=True, help_text="Phiên bản yêu cầu")
    mau_sac_yeu_cau = models.CharField(max_length=50, null=True, blank=True, help_text="Màu sắc yêu cầu")
    ngay_du_kien_giao = models.DateField(null=True, blank=True, help_text="Ngày dự kiến giao xe")
    class Meta:
        verbose_name = verbose_name_plural = "Hợp đồng"
    # ĐÃ BỎ trường xe


class ChiTietHopDong(models.Model):          # mới: hợp đồng gồm những xe nào
    hop_dong = models.ForeignKey(HopDong, on_delete=models.CASCADE, db_column="MaHD")
    xe = models.ForeignKey(Xe, on_delete=models.CASCADE, db_column="MaSP")

    class Meta:
        verbose_name = verbose_name_plural = "Chi tiết hợp đồng"
        constraints = [
            models.UniqueConstraint(fields=["hop_dong", "xe"], name="uniq_chitiethopdong_hd_xe"),
        ]

class PhieuXuatKho(models.Model):
    ma_pxk = models.CharField(max_length=50, primary_key=True)
    # mỗi dòng chi tiết hợp đồng (1 xe trong 1 hợp đồng) có đúng 1 phiếu xuất
    chi_tiet_hop_dong = models.OneToOneField(ChiTietHopDong, on_delete=models.CASCADE)
    kho = models.ForeignKey(Kho, on_delete=models.CASCADE, db_column="MaKho")
    ngay_lap = models.DateTimeField(auto_now_add=True)
    ngay_xuat = models.DateTimeField(null=True, blank=True)
    nguoi_lap = models.ForeignKey(NhanVien, on_delete=models.PROTECT, null=True, blank=True,
                                  related_name="phieu_xuat_da_lap", db_column="MaNVLap")
    nguoi_duyet = models.ForeignKey(NhanVien, on_delete=models.PROTECT, null=True, blank=True,
                                    related_name="phieu_xuat_da_duyet", db_column="MaNVDuyet")
    ngay_duyet = models.DateTimeField(null=True, blank=True)
    nguoi_nhan = models.CharField(max_length=255, default="", blank=True)
    ghi_chu = models.TextField(null=True, blank=True)
    trang_thai = models.CharField(max_length=30, choices=TrangThaiPhieuXuat.choices,
                                  default=TrangThaiPhieuXuat.CHO_DUYET, db_index=True)

    @property
    def hop_dong(self):
        return self.chi_tiet_hop_dong.hop_dong if hasattr(self,
                                                          'chi_tiet_hop_dong') and self.chi_tiet_hop_dong else None

    @property
    def xe(self):
        return self.chi_tiet_hop_dong.xe if hasattr(self, 'chi_tiet_hop_dong') and self.chi_tiet_hop_dong else None
    class Meta:
        verbose_name = verbose_name_plural = "Phiếu Xuất Kho"
        ordering = ["-ngay_lap"]
    def __str__(self):
        return f"{self.ma_pxk} ({self.get_trang_thai_display()})"


class PhieuKiemKe(models.Model):
    ma_pkk = models.CharField(max_length=50, primary_key=True)
    kho = models.ForeignKey(Kho, on_delete=models.PROTECT, db_column="MaKho")
    nhan_vien = models.ForeignKey(NhanVien, on_delete=models.PROTECT, db_column="MaNV")
    ngay_kiem_ke = models.DateTimeField()
    ky_kiem_ke = models.CharField(max_length=50, help_text="VD: Tháng 10/2026")
    pham_vi = models.CharField(max_length=100, default="Toàn kho")
    ghi_chu = models.TextField(null=True, blank=True)
    trang_thai = models.CharField(
        max_length=30,
        choices=TrangThaiKiemKe.choices,
        default=TrangThaiKiemKe.DANG_KIEM_KE,
        db_index=True
    )
    nguoi_duyet = models.ForeignKey(
        NhanVien, on_delete=models.PROTECT, null=True, blank=True,
        related_name="phieu_kiem_ke_da_duyet"
    )
    ngay_duyet = models.DateTimeField(null=True, blank=True)
    class Meta:
        verbose_name = verbose_name_plural = "Phiếu Kiểm Kê Hàng Hóa"
        ordering = ["-ngay_kiem_ke"]
    def __str__(self):
        return f"{self.ma_pkk} - {self.kho_id} ({self.get_trang_thai_display()})"


class ChiTietKiemKe(models.Model):
    class TonThucTe(models.IntegerChoices):
        MAT = 0, "Mất"
        CON = 1, "Còn"

    phieu_kiem_ke = models.ForeignKey(PhieuKiemKe, on_delete=models.CASCADE, db_column="MaPKK")
    xe = models.ForeignKey(Xe, on_delete=models.PROTECT, db_column="MaSP")
    ton_he_thong = models.IntegerField(default=1, validators=[MinValueValidator(0)])
    ton_thuc_te = models.IntegerField(choices=TonThucTe.choices, default=TonThucTe.CON)  # 1: còn, 0: mất
    vi_tri_he_thong = models.CharField(max_length=50, default="A01", blank=True)
    vi_tri_thuc_te = models.CharField(max_length=50, null=True, blank=True)
    tinh_trang = models.CharField(max_length=100, null=True, blank=True, default="Bình thường")
    phan_loai = models.CharField(
        max_length=30,
        choices=PhanLoaiKiemKe.choices,
        default=PhanLoaiKiemKe.KHOP
    )
    nguyen_nhan = models.TextField(null=True, blank=True)
    phuong_an_xu_ly = models.TextField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["phieu_kiem_ke", "xe"], name="uniq_chitietkiemke_pkk_xe"),
            models.CheckConstraint(condition=models.Q(ton_thuc_te__in=[0, 1]), name="chk_chitietkiemke_ton_thuc_te_0_1"),
            models.CheckConstraint(condition=models.Q(ton_he_thong__gte=0), name="chk_chitietkiemke_ton_he_thong_gte_0"),
        ]
        verbose_name = verbose_name_plural = "Chi Tiết Kiểm Kê"

    def __str__(self):
        return f"{self.phieu_kiem_ke_id} - {self.xe_id} ({self.phan_loai})"


class LichSuXuatKho(models.Model):
    phieu_xuat = models.ForeignKey(PhieuXuatKho, on_delete=models.CASCADE, related_name="lich_su")
    xe = models.ForeignKey(Xe, on_delete=models.PROTECT)
    kho = models.ForeignKey(Kho, on_delete=models.PROTECT)
    thoi_gian = models.DateTimeField(auto_now_add=True)
    hanh_dong = models.CharField(max_length=50) # TAO_PHIEU, DUYET_XUAT, HUY_PHIEU
    nguoi_thuc_hien = models.ForeignKey(NhanVien, on_delete=models.PROTECT)
    ghi_chu = models.TextField(null=True, blank=True)

    class Meta:
        verbose_name = verbose_name_plural = "Lịch sử xuất kho"
        ordering = ["-thoi_gian"]
