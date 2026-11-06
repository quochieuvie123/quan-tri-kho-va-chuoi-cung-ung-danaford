from django.shortcuts import redirect
from django.contrib import messages
from core.roles import get_user_role_info, user_can_access_url_name


class ModuleAccessMiddleware:
    """
    Middleware kiểm soát phân quyền truy cập các module nghiệp vụ trong chuỗi cung ứng Dana Ford.
    - Ngăn chặn truy cập trái phép khi người dùng cố ý gõ URL không thuộc thẩm quyền.
    - Bảo vệ dữ liệu cho vai trò BA (Chỉ đọc, không được can thiệp sửa đổi dữ liệu nghiệp vụ).
    """

    # Ánh xạ tiền tố đường dẫn URL sang url_name đại diện của module
    PATH_URL_MAPPING = {
        "/phan-bo/": ("orders:index", "Quản lý đặt xe & Phân bổ"),
        "/luu-chuyen/": ("transfers:index", "Quản lý lưu chuyển xe"),
        "/hop-dong/": ("contracts:index", "Quản lý hợp đồng xe bán"),
        "/kho/": ("warehouse:ton_kho", "Quản lý Kho"),
        "/du-bao/": ("analytics:index", "Dự báo nhu cầu & Nhập xe"),
        "/su-co/": ("incidents:index", "Quản lý sự cố vận chuyển"),
        "/canh-bao/": ("alerts:index", "Cảnh báo hệ thống"),
        "/thong-ke-bao-cao/": ("dashboard:index", "Thống kê & Báo cáo"),
    }

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = request.user
        path = request.path

        # Bỏ qua các đường dẫn hệ thống, xác thực và trang chủ
        if (
            not user.is_authenticated
            or path.startswith("/admin/")
            or path.startswith("/static/")
            or path.startswith("/dang-nhap/")
            or path.startswith("/dang-xuat/")
            or path.startswith("/su-kien/")
            or path.startswith("/thong-bao/")
            or path == "/"
        ):
            return self.get_response(request)

        # 1. Kiểm tra phân quyền truy cập theo đường dẫn module
        role_info = get_user_role_info(user)
        if role_info:
            for prefix, (url_name, module_title) in self.PATH_URL_MAPPING.items():
                if path.startswith(prefix):
                    if not user_can_access_url_name(user, url_name):
                        messages.warning(
                            request,
                            f"Tài khoản của bạn ({role_info.get('title')}) chưa được phân quyền truy cập phân hệ '{module_title}'!"
                        )
                        return redirect("dashboard:home")

            # 2. Quy tắc dành riêng cho BA: "Toàn bộ module theo dõi được nhưng không được can thiệp vào dữ liệu"
            if role_info.get("is_read_only") and request.method in ["POST", "PUT", "DELETE", "PATCH"]:
                # Cho phép BA tạo sự kiện và thông báo trên Trang chủ
                if not (path.startswith("/su-kien/") or path.startswith("/thong-bao/")):
                    messages.error(
                        request,
                        "Tài khoản Chuyên viên BA (Phân tích nghiệp vụ) chỉ có quyền Xem và Giám sát, không được phép thay đổi dữ liệu tác nghiệp!"
                    )
                    return redirect(request.META.get("HTTP_REFERER", "dashboard:home"))

        return self.get_response(request)
