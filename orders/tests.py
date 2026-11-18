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


    def test_hold_minutes_default_ten_minutes(self):
        """Hạn giữ chỗ phiếu nháp mặc định 10 phút cấu hình trong settings."""
        from django.conf import settings
        self.assertEqual(getattr(settings, "ORDER_DRAFT_HOLD_MINUTES", 10), 10)

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

        # Kiểm tra database tách thành 2 xe riêng biệt với mã VIN hậu tố -1 và -2, quantity = 1
        alloc1 = Allocation.objects.filter(vin=f"{test_vin}-1").first()
        alloc2 = Allocation.objects.filter(vin=f"{test_vin}-2").first()
        self.assertIsNotNone(alloc1)
        self.assertIsNotNone(alloc2)
        self.assertEqual(alloc1.quantity, 1)
        self.assertEqual(alloc2.quantity, 1)

        # Kiểm tra có thông báo về việc tách xe và tạo mã VIN riêng biệt
        messages = list(get_messages(response.wsgi_request))
        self.assertTrue(
            any("tách thành từng xe riêng biệt" in str(m) or "hậu tố" in str(m) for m in messages),
            f"Expected message not found. Messages: {[str(m) for m in messages]}"
        )

from datetime import timedelta
from django.utils import timezone
from database.models import HopDong, ChiTietHopDong, Xe, KhachHang
from orders.availability import (
    get_allocation_status,
    get_available_allocations,
    release_expired_draft_requests,
    AllocationAvailabilityStatus
)
from contracts.views import find_allocation_vehicles


