from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from database.models import ChiNhanh, ChiTietNhap, DonViVanChuyen, HoaDonNhap, Kho, NhaCungCap, TonKho, Xe
from orders.models import Allocation, VehicleRequest, VehicleRequestItem
from warehouse.models import PhieuNhapKho
from warehouse.order_intake import sync_request


class OrderIntakeTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_superuser(username='order_intake_test', password='test-pass')
        self.user = user
        self.order = VehicleRequest.objects.create(created_by=user, status=VehicleRequest.Status.ACCEPTED)
        self.allocation = Allocation.objects.create(order_number='ORDER-1', vehicle_code='RANGER',
            description='Ford Ranger', vin='TEST-VIN-ORDER-001', color_code='W',
            exterior_color='Trắng', engine_number='TEST-ENGINE-ORDER-001')
        VehicleRequestItem.objects.create(vehicle_request=self.order, allocation=self.allocation, quantity=1)

    def test_pyc_creates_a_real_draft_receipt_and_source_document(self):
        self.assertEqual(sync_request(self.order.pk), 1)
        receipt = PhieuNhapKho.objects.get(xe_id=self.allocation.vin)
        self.assertEqual(receipt.ma_phieu, f'PN-PYC-{self.order.pk}-1')
        self.assertEqual(receipt.trang_thai, 'NHAP')
        self.assertFalse(receipt.cac_lan_pdi.exists())
        self.assertFalse(TonKho.objects.filter(xe_id=self.allocation.vin).exists())

    def test_selected_car_appears_in_main_receipt_table_before_order_submission(self):
        self.order.status = VehicleRequest.Status.DRAFT
        self.order.save(update_fields=['status'])
        self.client.force_login(self.user)
        session = self.client.session
        session['selected_vehicles'] = {str(self.allocation.pk): 1}
        session.save()
        response = self.client.get('/kho/nhap/', HTTP_ACCEPT='text/html')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.allocation.vin)
        self.assertContains(response, 'Đang chọn đặt xe')
        self.assertNotContains(response, 'Xe đã đặt đang chờ chứng từ nhập')
        self.assertEqual(PhieuNhapKho.objects.count(), 0)

    def test_sync_is_idempotent_and_never_creates_stock(self):
        self.assertEqual(sync_request(self.order.pk), 1)
        self.assertEqual(sync_request(self.order.pk), 0)
        receipt = PhieuNhapKho.objects.get(xe_id=self.allocation.vin)
        self.assertEqual(receipt.chi_tiet_nhap.hoa_don_nhap_id, f'HDN-PYC-{self.order.pk}')
        self.assertEqual(receipt.kho_id, 'KHO01')
        self.assertEqual(receipt.trang_thai, 'NHAP')
        self.assertFalse(receipt.cac_lan_pdi.exists())
        self.assertFalse(TonKho.objects.filter(xe_id=self.allocation.vin).exists())
