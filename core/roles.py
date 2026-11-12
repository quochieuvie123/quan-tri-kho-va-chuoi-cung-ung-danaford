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
        "badge": "Phác thảo",
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

# Định nghĩa các vai trò và phạm vi quyền hạn (2 nhóm chính: Sale Admin & Nhân viên Sale)
ROLES = {
    "ADMIN": {
        "code": "ADMIN",
        "title": "Quản trị viên (Sale Admin)",
        "department": "Ban Điều Hành & Quản Trị Hệ Thống",
        "badge_color": "danger",
        "can_monitor_subordinates": True,
        "can_manage_events": True,
        "can_manage_notifications": True,
        "can_manage_allocations": True,
        "can_manage_transfers": True,
        "is_read_only": False,
        "allowed_urls": ["*"],  # Toàn bộ module
    },
    "SALE": {
        "code": "SALE",
        "title": "Sale Chi Nhánh",
        "department": "Phòng Kinh Doanh & Bán Hàng Chi Nhánh",
        "badge_color": "primary",
        "can_monitor_subordinates": False,
        "can_manage_events": False,
        "can_manage_notifications": False,
        "can_manage_allocations": True,   # Được up phân bổ theo yêu cầu
        "can_manage_transfers": True,     # Được lưu chuyển xe theo yêu cầu
        "is_read_only": False,
        "allowed_urls": ["*"],  # Truy cập toàn bộ module tác nghiệp
    },
    # Giữ lại các alias cũ để tương thích ngược tuyệt đối
    "BA": {
        "code": "ADMIN",
        "title": "Quản trị viên (Sale Admin)",
        "department": "Ban Điều Hành & Quản Trị Hệ Thống",
        "badge_color": "danger",
        "can_monitor_subordinates": True,
        "can_manage_events": True,
        "can_manage_notifications": True,
        "can_manage_allocations": True,
        "can_manage_transfers": True,
        "is_read_only": False,
        "allowed_urls": ["*"],
    },
    "KIEM_TRA_TON_KHO": {
        "code": "SALE",
        "title": "Sale Chi Nhánh",
        "department": "Phòng Kinh Doanh & Bán Hàng Chi Nhánh",
        "badge_color": "primary",
        "can_monitor_subordinates": False,
        "can_manage_events": False,
        "can_manage_notifications": False,
        "can_manage_allocations": True,
        "can_manage_transfers": True,
        "is_read_only": False,
        "allowed_urls": ["*"],
    },
    "DIEU_PHOI_SU_CO_DU_BAO": {
        "code": "SALE",
        "title": "Sale Chi Nhánh",
        "department": "Phòng Kinh Doanh & Bán Hàng Chi Nhánh",
        "badge_color": "primary",
        "can_monitor_subordinates": False,
        "can_manage_events": False,
        "can_manage_notifications": False,
        "can_manage_allocations": True,
        "can_manage_transfers": True,
        "is_read_only": False,
        "allowed_urls": ["*"],
    },
    "NHAN_VIEN_CHUNG": {
        "code": "SALE",
        "title": "Sale Chi Nhánh",
        "department": "Phòng Kinh Doanh & Bán Hàng Chi Nhánh",
        "badge_color": "primary",
        "can_monitor_subordinates": False,
        "can_manage_events": False,
        "can_manage_notifications": False,
        "can_manage_allocations": True,
        "can_manage_transfers": True,
        "is_read_only": False,
        "allowed_urls": ["*"],
    },
}

# Mapping người dùng theo username vào vai trò
# Nhóm 1: Sale Admin (Hiếu và Dung)
# Nhóm 2: Nhân viên Sale (4 bạn còn lại: Yên Giang, Linh Giang, Cẩm Tú, Minh Thư)
USER_ROLE_MAPPING = {
    "phanquochieu": "ADMIN",
    "hieu": "ADMIN",
    "admin": "ADMIN",
    "mydung": "ADMIN",
    "dung": "ADMIN",
    "tu": "SALE",
    "ygiang": "SALE",
    "lgiang": "SALE",
    "nhanvien": "SALE",
    "quanly": "SALE",
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
            groups = set(user.groups.values_list("name", flat=True))
            if groups.intersection({"Quản lý", "Admin", "Quản trị viên", "III-IV Sale Admin"}):
                role_code = "ADMIN"
            else:
                role_code = "SALE"

    role_info = dict(ROLES.get(role_code, ROLES["SALE"]))
    return role_info


def is_sale_admin(user):
    """Kiểm tra người dùng có quyền Sale Admin hay không dựa trên role_info."""
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    role_info = get_user_role_info(user)
    if role_info and role_info.get("code") in ("ADMIN", "SALE_ADMIN"):
        return True
    return False


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
