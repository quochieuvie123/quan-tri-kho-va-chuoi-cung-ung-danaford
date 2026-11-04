"""
Script tạo và chuẩn hóa dữ liệu mẫu đồng bộ 100% cho toàn bộ 9 module của hệ thống Dana Ford.
Chạy: python database/fixtures/tao_du_lieu_dong_nhat.py
"""
import os
import sys
import django
from datetime import date, timedelta
from decimal import Decimal

sys.stdout.reconfigure(encoding="utf-8")

# Setup Django environment
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.db import transaction
from django.utils import timezone

from database.models import (
    ChiNhanh, Kho, NhanVien, NhaCungCap, DonViVanChuyen, KhachHang,
    Xe, HoaDonNhap, ChiTietNhap, TonKho, HopDong, ChiTietHopDong,
    PhieuXuatKho, LichSuXuatKho, HoaDonBan, ChiTietBan,
    PhieuKiemKe, ChiTietKiemKe, BienBanPDI,
    TrangThaiXe, TrangThaiHopDong, TrangThaiPhieuXuat
)
from alerts.models import NguongCanhBao, CanhBao
from alerts.utils import cap_nhat_tat_ca_canh_bao
from orders.models import Allocation, VehicleRequest, VehicleRequestItem
from analytics.models import PhienDuBao, DongDuBao
from incidents.models import DvvcLienHe, HoSoSuCo, LichSuPhanHoi

User = get_user_model()

