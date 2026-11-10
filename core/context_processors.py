from django.urls import reverse
from core.roles import get_user_role_info, user_can_access_url_name

MENU = [
    {
        "label": "Trang chủ",
        "url_name": "dashboard:home",
        "icon": "bi-house-door",
        "always_visible": True,
    },
    {"label": "Quản lý đặt xe", "url_name": "orders:index", "icon": "bi-car-front"},
    {"label": "Quản lý lưu chuyển", "url_name": "transfers:index", "icon": "bi-truck"},
    {"label": "Quản lý hợp đồng xe bán", "url_name": "contracts:index", "icon": "bi-file-earmark-text"},
    {"label": "Quản lý nhập kho", "url_name": "warehouse:nhap", "icon": "bi-box-arrow-in-down"},
    {"label": "Quản lý xuất kho", "url_name": "warehouse:xuat", "icon": "bi-box-arrow-up"},
    {"label": "Quản lý tồn kho", "url_name": "warehouse:ton_kho", "icon": "bi-box-seam"},
    {"label": "Cảnh báo", "url_name": "alerts:index", "icon": "bi-bell"},
    {"label": "Thống kê và báo cáo", "url_name": "dashboard:index", "icon": "bi-bar-chart"},
    {"label": "Dự báo nhu cầu và đề xuất nhập xe", "url_name": "analytics:index", "icon": "bi-graph-up-arrow"},
    {"label": "Quản lý sự cố vận chuyển", "url_name": "incidents:index", "icon": "bi-exclamation-triangle"},
]


def layout(request):
    user = request.user
    if not user.is_authenticated:
        return {}

    role_info = get_user_role_info(user)

    items = []
    for m in MENU:
        # Nếu là Trang chủ thì luôn hiển thị cho mọi user đăng nhập
        if m.get("always_visible"):
            url = reverse(m["url_name"])
            active = request.path == "/" or request.path == url
            items.append({**m, "url": url, "active": active})
            continue

        # Phân quyền: Chỉ hiển thị các module mà user được phép truy cập
        if not user_can_access_url_name(user, m["url_name"]):
            continue

        try:
            url = reverse(m["url_name"])
            active = request.path == url if url == "/" else request.path.startswith(url)
            items.append({**m, "url": url, "active": active})
        except Exception:
            # Phòng trường hợp url_name chưa được nạp
            pass

    # Lấy tên hiển thị ưu tiên Full name > NhanVien.ten_nv > username
    name = user.get_full_name()
    if not name:
        if hasattr(user, "nhan_vien") and user.nhan_vien:
            name = user.nhan_vien.ten_nv
        else:
            name = user.username

    parts = name.split()
    initials = (parts[0][0] + parts[-1][0]) if len(parts) > 1 else name[:2]

    role_code = role_info.get("code", "SALE") if role_info else "SALE"
    role_title = role_info.get("title", "Nhân viên") if role_info else "Chưa phân quyền"
    department = role_info.get("department", "Dana Ford") if role_info else "Dana Ford"
    badge_color = role_info.get("badge_color", "primary") if role_info else "secondary"

    return {
        "menu_items": items,
        "role_info": role_info,
        "user_display": {
            "name": name,
            "username": user.username,
            "initials": initials.upper(),
            "role": role_title,
            "role_code": role_code,
            "department": department,
            "badge_color": badge_color,
            "can_manage_events": role_info.get("can_manage_events", False) if role_info else False,
            "can_monitor_subordinates": role_info.get("can_monitor_subordinates", False) if role_info else False,
            "can_manage_allocations": role_info.get("can_manage_allocations", False) if role_info else False,
            "can_manage_transfers": role_info.get("can_manage_transfers", False) if role_info else False,
            "is_read_only": role_info.get("is_read_only", False) if role_info else False,
        },
    }
