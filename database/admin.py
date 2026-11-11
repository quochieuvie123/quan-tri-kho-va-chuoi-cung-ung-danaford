# database/admin.py
from django.contrib import admin
from .models import (
    NhaCungCap, DonViVanChuyen, KhachHang, ChiNhanh, NhanVien, Kho, Xe,
    HoaDonNhap, HoaDonBan, TonKho, ChiTietNhap, ChiTietBan, BienBanPDI,
    HopDong, ChiTietHopDong, PhieuXuatKho, LichSuXuatKho,
    PhieuKiemKe, ChiTietKiemKe,
)


@admin.register(NhanVien)
class NhanVienAdmin(admin.ModelAdmin):
    list_display = ("ma_nv", "ten_nv", "chi_nhanh", "sdt_nv")
    search_fields = ("ma_nv", "ten_nv")


@admin.register(ChiTietNhap)
class ChiTietNhapAdmin(admin.ModelAdmin):
    list_display = ("hoa_don_nhap", "xe", "so_luong_nhap", "don_gia", "thanh_tien")
    readonly_fields = ("thanh_tien",)


@admin.register(ChiTietBan)
class ChiTietBanAdmin(admin.ModelAdmin):
    list_display = ("hoa_don_ban", "xe", "so_luong_ban", "gia_ban", "tien_vat", "tong_thanh_toan")
    readonly_fields = ("tien_vat", "tong_thanh_toan")


@admin.register(PhieuXuatKho)
class PhieuXuatKhoAdmin(admin.ModelAdmin):
    list_display = ("ma_pxk", "kho", "trang_thai", "ngay_lap", "nguoi_lap", "nguoi_duyet")
    list_filter = ("trang_thai", "kho")
    search_fields = ("ma_pxk", "nguoi_nhan")


@admin.register(LichSuXuatKho)
class LichSuXuatKhoAdmin(admin.ModelAdmin):
    list_display = ("phieu_xuat", "xe", "kho", "hanh_dong", "nguoi_thuc_hien", "thoi_gian")
    list_filter = ("hanh_dong", "kho")
    search_fields = ("phieu_xuat__ma_pxk", "xe__vin")
    readonly_fields = ("thoi_gian",)


@admin.register(PhieuKiemKe)
class PhieuKiemKeAdmin(admin.ModelAdmin):
    list_display = ("ma_pkk", "kho", "ky_kiem_ke", "trang_thai", "nhan_vien", "ngay_kiem_ke")
    list_filter = ("trang_thai", "kho")
    search_fields = ("ma_pkk", "ky_kiem_ke")


@admin.register(ChiTietKiemKe)
class ChiTietKiemKeAdmin(admin.ModelAdmin):
    list_display = ("phieu_kiem_ke", "xe", "phan_loai", "ton_he_thong", "ton_thuc_te")
    list_filter = ("phan_loai",)
    search_fields = ("xe__vin", "phieu_kiem_ke__ma_pkk")


# Các model còn lại đăng ký nhanh (không cần cấu hình thêm)
admin.site.register([
    NhaCungCap, DonViVanChuyen, KhachHang, ChiNhanh, Kho, Xe,
    HoaDonNhap, HoaDonBan, TonKho, BienBanPDI,
    ChiTietHopDong,
])
@admin.register(HopDong)
class HopDongAdmin(admin.ModelAdmin):
    list_display = ('ma_hd', 'khach_hang', 'chi_nhanh', 'trang_thai', 'ngay_du_kien_giao')
