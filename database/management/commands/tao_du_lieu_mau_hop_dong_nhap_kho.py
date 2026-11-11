"""Dữ liệu mẫu, chỉ dùng các bảng/cột của luồng hợp đồng - nhập kho hiện có.

Chạy: python manage.py tao_du_lieu_mau_hop_dong_nhap_kho
"""
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from database.models import (
    BienBanPDI, ChiNhanh, ChiTietBan, ChiTietHopDong, ChiTietNhap, DonViVanChuyen,
    HoaDonBan, HoaDonNhap, HopDong, KhachHang, Kho, NhaCungCap, NhanVien,
    TonKho, Xe,
)
from warehouse.models import KetQuaPDI, LichSuNhapKho, PhieuNhapKho
from incidents.models import DA_GUI_YEU_CAU, DA_XU_LY, CHUA_XU_LY, DvvcLienHe, HoSoSuCo, LichSuPhanHoi
from database.models import TrangThaiXe


class Command(BaseCommand):
    help = 'Tạo/cập nhật dữ liệu mẫu cho hợp đồng xe bán và nhập kho; có thể chạy lặp lại.'

    @transaction.atomic
    def handle(self, *args, **options):
        now = timezone.now()
        cn, _ = ChiNhanh.objects.update_or_create(ma_cn='CN01', defaults={'ten_cn': 'Dana Ford Đà Nẵng', 'dia_chi_cn': 'Đà Nẵng'})
        kho, _ = Kho.objects.update_or_create(ma_kho='KHO01', defaults={'chi_nhanh': cn})
        ncc, _ = NhaCungCap.objects.update_or_create(ma_ncc='NCC_MAU', defaults={'ten_ncc': 'Ford Việt Nam', 'dia_chi_ncc': 'Hà Nội', 'mst': '0100109999'})
        dvvc, _ = DonViVanChuyen.objects.update_or_create(ma_dvvc='DVVC_MAU', defaults={'ten_dvvc': 'Dana Logistics', 'sdt_dvvc': '0901234567', 'dia_chi_dvvc': 'Đà Nẵng'})
        kh, _ = KhachHang.objects.update_or_create(ma_kh='KH_MAU', defaults={'ten_kh': 'Công ty Khách hàng Mẫu', 'sdt_kh': '0912345678', 'mst_kh': '0401234567'})
        nv_kho, _ = NhanVien.objects.update_or_create(ma_nv='NVKHO_MAU', defaults={'chi_nhanh': cn, 'ten_nv': 'Nhân viên kho mẫu', 'sdt_nv': '0901111111'})
        nv_sale, _ = NhanVien.objects.update_or_create(ma_nv='NVSALE_MAU', defaults={'chi_nhanh': cn, 'ten_nv': 'Sale Admin mẫu', 'sdt_nv': '0902222222'})

        user_model = get_user_model()
        group_kho, _ = Group.objects.get_or_create(name='III-IV Nhân viên kho')
        group_sale, _ = Group.objects.get_or_create(name='III-IV Sale Admin')
        perms = Permission.objects.filter(content_type__app_label__in=['database', 'warehouse']).exclude(codename__startswith='delete_')
        group_kho.permissions.set(perms)
        group_sale.permissions.set(perms)
        for username, employee, group in [('kho_mau', nv_kho, group_kho), ('sale_mau', nv_sale, group_sale)]:
            user, _ = user_model.objects.get_or_create(username=username, defaults={'is_staff': True, 'nhan_vien': employee})
            user.nhan_vien = employee
            user.is_staff = True
            user.set_password('123456')
            user.groups.set([group])
            user.save()
        user_kho = user_model.objects.get(username='kho_mau')
        user_sale = user_model.objects.get(username='sale_mau')
        DvvcLienHe.objects.update_or_create(dvvc=dvvc, defaults={'email': 'dieuphoi@danalogistics.example'})

        def car(vin, engine, color):
            return Xe.objects.update_or_create(vin=vin, defaults={
                'ten_xe': 'Ford Ranger XLS 2.0L 4x2 AT', 'loai_xe': 'RANGER-XLS', 'so_may': engine,
                'mau_sac': color, 'nam_sx': 2026, 'hop_so': 'AT', 'nhien_lieu': 'Diesel', 'dung_tich': 1996,
            })[0]

        xe_ton = car('VINM00000000000001', 'ENGM000000000001', 'Trắng')
        xe_nhap = car('VINM00000000000002', 'ENGM000000000002', 'Đen')
        hdn, _ = HoaDonNhap.objects.update_or_create(ma_hdn='HDN_MAU_01', defaults={
            'nha_cung_cap': ncc, 'chi_nhanh': cn, 'don_vi_van_chuyen': dvvc, 'ngay_nhap': now,
            'so_hoa_don': '000001', 'ky_hieu': 'C26M', 'bien_so_xe': '43C-123.45', 'ten_tai_xe': 'Nguyễn Văn Vận',
        })
        ct_ton, _ = ChiTietNhap.objects.update_or_create(hoa_don_nhap=hdn, xe=xe_ton, defaults={'so_luong_nhap': 1, 'don_gia': Decimal('650000000.00')})
        ct_nhap, _ = ChiTietNhap.objects.update_or_create(hoa_don_nhap=hdn, xe=xe_nhap, defaults={'so_luong_nhap': 1, 'don_gia': Decimal('680000000.00')})
        TonKho.objects.update_or_create(kho=kho, xe=xe_ton, defaults={'ngay_vao_kho': now.date() - timedelta(days=2), 'so_luong_ton': 1})

        # Phiếu đã hoàn tất giúp danh sách tồn có xe; phiếu nháp giúp thử đủ PDI -> gửi duyệt -> duyệt nhập.
        phieu_da_duyet, _ = PhieuNhapKho.objects.update_or_create(ma_phieu='PN_MAU_DA_DUYET', defaults={
            'chi_tiet_nhap': ct_ton, 'xe': xe_ton, 'kho': kho, 'ngay_nhap': now.date() - timedelta(days=2),
            'trang_thai': PhieuNhapKho.TrangThai.DA_DUYET, 'nguoi_lap': user_model.objects.get(username='kho_mau'),
            'nguoi_duyet': user_model.objects.get(username='sale_mau'), 'thoi_gian_duyet': now - timedelta(days=2),
        })
        LichSuNhapKho.objects.update_or_create(phieu_nhap=phieu_da_duyet, defaults={'xe': xe_ton, 'kho': kho, 'nguoi_thuc_hien': user_model.objects.get(username='sale_mau'), 'thoi_gian': now - timedelta(days=2)})
        phieu_nhap, _ = PhieuNhapKho.objects.update_or_create(ma_phieu='PN_MAU_CHO_PDI', defaults={
            'chi_tiet_nhap': ct_nhap, 'xe': xe_nhap, 'kho': kho, 'ngay_nhap': now.date(),
            'trang_thai': PhieuNhapKho.TrangThai.NHAP, 'nguoi_lap': user_model.objects.get(username='kho_mau'),
            'nguoi_duyet': None, 'thoi_gian_duyet': None,
        })
        KetQuaPDI.objects.filter(phieu_nhap=phieu_nhap).delete()

        def tao_ca_pdi_loi(stt, color, loai_loi, trang_thai, mo_ta, xu_ly=None):
            """Một case nối đủ: HDN -> CTN -> PN -> PDI lỗi -> Biên bản sự cố."""
            xe = car(f'VINPDI2026{stt:08d}', f'ENGPDI2026{stt:08d}', color)
            Xe.objects.filter(pk=xe.pk).update(trang_thai=TrangThaiXe.SU_CO_PDI)
            hdn_case, _ = HoaDonNhap.objects.update_or_create(ma_hdn=f'HDN_PDI_LOI_{stt:02d}', defaults={
                'nha_cung_cap': ncc, 'chi_nhanh': cn, 'don_vi_van_chuyen': dvvc,
                'ngay_nhap': now - timedelta(days=stt), 'so_hoa_don': f'PDI-{stt:04d}',
                'ky_hieu': 'PDI26', 'bien_so_xe': '43C-123.45', 'ten_tai_xe': 'Nguyễn Văn Vận',
            })
            ct, _ = ChiTietNhap.objects.update_or_create(hoa_don_nhap=hdn_case, xe=xe, defaults={'so_luong_nhap': 1, 'don_gia': Decimal('680000000.00')})
            phieu, _ = PhieuNhapKho.objects.update_or_create(ma_phieu=f'PN_PDI_LOI_{stt:02d}', defaults={
                'chi_tiet_nhap': ct, 'xe': xe, 'kho': kho, 'ngay_nhap': (now - timedelta(days=stt)).date(),
                'trang_thai': PhieuNhapKho.TrangThai.NHAP, 'nguoi_lap': user_kho,
                'nguoi_duyet': None, 'thoi_gian_duyet': None,
            })
            KetQuaPDI.objects.filter(phieu_nhap=phieu).delete()
            KetQuaPDI.objects.create(
                phieu_nhap=phieu, tinh_trang=f'Không đạt: {loai_loi.lower()}', ket_qua='KHONG_DAT',
                ghi_chu=mo_ta, nguoi_kiem_tra=user_kho, nguoi_duyet=user_kho, thoi_gian_duyet=now - timedelta(days=stt),
                hang_muc=[
                    {'hang_muc': 'Ngoại thất', 'tinh_trang': loai_loi, 'ket_qua': 'KHONG_DAT', 'ghi_chu': mo_ta},
                    {'hang_muc': 'Nội thất', 'tinh_trang': 'Bình thường', 'ket_qua': 'DAT', 'ghi_chu': ''},
                    {'hang_muc': 'Vận hành', 'tinh_trang': 'Bình thường', 'ket_qua': 'DAT', 'ghi_chu': ''},
                ],
            )
            bb, _ = BienBanPDI.objects.update_or_create(ma_pdi=f'BBPDI_MAU_{stt:02d}', defaults={
                'hoa_don_nhap': hdn_case, 'xe': xe, 'nhan_vien': nv_kho, 'ngay_ghi_nhan': now - timedelta(days=stt),
                'loai_su_co': loai_loi, 'mo_ta_chi_tiet': mo_ta, 'trang_thai_claim': trang_thai,
            })
            LichSuPhanHoi.objects.filter(bien_ban=bb).delete()
            if trang_thai != CHUA_XU_LY:
                hs, _ = HoSoSuCo.objects.update_or_create(bien_ban=bb, defaults={
                    'han_phan_hoi': (now + timedelta(days=3)).date(), 'hinh_thuc_khac_phuc': 'SUA',
                    'ngay_xac_nhan': (now - timedelta(days=1)).date() if trang_thai == DA_XU_LY else None,
                })
                LichSuPhanHoi.objects.create(bien_ban=bb, nguoi_thuc_hien=user_sale,
                    hanh_dong='Gửi yêu cầu bồi thường' if trang_thai == DA_GUI_YEU_CAU else 'Cập nhật kết quả xử lý, đóng sự cố',
                    noi_dung=xu_ly or 'Đã ghi nhận hồ sơ xử lý sự cố.')
            else:
                HoSoSuCo.objects.filter(bien_ban=bb).delete()
            return phieu

        tao_ca_pdi_loi(1, 'Trắng', 'Trầy xước sơn', CHUA_XU_LY,
                        'Trầy xước cửa trước bên phải khi tiếp nhận xe.')
        tao_ca_pdi_loi(2, 'Đen', 'Móp méo thân vỏ', DA_GUI_YEU_CAU,
                        'Móp nhẹ cản trước, đã gửi yêu cầu ĐVVC phản hồi.', 'Chờ Dana Logistics xác nhận phương án sửa chữa.')
        tao_ca_pdi_loi(3, 'Xám', 'Hư hỏng linh kiện', DA_XU_LY,
                        'Thiếu nắp che khoang hành lý.', 'ĐVVC đã bổ sung linh kiện; cần kiểm định PDI lại trước khi nhập kho.')

        hd, _ = HopDong.objects.update_or_create(ma_hd='HD_MAU_01', defaults={'chi_nhanh': cn, 'khach_hang': kh, 'ngay_ky': now, 'so_tien_coc': Decimal('100000000.00')})
        ChiTietHopDong.objects.get_or_create(hop_dong=hd, xe=xe_ton)
        hdb, _ = HoaDonBan.objects.update_or_create(ma_hdb='HDB_MAU_01', defaults={'khach_hang': kh, 'chi_nhanh': cn, 'ngay_ban': now, 'so_hoa_don': '000101', 'hinh_thuc_tt': 'Chuyển khoản'})
        ChiTietBan.objects.update_or_create(hoa_don_ban=hdb, xe=xe_ton, defaults={'so_luong_ban': 1, 'gia_ban': Decimal('720000000.00')})
        self.stdout.write(self.style.SUCCESS('Đã tạo dữ liệu mẫu: HD_MAU_01, HDN_MAU_01, PN_MAU_DA_DUYET, PN_MAU_CHO_PDI và 3 ca PDI không đạt.'))
        self.stdout.write('Tài khoản: kho_mau / 123456 và sale_mau / 123456')
