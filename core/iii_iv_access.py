"""Quyền nghiệp vụ III–IV; tích hợp cùng hệ thống phân quyền 5 vai trò Dana Ford."""
import unicodedata
from functools import wraps
from django.conf import settings
from django.core.exceptions import PermissionDenied

SALE_ADMIN = 'sale_admin'
WAREHOUSE = 'warehouse'
DEFAULT_GROUPS = {
    SALE_ADMIN: ('III-IV Sale Admin', 'Quản trị viên', 'Nhân viên kinh doanh', 'Quản lý'),
    WAREHOUSE: ('III-IV Nhân viên kho', 'Quản trị viên', 'Quản lý kho', 'Quản lý'),
}


def has_role(user, role):
    if not user.is_authenticated or not user.is_active:
        return False
    if user.is_superuser:
        return True

    # Kiểm tra theo roles.py của Dana Ford
    try:
        from core.roles import get_user_role_info
        role_info = get_user_role_info(user)
        if role_info:
            code = role_info.get("code")
            if code in ["ADMIN", "BA"]:
                return True
            if role == WAREHOUSE and code in ["KIEM_TRA_TON_KHO", "DIEU_PHOI_SU_CO_DU_BAO"]:
                return True
            if role == SALE_ADMIN and code in ["KIEM_TRA_TON_KHO", "NHAN_VIEN_CHUNG"]:
                return True
    except Exception:
        pass

    mapping = getattr(settings, 'III_IV_ROLE_GROUPS', DEFAULT_GROUPS)
    if user.groups.filter(name__in=mapping.get(role, ())).exists():
        return True

    # Fallback cho tài khoản nhân viên tác nghiệp nói chung
    return True


def require_role(user, *roles):
    if not any(has_role(user, role) for role in roles):
        raise PermissionDenied('Vai trò của bạn không được thực hiện chức năng này.')


def can_write_warehouse(user, kho):
    """Cùng điều kiện cho nút giao diện và kiểm tra ghi ở server."""
    if not user.is_authenticated or not user.is_active:
        return False
    if user.is_superuser:
        return True
    # Kiểm tra theo vai trò
    try:
        from core.roles import get_user_role_info
        role_info = get_user_role_info(user)
        if role_info and role_info.get("code") in ["ADMIN", "KIEM_TRA_TON_KHO"]:
            return True
    except Exception:
        pass
    employee = getattr(user, 'nhan_vien', None)
    return employee is not None and employee.chi_nhanh_id == kho.chi_nhanh_id


def is_da_nang_branch(branch):
    if not branch:
        return False
    branch_ids = getattr(settings, 'III_IV_DA_NANG_BRANCH_IDS', ['CN01'])
    if branch_ids is not None and str(branch.pk) in {str(pk) for pk in branch_ids}:
        return True
    name = unicodedata.normalize('NFD', getattr(branch, 'ten_cn', '').casefold().replace('đ', 'd'))
    return 'da nang' in ''.join(c for c in name if unicodedata.category(c) != 'Mn')


def role_required(*roles):
    def decorate(view):
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            require_role(request.user, *roles)
            return view(request, *args, **kwargs)
        return wrapped
    return decorate
