from django.urls import reverse
from django.core.exceptions import ValidationError
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

    def test_detail_template_renders_cho_xe_ve_kho_state(self):
        html = render_to_string('contracts/detail.html', {'hop_dong': {
            'ma_hd': 'HD99', 'tieu_chi_xe': [], 'canh_bao': None, 'trang_thai': 'CHO_XE_VE_KHO'
        }})
        self.assertIn('Đang chờ xe về kho', html)
        self.assertIn('Xem nguồn phân bổ', html)


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

    def test_07_theo_lich_phan_bo_hien_thi_khi_cac_kho_khong_co_xe(self):
        """Khi cả kho Đà Nẵng và chi nhánh đều không có xe, tab Theo lịch phân bổ hiển thị danh sách xe phân bổ."""
        from orders.models import Allocation
        # Tạo allocation cho tháng 11/2026
        alloc = Allocation.objects.create(
            order_number='ORD-TEST-001',
            vehicle_code='EVEREST-TITANIUM+',
            description='Ford Everest Titanium+ 2.0L Bi-Turbo 4x4 AT',
            vin='RL2TESTVIN0000099',
            mau_sac='Trắng Tuyết',
            exterior_color='Trắng Tuyết',
            allocation_month=date(2026, 11, 1),
            contractual_delivery_date=date(2026, 11, 20),
            quantity=1,
            chi_nhanh=self.cn_dn
        )

        # Hợp đồng tìm Everest Titanium+ nhưng trong kho không có sẵn xe
        hd_new = HopDong.objects.create(
            ma_hd='HD-TEST-ALLOC',
            khach_hang=self.kh,
            chi_nhanh=self.cn_dn,
            dong_xe_yeu_cau='Ford Everest Titanium+ 2.0L Bi-Turbo 4x4 AT',
            phien_ban_yeu_cau='Titanium+',
            mau_sac_yeu_cau='Trắng Tuyết',
            trang_thai=TrangThaiHopDong.CHO_XU_LY,
            ngay_ky=date(2026, 10, 1)
        )

        self.client.force_login(self.user)
        response = self.client.get(f'/hop-dong/{hd_new.pk}/xe-phu-hop/', HTTP_ACCEPT='text/html')
        self.assertEqual(response.status_code, 200)
        self.assertIn('3. Theo lịch phân bổ', response.content.decode('utf-8'))
        self.assertIn('RL2TESTVIN0000099', response.content.decode('utf-8'))
        self.assertIn('ORD-TEST-001', response.content.decode('utf-8'))
        self.assertEqual(len(response.context['xe_phan_bo']), 1)

    def test_08_chon_xe_theo_lich_phan_bo_thanh_cong(self):
        """Khi chọn xe từ lịch phân bổ, xe được tạo/gán vào hợp đồng và trạng thái chuyển CHO_XE_VE_KHO."""
        from orders.models import Allocation
        alloc = Allocation.objects.create(
            order_number='ORD-TEST-002',
            vehicle_code='EVEREST-TITANIUM+',
            description='Ford Everest Titanium+ 2.0L Bi-Turbo 4x4 AT',
            vin='RL2TESTVIN0000100',
            mau_sac='Trắng Tuyết',
            exterior_color='Trắng Tuyết',
            allocation_month=date(2026, 11, 1),
            contractual_delivery_date=date(2026, 11, 25),
            quantity=1,
            chi_nhanh=self.cn_dn
        )

        hd_new = HopDong.objects.create(
            ma_hd='HD-TEST-ALLOC-CHON',
            khach_hang=self.kh,
            chi_nhanh=self.cn_dn,
            dong_xe_yeu_cau='Ford Everest Titanium+ 2.0L Bi-Turbo 4x4 AT',
            phien_ban_yeu_cau='Titanium+',
            mau_sac_yeu_cau='Trắng Tuyết',
            trang_thai=TrangThaiHopDong.CHO_XU_LY,
            ngay_ky=date(2026, 10, 1)
        )

        self.client.force_login(self.user)
        response = self.client.post(f'/hop-dong/{hd_new.pk}/chon-xe-phan-bo/{alloc.id}/')
        self.assertEqual(response.status_code, 302)

        hd_new.refresh_from_db()
        self.assertEqual(hd_new.trang_thai, TrangThaiHopDong.CHO_XE_VE_KHO)
        self.assertEqual(hd_new.ngay_du_kien_giao, date(2026, 11, 25))
        self.assertTrue(ChiTietHopDong.objects.filter(hop_dong=hd_new, xe__vin='RL2TESTVIN0000100').exists())


from contracts.sourcing import check_can_source_from_tier, SourcingTier
from django.contrib.messages import get_messages
from django.test import Client
from django.core.exceptions import ValidationError
from django.urls import reverse


class ContractSourcingTierTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_superuser(username='sourcing_tester', password='password123', email='sourcing@danaford.com.vn')
        self.cn_dn = ChiNhanh.objects.create(ma_cn="CN01", ten_cn="Dana Ford Đà Nẵng", dia_chi_cn="Đà Nẵng")
        self.cn_bd = ChiNhanh.objects.create(ma_cn="CN02", ten_cn="Dana Ford Bình Định", dia_chi_cn="Bình Định")
        self.kho_dn = Kho.objects.create(ma_kho="KHO01", chi_nhanh=self.cn_dn)
        self.kho_bd = Kho.objects.create(ma_kho="KHO02", chi_nhanh=self.cn_bd)
        self.nv = NhanVien.objects.create(ma_nv="NV_TIER_01", ten_nv="Sale Admin Tier", chi_nhanh=self.cn_dn, sdt_nv="0901234567")
        self.user.nhan_vien = self.nv
        self.user.save()
        self.kh = KhachHang.objects.create(ma_kh="KH_TIER_01", ten_kh="Khách Hàng Tier", sdt_kh="0909999888")

        self.client = Client()
        self.client.force_login(self.user)

    def test_da_nang_con_xe_chan_chot_chi_nhanh_va_chan_chot_phan_bo(self):
        # 1. Xe tại Đà Nẵng
        car_dn = Xe.objects.create(
            vin="VN0000000TIERDN01",
            ten_xe="Ford Ranger Wildtrak",
            phien_ban="Wildtrak 2.0L",
            mau_sac="Trắng",
            so_may="ENG-DN-001",
            trang_thai=TrangThaiXe.SAN_SANG,
            nam_sx=2026
        )
        TonKho.objects.create(kho=self.kho_dn, xe=car_dn, so_luong_ton=1, ngay_vao_kho=timezone.localdate())

        # 2. Xe tại Bình Định
        car_bd = Xe.objects.create(
            vin="VN0000000TIERBD01",
            ten_xe="Ford Ranger Wildtrak",
            phien_ban="Wildtrak 2.0L",
            mau_sac="Trắng",
            so_may="ENG-BD-001",
            trang_thai=TrangThaiXe.SAN_SANG,
            nam_sx=2026
        )
        TonKho.objects.create(kho=self.kho_bd, xe=car_bd, so_luong_ton=1, ngay_vao_kho=timezone.localdate())

        # 3. Xe theo lịch phân bổ
        from orders.models import Allocation
        alloc = Allocation.objects.create(
            order_number="ORD-TIER-01",
            vehicle_code="RANGER-WILDTRAK",
            description="Ford Ranger Wildtrak 2.0L",
            vin="RL2TIERALLOC00001",
            mau_sac="Trắng",
            exterior_color="Trắng",
            allocation_month=date(2026, 11, 1),
            contractual_delivery_date=date(2026, 11, 20),
            quantity=1,
            chi_nhanh=self.cn_dn
        )

        # Hợp đồng yêu cầu Ranger Wildtrak màu Trắng
        hd = HopDong.objects.create(
            ma_hd="HD-TIER-01",
            khach_hang=self.kh,
            chi_nhanh=self.cn_dn,
            dong_xe_yeu_cau="Ford Ranger Wildtrak",
            phien_ban_yeu_cau="Wildtrak 2.0L",
            mau_sac_yeu_cau="Trắng",
            trang_thai=TrangThaiHopDong.CHO_XU_LY,
            ngay_ky=date(2026, 11, 1)
        )

        # Kiểm tra check_can_source_from_tier
        can_bd, reason_bd = check_can_source_from_tier(hd, SourcingTier.CHI_NHANH)
        self.assertFalse(can_bd)
        self.assertIn("Kho Đà Nẵng còn", reason_bd)

        can_pb, reason_pb = check_can_source_from_tier(hd, SourcingTier.PHAN_BO)
        self.assertFalse(can_pb)
        self.assertIn("Kho Đà Nẵng còn", reason_pb)

        # Gọi choose_vehicle cho xe chi nhánh bị raise ValidationError
        with self.assertRaises(ValidationError) as ctx:
            choose_vehicle(hd.ma_hd, car_bd.vin, self.user)
        self.assertIn("Kho Đà Nẵng còn", str(ctx.exception))

        # Gọi thẳng URL POST cho xe chi nhánh bị chặn
        url_bd = reverse("contracts:choose_suggested_vehicle", args=[hd.ma_hd, car_bd.vin])
        resp_bd = self.client.post(url_bd)
        self.assertEqual(resp_bd.status_code, 302)
        messages_bd = list(get_messages(resp_bd.wsgi_request))
        self.assertTrue(any("Kho Đà Nẵng còn" in str(m) for m in messages_bd))

        # Gọi thẳng URL POST cho xe phân bổ bị chặn
        url_pb = reverse("contracts:choose_allocation_vehicle", args=[hd.ma_hd, alloc.id])
        resp_pb = self.client.post(url_pb)
        self.assertEqual(resp_pb.status_code, 302)
        messages_pb = list(get_messages(resp_pb.wsgi_request))
        self.assertTrue(any("Kho Đà Nẵng còn" in str(m) for m in messages_pb))

    def test_da_nang_het_chi_nhanh_con_duoc_chot_chi_nhanh_chan_phan_bo(self):
        # Đà Nẵng không có xe. Bình Định có 1 xe
        car_bd = Xe.objects.create(
            vin="VN0000000TIERBD02",
            ten_xe="Ford Ranger Wildtrak",
            phien_ban="Wildtrak 2.0L",
            mau_sac="Đen",
            so_may="ENG-BD-002",
            trang_thai=TrangThaiXe.SAN_SANG,
            nam_sx=2026
        )
        TonKho.objects.create(kho=self.kho_bd, xe=car_bd, so_luong_ton=1, ngay_vao_kho=timezone.localdate())

        from orders.models import Allocation
        alloc = Allocation.objects.create(
            order_number="ORD-TIER-02",
            vehicle_code="RANGER-WILDTRAK",
            description="Ford Ranger Wildtrak 2.0L",
            vin="RL2TIERALLOC00002",
            mau_sac="Đen",
            exterior_color="Đen",
            allocation_month=date(2026, 11, 1),
            contractual_delivery_date=date(2026, 11, 20),
            quantity=1,
            chi_nhanh=self.cn_dn
        )

        hd = HopDong.objects.create(
            ma_hd="HD-TIER-02",
            khach_hang=self.kh,
            chi_nhanh=self.cn_dn,
            dong_xe_yeu_cau="Ford Ranger Wildtrak",
            phien_ban_yeu_cau="Wildtrak 2.0L",
            mau_sac_yeu_cau="Đen",
            trang_thai=TrangThaiHopDong.CHO_XU_LY,
            ngay_ky=date(2026, 11, 1)
        )

        # Chốt phân bổ bị chặn vì chi nhánh còn xe
        can_pb, reason_pb = check_can_source_from_tier(hd, SourcingTier.PHAN_BO)
        self.assertFalse(can_pb)
        self.assertIn("Kho chi nhánh còn", reason_pb)

        url_pb = reverse("contracts:choose_allocation_vehicle", args=[hd.ma_hd, alloc.id])
        resp_pb = self.client.post(url_pb)
        self.assertEqual(resp_pb.status_code, 302)
        messages_pb = list(get_messages(resp_pb.wsgi_request))
        self.assertTrue(any("Kho chi nhánh còn" in str(m) for m in messages_pb))

        # Chốt chi nhánh được phép
        can_bd, reason_bd = check_can_source_from_tier(hd, SourcingTier.CHI_NHANH)
        self.assertTrue(can_bd)
        updated_hd = choose_vehicle(hd.ma_hd, car_bd.vin, self.user)
        self.assertEqual(updated_hd.trang_thai, TrangThaiHopDong.CHO_XE_VE_KHO)

    def test_ca_hai_het_duoc_chot_phan_bo(self):
        from orders.models import Allocation
        alloc = Allocation.objects.create(
            order_number="ORD-TIER-03",
            vehicle_code="TERRITORY-TITANIUM",
            description="Ford Territory Titanium 1.5L EcoBoost",
            vin="RL2TIERALLOC00003",
            mau_sac="Nâu Ánh Kim",
            exterior_color="Nâu Ánh Kim",
            allocation_month=date(2026, 11, 1),
            contractual_delivery_date=date(2026, 11, 28),
            quantity=1,
            chi_nhanh=self.cn_dn
        )

        hd = HopDong.objects.create(
            ma_hd="HD-TIER-03",
            khach_hang=self.kh,
            chi_nhanh=self.cn_dn,
            dong_xe_yeu_cau="Ford Territory Titanium 1.5L EcoBoost",
            phien_ban_yeu_cau="Titanium",
            mau_sac_yeu_cau="Nâu Ánh Kim",
            trang_thai=TrangThaiHopDong.CHO_XU_LY,
            ngay_ky=date(2026, 11, 1)
        )

        can_pb, reason_pb = check_can_source_from_tier(hd, SourcingTier.PHAN_BO)
        self.assertTrue(can_pb)
        self.assertEqual(reason_pb, "")

        resp = self.client.post(f"/hop-dong/{hd.ma_hd}/chon-xe-phan-bo/{alloc.id}/")
        self.assertEqual(resp.status_code, 302)
        hd.refresh_from_db()
        self.assertEqual(hd.trang_thai, TrangThaiHopDong.CHO_XE_VE_KHO)
        self.assertEqual(hd.ngay_du_kien_giao, date(2026, 11, 28))
