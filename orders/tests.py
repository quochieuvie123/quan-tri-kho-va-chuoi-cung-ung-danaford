import io
import openpyxl
from datetime import date
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from database.models import ChiNhanh, NhanVien
from orders.models import Allocation, VehicleRequest, VehicleRequestItem


class OrdersStage1Tests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_superuser(
            username="admin_orders",
            email="admin@orders.com",
            password="password123"
        )
        self.cn_dn = ChiNhanh.objects.create(
            ma_cn="CN01",
            ten_cn="Dana Ford Đà Nẵng",
            dia_chi_cn="Đà Nẵng"
        )
        self.nv = NhanVien.objects.create(
            ma_nv="NV_TEST_01",
            ten_nv="Tester",
            chi_nhanh=self.cn_dn,
            sdt_nv="0912345678"
        )
        self.user.nhan_vien = self.nv
        self.user.save()

        self.client = Client()
        self.client.force_login(self.user)

        self.alloc1 = Allocation.objects.create(
            vin="WF0TESTVIN0000001",
            vehicle_code="EVEREST",
            description="Everest Titanium 4x4",
            color_code="WH",
            exterior_color="Trắng",
            engine_number="ENG001",
            quantity=1,
            allocation_month=date(2026, 11, 1),
            chi_nhanh=self.cn_dn
        )

    def test_chi_tiet_xe_add_same_vin_twice(self):
        url = reverse("orders:chi_tiet_xe", args=[self.alloc1.id])

        # Lần 1: Thêm xe vào session
        response1 = self.client.post(url)
        self.assertEqual(response1.status_code, 302)
        session = self.client.session
        self.assertIn(str(self.alloc1.id), session.get("selected_vehicles", {}))
        self.assertEqual(session["selected_vehicles"][str(self.alloc1.id)], 1)

        # Lần 2: Thêm lại cùng xe/VIN -> Báo lỗi "Xe đã có trong phiếu."
        response2 = self.client.post(url)
        self.assertEqual(response2.status_code, 302)
        messages = list(get_messages(response2.wsgi_request))
        self.assertTrue(any("Xe đã có trong phiếu." in str(m) for m in messages))

        # Kiểm tra session vẫn chỉ có quantity = 1
        session = self.client.session
        self.assertEqual(session["selected_vehicles"][str(self.alloc1.id)], 1)

    def test_lap_phieu_yeu_cau_always_quantity_one(self):
        # Thiết lập session đã chọn xe
        session = self.client.session
        session["selected_vehicles"] = {str(self.alloc1.id): 1}
        session.save()

        lap_url = reverse("orders:lap_phieu_yeu_cau")
        response = self.client.get(lap_url)
        self.assertEqual(response.status_code, 302)

        phieu = VehicleRequest.objects.filter(created_by=self.user).last()
        self.assertIsNotNone(phieu)
        item = phieu.items.first()
        self.assertIsNotNone(item)
        self.assertEqual(item.quantity, 1)

    def test_import_excel_quantity_greater_than_one(self):
        # Tạo file Excel có một dòng quantity = 2
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append([
            "VIN", "MÃ DÒNG XE", "MÔ TẢ", "MÃ MÀU", "MÀU NGOẠI THẤT",
            "SỐ MÁY", "SỐ LƯỢNG", "SỐ ĐƠN ĐẶT HÀNG", "ĐẠI LÝ", "THÁNG"
        ])
        test_vin = "WF0EXCELQTY2VIN01"
        ws.append([
            test_vin, "RANGER", "Ranger Wildtrak", "BK", "Đen",
            "ENG_EXCEL_01", 2, "ORD9999", "Dana Ford Đà Nẵng", "11/2026"
        ])
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        uploaded = SimpleUploadedFile(
            "test_phan_bo.xlsx",
            buf.read(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

        upload_url = reverse("orders:allocation_list")
        response = self.client.post(upload_url, {"file": uploaded})
        self.assertEqual(response.status_code, 302)

        # Kiểm tra database lưu quantity = 1
        alloc = Allocation.objects.filter(vin=test_vin).first()
        self.assertIsNotNone(alloc)
        self.assertEqual(alloc.quantity, 1)

        # Kiểm tra có thông báo cảnh báo về số lượng > 1
        messages = list(get_messages(response.wsgi_request))
        self.assertTrue(
            any("chuẩn hóa về 1 xe" in str(m) or "chuẩn hóa về số lượng 1" in str(m) for m in messages),
            f"Expected warning message not found. Messages: {[str(m) for m in messages]}"
        )
