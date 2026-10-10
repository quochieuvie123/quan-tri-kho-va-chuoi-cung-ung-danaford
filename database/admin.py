from django.contrib import admin
from .models import (
    NhaCungCap, DonViVanChuyen, KhachHang, ChiNhanh, NhanVien, Kho, Xe,
    HoaDonNhap, HoaDonBan, TonKho, ChiTietNhap, ChiTietBan, BienBanPDI,
    HopDong, PhieuXuatKho, PhieuKiemKe, ChiTietKiemKe,
)

admin.site.register([
    NhaCungCap, DonViVanChuyen, KhachHang, ChiNhanh, NhanVien, Kho, Xe,
    HoaDonNhap, HoaDonBan, TonKho, ChiTietNhap, ChiTietBan, BienBanPDI,
    HopDong, PhieuXuatKho, PhieuKiemKe, ChiTietKiemKe,
])
