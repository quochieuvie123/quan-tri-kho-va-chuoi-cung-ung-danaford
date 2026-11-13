"""State changes caused by a manager explicitly choosing a proposed VIN."""
from decimal import Decimal
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from core.iii_iv_access import is_da_nang_branch
from database.models import (
    ChiTietBan, ChiTietHopDong, HoaDonBan, HopDong, Kho, LichSuXuatKho,
    NhanVien, PhieuXuatKho, TonKho, TrangThaiHopDong, TrangThaiPhieuXuat,
    TrangThaiXe, Xe
)


def matches_contract(car, contract):
    from .matching import matches_contract_smart
    return matches_contract_smart(car, contract)


def ensure_invoice_for_contract(contract, car):
    """
    Đảm bảo có hóa đơn bán hàng và chi tiết bán hàng hợp lệ cho hợp đồng và xe.
    Giúp đối chiếu hợp đồng - hóa đơn trong module xuất kho luôn chính xác và thành công.
    """
    hdb = HoaDonBan.objects.filter(khach_hang=contract.khach_hang, chi_nhanh=contract.chi_nhanh).first()
    if not hdb:
        ma_hdb = f"HDB-{contract.ma_hd}"[:50]
        so_hd = f"HD-{contract.ma_hd}"[:50]
        hdb, _ = HoaDonBan.objects.get_or_create(
            ma_hdb=ma_hdb,
            defaults={
                'khach_hang': contract.khach_hang,
                'chi_nhanh': contract.chi_nhanh,
                'ngay_ban': timezone.now(),
                'so_hoa_don': so_hd,
                'hinh_thuc_tt': 'Chuyển khoản',
            }
        )
    ctb = ChiTietBan.objects.filter(hoa_don_ban=hdb, xe=car).first()
    if not ctb:
        price = Decimal('850000000')
        ChiTietBan.objects.create(
            hoa_don_ban=hdb,
            xe=car,
            so_luong_ban=1,
            gia_ban=price
        )
    return hdb


