from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock
from django.test import SimpleTestCase
from django.template.loader import render_to_string
from .views import criteria_for, contract_summary, find_suitable


class ContractPresentationTests(SimpleTestCase):
    def contract(self, state='CHO_XU_LY'):
        cars = [SimpleNamespace(ten_xe='Ranger XLS', phien_ban='', mau_sac=color) for color in ('Trắng', 'Đen')]
        lines = Mock()
        lines.all.return_value = [SimpleNamespace(xe=car) for car in cars]
        requirements = Mock()
        requirements.all.return_value = []
        return SimpleNamespace(yeu_cau_xe=requirements, chi_nhanh=SimpleNamespace(pk='CN01', ten_cn='Đà Nẵng'), pk='HD01', dong_xe_yeu_cau='', phien_ban_yeu_cau='', mau_sac_yeu_cau='',
            chitiethopdong_set=lines, trang_thai=state, get_trang_thai_display=lambda: 'Hoàn tất',
            khach_hang_id='KH01', khach_hang=SimpleNamespace(ten_kh='Khách hàng'), chi_nhanh_id='CN01',
            ngay_ky=None, so_tien_coc=0, ngay_du_kien_giao=None)

    def test_multiple_legacy_requirements_are_visible_without_inventing_version(self):
        hd = self.contract()
        criteria, warning = criteria_for(hd)
        self.assertEqual(len(criteria), 2)
        self.assertTrue(warning)
        html = render_to_string('contracts/detail.html', {'hop_dong': {
            'ma_hd': hd.pk, 'tieu_chi_xe': criteria, 'canh_bao': warning}})
        self.assertIn('Ranger XLS', html)
        self.assertIn('Trắng', html)
        self.assertIn('Đen', html)
        self.assertIn('Chưa có phiên bản', html)

    def test_completed_contract_cannot_suggest_cars(self):
        hd = self.contract('HOAN_TAT')
        user = Mock(is_authenticated=True, is_active=True, is_superuser=True)
        summary = contract_summary(hd, user)
        self.assertEqual(summary['trang_thai_hien_thi'], 'Hoàn tất')
        self.assertFalse(summary['thao_tac']['de_xuat_xe'])
        self.assertEqual(find_suitable(hd)[1], [])
        self.assertIn('hoàn tất', find_suitable(hd)[2])

    def test_detail_template_contains_delivery_date_input(self):
        html = render_to_string('contracts/detail.html', {'hop_dong': {
            'ma_hd': 'HD99', 'tieu_chi_xe': [], 'canh_bao': None, 'ngay_du_kien_giao': None
        }, 'co_the_chinh_sua': True})
        self.assertIn('name="ngay_du_kien_giao"', html)
        self.assertIn('Lưu ngày giao', html)
        self.assertIn('openDateModal', html)


from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from database.models import (
    ChiNhanh, Kho, NhanVien, KhachHang, Xe, TonKho,
    HopDong, ChiTietHopDong, PhieuXuatKho,
    TrangThaiXe, TrangThaiHopDong, TrangThaiPhieuXuat,
    DonViVanChuyen
)
from contracts.workflow import choose_vehicle, sync_contract_for_vin


class ContractWorkflowTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_superuser(username='contract_tester', password='password123', email='admin@danaford.com.vn')

        self.cn_dn = ChiNhanh.objects.create(ma_cn="CN01", ten_cn="Dana Ford Đà Nẵng", dia_chi_cn="Đà Nẵng")
        self.cn_bd = ChiNhanh.objects.create(ma_cn="CN02", ten_cn="Dana Ford Bình Định", dia_chi_cn="Bình Định")

        self.kho_dn = Kho.objects.create(ma_kho="KHO01", chi_nhanh=self.cn_dn)
        self.kho_bd = Kho.objects.create(ma_kho="KHO02", chi_nhanh=self.cn_bd)

        self.nv = NhanVien.objects.create(ma_nv="NV_DN_02", ten_nv="Sale Admin ĐN", chi_nhanh=self.cn_dn, sdt_nv="0901234567")
        self.user.nhan_vien = self.nv
        self.user.save()

        self.kh = KhachHang.objects.create(ma_kh="KH_CT_01", ten_kh="Khách Hàng Test", sdt_kh="0909999888")

        self.dvvc = DonViVanChuyen.objects.create(ma_dvvc="DVVC_02", ten_dvvc="Vận Tải Miền Trung", sdt_dvvc="0905999999")

        # Hợp đồng yêu cầu Ford Everest Titanium màu Trắng
        self.hd1 = HopDong.objects.create(
            ma_hd="HD-TEST-001",
            chi_nhanh=self.cn_dn,
            khach_hang=self.kh,
            ngay_ky=timezone.now(),
            dong_xe_yeu_cau="Ford Everest",
            phien_ban_yeu_cau="Titanium",
            mau_sac_yeu_cau="Trắng",
            trang_thai=TrangThaiHopDong.CHO_PHAN_BO
        )

        # Xe 1 ở kho Đà Nẵng
        self.xe_dn = Xe.objects.create(
            vin="VIN-DN-001", ten_xe="Ford Everest", phien_ban="Titanium",
            loai_xe="Everest", so_may="SM-DN01", mau_sac="Trắng", trang_thai=TrangThaiXe.SAN_SANG
        )
        self.ton_dn = TonKho.objects.create(
            kho=self.kho_dn, xe=self.xe_dn, so_luong_ton=1, ngay_vao_kho=timezone.localdate()
        )

        # Xe 2 ở kho Bình Định
        self.xe_bd = Xe.objects.create(
            vin="VIN-BD-002", ten_xe="Ford Everest", phien_ban="Titanium",
            loai_xe="Everest", so_may="SM-BD02", mau_sac="Trắng", trang_thai=TrangThaiXe.SAN_SANG
        )
        self.ton_bd = TonKho.objects.create(
            kho=self.kho_bd, xe=self.xe_bd, so_luong_ton=1, ngay_vao_kho=timezone.localdate()
        )

    def test_01_chot_xe_tai_da_nang_luong_xuat_kho_cu(self):
        """Xe tại Đà Nẵng: giữ chỗ xe, hợp đồng chuyển DANG_XUAT_KHO, tạo phiếu xuất kho chờ duyệt."""
        hd = choose_vehicle(self.hd1.pk, self.xe_dn.vin, self.user)

        self.xe_dn.refresh_from_db()
        self.assertEqual(self.xe_dn.trang_thai, TrangThaiXe.GIU_CHO_XUAT)

        hd.refresh_from_db()
        self.assertEqual(hd.trang_thai, TrangThaiHopDong.DANG_XUAT_KHO)

        pxk = PhieuXuatKho.objects.filter(chi_tiet_hop_dong__hop_dong=hd, chi_tiet_hop_dong__xe=self.xe_dn).first()
        self.assertIsNotNone(pxk)
        self.assertEqual(pxk.trang_thai, TrangThaiPhieuXuat.CHO_DUYET)
        self.assertEqual(pxk.kho, self.kho_dn)

        # Không tạo lệnh lưu chuyển
        from transfers.models import LenhLuuChuyen
        self.assertFalse(LenhLuuChuyen.objects.filter(chi_tiet__xe=self.xe_dn).exists())

    def test_02_chot_xe_chi_nhanh_tao_lenh_luu_chuyen_cho_duyet(self):
        """Xe tại Bình Định: giữ chỗ xe, hợp đồng CHO_XE_VE_KHO, tạo lệnh lưu chuyển ở trạng thái CHO_DUYET."""
        from transfers.models import LenhLuuChuyen

        hd = choose_vehicle(self.hd1.pk, self.xe_bd.vin, self.user)

        self.xe_bd.refresh_from_db()
        self.assertEqual(self.xe_bd.trang_thai, TrangThaiXe.GIU_CHO_XUAT)

        hd.refresh_from_db()
        self.assertEqual(hd.trang_thai, TrangThaiHopDong.CHO_XE_VE_KHO)

        # Lệnh lưu chuyển phải ở trạng thái CHO_DUYET
        lenh = LenhLuuChuyen.objects.filter(chi_tiet__xe=self.xe_bd).first()
        self.assertIsNotNone(lenh)
        self.assertEqual(lenh.trang_thai, LenhLuuChuyen.TrangThai.CHO_DUYET)
        self.assertEqual(lenh.kho_xuat, self.kho_bd)
        self.assertEqual(lenh.kho_nhap, self.kho_dn)

    def test_03_chot_hai_lan(self):
        """Hợp đồng đã chốt xe không được chốt lần hai."""
        from django.core.exceptions import ValidationError
        choose_vehicle(self.hd1.pk, self.xe_dn.vin, self.user)

        with self.assertRaises(ValidationError) as ctx:
            choose_vehicle(self.hd1.pk, self.xe_dn.vin, self.user)
        self.assertIn("đang xuất kho hoặc đã hoàn tất", str(ctx.exception))

    def test_04_xe_da_giu_cho_hop_dong_khac(self):
        """Không cho phép hợp đồng khác chốt xe đã được giữ chỗ."""
        from django.core.exceptions import ValidationError

        hd2 = HopDong.objects.create(
            ma_hd="HD-TEST-002",
            chi_nhanh=self.cn_dn,
            khach_hang=self.kh,
            ngay_ky=timezone.now(),
            dong_xe_yeu_cau="Ford Everest",
            phien_ban_yeu_cau="Titanium",
            mau_sac_yeu_cau="Trắng",
            trang_thai=TrangThaiHopDong.CHO_PHAN_BO
        )

        # HĐ 1 chốt xe Đà Nẵng
        choose_vehicle(self.hd1.pk, self.xe_dn.vin, self.user)

        # HĐ 2 cố chốt xe đó -> Bị chặn
        with self.assertRaises(ValidationError) as ctx:
            choose_vehicle(hd2.pk, self.xe_dn.vin, self.user)
        self.assertTrue("đã được giữ" in str(ctx.exception) or "đang giữ chỗ" in str(ctx.exception))

    def test_05_lenh_bi_tu_choi_hoac_huy_nha_xe_va_hop_dong_quay_lai(self):
        """Khi lệnh lưu chuyển bị từ chối/hủy: xe được nhả về SAN_SANG, hợp đồng quay lại CHO_PHAN_BO."""
        from transfers.models import LenhLuuChuyen
        from transfers.services import tu_choi_lenh_luu_chuyen

        choose_vehicle(self.hd1.pk, self.xe_bd.vin, self.user)

        lenh = LenhLuuChuyen.objects.filter(chi_tiet__xe=self.xe_bd).first()
        self.assertIsNotNone(lenh)

        # Sale Admin từ chối lệnh
        tu_choi_lenh_luu_chuyen(self.user, lenh.pk, ly_do="Chi nhánh Bình Định giữ lại xe theo yêu cầu địa phương")

        # Xe phải được nhả về SẴN SÀNG
        self.xe_bd.refresh_from_db()
        self.assertEqual(self.xe_bd.trang_thai, TrangThaiXe.SAN_SANG)

        # Hợp đồng quay lại CHO_PHAN_BO
        self.hd1.refresh_from_db()
        self.assertEqual(self.hd1.trang_thai, TrangThaiHopDong.CHO_PHAN_BO)

        # Chi tiết hợp đồng với xe đó phải bị gỡ
        self.assertFalse(ChiTietHopDong.objects.filter(hop_dong=self.hd1, xe=self.xe_bd).exists())

    def test_06_xe_ve_da_nang_nhap_kho_pdi_dat_hop_dong_du_dieu_kien_xuat(self):
        """Sau khi xe nhập kho Đà Nẵng và PDI đạt: sync_contract_for_vin chuyển hợp đồng sang DU_DIEU_KIEN_XUAT."""
        choose_vehicle(self.hd1.pk, self.xe_bd.vin, self.user)
        self.hd1.refresh_from_db()
        self.assertEqual(self.hd1.trang_thai, TrangThaiHopDong.CHO_XE_VE_KHO)

        # Giả lập xe đã hoàn tất nhập kho Đà Nẵng
        TonKho.objects.create(kho=self.kho_dn, xe=self.xe_bd, so_luong_ton=1, ngay_vao_kho=timezone.localdate())
        self.xe_bd.trang_thai = TrangThaiXe.SAN_SANG
        self.xe_bd.save(update_fields=['trang_thai'])

        # Đồng bộ trạng thái hợp đồng
        updated = sync_contract_for_vin(self.xe_bd.vin)
        self.assertEqual(updated, 1)

        self.hd1.refresh_from_db()
        self.assertEqual(self.hd1.trang_thai, TrangThaiHopDong.DU_DIEU_KIEN_XUAT)
