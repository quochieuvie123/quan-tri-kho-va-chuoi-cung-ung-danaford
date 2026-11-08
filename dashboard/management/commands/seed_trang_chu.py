import sys
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from django.contrib.auth import get_user_model
from database.models import NhanVien, ChiNhanh
from dashboard.models import SuKienNoiBat, ThongBaoHoatDong

User = get_user_model()


class Command(BaseCommand):
    help = "Khởi tạo dữ liệu mẫu cho Trang chủ, 5 nhân viên và phân quyền"

    def handle(self, *args, **options):
        if hasattr(sys.stdout, "reconfigure"):
            try:
                sys.stdout.reconfigure(encoding="utf-8")
            except Exception:
                pass

        self.stdout.write("Bắt đầu khởi tạo dữ liệu 5 tài khoản nhân viên...")

        chi_nhanh_dn = ChiNhanh.objects.filter(ma_cn="CN01").first()
        if not chi_nhanh_dn:
            chi_nhanh_dn = ChiNhanh.objects.first()

        # Danh sách 5 nhân sự được yêu cầu
        nhan_vien_data = [
            {
                "username": "phanquochieu",
                "alt_username": "hieu",
                "password": "hieuduanlon",
                "first_name": "Quốc Hiếu",
                "last_name": "Phan",
                "full_name": "Phan Quốc Hiếu",
                "chuc_vu": "Quản trị viên (Admin)",
                "ma_nv": "NV10",
                "sdt": "0905123456",
                "is_superuser": True,
                "is_staff": True,
            },
            {
                "username": "mydung",
                "alt_username": "dung",
                "password": "dungduanlon",
                "first_name": "Vũ Mỹ Dung",
                "last_name": "Nguyễn",
                "full_name": "Nguyễn Vũ Mỹ Dung",
                "chuc_vu": "Chuyên viên BA",
                "ma_nv": "NV11",
                "sdt": "0905234567",
                "is_superuser": False,
                "is_staff": True,
            },
            {
                "username": "tu",
                "alt_username": None,
                "password": "tuduanlon",
                "first_name": "Nguyễn Cẩm Tú",
                "last_name": "Đỗ",
                "full_name": "Đỗ Nguyễn Cẩm Tú",
                "chuc_vu": "Kiểm tra tồn kho",
                "ma_nv": "NV12",
                "sdt": "0905345678",
                "is_superuser": False,
                "is_staff": False,
            },
            {
                "username": "ygiang",
                "alt_username": None,
                "password": "ygiangduanlon",
                "first_name": "Thị Yên Giang",
                "last_name": "Nguyễn",
                "full_name": "Nguyễn Thị Yên Giang",
                "chuc_vu": "Kiểm tra tồn kho",
                "ma_nv": "NV13",
                "sdt": "0905456789",
                "is_superuser": False,
                "is_staff": False,
            },
            {
                "username": "lgiang",
                "alt_username": None,
                "password": "lgiangduanlon",
                "first_name": "Linh Giang",
                "last_name": "Nguyễn",
                "full_name": "Nguyễn Linh Giang",
                "chuc_vu": "Điều phối sự cố & Dự báo",
                "ma_nv": "NV14",
                "sdt": "0905567890",
                "is_superuser": False,
                "is_staff": False,
            },
        ]

        created_users = {}

        for item in nhan_vien_data:
            # Tạo hoặc cập nhật NhanVien
            nv, _ = NhanVien.objects.get_or_create(
                ma_nv=item["ma_nv"],
                defaults={
                    "ten_nv": item["full_name"],
                    "chi_nhanh": chi_nhanh_dn,
                    "sdt_nv": item["sdt"],
                }
            )
            nv.ten_nv = item["full_name"]
            nv.save()

            # Tạo hoặc cập nhật User chính
            u, _ = User.objects.get_or_create(username=item["username"])
            u.first_name = item["first_name"]
            u.last_name = item["last_name"]
            u.is_superuser = item["is_superuser"]
            u.is_staff = item["is_staff"]
            u.nhan_vien = nv
            u.set_password(item["password"])
            u.save()
            created_users[item["username"]] = u
            self.stdout.write(f" -> Đã cập nhật tài khoản: {item['username']} ({item['full_name']})")

            # Đồng bộ mật khẩu cho username phụ nếu có (ví dụ 'hieu' và 'dung')
            if item["alt_username"]:
                alt_u = User.objects.filter(username=item["alt_username"]).first()
                if alt_u:
                    alt_u.first_name = item["first_name"]
                    alt_u.last_name = item["last_name"]
                    alt_u.nhan_vien = None
                    alt_u.set_password(item["password"])
                    alt_u.save()
                    self.stdout.write(f" -> Đã đồng bộ tài khoản phụ: {item['alt_username']}")

        admin_user = created_users.get("phanquochieu")

        # Khởi tạo Sự kiện nổi bật mẫu
        SuKienNoiBat.objects.all().delete()
        now = timezone.now()

        events_data = [
            {
                "tieu_de": "Lịch tổng kiểm kê xe tồn kho Quý 4 - Dana Ford",
                "noi_dung": "Đề nghị bộ phận Kho vận và nhân viên kiểm kê đối chiếu 100% số khung VIN thực tế tại 3 kho Đà Nẵng, Bình Định và Gia Lai trước ngày 25 hàng tháng.",
                "loai_su_kien": "kiem_ke",
                "dia_diem": "Toàn bộ 3 kho chi nhánh",
                "thoi_gian_dien_ra": now + timedelta(days=2, hours=3),
            },
            {
                "tieu_de": "Tiếp nhận 45 xe Ford Everest & Ranger thế hệ mới từ Nhà máy",
                "noi_dung": "Kế hoạch đoàn xe lồng vận tải giao đợt 1 về Kho Trung tâm Đà Nẵng. Nhân viên kho chuẩn bị bãi đậu và tiến hành kiểm tra biên bản PDI ngay khi xe đến.",
                "loai_su_kien": "van_chuyen",
                "dia_diem": "Kho Tổng Dana Ford Đà Nẵng",
                "thoi_gian_dien_ra": now + timedelta(days=4, hours=1),
            },
            {
                "tieu_de": "Họp giao ban điều phối cung ứng & Đánh giá năng lực lưu chuyển",
                "noi_dung": "Cuộc họp giữa Ban Giám đốc, bộ phận BA, Điều vận và Quản lý kho nhằm rà soát tỷ lệ đáp ứng đơn hàng và chi phí vận chuyển.",
                "loai_su_kien": "hop_giao_ban",
                "dia_diem": "Phòng họp Ban Giám Đốc - Trực tuyến 3 điểm cầu",
                "thoi_gian_dien_ra": now + timedelta(days=6, hours=2),
            },
            {
                "tieu_de": "Cảnh báo khẩn: Hạn mức lưu kho dòng xe Ford Territory tại Bình Định",
                "noi_dung": "Lượng xe tồn kho chi nhánh Bình Định chạm ngưỡng 90% công suất bãi. Yêu cầu bộ phận điều vận ưu tiên luân chuyển xe về Gia Lai hoặc tăng tốc bàn giao hợp đồng.",
                "loai_su_kien": "khan_cap",
                "dia_diem": "Chi nhánh Bình Định",
                "thoi_gian_dien_ra": now + timedelta(hours=14),
            },
        ]

        for ev in events_data:
            SuKienNoiBat.objects.create(
                tieu_de=ev["tieu_de"],
                noi_dung=ev["noi_dung"],
                loai_su_kien=ev["loai_su_kien"],
                dia_diem=ev["dia_diem"],
                thoi_gian_dien_ra=ev["thoi_gian_dien_ra"],
                nguoi_tao=admin_user,
                is_active=True,
            )
        self.stdout.write(" -> Đã tạo 4 sự kiện nổi bật mẫu.")

        # Khởi tạo Nhật ký hoạt động / Thông báo update mẫu
        ThongBaoHoatDong.objects.all().delete()

        activities_data = [
            {
                "username": "tu",
                "ten": "Đỗ Nguyễn Cẩm Tú",
                "chuc_vu": "Kiểm tra tồn kho",
                "hanh_dong": "Đã import và đối chiếu bảng dữ liệu luân chuyển xe tháng này",
                "chi_tiet": "Hoàn tất import file Excel điều chuyển 16 xe Ford Ranger từ kho Đà Nẵng sang chi nhánh Bình Định.",
                "module": "transfers",
                "loai": "tu_dong",
            },
            {
                "username": "ygiang",
                "ten": "Nguyễn Thị Yên Giang",
                "chuc_vu": "Kiểm tra tồn kho",
                "hanh_dong": "Đã ghi nhận phiếu kiểm đếm tồn kho thực tế PKK-DN-011",
                "chi_tiet": "Hoàn thành kiểm đếm khu vực Bãi A: 84 xe, khớp 100% với dữ liệu phần mềm.",
                "module": "warehouse",
                "loai": "tu_dong",
            },
            {
                "username": "lgiang",
                "ten": "Nguyễn Linh Giang",
                "chuc_vu": "Điều phối sự cố & Dự báo",
                "hanh_dong": "Báo cáo sự cố vận chuyển mã SC-2026-004 đã được tiếp nhận",
                "chi_tiet": "Xe đầu kéo vận chuyển lô 6 xe gặp sự cố hỏng lốp trên Quốc lộ 1A (Quảng Nam), đã điều xe hỗ trợ và cập nhật ETA mới.",
                "module": "incidents",
                "loai": "tu_dong",
            },
            {
                "username": "lgiang",
                "ten": "Nguyễn Linh Giang",
                "chuc_vu": "Điều phối sự cố & Dự báo",
                "hanh_dong": "Cập nhật mô hình dự báo nhu cầu đặt xe Ford Everest Quý 1/2027",
                "chi_tiet": "Đề xuất mức dự trữ an toàn tăng thêm 12% đáp ứng dịp cao điểm Tết Nguyên Đán.",
                "module": "analytics",
                "loai": "tu_dong",
            },
            {
                "username": "mydung",
                "ten": "Nguyễn Vũ Mỹ Dung",
                "chuc_vu": "Chuyên viên BA",
                "hanh_dong": "Hoàn thành kiểm tra đối soát số liệu liên kết giữa Hợp đồng và Phiếu xuất",
                "chi_tiet": "Dữ liệu 9 phân hệ đã được đồng bộ chuẩn xác. Không phát hiện sai lệch số liệu tồn kho khả dụng.",
                "module": "reports",
                "loai": "tu_dong",
            },
            {
                "username": "phanquochieu",
                "ten": "Phan Quốc Hiếu",
                "chuc_vu": "Quản trị viên (Admin)",
                "hanh_dong": "Ban hành phân quyền truy cập và phân công nhiệm vụ chuỗi cung ứng Dana Ford",
                "chi_tiet": "Hệ thống phân quyền theo 5 vị trí nhân sự đã chính thức kích hoạt trên cổng thông tin Trang chủ.",
                "module": "he_thong",
                "loai": "thu_cong",
            },
        ]

        for act in activities_data:
            user_obj = created_users.get(act["username"]) or User.objects.filter(username=act["username"]).first()
            ThongBaoHoatDong.objects.create(
                user=user_obj,
                ten_nhan_vien=act["ten"],
                chuc_vu=act["chuc_vu"],
                hanh_dong=act["hanh_dong"],
                chi_tiet=act["chi_tiet"],
                module=act["module"],
                loai=act["loai"],
                is_active=True,
            )
        self.stdout.write(" -> Đã tạo 6 bản ghi nhật ký hoạt động mẫu.")
        self.stdout.write(self.style.SUCCESS("Khởi tạo toàn bộ dữ liệu mẫu Trang chủ THÀNH CÔNG!"))