@transaction.atomic
def choose_vehicle(contract_id, vin, user):
    """
    Chốt VIN đề xuất cho hợp đồng:
    1. Nếu xe tại kho Đà Nẵng:
       - Giữ chỗ xe (GIU_CHO_XUAT), hợp đồng chuyển DANG_XUAT_KHO.
       - Gửi yêu cầu xuất kho sang Quản lý xuất kho (PhieuXuatKho: CHO_DUYET).
       - Phát thông báo cho Sale Admin để kiểm tra và phê duyệt.
       - KHÔNG xuất kho ngay và KHÔNG đi qua lưu chuyển.
    2. Nếu xe tại Bình Định / Gia Lai:
       - Giữ chỗ xe (GIU_CHO_XUAT) để không hợp đồng/phiếu xuất khác lấy mất.
       - Lập lệnh lưu chuyển qua service transfers (LenhLuuChuyen: CHO_DUYET).
       - Kho nhận lấy từ cấu hình hoặc kho trung tâm Đà Nẵng thay vì hard-code 'KHO01'.
       - Hợp đồng chuyển sang CHO_XE_VE_KHO.
       - Phát thông báo cho Sale Admin để duyệt lưu chuyển.
    """
    contract = HopDong.objects.select_for_update().select_related('chi_nhanh', 'khach_hang').get(pk=contract_id)
    car = Xe.objects.select_for_update().get(pk=vin)
    if contract.trang_thai in (TrangThaiHopDong.DANG_XUAT_KHO, TrangThaiHopDong.HOAN_TAT):
        raise ValidationError('Hợp đồng đang xuất kho hoặc đã hoàn tất.')
    if not matches_contract(car, contract):
        raise ValidationError('VIN không khớp dòng xe, phiên bản và màu sắc của hợp đồng.')

    other = ChiTietHopDong.objects.filter(xe=car).exclude(hop_dong=contract).exists()
    if other:
        raise ValidationError('VIN đã được giữ cho hợp đồng khác.')

    if car.trang_thai in (TrangThaiXe.DA_XUAT, TrangThaiXe.GIU_CHO_XUAT):
        if not ChiTietHopDong.objects.filter(hop_dong=contract, xe=car).exists():
            raise ValidationError('Xe đã xuất hoặc đang giữ chỗ cho phiếu xuất / hợp đồng khác.')

    ct_hd, _ = ChiTietHopDong.objects.get_or_create(hop_dong=contract, xe=car)
    available_here = TonKho.objects.filter(
        xe=car, so_luong_ton__gt=0
    ).select_related('kho__chi_nhanh').first()

    if not available_here:
        raise ValidationError('Xe không còn tồn kho tại bất kỳ chi nhánh nào.')

    nv = getattr(user, 'nhan_vien', None)
    if not nv:
        nv = NhanVien.objects.filter(chi_nhanh=contract.chi_nhanh).first() or NhanVien.objects.first()

    dn_branch_ids = getattr(settings, 'III_IV_DA_NANG_BRANCH_IDS', ['CN01'])

    if is_da_nang_branch(available_here.kho.chi_nhanh):
        # 1. Xe tại kho Đà Nẵng: Giữ chỗ xe & chuyển trạng thái hợp đồng
        car.trang_thai = TrangThaiXe.GIU_CHO_XUAT
        car.save(update_fields=['trang_thai'])

        contract.trang_thai = TrangThaiHopDong.DANG_XUAT_KHO
        contract.save(update_fields=['trang_thai'])

        # 2. Đảm bảo hóa đơn bán hàng đồng bộ
        ensure_invoice_for_contract(contract, car)

        # 3. Tạo / Cập nhật phiếu xuất kho ở trạng thái CHỜ DUYỆT
        ma_pxk = f"PXK-{contract.ma_hd}-{car.vin[-6:]}"[:50]
        phieu_xuat = PhieuXuatKho.objects.filter(chi_tiet_hop_dong=ct_hd).first()
        if not phieu_xuat:
            phieu_xuat = PhieuXuatKho.objects.create(
                ma_pxk=ma_pxk,
                chi_tiet_hop_dong=ct_hd,
                kho=available_here.kho,
                nguoi_nhan=contract.khach_hang.ten_kh,
                nguoi_lap=nv,
                trang_thai=TrangThaiPhieuXuat.CHO_DUYET,
                ghi_chu=f"Yêu cầu xuất kho giao xe {car.vin} cho hợp đồng {contract.ma_hd}."
            )
        else:
            phieu_xuat.kho = available_here.kho
            phieu_xuat.nguoi_nhan = contract.khach_hang.ten_kh
            phieu_xuat.nguoi_lap = nv
            phieu_xuat.trang_thai = TrangThaiPhieuXuat.CHO_DUYET
            phieu_xuat.save(update_fields=['kho', 'nguoi_nhan', 'nguoi_lap', 'trang_thai'])

        # 4. Ghi lịch sử xuất kho
        LichSuXuatKho.objects.create(
            phieu_xuat=phieu_xuat,
            xe=car,
            kho=available_here.kho,
            hanh_dong="TAO_PHIEU_CHO_DUYET",
            nguoi_thuc_hien=nv,
            ghi_chu=f"Chốt xe Đà Nẵng {car.vin} cho HĐ {contract.ma_hd}. Đã gửi yêu cầu xuất kho chờ Sale Admin duyệt."
        )

        # 5. Phát thông báo hệ thống minh bạch
        from dashboard.models import ThongBaoHoatDong
        ten_kho = available_here.kho.chi_nhanh.ten_cn if available_here.kho and available_here.kho.chi_nhanh else available_here.kho.ma_kho
        ThongBaoHoatDong.objects.create(
            user=user if user and user.is_authenticated else None,
            ten_nhan_vien=nv.ten_nv if nv else "Hệ thống",
            chuc_vu="Nhân viên kinh doanh",
            hanh_dong=f"Tạo phiếu xuất kho {phieu_xuat.ma_pxk}",
            chi_tiet=f"Hợp đồng {contract.ma_hd} đã chốt xe {car.ten_xe} ({car.vin}) tại {ten_kho}. Chờ Sale Admin duyệt xuất kho.",
            module="warehouse",
            loai="THONG_TIN"
        )

    else:
        # Xe ở Bình Định / Gia Lai:
        # 1. Giữ chỗ xe để không hợp đồng hay phiếu xuất khác lấy mất
        car.trang_thai = TrangThaiXe.GIU_CHO_XUAT
        car.save(update_fields=['trang_thai'])

        # 2. Xác định kho tiếp nhận từ cấu hình hoặc kho trung tâm Đà Nẵng thay vì hard-code 'KHO01'
        target_warehouse = Kho.objects.filter(chi_nhanh_id__in=dn_branch_ids).first()
        if not target_warehouse:
            target_warehouse = Kho.objects.filter(ma_kho='KHO01').first() or Kho.objects.first()

        # 3. Lập lệnh lưu chuyển qua service của transfers (trạng thái: CHO_DUYET)
        from transfers.services import tao_lenh_luu_chuyen, gui_lenh_luu_chuyen
        transfer = tao_lenh_luu_chuyen(user, available_here.kho, target_warehouse, ds_xe=[car])
        transfer = gui_lenh_luu_chuyen(user, transfer.pk)

        # 4. Hợp đồng chuyển sang CHO_XE_VE_KHO
        contract.trang_thai = TrangThaiHopDong.CHO_XE_VE_KHO
        contract.save(update_fields=['trang_thai'])

        # 5. Phát thông báo hệ thống minh bạch
        from dashboard.models import ThongBaoHoatDong
        ten_kho_xuat = available_here.kho.chi_nhanh.ten_cn if available_here.kho and available_here.kho.chi_nhanh else available_here.kho.ma_kho
        ten_kho_nhap = target_warehouse.chi_nhanh.ten_cn if target_warehouse and target_warehouse.chi_nhanh else target_warehouse.ma_kho
        ThongBaoHoatDong.objects.create(
            user=user if user and user.is_authenticated else None,
            ten_nhan_vien=nv.ten_nv if nv else "Hệ thống",
            chuc_vu="Nhân viên kinh doanh",
            hanh_dong=f"Tạo lệnh lưu chuyển xe {transfer.ma_lenh}",
            chi_tiet=f"Hợp đồng {contract.ma_hd} đã chốt xe {car.ten_xe} ({car.vin}) từ {ten_kho_xuat} về {ten_kho_nhap}. Trạng thái lệnh: Chờ duyệt.",
            module="transfers",
            loai="THONG_TIN"
        )

    return contract