class OrdersStage2Tests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user1 = User.objects.create_superuser(
            username="user_sale_1",
            email="user1@orders.com",
            password="password123"
        )
        self.user2 = User.objects.create_superuser(
            username="user_sale_2",
            email="user2@orders.com",
            password="password123"
        )
        self.cn_dn = ChiNhanh.objects.create(
            ma_cn="CN01",
            ten_cn="Dana Ford Đà Nẵng",
            dia_chi_cn="Đà Nẵng"
        )
        self.alloc = Allocation.objects.create(
            vin="WF0STAGE2VIN000001",
            vehicle_code="EVEREST",
            description="Everest Titanium 4x4",
            color_code="WH",
            exterior_color="Trắng",
            engine_number="ENG002",
            quantity=1,
            allocation_month=date(2026, 11, 1),
            chi_nhanh=self.cn_dn
        )
        self.client1 = Client()
        self.client1.force_login(self.user1)

        self.client2 = Client()
        self.client2.force_login(self.user2)

    def test_phieu_nhap_qua_han_thi_nhap_xe(self):
        # Tạo phiếu DRAFT quá hạn 10 phút trước
        past_time = timezone.now() - timedelta(minutes=10)
        req = VehicleRequest.objects.create(
            created_by=self.user1,
            status=VehicleRequest.Status.DRAFT,
            hold_until=past_time
        )
        VehicleRequestItem.objects.create(
            vehicle_request=req,
            allocation=self.alloc,
            quantity=1
        )
        # Xe phải được tính là còn trống và hàm nhả giải phóng phiếu
        status_info = get_allocation_status(self.alloc)
        self.assertTrue(status_info["is_available"])
        self.assertEqual(status_info["status"], AllocationAvailabilityStatus.CON_TRONG)

    def test_gui_phieu_roi_thi_khong_nha_xe(self):
        # Tạo phiếu PENDING (đã gửi)
        req = VehicleRequest.objects.create(
            created_by=self.user1,
            status=VehicleRequest.Status.PENDING,
            sent_at=timezone.now() - timedelta(days=5),
            hold_until=None
        )
        VehicleRequestItem.objects.create(
            vehicle_request=req,
            allocation=self.alloc,
            quantity=1
        )
        status_info = get_allocation_status(self.alloc)
        self.assertFalse(status_info["is_available"])
        self.assertEqual(status_info["status"], AllocationAvailabilityStatus.DA_DAT)

    def test_tu_choi_thi_nha_xe(self):
        # Phiếu PENDING bị Sale Admin từ chối
        req = VehicleRequest.objects.create(
            created_by=self.user1,
            status=VehicleRequest.Status.PENDING,
            sent_at=timezone.now(),
        )
        VehicleRequestItem.objects.create(
            vehicle_request=req,
            allocation=self.alloc,
            quantity=1
        )
        # Từ chối phiếu
        tu_choi_url = reverse("orders:tu_choi_phieu", args=[req.id])
        resp = self.client1.post(tu_choi_url, {"ly_do": "Không đạt yêu cầu"})
        self.assertEqual(resp.status_code, 302)

        req.refresh_from_db()
        self.assertEqual(req.status, VehicleRequest.Status.REJECTED)

        # Xe trở lại Còn trống
        status_info = get_allocation_status(self.alloc)
        self.assertTrue(status_info["is_available"])
        self.assertEqual(status_info["status"], AllocationAvailabilityStatus.CON_TRONG)

    def test_hai_nguoi_chon_cung_vin(self):
        # User 1 lập phiếu nháp giữ xe
        future_time = timezone.now() + timedelta(minutes=30)
        req = VehicleRequest.objects.create(
            created_by=self.user1,
            status=VehicleRequest.Status.DRAFT,
            hold_until=future_time
        )
        VehicleRequestItem.objects.create(
            vehicle_request=req,
            allocation=self.alloc,
            quantity=1
        )

        # User 2 cố gắng chọn xe qua chi_tiet_xe
        url = reverse("orders:chi_tiet_xe", args=[self.alloc.id])
        resp = self.client2.post(url)
        self.assertEqual(resp.status_code, 302)
        messages = list(get_messages(resp.wsgi_request))
        self.assertTrue(any("không khả dụng" in str(m) or "Đang giữ chỗ" in str(m) for m in messages))

        # Session của User 2 không được lưu xe này
        session2 = self.client2.session
        self.assertNotIn(str(self.alloc.id), session2.get("selected_vehicles", {}))

    def test_xe_da_chot_hop_dong_khong_hien_khi_dat_xe(self):
        kh = KhachHang.objects.create(ma_kh="KH001", ten_kh="Khách hàng A", sdt_kh="0909090909")
        hd = HopDong.objects.create(ma_hd="HD-TEST-01", khach_hang=kh, chi_nhanh=self.cn_dn, ngay_ky=timezone.now())
        car = Xe.objects.create(vin=self.alloc.vin, ten_xe=self.alloc.description, so_may="ENG999")
        ChiTietHopDong.objects.create(hop_dong=hd, xe=car)

        # Kiểm tra availability
        status_info = get_allocation_status(self.alloc)
        self.assertFalse(status_info["is_available"])
        self.assertEqual(status_info["status"], AllocationAvailabilityStatus.DA_GAN_HOP_DONG)

        # Không xuất hiện trong danh sách xe còn trống
        avail_qs = get_available_allocations()
        self.assertNotIn(self.alloc, list(avail_qs))

    def test_xe_da_dat_khong_hien_trong_find_allocation_vehicles(self):
        # Xe nằm trong PYC đã gửi (PENDING)
        req = VehicleRequest.objects.create(
            created_by=self.user1,
            status=VehicleRequest.Status.PENDING,
            sent_at=timezone.now(),
        )
        VehicleRequestItem.objects.create(
            vehicle_request=req,
            allocation=self.alloc,
            quantity=1
        )

        kh = KhachHang.objects.create(ma_kh="KH002", ten_kh="Khách hàng B", sdt_kh="0909090908")
        hd = HopDong.objects.create(ma_hd="HD-TEST-02", khach_hang=kh, chi_nhanh=self.cn_dn, ngay_ky=timezone.now())
        criteria = [{"dong_xe": "Everest", "phien_ban": "Titanium", "mau_sac": "Trắng"}]

        found = find_allocation_vehicles(hd, criteria)
        found_vins = [x["vin"] for x in found]
        self.assertNotIn(self.alloc.vin, found_vins)

    def test_dat_xe_available_count_chi_dem_xe_con_trong(self):
        """Menu Đặt xe hiển thị 'Có X xe sẵn sàng' chỉ đếm các xe ở trạng thái Còn trống."""
        alloc_ordered = Allocation.objects.create(
            vin="WF0AVAILTEST00002", vehicle_code="EVEREST", description="Everest Titanium 4x4",
            color_code="BK", exterior_color="Đen", engine_number="ENG002", quantity=1,
            allocation_month=date(2026, 11, 1), chi_nhanh=self.cn_dn
        )
        req = VehicleRequest.objects.create(created_by=self.user1, status=VehicleRequest.Status.PENDING, sent_at=timezone.now())
        VehicleRequestItem.objects.create(vehicle_request=req, allocation=alloc_ordered, quantity=1)

        alloc_contract = Allocation.objects.create(
            vin="WF0AVAILTEST00003", vehicle_code="EVEREST", description="Everest Titanium 4x4",
            color_code="SL", exterior_color="Bạc", engine_number="ENG003", quantity=1,
            allocation_month=date(2026, 11, 1), chi_nhanh=self.cn_dn
        )
        kh = KhachHang.objects.create(ma_kh="KH-CNT", ten_kh="Khách Count", sdt_kh="0901112233")
        hd = HopDong.objects.create(ma_hd="HD-CNT-01", khach_hang=kh, chi_nhanh=self.cn_dn, ngay_ky=timezone.now())
        car = Xe.objects.create(vin=alloc_contract.vin, ten_xe=alloc_contract.description, so_may="ENG003")
        ChiTietHopDong.objects.create(hop_dong=hd, xe=car)

        self.client1.force_login(self.user1)
        resp = self.client1.get(reverse("orders:vehicle_orders") + "?month=2026-11")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.context["allocations"]), 3)
        self.assertEqual(resp.context["available_count"], 1)
        self.assertIn("Có <strong>1</strong> xe sẵn sàng", resp.content.decode("utf-8"))
