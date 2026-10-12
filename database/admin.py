from django.contrib import admin
from .models import (
    NhaCungCap, DonViVanChuyen, KhachHang, ChiNhanh, NhanVien, Kho, Xe,
    HoaDonNhap, HoaDonBan, TonKho, ChiTietNhap, ChiTietBan, BienBanPDI,
    HopDong, PhieuXuatKho, PhieuKiemKe, ChiTietKiemKe,
)


@admin.register(NhanVien)
class NhanVienAdmin(admin.ModelAdmin):
    list_display = ("ma_nv", "ten_nv", "chi_nhanh", "sdt_nv")
    search_fields = ("ma_nv", "ten_nv")


@admin.register(ChiTietNhap)
class ChiTietNhapAdmin(admin.ModelAdmin):
    list_display = ("hoa_don_nhap", "xe", "so_luong_nhap", "don_gia", "thanh_tien")
    readonly_fields = ("thanh_tien",)  # tự tính khi lưu


admin.site.register([
    NhaCungCap, DonViVanChuyen, KhachHang, ChiNhanh, Kho, Xe,
    HoaDonNhap, HoaDonBan, TonKho, ChiTietBan, BienBanPDI,
    HopDong, PhieuXuatKho, PhieuKiemKe, ChiTietKiemKe,
])