@transaction.atomic
def sync_contract_for_vin(vin):
    """After PDI/receipt puts a chosen VIN in Đà Nẵng stock, enable export."""
    from django.conf import settings
    car = Xe.objects.select_for_update().get(pk=vin)
    dn_branch_ids = getattr(settings, 'III_IV_DA_NANG_BRANCH_IDS', ['CN01'])
    if not TonKho.objects.filter(
        xe=car, so_luong_ton__gt=0, xe__trang_thai=TrangThaiXe.SAN_SANG,
        kho__chi_nhanh_id__in=dn_branch_ids
    ).exists():
        return 0
    updated = 0
    for contract in HopDong.objects.select_for_update().filter(
        chitiethopdong__xe=car,
        trang_thai__in=[TrangThaiHopDong.CHO_XE_VE_KHO, TrangThaiHopDong.CHO_PHAN_BO]
    ).distinct():
        contract.trang_thai = TrangThaiHopDong.DU_DIEU_KIEN_XUAT
        contract.save(update_fields=['trang_thai'])
        # Đảm bảo có hóa đơn bán hàng sẵn sàng
        ensure_invoice_for_contract(contract, car)
        updated += 1
    return updated


@transaction.atomic
def handle_transfer_rejected_or_cancelled(lenh, user=None):
    """Khi lệnh lưu chuyển bị từ chối hoặc hủy: hợp đồng quay lại trạng thái phù hợp và nhả xe."""
    from dashboard.models import ThongBaoHoatDong
    for item in lenh.chi_tiet.select_related("xe").all():
        car = Xe.objects.select_for_update().get(pk=item.xe_id)
        contracts = list(HopDong.objects.select_for_update().filter(
            chitiethopdong__xe=car,
            trang_thai=TrangThaiHopDong.CHO_XE_VE_KHO
        ))
        for contract in contracts:
            ChiTietHopDong.objects.filter(hop_dong=contract, xe=car).delete()
            contract.trang_thai = TrangThaiHopDong.CHO_PHAN_BO
            contract.save(update_fields=['trang_thai'])

            ten_user = user.get_full_name() or user.username if user and user.is_authenticated else "Hệ thống"
            ThongBaoHoatDong.objects.create(
                user=user if user and user.is_authenticated else None,
                ten_nhan_vien=ten_user,
                chuc_vu="Quản trị viên (Sale Admin)",
                hanh_dong=f"Nhả xe hợp đồng {contract.ma_hd}",
                chi_tiet=f"Lệnh lưu chuyển {lenh.ma_lenh} đã bị {lenh.get_trang_thai_display().lower()}. Đã hủy gán xe {car.vin} và chuyển hợp đồng {contract.ma_hd} về trạng thái Chờ lịch phân bổ.",
                module="contracts",
                loai="CANH_BAO"
            )

        # Nhả giữ chỗ xe về SẴN SÀNG nếu không còn hợp đồng active nào khác
        still_held = ChiTietHopDong.objects.filter(
            xe=car,
            hop_dong__trang_thai__in=[TrangThaiHopDong.CHO_XU_LY, TrangThaiHopDong.CHO_PHAN_BO, TrangThaiHopDong.CHO_XE_VE_KHO, TrangThaiHopDong.DANG_XUAT_KHO]
        ).exists()
        if not still_held and car.trang_thai == TrangThaiXe.GIU_CHO_XUAT:
            car.trang_thai = TrangThaiXe.SAN_SANG
            car.save(update_fields=['trang_thai'])


@receiver(post_save, sender='transfers.LenhLuuChuyen')
def on_transfer_order_saved(sender, instance, **kwargs):
    """Lắng nghe sự kiện lệnh lưu chuyển bị từ chối hoặc hủy để tự động nhả hợp đồng và xe."""
    if instance.trang_thai in ('TU_CHOI', 'HUY'):
        handle_transfer_rejected_or_cancelled(instance, getattr(instance, 'nguoi_duyet', None))
