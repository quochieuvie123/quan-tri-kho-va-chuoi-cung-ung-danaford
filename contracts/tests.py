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

        # Khi Đà Nẵng hết xe phù hợp, được phép chốt xe chi nhánh
        self.ton_dn.delete()
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

        self.ton_dn.delete()
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
        self.ton_dn.delete()
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
            ngay_ky=date(2026, 10, 15)
        )

        can_pb, reason_pb = check_can_source_from_tier(hd, SourcingTier.PHAN_BO)
        self.assertTrue(can_pb)
        self.assertEqual(reason_pb, "")

        resp = self.client.post(f"/hop-dong/{hd.ma_hd}/chon-xe-phan-bo/{alloc.id}/")
        self.assertEqual(resp.status_code, 302)
        hd.refresh_from_db()
        self.assertEqual(hd.trang_thai, TrangThaiHopDong.CHO_XE_VE_KHO)
        self.assertEqual(hd.ngay_du_kien_giao, date(2026, 11, 28))

    def test_choose_allocation_creates_vehicle_request_in_orders(self):
        """Khi chốt xe từ lịch phân bổ cho hợp đồng, hệ thống tự động sinh Phiếu yêu cầu đặt xe bên orders."""
        from orders.models import Allocation, VehicleRequest, VehicleRequestItem
        from contracts.sourcing import check_can_source_from_tier, SourcingTier

        alloc = Allocation.objects.create(
            order_number="ORD-AUTO-PYC",
            vehicle_code="TERRITORY",
            description="Ford Territory Trend",
            vin="RL2AUTOPYC0000001",
            mau_sac="Đỏ",
            exterior_color="Đỏ",
            allocation_month=date(2026, 11, 1),
            contractual_delivery_date=date(2026, 11, 25),
            quantity=1,
            chi_nhanh=self.cn_dn
        )

        hd = HopDong.objects.create(
            ma_hd="HD-AUTO-PYC-01",
            khach_hang=self.kh,
            chi_nhanh=self.cn_dn,
            dong_xe_yeu_cau="Ford Territory Trend",
            phien_ban_yeu_cau="Trend",
            mau_sac_yeu_cau="Đỏ",
            trang_thai=TrangThaiHopDong.CHO_XU_LY,
            ngay_ky=date(2026, 10, 15)
        )

        can_pb, _ = check_can_source_from_tier(hd, SourcingTier.PHAN_BO)
        self.assertTrue(can_pb)

        url = reverse("contracts:choose_allocation_vehicle", args=[hd.ma_hd, alloc.id])
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 302)

        # Khi vừa chốt xe phân bổ: xe được đưa vào Danh sách xe đã chọn đặt hàng (session) kèm mã HĐ, chưa tự duyệt mua ngay
        self.assertIn(str(alloc.id), self.client.session.get("selected_vehicles", {}))
        self.assertEqual(self.client.session.get("selected_vehicle_contracts", {}).get(str(alloc.id)), hd.ma_hd)
        self.assertFalse(VehicleRequest.objects.filter(items__allocation=alloc, status=VehicleRequest.Status.ACCEPTED).exists())

        # Nhân viên / Sale Admin bấm Lập phiếu yêu cầu đặt xe -> Gửi phiếu -> Duyệt đặt xe
        self.client.get(reverse("orders:lap_phieu_yeu_cau"))
        pyc = VehicleRequest.objects.filter(items__allocation=alloc).first()
        self.assertIsNotNone(pyc)
        self.assertEqual(pyc.status, VehicleRequest.Status.DRAFT)
        self.assertEqual(pyc.hop_dong_id, hd.ma_hd)

        self.client.post(reverse("orders:gui_phieu_yeu_cau", args=[pyc.id]))
        pyc.refresh_from_db()
        self.assertEqual(pyc.status, VehicleRequest.Status.PENDING)

        self.client.post(reverse("orders:xac_nhan_phieu", args=[pyc.id]))
        pyc.refresh_from_db()
        self.assertEqual(pyc.status, VehicleRequest.Status.ACCEPTED)

    def test_sourcing_tier_counts_pyc_waiting_pdi_in_tier_3(self):
        """Tầng xe từ PYC chờ PDI (uu_tien=4) được xếp cùng tầng với lịch phân bổ (Tầng 3)."""
        from warehouse.models import PhieuNhapKho
        from contracts.sourcing import get_sourcing_counts_by_tier, SourcingTier

        hd = HopDong.objects.create(
            ma_hd="HD-PYC-WAIT-01",
            khach_hang=self.kh,
            chi_nhanh=self.cn_dn,
            dong_xe_yeu_cau="Ford Transit",
            phien_ban_yeu_cau="Trend",
            mau_sac_yeu_cau="Bạc",
            trang_thai=TrangThaiHopDong.CHO_XU_LY,
            ngay_ky=date(2026, 11, 1)
        )

        # Tạo xe PYC chờ PDI theo đúng luồng thật: PYC được duyệt -> sync_request sinh phiếu nhập NHAP
        from orders.models import Allocation, VehicleRequest, VehicleRequestItem
        from warehouse.order_intake import sync_request
        alloc = Allocation.objects.create(
            order_number="ORD-PYC-WAIT", vehicle_code="TRANSIT", description="Ford Transit Trend",
            vin="VIN-PYC-TEST-001", mau_sac="Bạc", exterior_color="Bạc", engine_number="SM-PYC01",
            allocation_month=date(2026, 10, 1), quantity=1, chi_nhanh=self.cn_dn,
        )
        pyc = VehicleRequest.objects.create(created_by=self.user, status=VehicleRequest.Status.ACCEPTED)
        VehicleRequestItem.objects.create(vehicle_request=pyc, allocation=alloc, quantity=1)
        sync_request(pyc.pk)
        xe_pyc = Xe.objects.get(pk="VIN-PYC-TEST-001")
        self.assertTrue(PhieuNhapKho.objects.filter(xe=xe_pyc, trang_thai="NHAP").exists())

        counts = get_sourcing_counts_by_tier(hd)
        self.assertEqual(counts[SourcingTier.DA_NANG], 0)
        self.assertEqual(counts[SourcingTier.CHI_NHANH], 0)
        # Xe PYC chờ PDI được tính vào số lượng tầng 3 (PHAN_BO)
        self.assertGreaterEqual(counts[SourcingTier.PHAN_BO], 1)

        # Chốt được xe PYC này cho hợp đồng
        hd_updated = choose_vehicle(hd.pk, xe_pyc.vin, self.user)
        self.assertEqual(hd_updated.trang_thai, TrangThaiHopDong.CHO_XE_VE_KHO)
        xe_pyc.refresh_from_db()
        self.assertEqual(xe_pyc.trang_thai, TrangThaiXe.GIU_CHO_XUAT)

    def test_real_time_hop_dong_cho_giao_updates_live(self):
        """Kiểm tra hàm tính toán thời gian thực hợp đồng chờ giao xe phản ánh đúng ngay khi chốt xe."""
        from orders.views import tinh_hop_dong_cho_giao_thuc_te

        hd = HopDong.objects.create(
            ma_hd="HD-LIVE-DEMAND-01",
            khach_hang=self.kh,
            chi_nhanh=self.cn_dn,
            dong_xe_yeu_cau="Ford Explorer Limited",
            phien_ban_yeu_cau="Limited",
            mau_sac_yeu_cau="Đen",
            trang_thai=TrangThaiHopDong.CHO_XU_LY,
            ngay_ky=date(2026, 11, 1)
        )

        initial_count = tinh_hop_dong_cho_giao_thuc_te("Explorer")
        self.assertEqual(initial_count, 1)

        # Sau khi hoàn tất hợp đồng (HOAN_TAT), số hợp đồng chờ giao phải giảm về 0
        hd.trang_thai = TrangThaiHopDong.HOAN_TAT
        hd.save(update_fields=['trang_thai'])

        after_complete_count = tinh_hop_dong_cho_giao_thuc_te("Explorer")
        self.assertEqual(after_complete_count, 0)

    def test_detail_view_renders_allocation_schedule_and_color_filter(self):
        """Trang chi tiết hợp đồng hiển thị lịch phân bổ dự kiến cập bến kho Đà Nẵng và bộ lọc nâng cao màu sắc trong modal chọn ngày giao."""
        from orders.models import Allocation

        alloc1 = Allocation.objects.create(
            order_number="ORD-MODAL-01",
            vehicle_code="EVEREST",
            description="Ford Everest Titanium 4x2",
            vin="RL2MODALALLOC0001",
            mau_sac="Trắng Ngọc Trai",
            exterior_color="Trắng Ngọc Trai",
            allocation_month=date(2026, 11, 1),
            expected_ship_date=date(2026, 11, 18),
            contractual_delivery_date=date(2026, 11, 22),
            quantity=1,
            chi_nhanh=self.cn_dn
        )
        alloc2 = Allocation.objects.create(
            order_number="ORD-MODAL-02",
            vehicle_code="EVEREST",
            description="Ford Everest Titanium 4x2",
            vin="RL2MODALALLOC0002",
            mau_sac="Đen Ánh Kim",
            exterior_color="Đen Ánh Kim",
            allocation_month=date(2026, 11, 1),
            expected_ship_date=date(2026, 11, 20),
            contractual_delivery_date=date(2026, 11, 25),
            quantity=1,
            chi_nhanh=self.cn_dn
        )

        hd = HopDong.objects.create(
            ma_hd="HD-MODAL-DATE-01",
            khach_hang=self.kh,
            chi_nhanh=self.cn_dn,
            dong_xe_yeu_cau="Ford Everest",
            phien_ban_yeu_cau="Titanium",
            mau_sac_yeu_cau="Trắng Ngọc Trai",
            trang_thai=TrangThaiHopDong.CHO_XU_LY,
            ngay_ky=date(2026, 11, 1)
        )

        url = reverse("contracts:detail", args=[hd.ma_hd])
        resp = self.client.get(url, HTTP_ACCEPT="text/html")
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode("utf-8")

        # Kiểm tra bảng tra cứu lịch phân bổ và bộ lọc nâng cao màu xe
        self.assertIn("modalAllocTable", html)
        self.assertIn("modalColorFilter", html)
        self.assertIn("RL2MODALALLOC0001", html)
        self.assertIn("RL2MODALALLOC0002", html)
        self.assertIn("Trắng Ngọc Trai", html)
        self.assertIn("Đen Ánh Kim", html)
        self.assertIn("22/11/2026", html)

    def test_pyc_waiting_pdi_blocked_when_da_nang_has_stock(self):
        """Khi kho Đà Nẵng còn xe phù hợp, chặn cứng việc chốt xe từ PYC chờ PDI (Tầng 3)."""
        from orders.models import Allocation, VehicleRequest, VehicleRequestItem
        from warehouse.order_intake import sync_request

        # Tạo 1 xe sẵn sàng tại kho Đà Nẵng
        car_dn = Xe.objects.create(
            vin="VN-DN-STOCK-99",
            ten_xe="Ford Transit",
            phien_ban="Trend",
            loai_xe="Transit",
            mau_sac="Bạc",
            so_may="SM-DN-99",
            trang_thai=TrangThaiXe.SAN_SANG
        )
        TonKho.objects.create(kho=self.kho_dn, xe=car_dn, so_luong_ton=1, ngay_vao_kho=timezone.localdate())

        # Tạo 1 xe từ PYC chờ PDI
        alloc = Allocation.objects.create(
            order_number="ORD-PYC-BLK", vehicle_code="TRANSIT", description="Ford Transit Trend",
            vin="VIN-PYC-BLOCKED-01", mau_sac="Bạc", exterior_color="Bạc", engine_number="SM-PYC-BLK",
            allocation_month=date(2026, 10, 1), quantity=1, chi_nhanh=self.cn_dn,
        )
        pyc = VehicleRequest.objects.create(created_by=self.user, status=VehicleRequest.Status.ACCEPTED)
        VehicleRequestItem.objects.create(vehicle_request=pyc, allocation=alloc, quantity=1)
        sync_request(pyc.pk)

        hd = HopDong.objects.create(
            ma_hd="HD-PYC-BLOCKED-01",
            khach_hang=self.kh,
            chi_nhanh=self.cn_dn,
            dong_xe_yeu_cau="Ford Transit",
            phien_ban_yeu_cau="Trend",
            mau_sac_yeu_cau="Bạc",
            trang_thai=TrangThaiHopDong.CHO_XU_LY,
            ngay_ky=date(2026, 11, 1)
        )

        # Cố tình chốt xe PYC chờ PDI khi Đà Nẵng còn xe -> Bị chặn cứng
        with self.assertRaises(ValidationError) as ctx:
            choose_vehicle(hd.pk, "VIN-PYC-BLOCKED-01", self.user)
        self.assertIn("Kho Đà Nẵng còn", str(ctx.exception))

    def test_danh_sach_yeu_cau_shows_contract_badge_and_rejected_phieu_shows_banner(self):
        """Kiểm tra giao diện Danh sách yêu cầu hiển thị badge HĐ liên kết và trang chi tiết phiếu bị từ chối hiển thị lý do."""
        from orders.models import Allocation, VehicleRequest, VehicleRequestItem

        alloc = Allocation.objects.create(
            order_number="ORD-UI-01",
            vehicle_code="TERRITORY",
            description="Ford Territory Titanium",
            vin="RL2UITEST00000001",
            mau_sac="Trắng",
            exterior_color="Trắng",
            allocation_month=date(2026, 11, 1),
            quantity=1,
            chi_nhanh=self.cn_dn
        )
        hd = HopDong.objects.create(
            ma_hd="HD-UI-BADGE-01",
            khach_hang=self.kh,
            chi_nhanh=self.cn_dn,
            dong_xe_yeu_cau="Ford Territory Titanium",
            phien_ban_yeu_cau="Titanium",
            mau_sac_yeu_cau="Trắng",
            trang_thai=TrangThaiHopDong.CHO_XU_LY,
            ngay_ky=date(2026, 10, 15)
        )

        # Chốt xe phân bổ cho hợp đồng -> Đưa vào Danh sách xe đã chọn đặt hàng -> Lập PYC
        self.client.post(reverse("contracts:choose_allocation_vehicle", args=[hd.ma_hd, alloc.id]))
        resp_orders = self.client.get(reverse("orders:vehicle_orders"))
        self.assertEqual(resp_orders.status_code, 200)
        self.assertIn("Đặt theo HĐ HD-UI-BADGE-01", resp_orders.content.decode("utf-8"))

        self.client.get(reverse("orders:lap_phieu_yeu_cau"))

        # Mở danh sách yêu cầu bên module orders -> Phải thấy badge "Đặt theo HĐ HD-UI-BADGE-01"
        resp_list = self.client.get(reverse("orders:danh_sach_yeu_cau"))
        self.assertEqual(resp_list.status_code, 200)
        self.assertIn("Đặt theo HĐ HD-UI-BADGE-01", resp_list.content.decode("utf-8"))

        # Tạo 1 phiếu PENDING khác rồi bấm từ chối
        alloc2 = Allocation.objects.create(
            order_number="ORD-UI-02",
            vehicle_code="RANGER",
            description="Ford Ranger XLS",
            vin="RL2UITEST00000002",
            mau_sac="Đen",
            exterior_color="Đen",
            allocation_month=date(2026, 11, 1),
            quantity=1,
            chi_nhanh=self.cn_dn
        )
        req_reject = VehicleRequest.objects.create(
            created_by=self.user,
            status=VehicleRequest.Status.PENDING,
            sent_at=timezone.now()
        )
        VehicleRequestItem.objects.create(vehicle_request=req_reject, allocation=alloc2, quantity=1)

        self.client.post(reverse("orders:tu_choi_phieu", args=[req_reject.id]), {"ly_do": "Sai cấu hình màu ngoại thất"})
        resp_detail = self.client.get(reverse("orders:phieu_yeu_cau", args=[req_reject.id]))
        self.assertEqual(resp_detail.status_code, 200)
        html_detail = resp_detail.content.decode("utf-8")
        self.assertIn("Đã từ chối", html_detail)
        self.assertIn("Sai cấu hình màu ngoại thất", html_detail)
        self.assertIn("tự động nhả về trạng thái", html_detail)

    def test_proposal_list_view_updates_hop_dong_cho_giao_live_after_chot_xe(self):
        """Màn hình Đề xuất nhập xe (orders:proposal_list & proposal_detail) cập nhật ngay cột Hợp đồng chờ giao xe khi chốt xe."""
        from analytics.models import PhienDuBao, DongDuBao

        today = timezone.localdate()
        phien = PhienDuBao.objects.create(
            thang=today.month,
            nam=today.year,
            nguoi_tao=self.user
        )
        # Snapshot cũ trong DongDuBao đang có hop_dong_cho_giao = 0
        dong = DongDuBao.objects.create(
            phien=phien,
            loai_xe="SUV",
            ma_dong_xe="EVEREST-PLATINUM",
            ten_xe="Ford Everest Platinum",
            ten_ngan="Ford Everest",
            phien_ban="Platinum",
            du_bao_sarima=2.0,
            hop_dong_cho_giao=0,
            ton_kho=0,
            de_xuat_poq=2
        )

        # Tạo hợp đồng và chốt 1 xe Ford Everest Platinum
        car = Xe.objects.create(
            vin="VN-PLATINUM-LIVE-01",
            ten_xe="Ford Everest Platinum",
            phien_ban="Platinum",
            loai_xe="Everest",
            mau_sac="Đen",
            so_may="SM-PLAT-01",
            trang_thai=TrangThaiXe.SAN_SANG
        )
        TonKho.objects.create(kho=self.kho_dn, xe=car, so_luong_ton=1, ngay_vao_kho=today)

        hd = HopDong.objects.create(
            ma_hd="HD-PLATINUM-LIVE-01",
            khach_hang=self.kh,
            chi_nhanh=self.cn_dn,
            dong_xe_yeu_cau="Ford Everest Platinum",
            phien_ban_yeu_cau="Platinum",
            mau_sac_yeu_cau="Đen",
            trang_thai=TrangThaiHopDong.CHO_XU_LY,
            ngay_ky=timezone.now()
        )
        choose_vehicle(hd.pk, car.vin, self.user)

        # Truy cập trang danh sách đề xuất và chi tiết đề xuất
        resp_list = self.client.get(reverse("orders:proposal_list") + f"?month={today.year}-{today.month:02d}")
        self.assertEqual(resp_list.status_code, 200)
        danh_sach = resp_list.context["danh_sach"]
        row = next((item for item in danh_sach if item["dong_id"] == dong.id), None)
        self.assertIsNotNone(row)
        self.assertEqual(row["hop_dong_cho_giao"], 1)

        resp_detail = self.client.get(reverse("orders:proposal_detail", args=[dong.id]))
        self.assertEqual(resp_detail.status_code, 200)
        self.assertEqual(resp_detail.context["hop_dong_cho_giao"], 1)

    def test_big_update_3_warehouse_receipt_form_manual_and_preset_transfer(self):
        """Mục 1: Tạo phiếu nhập thủ công chỉ nhập tên dòng xe (không droplist, không NCC); từ nút Lập phiếu thì đọc thẳng xe lưu chuyển."""
        from transfers.models import LenhLuuChuyen
        from transfers.services import tao_lenh_luu_chuyen, gui_lenh_luu_chuyen, duyet_lenh_luu_chuyen
        from warehouse.models import PhieuNhapKho

        # 1. Kiểm tra chế độ tạo phiếu thủ công: không có <select name="nguon_xe">, có input name="ten_dong_xe"
        resp_manual = self.client.get(reverse("warehouse:receipt_create_page"), HTTP_ACCEPT="text/html")
        self.assertEqual(resp_manual.status_code, 200)
        html_manual = resp_manual.content.decode("utf-8")
        self.assertNotIn('<select class="select" name="nguon_xe"', html_manual)
        self.assertIn('name="ten_dong_xe"', html_manual)

        # Tạo 1 xe sẵn sàng tại chi nhánh Bình Định rồi lập phiếu nhập kho thủ công chỉ bằng Tên dòng xe
        car_bd = Xe.objects.create(
            vin="VN-MANUAL-NHAP-01",
            ten_xe="Ford Explorer Limited",
            phien_ban="Limited",
            loai_xe="Explorer",
            mau_sac="Đỏ",
            so_may="SM-MAN-01",
            trang_thai=TrangThaiXe.SAN_SANG
        )
        TonKho.objects.create(kho=self.kho_bd, xe=car_bd, so_luong_ton=1, ngay_vao_kho=timezone.localdate())

        resp_post = self.client.post(reverse("warehouse:receipt_create_page"), {
            "ten_dong_xe": "Ford Explorer Limited",
            "kho_id": self.kho_dn.pk,
            "ngay_nhap": timezone.localdate().isoformat(),
        })
        self.assertEqual(resp_post.status_code, 302)
        self.assertTrue(PhieuNhapKho.objects.filter(xe=car_bd).exists())

        # 2. Kiểm tra chế độ bấm "Lập phiếu" từ dòng Lệnh lưu chuyển bên ngoài (?nguon_xe=luu-chuyen:<id>)
        car_tf = Xe.objects.create(
            vin="VN-PRESET-TF-001",
            ten_xe="Ford Territory Titanium",
            phien_ban="Titanium",
            loai_xe="Territory",
            mau_sac="Trắng",
            so_may="SM-TF-01",
            trang_thai=TrangThaiXe.SAN_SANG
        )
        TonKho.objects.create(kho=self.kho_bd, xe=car_tf, so_luong_ton=1, ngay_vao_kho=timezone.localdate())
        lenh = tao_lenh_luu_chuyen(self.user, self.kho_bd, self.kho_dn, ds_xe=[car_tf])
        lenh = gui_lenh_luu_chuyen(self.user, lenh.pk)
        lenh = duyet_lenh_luu_chuyen(self.user, lenh.pk)
        from transfers.services import xac_nhan_xuat_kho_nguon
        dvvc_tf, _ = DonViVanChuyen.objects.get_or_create(ma_dvvc="DVVC_TF_01", defaults={"ten_dvvc": "Vận tải ĐN", "sdt_dvvc": "0905111222"})
        lenh = xac_nhan_xuat_kho_nguon(
            self.user,
            lenh.pk,
            don_vi_van_chuyen_id=dvvc_tf.pk,
            bien_so_xe="43C-666.88",
            tai_xe="Lê Văn Tài",
            ngay_du_kien_den=timezone.localdate(),
        )
        ct_tf = lenh.chi_tiet.first()

        resp_preset = self.client.get(
            reverse("warehouse:receipt_create_page") + f"?nguon_xe=luu-chuyen:{ct_tf.pk}",
            HTTP_ACCEPT="text/html"
        )
        self.assertEqual(resp_preset.status_code, 200)
        html_preset = resp_preset.content.decode("utf-8")
        self.assertNotIn('<select class="select" name="nguon_xe"', html_preset)
        self.assertIn(f'type="hidden" name="nguon_xe" value="luu-chuyen:{ct_tf.pk}"', html_preset)
        self.assertIn("VN-PRESET-TF-001", html_preset)

    def test_big_update_3_contract_only_two_statuses_and_transfer_from_branch_ui(self):
        """Mục 3 & 4: Hợp đồng chỉ hiển thị 2 trạng thái (Chờ xử lý / Hoàn tất) và cho phép gắn HĐ Đà Nẵng ngay tại trang Lưu chuyển xe."""
        hd1 = HopDong.objects.create(
            ma_hd="HD-2STATE-01",
            khach_hang=self.kh,
            chi_nhanh=self.cn_dn,
            dong_xe_yeu_cau="Ford Everest",
            phien_ban_yeu_cau="Titanium",
            mau_sac_yeu_cau="Trắng",
            trang_thai=TrangThaiHopDong.CHO_PHAN_BO,
            ngay_ky=date(2026, 10, 15)
        )
        resp_idx = self.client.get(reverse("contracts:index"), HTTP_ACCEPT="text/html")
        self.assertEqual(resp_idx.status_code, 200)
        opts = resp_idx.context["trang_thai_options"]
        self.assertEqual(len(opts), 2)
        self.assertEqual([o[1] for o in opts], ["Chờ xử lý", "Hoàn tất"])

        # Hợp đồng CHO_PHAN_BO cũng hiển thị là "Chờ xử lý"
        row_hd1 = next((r for r in resp_idx.context["hop_dong"] if r["ma_hd"] == hd1.ma_hd), None)
        self.assertIsNotNone(row_hd1)
        self.assertEqual(row_hd1["trang_thai_hien_thi"], "Chờ xử lý")

        # Tạo xe ở chi nhánh Bình Định và gắn trực tiếp cho HĐ Đà Nẵng từ màn hình Lưu chuyển (/luu-chuyen/chi-tiet-xe/<id>/)
        car_gl = Xe.objects.create(
            vin="VN-GL-TO-DN-001",
            ten_xe="Ford Everest Titanium",
            phien_ban="Titanium",
            loai_xe="Everest",
            mau_sac="Trắng",
            so_may="SM-GL-01",
            trang_thai=TrangThaiXe.SAN_SANG
        )
        ton_gl = TonKho.objects.create(kho=self.kho_bd, xe=car_gl, so_luong_ton=1, ngay_vao_kho=timezone.localdate())

        resp_tf = self.client.post(reverse("transfers:chi_tiet_xe", args=[ton_gl.pk]), {
            "kho_nhan": self.kho_dn.pk,
            "so_luong": "1",
            "hop_dong_id": hd1.ma_hd,
        })
        self.assertEqual(resp_tf.status_code, 302)
        hd1.refresh_from_db()
        # Sau khi gắn xe và lập lệnh lưu chuyển, trạng thái hiển thị của hợp đồng chuyển sang "Hoàn tất"
        resp_idx2 = self.client.get(reverse("contracts:index") + "?trang_thai=HOAN_TAT", HTTP_ACCEPT="text/html")
        row_after = next((r for r in resp_idx2.context["hop_dong"] if r["ma_hd"] == hd1.ma_hd), None)
        self.assertIsNotNone(row_after)
        self.assertEqual(row_after["trang_thai_hien_thi"], "Hoàn tất")

    def test_big_update_3_buttons_money_dates_and_alerts(self):
        """Kiểm tra giữ 1 nút thao tác trên cùng ở detail, format tiền 600.000.000, lọc kỳ phân bổ >= tháng ký và cảnh báo hết hàng."""
        from decimal import Decimal
        from orders.models import Allocation
        from alerts.models import CanhBao

        hd_money = HopDong.objects.create(
            ma_hd="HD-MONEY-BTN-01",
            khach_hang=self.kh,
            chi_nhanh=self.cn_dn,
            dong_xe_yeu_cau="Ford Ranger Wildtrak",
            phien_ban_yeu_cau="Wildtrak",
            mau_sac_yeu_cau="Trắng",
            so_tien_coc=Decimal("600000000.00"),
            trang_thai=TrangThaiHopDong.CHO_XU_LY,
            ngay_ky=date(2026, 10, 15),
        )
        car_dn = Xe.objects.create(
            vin="VN-BTN-TEST-0001",
            ten_xe="Ford Ranger Wildtrak",
            phien_ban="Wildtrak",
            loai_xe="Ranger",
            mau_sac="Trắng",
            so_may="SM-BTN-01",
            trang_thai=TrangThaiXe.SAN_SANG,
        )
        TonKho.objects.create(kho=self.kho_dn, xe=car_dn, so_luong_ton=1, ngay_vao_kho=timezone.localdate())
        choose_vehicle(hd_money.ma_hd, car_dn.vin, self.user)

        resp_dt = self.client.get(reverse("contracts:detail", args=[hd_money.ma_hd]), HTTP_ACCEPT="text/html")
        self.assertEqual(resp_dt.status_code, 200)
        html_dt = resp_dt.content.decode("utf-8")
        # 1. Định dạng tiền 600.000.000
        self.assertIn("600.000.000", html_dt)
        self.assertNotIn("600000000,00", html_dt)
        # 2. Chỉ giữ 1 nút Duyệt xuất kho ở trên cùng, xóa 2 nút trùng bên dưới
        self.assertIn("Duyệt xuất kho (", html_dt)
        self.assertNotIn("Chuyển tới Quản lý xuất kho để duyệt", html_dt)
        self.assertNotIn("Duyệt xuất kho tại Quản lý xuất kho", html_dt)
        self.assertNotIn("Xuất kho xe & Hoàn tất hợp đồng", html_dt)

        # 3. Kiểm tra hợp đồng tháng 10 không lấy phân bổ tháng 08/09 và tự chuẩn hóa ngày giao theo tháng phân bổ
        Allocation.objects.create(
            order_number="ORD-OLD-08",
            vehicle_code="TERRITORY",
            description="Ford Territory Titanium",
            vin="RL2OLD08000000001",
            mau_sac="Đỏ Cam",
            allocation_month=date(2026, 8, 1),
            contractual_delivery_date=date(2026, 8, 25),
            quantity=1,
        )
        alloc_11 = Allocation.objects.create(
            order_number="ORD-NEW-11",
            vehicle_code="TERRITORY",
            description="Ford Territory Titanium",
            vin="RL2NEW11000000001",
            mau_sac="Đỏ Cam",
            allocation_month=date(2026, 11, 1),
            contractual_delivery_date=date(2026, 9, 15),  # Ngày cũ bị lệch tháng 9
            quantity=1,
        )
        hd_t10 = HopDong.objects.create(
            ma_hd="HD-T10-CHECK-PB",
            khach_hang=self.kh,
            chi_nhanh=self.cn_dn,
            dong_xe_yeu_cau="Ford Territory Titanium",
            phien_ban_yeu_cau="Titanium",
            mau_sac_yeu_cau="Đỏ Cam",
            trang_thai=TrangThaiHopDong.CHO_XU_LY,
            ngay_ky=date(2026, 10, 20),
        )
        from .views import find_allocation_vehicles, criteria_for
        crits, _ = criteria_for(hd_t10)
        matched_pb = find_allocation_vehicles(hd_t10, crits)
        vins_pb = [x["vin"] for x in matched_pb]
        self.assertNotIn("RL2OLD08000000001", vins_pb)
        self.assertIn("RL2NEW11000000001", vins_pb)
        row_11 = next(x for x in matched_pb if x["vin"] == "RL2NEW11000000001")
        self.assertEqual(row_11["contractual_delivery_date"].month, 11)

        # 4. Kiểm tra xuất kho 1 xe duy nhất (1 -> 0) tự động cập nhật cảnh báo Hết hàng và xuất CSV hết hàng
        resp_ht = self.client.post(reverse("contracts:hoan_tat", args=[hd_money.ma_hd]))
        self.assertEqual(resp_ht.status_code, 302)
        cb_het = CanhBao.objects.filter(nguong__ten_xe="Ranger", nguong__mau_sac="Trắng", con_hieu_luc=True).first()
        self.assertIsNotNone(cb_het)
        self.assertEqual(cb_het.loai, CanhBao.Loai.HET_HANG)
        self.assertEqual(cb_het.so_luong_hien_tai, 0)

        resp_csv = self.client.get(reverse("alerts:xuat_het_hang"))
        self.assertEqual(resp_csv.status_code, 200)
        self.assertIn("Ranger", resp_csv.content.decode("utf-8-sig"))

    def test_big_update_3_hardening_fixes(self):
        """Kiểm tra import Excel hợp đồng linh hoạt, giỏ Đặt xe bền vững qua DB (khác session) và chặn xuất bán khi chưa nhập kho/PDI."""
        import io
        import openpyxl
        from decimal import Decimal
        from orders.models import Allocation, VehicleRequest
        from . import contract_import

        # 1. Import Excel hợp đồng với tên cột tiếng Việt, đổi thứ tự cột, ngày dạng text dd/mm/yyyy, tiền 600.000.000
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append([
            "Mã hợp đồng", "Mã khách hàng", "Tên khách hàng", "SĐT", "MST",
            "Mã chi nhánh", "Ngày ký", "Tiền đặt cọc", "Dòng xe", "Phiên bản", "Màu sắc"
        ])
        ws.append([
            "HD-IMP-FLEX-01", "KH-FLEX-01", "Nguyễn Flex", "0905123456", "",
            self.cn_dn.pk, "15/10/2026", "600.000.000", "Ford Ranger", "Wildtrak", "Đen"
        ])
        buf = io.BytesIO()
        wb.save(buf)
        parsed = contract_import.read_file(buf.getvalue())
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["ngay_ky"], date(2026, 10, 15))
        self.assertEqual(parsed[0]["so_tien_coc"], Decimal("600000000"))

        # 2. Chốt xe phân bổ -> đăng nhập ở Client mới (khác session) vẫn thấy trong /dat-xe/ và lập PYC được
        alloc = Allocation.objects.create(
            order_number="ORD-CROSS-01",
            vehicle_code="EXPLORER",
            description="Ford Explorer Limited",
            vin="RL2CROSSSESS00001",
            mau_sac="Trắng",
            exterior_color="Trắng",
            allocation_month=date(2026, 11, 1),
            quantity=1,
            chi_nhanh=self.cn_dn,
        )
        hd_pb = HopDong.objects.create(
            ma_hd="HD-CROSS-SESS-01",
            khach_hang=self.kh,
            chi_nhanh=self.cn_dn,
            dong_xe_yeu_cau="Ford Explorer Limited",
            phien_ban_yeu_cau="Limited",
            mau_sac_yeu_cau="Trắng",
            trang_thai=TrangThaiHopDong.CHO_XU_LY,
            ngay_ky=date(2026, 10, 15),
        )
        self.client.post(reverse("contracts:choose_allocation_vehicle", args=[hd_pb.ma_hd, alloc.id]))

        # Cố tình bấm Hoàn tất xuất bán khi xe CHƯA nhập kho Đà Nẵng / chưa PDI -> Bị chặn cứng
        self.client.post(reverse("contracts:hoan_tat", args=[hd_pb.ma_hd]))
        hd_pb.refresh_from_db()
        self.assertEqual(hd_pb.trang_thai, TrangThaiHopDong.CHO_XE_VE_KHO)

        # Mở trình duyệt / session mới hoàn toàn với 1 tài khoản khác
        User = get_user_model()
        user_b = User.objects.create_superuser(username="order_staff_b", password="password123", email="b@danaford.vn")
        client_b = Client()
        client_b.force_login(user_b)
        resp_orders_b = client_b.get(reverse("orders:vehicle_orders"))
        self.assertEqual(resp_orders_b.status_code, 200)
        self.assertIn("RL2CROSSSESS00001", resp_orders_b.content.decode("utf-8"))
        self.assertIn("Đặt theo HĐ HD-CROSS-SESS-01", resp_orders_b.content.decode("utf-8"))

        client_b.get(reverse("orders:lap_phieu_yeu_cau"))
        vr_b = VehicleRequest.objects.filter(items__allocation=alloc, hop_dong=hd_pb).first()
        self.assertIsNotNone(vr_b)
        self.assertEqual(vr_b.status, VehicleRequest.Status.DRAFT)

    def test_spec_4_images_strict_color_no_hardcode_and_idempotency(self):
        """Kiểm tra toàn bộ 4 ảnh đặc tả: ẩn xe khác màu, 'Không có xe phù hợp', kỳ phân bổ liền sau tháng ký, chống bấm trùng."""
        from orders.models import Allocation
        from transfers.models import LenhLuuChuyen

        # 1. Xe khác màu ở Đà Nẵng (Trắng), Bình Định (Bạc) và Phân bổ (Trắng) đều KHÔNG được xuất hiện
        car_dn_wrong = Xe.objects.create(
            vin="VN-WRONG-DN-01", ten_xe="Ford Everest Titanium+", phien_ban="Titanium+",
            mau_sac="Trắng", so_may="SM-WDN01", trang_thai=TrangThaiXe.SAN_SANG
        )
        TonKho.objects.create(kho=self.kho_dn, xe=car_dn_wrong, so_luong_ton=1, ngay_vao_kho=timezone.localdate())

        car_bd_wrong = Xe.objects.create(
            vin="VN-WRONG-BD-01", ten_xe="Ford Everest Titanium+", phien_ban="Titanium+",
            mau_sac="Bạc", so_may="SM-WBD01", trang_thai=TrangThaiXe.SAN_SANG
        )
        TonKho.objects.create(kho=self.kho_bd, xe=car_bd_wrong, so_luong_ton=1, ngay_vao_kho=timezone.localdate())

        # Hợp đồng ký Tháng 11/2026 đòi màu Đen -> chỉ tìm phân bổ từ Tháng 12/2026 trở đi
        hd_black = HopDong.objects.create(
            ma_hd="HD-STRICT-BLACK", khach_hang=self.kh, chi_nhanh=self.cn_dn,
            dong_xe_yeu_cau="Ford Everest Titanium+", phien_ban_yeu_cau="Titanium+",
            mau_sac_yeu_cau="Đen", trang_thai=TrangThaiHopDong.CHO_XU_LY,
            ngay_ky=date(2026, 11, 10),
        )
        # Phân bổ tháng 11/2026 (cùng tháng ký) và khác màu tháng 12 đều bị loại
        Allocation.objects.create(
            order_number="ORD-SAME-11", vehicle_code="EVEREST", description="Ford Everest Titanium+",
            vin="RL2SAME11BLACK001", mau_sac="Đen", exterior_color="Đen",
            allocation_month=date(2026, 11, 1), quantity=1, chi_nhanh=self.cn_dn,
        )
        alloc_wrong_color = Allocation.objects.create(
            order_number="ORD-DIFF-12", vehicle_code="EVEREST", description="Ford Everest Titanium+",
            vin="RL2DIFF12WHITE001", mau_sac="Trắng", exterior_color="Trắng",
            allocation_month=date(2026, 12, 1), quantity=1, chi_nhanh=self.cn_dn,
        )

        resp_empty = self.client.get(reverse("contracts:xe_phu_hop", args=[hd_black.ma_hd]), HTTP_ACCEPT="text/html")
        self.assertEqual(resp_empty.status_code, 200)
        html_empty = resp_empty.content.decode("utf-8")
        self.assertNotIn("VN-WRONG-DN-01", html_empty)
        self.assertNotIn("VN-WRONG-BD-01", html_empty)
        self.assertNotIn("RL2SAME11BLACK001", html_empty)
        self.assertNotIn("RL2DIFF12WHITE001", html_empty)
        self.assertEqual(html_empty.count("Không có xe phù hợp"), 3)

        # Cố tình POST chọn phân bổ khác màu hoặc cùng tháng ký -> bị chặn
        self.client.post(reverse("contracts:choose_allocation_vehicle", args=[hd_black.ma_hd, alloc_wrong_color.id]))
        hd_black.refresh_from_db()
        self.assertEqual(hd_black.trang_thai, TrangThaiHopDong.CHO_XU_LY)

        # Tháng 12 không có, sang Tháng 01/2027 có xe Đen -> tự động tìm thấy kỳ Tháng 01/2027 (không hardcode 11/2026)
        alloc_jan = Allocation.objects.create(
            order_number="ORD-JAN-27", vehicle_code="EVEREST", description="Ford Everest Titanium+",
            vin="RL2JAN27BLACK0001", mau_sac="Đen", exterior_color="Đen",
            allocation_month=date(2027, 1, 1), quantity=1, chi_nhanh=self.cn_dn,
        )
        resp_jan = self.client.get(reverse("contracts:xe_phu_hop", args=[hd_black.ma_hd]), HTTP_ACCEPT="text/html")
        html_jan = resp_jan.content.decode("utf-8")
        self.assertIn("RL2JAN27BLACK0001", html_jan)
        self.assertIn("Tháng 01/2027", html_jan)
        self.assertNotIn("(Tháng 11/2026)", html_jan)

        # Chốt 2 lần liên tiếp cùng hợp đồng -> chỉ giữ 1 ChiTietHopDong, không trùng
        self.client.post(reverse("contracts:choose_allocation_vehicle", args=[hd_black.ma_hd, alloc_jan.id]))
        self.client.post(reverse("contracts:choose_allocation_vehicle", args=[hd_black.ma_hd, alloc_jan.id]))
        self.assertEqual(ChiTietHopDong.objects.filter(hop_dong=hd_black).count(), 1)

        # Kiểm tra chống chốt trùng cho nguồn Bình Định/Gia Lai (CHO_XE_VE_KHO)
        car_bd_ok = Xe.objects.create(
            vin="VN-OK-BD-01", ten_xe="Ford Everest Titanium+", phien_ban="Titanium+",
            mau_sac="Đen", so_may="SM-OBD01", trang_thai=TrangThaiXe.SAN_SANG
        )
        car_bd_ok2 = Xe.objects.create(
            vin="VN-OK-BD-02", ten_xe="Ford Everest Titanium+", phien_ban="Titanium+",
            mau_sac="Đen", so_may="SM-OBD02", trang_thai=TrangThaiXe.SAN_SANG
        )
        TonKho.objects.create(kho=self.kho_bd, xe=car_bd_ok, so_luong_ton=1, ngay_vao_kho=timezone.localdate())
        TonKho.objects.create(kho=self.kho_bd, xe=car_bd_ok2, so_luong_ton=1, ngay_vao_kho=timezone.localdate())
        hd_bd = HopDong.objects.create(
            ma_hd="HD-STRICT-BD", khach_hang=self.kh, chi_nhanh=self.cn_dn,
            dong_xe_yeu_cau="Ford Everest Titanium+", phien_ban_yeu_cau="Titanium+",
            mau_sac_yeu_cau="Đen", trang_thai=TrangThaiHopDong.CHO_XU_LY, ngay_ky=date(2026, 11, 10),
        )
        choose_vehicle(hd_bd.ma_hd, car_bd_ok.vin, self.user)
        with self.assertRaises(ValidationError):
            choose_vehicle(hd_bd.ma_hd, car_bd_ok2.vin, self.user)
        self.assertEqual(LenhLuuChuyen.objects.filter(chi_tiet__xe__chitiethopdong__hop_dong=hd_bd).count(), 1)
