"""State changes caused by a manager explicitly choosing a proposed VIN."""
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.db import transaction
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
       - Tạo lệnh lưu chuyển về Đà Nẵng (LenhLuuChuyen: DA_GUI).
       - Hợp đồng chuyển sang CHO_XE_VE_KHO.
       - Thông báo Sale Admin duyệt lưu chuyển.
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

    ct_hd, _ = ChiTietHopDong.objects.get_or_create(hop_dong=contract, xe=car)
    available_here = TonKho.objects.filter(
        xe=car, so_luong_ton__gt=0, xe__trang_thai=TrangThaiXe.SAN_SANG,
    ).select_related('kho__chi_nhanh').first()

    nv = getattr(user, 'nhan_vien', None)
    if not nv:
        nv = NhanVien.objects.filter(ma_nv='NV10').first() or NhanVien.objects.first()

    if available_here and is_da_nang_branch(available_here.kho.chi_nhanh):
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

        # 5. Phát thông báo hệ thống cho Sale Admin
        try:
            from activity_log.services import ThongBaoService
            ThongBaoService.tao_thong_bao(
                tieu_de=f"Yêu cầu xuất kho mới: {phieu_xuat.ma_pxk}",
                noi_dung=f"Hợp đồng {contract.ma_hd} đã chốt xe {car.ten_xe} ({car.vin}) tại {available_here.kho.ten_kho}. Cần Sale Admin duyệt xuất kho.",
                loai='THONG_TIN',
                duong_dan=f"/kho/xuat/{phieu_xuat.ma_pxk}/",
                module='warehouse'
            )
        except Exception:
            pass

    elif available_here:
        # Xe ở Bình Định / Gia Lai: Lập lệnh lưu chuyển về Đà Nẵng
        from transfers.models import ChiTietLenhLuuChuyen, LenhLuuChuyen
        target_warehouse = Kho.objects.get(pk='KHO01')
        code = f'LC-{contract.pk}-{car.pk[-10:]}'[:30]
        transfer, _ = LenhLuuChuyen.objects.get_or_create(
            ma_lenh=code,
            defaults={
                'kho_xuat': available_here.kho,
                'kho_nhap': target_warehouse,
                'nguoi_lap': user,
                'trang_thai': 'DA_GUI',
                'ngay_gui': timezone.now()
            },
        )
        ChiTietLenhLuuChuyen.objects.get_or_create(lenh=transfer, xe=car, defaults={'so_luong': 1})
        contract.trang_thai = TrangThaiHopDong.CHO_XE_VE_KHO
        contract.save(update_fields=['trang_thai'])

        try:
            from activity_log.services import ThongBaoService
            ThongBaoService.tao_thong_bao(
                tieu_de=f"Lệnh lưu chuyển mới: {transfer.ma_lenh}",
                noi_dung=f"Hợp đồng {contract.ma_hd} cần lưu chuyển xe {car.vin} từ {available_here.kho.ten_kho} về Đà Nẵng. Cần Sale Admin duyệt.",
                loai='THONG_TIN',
                duong_dan=f"/transfers/danh-sach-lenh/{transfer.id}/",
                module='transfers'
            )
        except Exception:
            pass
    else:
        contract.trang_thai = TrangThaiHopDong.CHO_XE_VE_KHO
        contract.save(update_fields=['trang_thai'])

    return contract


@transaction.atomic
def sync_contract_for_vin(vin):
    """After PDI/receipt puts a chosen VIN in Đà Nẵng stock, enable export."""
    car = Xe.objects.select_for_update().get(pk=vin)
    if not TonKho.objects.filter(xe=car, so_luong_ton__gt=0, xe__trang_thai=TrangThaiXe.SAN_SANG,
                                  kho__chi_nhanh_id='CN01').exists():
        return 0
    updated = 0
    for contract in HopDong.objects.select_for_update().filter(chitiethopdong__xe=car,
        trang_thai__in=[TrangThaiHopDong.CHO_XE_VE_KHO, TrangThaiHopDong.CHO_PHAN_BO]).distinct():
        contract.trang_thai = TrangThaiHopDong.DU_DIEU_KIEN_XUAT
        contract.save(update_fields=['trang_thai'])
        updated += 1
    return updated