@transaction.atomic
def dong_bo_tat_ca():
    print("=== 1. TẠO TÀI KHOẢN VÀ PHÂN QUYỀN ===")
    # 1. Nhóm quyền
    BUSINESS_APPS = ["database", "alerts", "analytics", "incidents", "orders", "warehouse"]
    perms = Permission.objects.filter(content_type__app_label__in=BUSINESS_APPS)
    
    quan_ly, _ = Group.objects.get_or_create(name="Quản lý")
    quan_ly.permissions.set(perms)
    
    nhan_vien_group, _ = Group.objects.get_or_create(name="Nhân viên")
    nhan_vien_group.permissions.set(perms.exclude(codename__startswith="delete_"))
    
    # 2. Tài khoản người dùng
    admin_user, _ = User.objects.get_or_create(username="admin", defaults={
        "first_name": "Quản trị", "last_name": "Viên", "is_staff": True, "is_superuser": True
    })
    admin_user.set_password("123")
    admin_user.save()
    
    quanly_user, _ = User.objects.get_or_create(username="quanly", defaults={
        "first_name": "Nguyễn Văn", "last_name": "Hải", "is_staff": True
    })
    quanly_user.set_password("123")
    quanly_user.nhan_vien_id = "NV01"
    quanly_user.groups.set([quan_ly])
    quanly_user.save()
    
    nhanvien_user, _ = User.objects.get_or_create(username="nhanvien", defaults={
        "first_name": "Trần Thị", "last_name": "Minh Thư", "is_staff": False
    })
    nhanvien_user.set_password("123")
    nhanvien_user.nhan_vien_id = "NV02"
    nhanvien_user.groups.set([nhan_vien_group])
    nhanvien_user.save()
    print(" -> Đã tạo 3 tài khoản: admin / quanly / nhanvien (mật khẩu đều là '123')")

    print("\n=== 2. ĐỒNG BỘ TRẠNG THÁI HỢP ĐỒNG & XUẤT KHO ===")
    # Các hợp đồng đã xuất kho hoàn tất
    da_xuat = ["HD01", "HD03", "HD04", "HD05", "HD06", "HD07", "HD08", "HD09", "HD10", "HD15", "HD16"]
    HopDong.objects.filter(ma_hd__in=da_xuat).update(trang_thai=TrangThaiHopDong.HOAN_TAT)
    
    # 4 Hợp đồng tháng 10/2026:
    # HD11: Đủ điều kiện xuất kho (Đà Nẵng)
    HopDong.objects.filter(ma_hd="HD11").update(trang_thai=TrangThaiHopDong.DU_DIEU_KIEN_XUAT)
    # HD12: Chờ xử lý (Bình Định)
    HopDong.objects.filter(ma_hd="HD12").update(trang_thai=TrangThaiHopDong.CHO_XU_LY)
    # HD13: Chờ xử lý (Gia Lai)
    HopDong.objects.filter(ma_hd="HD13").update(trang_thai=TrangThaiHopDong.CHO_XU_LY)
    # HD14: Đang xuất kho (Gia Lai) - tạo 1 phiếu xuất kho đang Chờ duyệt
    HopDong.objects.filter(ma_hd="HD14").update(trang_thai=TrangThaiHopDong.DANG_XUAT_KHO)
    
    # Tạo phiếu xuất kho chờ duyệt cho HD14 nếu chưa có
    cthd14 = ChiTietHopDong.objects.filter(hop_dong_id="HD14").first()
    if cthd14 and not PhieuXuatKho.objects.filter(chi_tiet_hop_dong=cthd14).exists():
        pxk14 = PhieuXuatKho.objects.create(
            ma_pxk="PXK14",
            chi_tiet_hop_dong=cthd14,
            kho_id="KHO03",
            nguoi_lap_id="NV08",
            nguoi_nhan="Nguyễn Văn Đại",
            ghi_chu="Phiếu xuất kho chờ duyệt giao xe theo HĐ14",
            trang_thai=TrangThaiPhieuXuat.CHO_DUYET
        )
        # Giữ chỗ xe
        Xe.objects.filter(vin=cthd14.xe_id).update(trang_thai=TrangThaiXe.GIU_CHO_XUAT)
        LichSuXuatKho.objects.create(
            phieu_xuat=pxk14,
            xe=cthd14.xe,
            kho_id="KHO03",
            hanh_dong="TAO_PHIEU_CHO_DUYET",
            nguoi_thuc_hien_id="NV08",
            ghi_chu="Lập phiếu xuất cho HĐ HD14, giữ chỗ xe VIN " + cthd14.xe_id
        )
        print(" -> Đã tạo phiếu xuất kho PXK14 ở trạng thái CHO_DUYET cho HD14")

    print("\n=== 3. TẠO DỮ LIỆU ĐẶT XE (ORDERS) ===")
    Allocation.objects.all().delete()
    allocations_data = [
        ("FVL-AL2610-01", "RANGER-WILDTRAK", "Ford Ranger Wildtrak 2.0L Bi-Turbo 4x4 AT", "RL2FMA001TZ000051", "OR1", "Cam Luxe", "YN2S-0051", date(2026, 11, 15), date(2026, 11, 25), date(2026, 11, 1), 2),
        ("FVL-AL2610-02", "EVEREST-TITANIUM+", "Ford Everest Titanium+ 2.0L Bi-Turbo 4x4 AT", "RL2FMA001TZ000052", "WH1", "Trắng Tuyết", "YN2S-0052", date(2026, 11, 20), date(2026, 11, 30), date(2026, 11, 1), 3),
        ("FVL-AL2610-03", "TERRITORY-TITANIUM-X", "Ford Territory Titanium X 1.5L EcoBoost", "RL2FMA001TZ000053", "BK1", "Đen Ánh Kim", "YN2S-0053", date(2026, 11, 10), date(2026, 11, 18), date(2026, 11, 1), 4),
        ("FVL-AL2610-04", "EXPLORER-LIMITED", "Ford Explorer Limited 2.3L EcoBoost", "RL2FMA001TZ000054", "BL1", "Xanh Dương", "YN2S-0054", date(2026, 12, 5), date(2026, 12, 15), date(2026, 12, 1), 1),
        ("FVL-AL2610-05", "TRANSIT-16", "Ford Transit Trend 16 chỗ 2.3L", "RL2FMA001TZ000055", "SL1", "Bạc Ánh Kim", "YN2S-0055", date(2026, 11, 25), date(2026, 12, 5), date(2026, 11, 1), 2),
        ("FVL-AL2610-06", "RANGER-SPORT", "Ford Ranger Sport 2.0L 4x4 AT", "RL2FMA001TZ000056", "RD1", "Đỏ Cam", "YN2S-0056", date(2026, 12, 10), date(2026, 12, 20), date(2026, 12, 1), 3),
        ("FVL-AL2610-07", "EVEREST-SPORT", "Ford Everest Sport 2.0L 4x2 AT", "RL2FMA001TZ000057", "GR1", "Xám Meteor", "YN2S-0057", date(2026, 12, 15), date(2026, 12, 25), date(2026, 12, 1), 2),
        ("FVL-AL2610-08", "TERRITORY-TREND", "Ford Territory Trend 1.5L EcoBoost", "RL2FMA001TZ000058", "WH1", "Trắng Tuyết", "YN2S-0058", date(2026, 11, 12), date(2026, 11, 20), date(2026, 11, 1), 5),
    ]
    alloc_objs = []
    for num, code, desc, vin, ccode, cname, eng, ship, dlv, mth, qty in allocations_data:
        alloc_objs.append(Allocation.objects.create(
            order_number=num, vehicle_code=code, description=desc, vin=vin,
            color_code=ccode, exterior_color=cname, engine_number=eng,
            expected_ship_date=ship, contractual_delivery_date=dlv,
            allocation_month=mth, quantity=qty
        ))
    print(f" -> Đã tạo {len(alloc_objs)} bản ghi phân bổ Allocation FVL")

    VehicleRequestItem.objects.all().delete()
    VehicleRequest.objects.all().delete()
    
    vr1 = VehicleRequest.objects.create(
        created_by=quanly_user,
        sent_at=timezone.now() - timedelta(days=15),
        status=VehicleRequest.Status.ACCEPTED
    )
    VehicleRequestItem.objects.create(vehicle_request=vr1, allocation=alloc_objs[0], quantity=2)
    VehicleRequestItem.objects.create(vehicle_request=vr1, allocation=alloc_objs[2], quantity=2)
    
    vr2 = VehicleRequest.objects.create(
        created_by=quanly_user,
        sent_at=timezone.now() - timedelta(days=2),
        status=VehicleRequest.Status.PENDING
    )
    VehicleRequestItem.objects.create(vehicle_request=vr2, allocation=alloc_objs[1], quantity=2)
    VehicleRequestItem.objects.create(vehicle_request=vr2, allocation=alloc_objs[7], quantity=3)
    
    vr3 = VehicleRequest.objects.create(
        created_by=nhanvien_user,
        status=VehicleRequest.Status.DRAFT
    )
    VehicleRequestItem.objects.create(vehicle_request=vr3, allocation=alloc_objs[3], quantity=1)
    VehicleRequestItem.objects.create(vehicle_request=vr3, allocation=alloc_objs[5], quantity=2)
    print(" -> Đã tạo 3 phiếu yêu cầu đặt xe: PYC00001 (Đã duyệt), PYC00002 (Chờ duyệt), PYC00003 (Nháp)")

    print("\n=== 4. TẠO CẤU HÌNH NGƯỠNG & DỮ LIỆU CẢNH BÁO (ALERTS) ===")
    CanhBao.objects.all().delete()
    NguongCanhBao.objects.all().delete()

    nguong_list = [
        ("KHO01", "Ford Ranger XLS 2.0L 4x2 AT", "Trắng", 3),
        ("KHO01", "Ford Everest Titanium+ 2.0L Bi-Turbo 4x4 AT", "Trắng Tuyết", 2),
        ("KHO01", "Ford Explorer Limited 2.3L EcoBoost", "Trắng Tuyết", 2),
        ("KHO02", "Ford Ranger Sport 2.0L 4x4 AT", "Đỏ Cam", 2),
        ("KHO02", "Ford Territory Titanium 1.5L EcoBoost", "Trắng", 2),
        ("KHO03", "Ford Territory Trend 1.5L EcoBoost", "Trắng", 3),
        ("KHO03", "Ford Transit Trend 16 chỗ 2.3L", "Trắng", 2),
    ]
    for kho_id, ten_xe, mau_sac, ton_min in nguong_list:
        NguongCanhBao.objects.create(
            kho_id=kho_id, ten_xe=ten_xe, mau_sac=mau_sac,
            ton_toi_thieu=ton_min, dang_theo_doi=True
        )
    print(f" -> Đã tạo {len(nguong_list)} ngưỡng cảnh báo tồn tối thiểu")

    # Sinh cảnh báo tự động
    cap_nhat_tat_ca_canh_bao()
    
    # Cập nhật trạng thái mẫu cho vài cảnh báo sinh động (Đang xử lý, Đã xử lý)
    cb_first = CanhBao.objects.filter(con_hieu_luc=True).first()
    if cb_first:
        cb_first.trang_thai = CanhBao.TrangThai.DANG_XU_LY
        cb_first.nguoi_xu_ly = quanly_user
        cb_first.thoi_diem_xu_ly = timezone.now() - timedelta(hours=3)
        cb_first.save()

    cb_second = CanhBao.objects.filter(con_hieu_luc=True).exclude(pk=cb_first.pk).first()
    if cb_second:
        cb_second.trang_thai = CanhBao.TrangThai.DA_XU_LY
        cb_second.nguoi_xu_ly = admin_user
        cb_second.thoi_diem_xu_ly = timezone.now() - timedelta(days=1)
        cb_second.save()

    tong_cb = CanhBao.objects.count()
    cb_ton_lau = CanhBao.objects.filter(loai=CanhBao.Loai.TON_LAU).count()
    cb_het_hang = CanhBao.objects.filter(loai=CanhBao.Loai.HET_HANG).count()
    cb_duoi_nguong = CanhBao.objects.filter(loai=CanhBao.Loai.DUOI_NGUONG).count()
    print(f" -> Đã sinh tổng cộng {tong_cb} cảnh báo: {cb_ton_lau} xe tồn lâu, {cb_het_hang} hết hàng, {cb_duoi_nguong} dưới ngưỡng")

    print("\n=== 5. ĐỒNG BỘ DỰ BÁO NHU CẦU (ANALYTICS) ===")
    if not PhienDuBao.objects.exists():
        phien = PhienDuBao.objects.create(
            nam=2026, thang=12,
            tao_luc=timezone.now(),
            het_han_luc=timezone.now() + timedelta(days=7),
            trang_thai="Hoàn tất",
            trang_thai_de_xuat="Tự động",
            canh_bao="Dữ liệu bán hàng ổn định.",
            nguoi_tao=quanly_user
        )
        print(" -> Đã tạo phiên dự báo mẫu")
    else:
        print(f" -> Phiên dự báo đã có: {PhienDuBao.objects.count()} phiên, {DongDuBao.objects.count()} dòng chi tiết")

    print("\n=== 6. ĐỒNG BỘ SỰ CỐ VẬN CHUYỂN (INCIDENTS) ===")
    DvvcLienHe.objects.all().delete()
    dvvc_emails = [
        ("DVVC01", "van.chuyen.hanoilogistics@gmail.com"),
        ("DVVC02", "contact@saigonlogistics.vn"),
        ("DVVC03", "dieuhanh@mientrungexpress.vn"),
        ("DVVC04", "info@danangtrans.com.vn"),
    ]
    for ma_dv, em in dvvc_emails:
        DvvcLienHe.objects.create(dvvc_id=ma_dv, email=em)
    print(f" -> Đã cấu hình email liên hệ cho {len(dvvc_emails)} đơn vị vận chuyển")

    # Hồ sơ sự cố mẫu cho PDI
    pdi_list = list(BienBanPDI.objects.all()[:4])
    if len(pdi_list) >= 4:
        HoSoSuCo.objects.all().delete()
        LichSuPhanHoi.objects.all().delete()

        # PDI 1: Đã xử lý bồi thường tiền
        hs1 = HoSoSuCo.objects.create(
            bien_ban=pdi_list[0],
            han_phan_hoi=date(2026, 8, 15),
            hinh_thuc_khac_phuc="TIEN",
            so_tien_boi_thuong=Decimal("15000000.00"),
            ngay_xac_nhan=date(2026, 8, 20)
        )
        pdi_list[0].trang_thai_claim = "Đã xử lý"
        pdi_list[0].save()
        LichSuPhanHoi.objects.create(
            bien_ban=pdi_list[0], nguoi_thuc_hien=admin_user,
            hanh_dong="Đóng hồ sơ", noi_dung="ĐVVC đã bồi thường 15,000,000 đ theo thỏa thuận."
        )

        # PDI 2: Đã gửi yêu cầu, đang chờ phản hồi
        hs2 = HoSoSuCo.objects.create(
            bien_ban=pdi_list[1],
            han_phan_hoi=date(2026, 11, 12),
            hinh_thuc_khac_phuc="SUA"
        )
        pdi_list[1].trang_thai_claim = "Đã gửi yêu cầu"
        pdi_list[1].save()
        LichSuPhanHoi.objects.create(
            bien_ban=pdi_list[1], nguoi_thuc_hien=quanly_user,
            hanh_dong="Gửi yêu cầu bồi thường", noi_dung="Đã gửi biên bản và hình ảnh hư hỏng cho ĐVVC."
        )

        # PDI 3: Chưa xử lý
        pdi_list[2].trang_thai_claim = "Chưa xử lý"
        pdi_list[2].save()

        # PDI 4: Chưa xử lý
        pdi_list[3].trang_thai_claim = "Chưa xử lý"
        pdi_list[3].save()

        print(f" -> Đã cập nhật 8 biên bản PDI và hồ sơ bồi thường sự cố (Đã xử lý, Đã gửi yêu cầu, Chưa xử lý)")

    print("\n=== HOÀN TẤT ĐỒNG BỘ CẢ 9 MODULE THÀNH CÔNG ===")

if __name__ == "__main__":
    dong_bo_tat_ca()
