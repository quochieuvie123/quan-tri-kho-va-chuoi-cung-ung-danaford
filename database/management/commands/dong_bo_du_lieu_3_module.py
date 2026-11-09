from datetime import date, timedelta
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from database.models import Xe, HopDong, Kho, ChiTietNhap, TonKho
from transfers.models import LenhLuuChuyen, ChiTietLenhLuuChuyen
from warehouse.models import PhieuNhapKho, KetQuaPDI, LichSuNhapKho


class Command(BaseCommand):
    help = "Chuan hoa va dong bo du lieu cho 3 module Hop dong, Nhap kho va Luu chuyen tu du lieu mau co san."

    @transaction.atomic
    def handle(self, *args, **options):
        User = get_user_model()
        admin_user = User.objects.filter(is_superuser=True).first() or User.objects.first()

        # 1. Chuẩn hóa phiên bản cho Xe
        xe_count = 0
        for car in Xe.objects.all():
            parts = car.ten_xe.split()
            if len(parts) >= 3 and parts[0].lower() == 'ford':
                phien_ban = " ".join(parts[2:])
                if car.phien_ban != phien_ban:
                    car.phien_ban = phien_ban
                    car.save(update_fields=['phien_ban'])
                    xe_count += 1
        self.stdout.write(f"Da chuan hoa phien ban cho {xe_count} xe.")

        # 2. Chuẩn hóa tiêu chí yêu cầu cho Hợp đồng
        hd_count = 0
        for hd in HopDong.objects.all():
            lines = list(hd.chitiethopdong_set.select_related('xe'))
            if lines:
                car = lines[0].xe
                parts = car.ten_xe.split()
                dong_xe = " ".join(parts[:2]) if len(parts) >= 2 else car.ten_xe
                phien_ban = " ".join(parts[2:]) if len(parts) >= 3 else (car.phien_ban or "")
                hd.dong_xe_yeu_cau = dong_xe
                hd.phien_ban_yeu_cau = phien_ban
                hd.mau_sac_yeu_cau = car.mau_sac or "Trắng"
                if not hd.ngay_du_kien_giao:
                    hd.ngay_du_kien_giao = (hd.ngay_ky + timedelta(days=15)).date()
                hd.save(update_fields=['dong_xe_yeu_cau', 'phien_ban_yeu_cau', 'mau_sac_yeu_cau', 'ngay_du_kien_giao'])
                hd_count += 1
        self.stdout.write(f"Da chuan hoa tieu chi cho {hd_count} hop dong.")

        # 3. Tạo mẫu Phiếu nhập kho & PDI (nếu chưa có)
        kho_dn = Kho.objects.filter(chi_nhanh_id='CN01').first() or Kho.objects.first()
        lines = list(ChiTietNhap.objects.select_for_update().select_related('hoa_don_nhap', 'xe'))
        pn_count = 0
        if not PhieuNhapKho.objects.exists() and lines and kho_dn:
            scenarios = [
                ("PN-2026-001", lines[0], "DA_DUYET", "DAT"),
                ("PN-2026-002", lines[1] if len(lines) > 1 else lines[0], "CHO_DUYET", "DAT"),
                ("PN-2026-003", lines[2] if len(lines) > 2 else lines[0], "NHAP", "CHO_PDI"),
            ]
            for ma_phieu, line, state, pdi_state in scenarios:
                if PhieuNhapKho.objects.filter(xe_id=line.xe_id).exists():
                    continue
                pn = PhieuNhapKho.objects.create(
                    ma_phieu=ma_phieu,
                    chi_tiet_nhap=line,
                    xe=line.xe,
                    kho=kho_dn,
                    ngay_nhap=line.hoa_don_nhap.ngay_nhap.date(),
                    trang_thai=state,
                    nguoi_lap=admin_user,
                    nguoi_duyet=admin_user if state == "DA_DUYET" else None,
                    thoi_gian_duyet=timezone.now() if state == "DA_DUYET" else None,
                )
                if pdi_state != "CHO_PDI":
                    items = [
                        {"hang_muc": "Ngoại thất", "tinh_trang": "Sơn bóng đẹp, không trầy xước", "ket_qua": "DAT", "ghi_chu": "Chuẩn nhà máy"},
                        {"hang_muc": "Nội thất", "tinh_trang": "Ghế da và tablo hoàn hảo", "ket_qua": "DAT", "ghi_chu": "Đầy đủ phụ kiện"},
                        {"hang_muc": "Vận hành", "tinh_trang": "Động cơ khởi động êm, phanh nhạy", "ket_qua": "DAT", "ghi_chu": "Hoạt động tốt"}
                    ]
                    KetQuaPDI.objects.create(
                        phieu_nhap=pn,
                        hang_muc=items,
                        tinh_trang="Xe đạt chuẩn xuất xưởng, bàn giao đủ phụ kiện.",
                        ket_qua="DAT",
                        ghi_chu="PDI đạt yêu cầu kỹ thuật",
                        nguoi_kiem_tra=admin_user,
                        nguoi_duyet=admin_user,
                        thoi_gian_duyet=timezone.now(),
                    )
                if state == "DA_DUYET":
                    LichSuNhapKho.objects.create(
                        phieu_nhap=pn,
                        xe=line.xe,
                        kho=kho_dn,
                        nguoi_thuc_hien=admin_user,
                        thoi_gian=timezone.now(),
                    )
                pn_count += 1
            self.stdout.write(f"Da tao {pn_count} phieu nhap kho minh hoa tu hoa don nhap co san.")
        else:
            self.stdout.write("Phieu nhap kho da ton tai hoac khong du dieu kien.")

        # 4. Tạo mẫu Lệnh lưu chuyển (nếu chưa có)
        kho_xuat_bdi = Kho.objects.filter(chi_nhanh_id='CN02').first()
        kho_xuat_gla = Kho.objects.filter(chi_nhanh_id='CN03').first()
        lc_count = 0
        if not LenhLuuChuyen.objects.exists() and kho_dn and kho_xuat_bdi:
            # Lấy xe từ kho Bình Định để chuyển về Đà Nẵng
            tk_bdi = TonKho.objects.filter(kho=kho_xuat_bdi, so_luong_ton__gt=0).first()
            if tk_bdi:
                lenh1 = LenhLuuChuyen.objects.create(
                    ma_lenh="LC-202610-001",
                    kho_xuat=kho_xuat_bdi,
                    kho_nhap=kho_dn,
                    nguoi_lap=admin_user,
                    trang_thai="DA_XAC_NHAN",
                    ngay_gui=timezone.now() - timedelta(days=5),
                    ngay_xac_nhan=timezone.now() - timedelta(days=3),
                    nguoi_xac_nhan=admin_user,
                )
                ChiTietLenhLuuChuyen.objects.create(
                    lenh=lenh1,
                    xe=tk_bdi.xe,
                    so_luong=1
                )
                lc_count += 1

            if kho_xuat_gla:
                tk_gla = TonKho.objects.filter(kho=kho_xuat_gla, so_luong_ton__gt=0).first()
                if tk_gla:
                    lenh2 = LenhLuuChuyen.objects.create(
                        ma_lenh="LC-202611-002",
                        kho_xuat=kho_xuat_gla,
                        kho_nhap=kho_dn,
                        nguoi_lap=admin_user,
                        trang_thai="DA_GUI",
                        ngay_gui=timezone.now() - timedelta(hours=12),
                    )
                    ChiTietLenhLuuChuyen.objects.create(
                        lenh=lenh2,
                        xe=tk_gla.xe,
                        so_luong=1
                    )
                    # Cập nhật trạng thái xe Đang lưu chuyển
                    from database.models import TrangThaiXe
                    Xe.objects.filter(pk=tk_gla.xe_id).update(trang_thai=TrangThaiXe.DANG_LUU_CHUYEN)
                    lc_count += 1

            lenh3 = LenhLuuChuyen.objects.create(
                ma_lenh="LC-202611-003",
                kho_xuat=kho_xuat_bdi,
                kho_nhap=kho_dn,
                nguoi_lap=admin_user,
                trang_thai="NHAP",
            )
            tk_bdi_2 = TonKho.objects.filter(kho=kho_xuat_bdi, so_luong_ton__gt=0).last()
            if tk_bdi_2:
                ChiTietLenhLuuChuyen.objects.create(
                    lenh=lenh3,
                    xe=tk_bdi_2.xe,
                    so_luong=1
                )
            lc_count += 1
            self.stdout.write(f"Da tao {lc_count} lenh luu chuyen mau tu ton kho co san.")

        self.stdout.write(self.style.SUCCESS("Hoan tat dong bo du lieu 3 module!"))
