from django.urls import reverse

MENU = [
    {"label": "Quản lý đặt xe", "url_name": "orders:index", "icon": "bi-car-front", "perm": None},
    {"label": "Quản lý lưu chuyển", "url_name": "transfers:index", "icon": "bi-truck", "perm": None},
    {"label": "Quản lý hợp đồng xe bán", "url_name": "contracts:index", "icon": "bi-file-earmark-text", "perm": None},
    {"label": "Quản lý nhập kho", "url_name": "warehouse:nhap", "icon": "bi-box-arrow-in-down", "perm": None},
    {"label": "Quản lý xuất kho", "url_name": "warehouse:xuat", "icon": "bi-box-arrow-up", "perm": None},
    {"label": "Quản lý tồn kho", "url_name": "warehouse:ton_kho", "icon": "bi-box-seam", "perm": None},
    {"label": "Thống kê và báo cáo", "url_name": "dashboard:index", "icon": "bi-bar-chart", "perm": None},
    {"label": "Dự báo nhu cầu và đề xuất nhập xe", "url_name": "analytics:index", "icon": "bi-graph-up-arrow", "perm": None},
    {"label": "Quản lý sự cố vận chuyển", "url_name": "incidents:index", "icon": "bi-exclamation-triangle", "perm": None},
]


def layout(request):
    user = request.user
    if not user.is_authenticated:
        return {}

    items = []
    for m in MENU:
        if m["perm"] and not user.has_perm(m["perm"]):
            continue
        url = reverse(m["url_name"])
        active = request.path == url if url == "/" else request.path.startswith(url)
        items.append({**m, "url": url, "active": active})

    name = user.get_full_name() or user.username
    parts = name.split()
    initials = (parts[0][0] + parts[-1][0]) if len(parts) > 1 else name[:2]
    group = user.groups.values_list("name", flat=True).first()
    role = "Quản trị viên" if user.is_superuser else (group or "Chưa gán vai trò")

    return {
        "menu_items": items,
        "user_display": {"name": name, "initials": initials.upper(), "role": role},
    }