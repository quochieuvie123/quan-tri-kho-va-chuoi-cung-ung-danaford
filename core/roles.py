"""
Cấu hình Vai trò, Phân quyền và Danh mục Module trong hệ thống Dana Ford.
"""

# Danh mục đầy đủ 10 Module trong hệ thống
ALL_MODULES = [
    {
        "id": "orders",
        "label": "Quản lý đặt xe",
        "url_name": "orders:index",
        "icon": "bi-car-front",
        "badge": "Kinh doanh",
        "description": "Quản lý yêu cầu đặt xe, phân bổ chỉ tiêu và điều phối xe theo đại lý.",
    },
    {
        "id": "transfers",
        "label": "Quản lý lưu chuyển",
        "url_name": "transfers:index",
        "icon": "bi-truck",
        "badge": "Vận chuyển",
        "description": "Theo dõi kế hoạch luân chuyển xe giữa các kho chi nhánh Dana Ford.",
    },
    {
        "id": "contracts",
        "label": "Quản lý hợp đồng xe bán",
        "url_name": "contracts:index",
        "icon": "bi-file-earmark-text",
        "badge": "Hợp đồng",
        "description": "Quản lý hồ sơ hợp đồng mua bán xe, tiến độ thanh toán và khách hàng.",
    },
    {
        "id": "warehouse_nhap",
        "label": "Quản lý nhập kho",
        "url_name": "warehouse:nhap",
        "icon": "bi-box-arrow-in-down",
        "badge": "Kho vận",
        "description": "Tiếp nhận lô xe mới từ nhà máy, kiểm tra biên bản PDI và hóa đơn nhập.",
    },
    {
        "id": "warehouse_xuat",
        "label": "Quản lý xuất kho",
        "url_name": "warehouse:xuat",
        "icon": "bi-box-arrow-up",
        "badge": "Kho vận",
        "description": "Lập phiếu xuất kho, tra cứu xe khả dụng, phê duyệt xuất xe bàn giao.",
    },
    {
        "id": "warehouse_ton_kho",
        "label": "Quản lý tồn kho",
        "url_name": "warehouse:ton_kho",
        "icon": "bi-box-seam",
        "badge": "Kho vận",
        "description": "Theo dõi số lượng xe tồn kho, vị trí lưu kho và định kỳ kiểm kê đối chiếu.",
    },
    {
        "id": "alerts",
        "label": "Cảnh báo",
        "url_name": "alerts:index",
        "icon": "bi-bell",
        "badge": "Giám sát",
        "description": "Cảnh báo xe lưu kho quá hạn, sự cố vận chuyển và các ngưỡng an toàn.",
    },
    {
        "id": "reports",
        "label": "Thống kê và báo cáo",
        "url_name": "dashboard:index",
        "icon": "bi-bar-chart",
        "badge": "Báo cáo",
        "description": "Báo cáo tổng quan hiệu suất chuỗi cung ứng, doanh số và tồn kho chi nhánh.",
    },
    {
        "id": "analytics",
        "label": "Dự báo nhu cầu và đề xuất nhập xe",
        "url_name": "analytics:index",
        "icon": "bi-graph-up-arrow",
        "badge": "Phân tích",
        "description": "Dự báo xu hướng tiêu thụ từng dòng xe Ford và đề xuất kế hoạch đặt hàng.",
    },
    {
        "id": "incidents",
        "label": "Quản lý sự cố vận chuyển",
        "url_name": "incidents:index",
        "icon": "bi-exclamation-triangle",
        "badge": "Vận chuyển",
        "description": "Ghi nhận và xử lý sự cố va quẹt, hỏng hóc phát sinh trong quá trình vận chuyển.",
    },
]

