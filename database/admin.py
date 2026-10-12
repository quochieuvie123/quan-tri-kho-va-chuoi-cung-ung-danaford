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


admin.site.register([
    NhaCungCap, DonViVanChuyen, KhachHang, ChiNhanh, Kho, Xe,
    HoaDonNhap, HoaDonBan, TonKho, ChiTietNhap, ChiTietBan, BienBanPDI,
    HopDong, PhieuXuatKho, PhieuKiemKe, ChiTietKiemKe,
])