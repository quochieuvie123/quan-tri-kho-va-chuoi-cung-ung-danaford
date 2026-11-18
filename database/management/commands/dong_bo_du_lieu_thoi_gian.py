from datetime import date, datetime
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.contrib.auth import get_user_model

from database.models import (
    ChiNhanh, Kho, NhanVien, KhachHang, NhaCungCap, DonViVanChuyen,
    Xe, TonKho, HoaDonNhap, ChiTietNhap, HopDong, ChiTietHopDong,
    PhieuXuatKho, BienBanPDI, TrangThaiXe, TrangThaiHopDong, TrangThaiPhieuXuat
)
from warehouse.models import PhieuNhapKho
from orders.models import Allocation, VehicleRequest, VehicleRequestItem
from transfers.models import LenhLuuChuyen, ChiTietLenhLuuChuyen
from alerts.models import CanhBao, NguongCanhBao
from alerts.utils import cap_nhat_tat_ca_canh_bao, lay_dong_xe


class Command(BaseCommand):
    help = "Phân bổ đồng đều dữ liệu mẫu qua các tháng 08, 09, 10, 11/2026 cho toàn bộ module (Thống kê, Đặt xe, Lưu chuyển, Nhập/Xuất, Sự cố, Cảnh báo)"

    def handle(self, *args, **options):
        User = get_user_model()
        admin_user = User.objects.filter(is_superuser=True).first() or User.objects.first()
        tz = timezone.get_current_timezone()

        def aware_dt(y, m, d, hour=9, minute=30):
            return timezone.make_aware(datetime(y, m, d, hour, minute), tz)

        # 1. Phân bổ đều VehicleRequest (Đặt xe) qua Tháng 08, 09, 10, 11/2026
        target_months = [
            (2026, 8, 12),
            (2026, 9, 15),
            (2026, 10, 18),
            (2026, 11, 10),
        ]
        reqs = list(VehicleRequest.objects.order_by("id"))
        for idx, req in enumerate(reqs):
            y, m, d_base = target_months[idx % len(target_months)]
            d = min(28, d_base + (idx % 10))
            dt = aware_dt(y, m, d, 9 + (idx % 8), 15)
            VehicleRequest.objects.filter(pk=req.pk).update(
                created_at=dt,
                sent_at=dt if req.status != VehicleRequest.Status.DRAFT else None,
            )

        # 2. Phân bổ đều LenhLuuChuyen (Lưu chuyển) qua Tháng 08, 09, 10, 11/2026
        lenhs = list(LenhLuuChuyen.objects.order_by("id"))
        for idx, lenh in enumerate(lenhs):
            # Nếu mã lệnh có sẵn 202609 hoặc 202610 thì giữ đúng tháng đó
            if "202609" in (lenh.ma_lenh or ""):
                y, m = 2026, 9
            elif "202610" in (lenh.ma_lenh or ""):
                y, m = 2026, 10
            elif "202608" in (lenh.ma_lenh or ""):
                y, m = 2026, 8
            else:
                y, m, _ = target_months[idx % len(target_months)]
            d = min(27, 5 + (idx * 2) % 22)
            dt = aware_dt(y, m, d, 10, 0)
            LenhLuuChuyen.objects.filter(pk=lenh.pk).update(
                ngay_lap=dt,
                ngay_gui=dt if lenh.ngay_gui else None,
                ngay_duyet=aware_dt(y, m, min(28, d + 1), 14, 0) if lenh.ngay_duyet else None,
            )

        # 3. Phân bổ đều PhieuNhapKho qua Tháng 08, 09, 10, 11/2026
        pnks = list(PhieuNhapKho.objects.order_by("id"))
        for idx, pnk in enumerate(pnks):
            y, m, _ = target_months[idx % len(target_months)]
            d = min(27, 4 + (idx * 2) % 23)
            dt = aware_dt(y, m, d, 8, 45)
            PhieuNhapKho.objects.filter(pk=pnk.pk).update(
                ngay_nhap=date(y, m, d),
                ngay_lap=dt,
            )

        # 4. Phân bổ đều PhieuXuatKho qua Tháng 08, 09, 10, 11/2026
        pxks = list(PhieuXuatKho.objects.order_by("ma_pxk"))
        for idx, pxk in enumerate(pxks):
            y, m, _ = target_months[idx % len(target_months)]
            d = min(27, 6 + (idx * 2) % 21)
            dt_lap = aware_dt(y, m, d, 11, 0)
            dt_xuat = aware_dt(y, m, min(28, d + 1), 15, 30) if pxk.trang_thai == TrangThaiPhieuXuat.DA_DUYET else None
            PhieuXuatKho.objects.filter(pk=pxk.pk).update(
                ngay_lap=dt_lap,
                ngay_xuat=dt_xuat,
                ngay_duyet=dt_xuat,
            )

        # 5. Bổ sung & phân bổ đều BienBanPDI (Sự cố vận chuyển/PDI) có đủ ở Tháng 08, 09, 10, 11/2026
        nv_default = NhanVien.objects.first()
        hdn_default = HoaDonNhap.objects.first()
        cars_all = list(Xe.objects.all()[:10])
        if nv_default and hdn_default and cars_all:
            for extra_idx, (y, m, d) in enumerate([(2026, 9, 14), (2026, 10, 9), (2026, 10, 21), (2026, 11, 5)], start=1):
                ma_pdi = f"PDI-DEMO-{y}{m:02d}-{extra_idx:02d}"
                car_sample = cars_all[extra_idx % len(cars_all)]
                BienBanPDI.objects.update_or_create(
                    ma_pdi=ma_pdi,
                    defaults={
                        "hoa_don_nhap": hdn_default,
                        "xe": car_sample,
                        "nhan_vien": nv_default,
                        "ngay_ghi_nhan": aware_dt(y, m, d, 13, 30),
                        "loai_su_co": "Trầy xước cản trước khi vận chuyển" if extra_idx % 2 == 0 else "Chưa đủ bộ phụ kiện tiêu chuẩn",
                        "mo_ta_chi_tiet": f"Biên bản ghi nhận sự cố kỳ tháng {m:02d}/{y} phục vụ đối chiếu và thống kê.",
                        "trang_thai_claim": "Đã xử lý",
                    },
                )

        pdis = list(BienBanPDI.objects.order_by("ma_pdi"))
        for idx, pdi in enumerate(pdis):
            if "202609" in pdi.ma_pdi:
                y, m = 2026, 9
            elif "202610" in pdi.ma_pdi:
                y, m = 2026, 10
            else:
                y, m, _ = target_months[idx % len(target_months)]
            d = min(27, 7 + (idx * 3) % 20)
            BienBanPDI.objects.filter(pk=pdi.pk).update(
                ngay_ghi_nhan=aware_dt(y, m, d, 14, 0)
            )

        # 6. Phân bổ đều CanhBao qua Tháng 08, 09, 10, 11/2026
        cbs = list(CanhBao.objects.order_by("id"))
        for idx, cb in enumerate(cbs):
            y, m, _ = target_months[idx % len(target_months)]
            d = min(27, 3 + (idx * 2) % 24)
            dt = aware_dt(y, m, d, 8, 30)
            CanhBao.objects.filter(pk=cb.pk).update(
                ngay_phat_sinh=dt,
                ngay_cap_nhat=dt,
            )

        # 7. Đảm bảo có sẵn kịch bản mẫu "Khách ở Đà Nẵng mua xe Everest Titanium (Đà Nẵng hết xe, Gia Lai có xe RL2FMA001TZ000040)"
        cn_dn = ChiNhanh.objects.filter(ma_cn="CN01").first()
        cn_gl = ChiNhanh.objects.filter(ma_cn="CN03").first() or cn_dn
        kh_sample = KhachHang.objects.first()
        if cn_dn and kh_sample:
            HopDong.objects.update_or_create(
                ma_hd="HD-DN-LUU-CHUYEN-GL",
                defaults={
                    "chi_nhanh": cn_dn,
                    "khach_hang": kh_sample,
                    "ngay_ky": aware_dt(2026, 10, 25, 9, 0),
                    "so_tien_coc": Decimal("50000000"),
                    "dong_xe_yeu_cau": "Ford Everest",
                    "phien_ban_yeu_cau": "Titanium 2.0L 4x2 AT",
                    "mau_sac_yeu_cau": "Trắng Tuyết",
                    "trang_thai": TrangThaiHopDong.CHO_XU_LY,
                },
            )

        # 8. Đồng bộ ngày giao dự kiến & kỳ phân bổ của Allocation và HopDong (Mục 3)
        for alloc in Allocation.objects.all():
            am = alloc.allocation_month or date(2026, 11, 1)
            am_first = date(am.year, am.month, 1)
            ship_d = alloc.expected_ship_date
            deliv_d = alloc.contractual_delivery_date
            base_day = 12 + (alloc.id % 10)
            if not ship_d or (ship_d.year, ship_d.month) != (am_first.year, am_first.month):
                ship_d = date(am_first.year, am_first.month, min(23, base_day))
            if not deliv_d or (deliv_d.year, deliv_d.month) != (am_first.year, am_first.month) or deliv_d < ship_d:
                deliv_d = date(am_first.year, am_first.month, min(28, ship_d.day + 5))
            if (
                alloc.allocation_month != am_first
                or alloc.expected_ship_date != ship_d
                or alloc.contractual_delivery_date != deliv_d
            ):
                Allocation.objects.filter(pk=alloc.pk).update(
                    allocation_month=am_first,
                    expected_ship_date=ship_d,
                    contractual_delivery_date=deliv_d,
                )

        # Các hợp đồng Tháng 9 đã HOAN_TAT thì kỳ phân bổ và ngày giao đều nằm trong Tháng 9/2026
        for hd in HopDong.objects.prefetch_related("chitiethopdong_set__xe").all():
            ky_dt = timezone.localtime(hd.ngay_ky).date() if timezone.is_aware(hd.ngay_ky) else hd.ngay_ky.date()
            if ky_dt.month == 9 and hd.trang_thai == TrangThaiHopDong.HOAN_TAT:
                giao_t9 = date(2026, 9, min(28, max(ky_dt.day + 12, 22)))
                if hd.ngay_du_kien_giao != giao_t9:
                    HopDong.objects.filter(pk=hd.pk).update(ngay_du_kien_giao=giao_t9)
                for ct in hd.chitiethopdong_set.all():
                    Allocation.objects.filter(vin=ct.xe_id).update(
                        allocation_month=date(2026, 9, 1),
                        expected_ship_date=date(2026, 9, max(10, giao_t9.day - 5)),
                        contractual_delivery_date=giao_t9,
                    )
            else:
                # Hợp đồng gắn với Allocation kỳ nào thì ngày dự kiến giao phải >= kỳ phân bổ và >= ngày ký
                for ct in hd.chitiethopdong_set.all():
                    al = Allocation.objects.filter(vin=ct.xe_id).first()
                    if al and al.allocation_month:
                        target_deliv = al.contractual_delivery_date or al.expected_ship_date or date(al.allocation_month.year, al.allocation_month.month, 20)
                        if not hd.ngay_du_kien_giao or hd.ngay_du_kien_giao < al.allocation_month or hd.ngay_du_kien_giao < ky_dt:
                            HopDong.objects.filter(pk=hd.pk).update(ngay_du_kien_giao=target_deliv)

        # 9. Bổ sung xe phân bổ kỳ Tháng 11/2026 cho hợp đồng HD-T10-EV-GL-0002 (Ford Everest Titanium 2.0L 4x2 AT - Trắng Tuyết)
        for idx_ev, (vin_ev, mau_ev, code_m) in enumerate([
            ("RL2FMA001TZ000091", "Trắng Tuyết", "WH1"),
            ("RL2FMA001TZ000092", "Đen Ánh Kim", "BK1"),
        ], start=1):
            Allocation.objects.update_or_create(
                vin=vin_ev,
                defaults={
                    "order_number": f"FVL-AL2611-EV0{idx_ev}",
                    "vehicle_code": "EVEREST-TITANIUM-4X2",
                    "description": "Ford Everest Titanium 2.0L 4x2 AT",
                    "color_code": code_m,
                    "exterior_color": mau_ev,
                    "mau_sac": mau_ev,
                    "engine_number": f"EV20T-009{idx_ev}",
                    "allocation_month": date(2026, 11, 1),
                    "expected_ship_date": date(2026, 11, 15 + idx_ev),
                    "contractual_delivery_date": date(2026, 11, 20 + idx_ev),
                    "dealer_name": "Dana Ford Gia Lai",
                    "chi_nhanh": cn_gl,
                    "quantity": 1,
                },
            )

        # 10. Chuẩn hóa màu sắc Xe & thiết lập quy tắc NguongCanhBao (Mục 6)
        color_norm_map = {
            "FROZEN WHITE": "Trắng",
            "Trang Oxford": "Trắng",
            "SNOW FLAKE WHITE PEARL MC": "Trắng Tuyết",
            "ABSOLUTE BLACK": "Đen",
            "Den Absolute": "Đen",
            "PACE RED": "Đỏ Cam",
            "Xam Meteor": "Xám Meteor",
            "MAGNETIC": "Xám",
            "VAPOR BLUE/WHISPER BLUE": "Xanh",
            "ACACIA GREEN": "Xanh",
            "IGNITE ORANGE SOLID 2C": "Cam",
        }
        for raw_c, std_c in color_norm_map.items():
            Xe.objects.filter(mau_sac=raw_c).update(mau_sac=std_c)
            Allocation.objects.filter(mau_sac=raw_c).update(mau_sac=std_c)

        # Xóa các cảnh báo & ngưỡng màu tiếng Anh rác trước khi đồng bộ lại
        CanhBao.objects.filter(nguong__mau_sac__in=list(color_norm_map.keys())).delete()
        NguongCanhBao.objects.filter(mau_sac__in=list(color_norm_map.keys())).delete()

        cap_nhat_tat_ca_canh_bao()

        # Chỉ bật theo dõi (dang_theo_doi=True) cho các nhóm đang có tồn kho thực tế + 3 nhóm hết hàng tiêu biểu
        nhom_co_ton = set()
        for t in TonKho.objects.filter(so_luong_ton__gt=0).select_related("xe"):
            dx = lay_dong_xe(t.xe.ten_xe)
            if dx:
                nhom_co_ton.add((dx, (t.xe.mau_sac or "").strip()))

        nhom_het_hang_mau = {
            ("Explorer", "Trắng Tuyết"),
            ("Territory", "Bạc"),
            ("Transit", "Trắng"),
        }
        for ng in NguongCanhBao.objects.all():
            key = (ng.ten_xe, ng.mau_sac)
            should_track = (key in nhom_co_ton) or (key in nhom_het_hang_mau)
            if ng.dang_theo_doi != should_track:
                ng.dang_theo_doi = should_track
                ng.save(update_fields=["dang_theo_doi"])

        cap_nhat_tat_ca_canh_bao()

        # Phân bổ thời gian cho các cảnh báo lịch sử, nhưng giữ thời gian mới nhất khi phát sinh mới
        cbs = list(CanhBao.objects.filter(con_hieu_luc=True).order_by("id"))
        for idx, cb in enumerate(cbs):
            y, m, _ = target_months[idx % len(target_months)]
            d = min(27, 3 + (idx * 2) % 24)
            dt = aware_dt(y, m, d, 8, 30)
            CanhBao.objects.filter(pk=cb.pk).update(
                ngay_phat_sinh=dt,
                ngay_cap_nhat=dt,
            )

        self.stdout.write(self.style.SUCCESS("Đã đồng bộ dữ liệu thời gian, kỳ phân bổ, hợp đồng và quy tắc cảnh báo tồn kho!"))