# Định nghĩa các vai trò và phạm vi quyền hạn
ROLES = {
    "SALE_ADMIN": {
        "code": "SALE_ADMIN", "title": "Sale Admin", "department": "Kinh doanh",
        "badge_color": "primary", "can_monitor_subordinates": False,
        "can_manage_events": False, "can_manage_notifications": False, "is_read_only": False,
        "allowed_urls": ["orders:index", "contracts:index", "warehouse:ton_kho", "warehouse:nhap", "warehouse:xuat", "alerts:index"],
    },
    "ADMIN": {
        "code": "ADMIN",
        "title": "Quản trị viên (Admin)",
        "department": "Ban Điều Hành & Quản Trị Hệ Thống",
        "badge_color": "danger",
        "can_monitor_subordinates": True,
        "can_manage_events": True,
        "can_manage_notifications": True,
        "is_read_only": False,
        "allowed_urls": ["*"],  # Toàn bộ module
    },
    "BA": {
        "code": "BA",
        "title": "Chuyên viên BA (Phân tích nghiệp vụ)",
        "department": "Phòng Kế Hoạch & Phân Tích Dữ Liệu",
        "badge_color": "info",
        "can_monitor_subordinates": True,
        "can_manage_events": True,
        "can_manage_notifications": True,
        "is_read_only": True,  # Không được can thiệp sửa dữ liệu tác nghiệp
        "allowed_urls": ["*"],  # Toàn bộ module (chế độ xem & phân tích)
    },
    "KIEM_TRA_TON_KHO": {
        "code": "KIEM_TRA_TON_KHO",
        "title": "Kiểm tra tồn kho & Quản lý kho",
        "department": "Bộ Phận Quản Lý Kho & Lưu Chuyển",
        "badge_color": "warning",
        "can_monitor_subordinates": False,
        "can_manage_events": False,
        "can_manage_notifications": False,
        "is_read_only": False,
        "allowed_urls": [
            "contracts:index",
            "incidents:index",
            "warehouse:ton_kho",
            "warehouse:xuat",
            "warehouse:nhap",
            "transfers:index",
            "alerts:index",
        ],
    },
    "DIEU_PHOI_SU_CO_DU_BAO": {
        "code": "DIEU_PHOI_SU_CO_DU_BAO",
        "title": "Điều phối Sự cố & Dự báo nhu cầu",
        "department": "Phòng Điều Vận & Kế Hoạch Cung Ứng",
        "badge_color": "primary",
        "can_monitor_subordinates": False,
        "can_manage_events": False,
        "can_manage_notifications": False,
        "is_read_only": False,
        "allowed_urls": [
            "incidents:index",
            "analytics:index",
            "alerts:index",
        ],
    },
    "NHAN_VIEN_CHUNG": {
        "code": "NHAN_VIEN_CHUNG",
        "title": "Nhân viên tác nghiệp",
        "department": "Chi Nhánh Dana Ford",
        "badge_color": "secondary",
        "can_monitor_subordinates": False,
        "can_manage_events": False,
        "can_manage_notifications": False,
        "is_read_only": False,
        "allowed_urls": [
            "alerts:index",
        ],
    },
}

# Mapping người dùng theo username vào vai trò
USER_ROLE_MAPPING = {
    "phanquochieu": "ADMIN",
    "hieu": "ADMIN",
    "admin": "ADMIN",
    "mydung": "BA",
    "dung": "BA",
    "tu": "KIEM_TRA_TON_KHO",
    "ygiang": "KIEM_TRA_TON_KHO",
    "lgiang": "DIEU_PHOI_SU_CO_DU_BAO",
    "quanly": "KIEM_TRA_TON_KHO",
    "nhanvien": "NHAN_VIEN_CHUNG",
}


def get_user_role_info(user):
    """Lấy thông tin cấu hình vai trò, bộ phận và quyền hạn của một User."""
    if not user or not user.is_authenticated:
        return None

    username = user.username.lower()

    if user.is_superuser:
        role_code = USER_ROLE_MAPPING.get(username, "ADMIN")
    else:
        role_code = USER_ROLE_MAPPING.get(username, None)
        if not role_code:
            # Fallback từ Django Groups nếu có
            group_name = user.groups.values_list("name", flat=True).first()
            groups = set(user.groups.values_list("name", flat=True))
            if "Quản trị viên" in groups:
                role_code = "ADMIN"
            elif groups.intersection({"III-IV Sale Admin", "Nhân viên kinh doanh"}):
                role_code = "SALE_ADMIN"
            elif groups.intersection({"III-IV Nhân viên kho", "Quản lý kho"}):
                role_code = "KIEM_TRA_TON_KHO"
            elif group_name == "Quản lý":
                role_code = "KIEM_TRA_TON_KHO"
            else:
                role_code = "NHAN_VIEN_CHUNG"

    role_info = dict(ROLES.get(role_code, ROLES["NHAN_VIEN_CHUNG"]))
    return role_info


def get_user_allowed_modules(user):
    """Trả về danh sách các module mà user được quyền truy cập."""
    role_info = get_user_role_info(user)
    if not role_info:
        return []

    allowed_urls = role_info.get("allowed_urls", [])
    if "*" in allowed_urls:
        return ALL_MODULES

    return [m for m in ALL_MODULES if m["url_name"] in allowed_urls]


def user_can_access_url_name(user, url_name):
    """Kiểm tra xem user có quyền truy cập url_name này không."""
    if not user or not user.is_authenticated:
        return False
    role_info = get_user_role_info(user)
    if not role_info:
        return False
    allowed_urls = role_info.get("allowed_urls", [])
    if "*" in allowed_urls:
        return True
    return url_name in allowed_urls
