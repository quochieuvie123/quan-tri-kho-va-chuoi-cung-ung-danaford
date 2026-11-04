"""Quyền nghiệp vụ III–IV; không suy vai trò từ is_staff hoặc tên đăng nhập."""
import unicodedata
from functools import wraps
from django.conf import settings
from django.core.exceptions import PermissionDenied

SALE_ADMIN = 'sale_admin'
WAREHOUSE = 'warehouse'
DEFAULT_GROUPS = {
    SALE_ADMIN: ('III-IV Sale Admin',),
    WAREHOUSE: ('III-IV Nhân viên kho',),
}


def has_role(user, role):
    if not user.is_authenticated or not user.is_active:
        return False
    if user.is_superuser:
        return True
    mapping = getattr(settings, 'III_IV_ROLE_GROUPS', DEFAULT_GROUPS)
    if not user.groups.filter(name__in=mapping.get(role, ())).exists():
        return False
    if role == WAREHOUSE:
        employee = getattr(user, 'nhan_vien', None)
        if employee is None:
            return False
        branch = employee.chi_nhanh
        branch_ids = getattr(settings, 'III_IV_DA_NANG_BRANCH_IDS', None)
        if branch_ids is not None:
            return str(branch.pk) in {str(pk) for pk in branch_ids}
        normalized = unicodedata.normalize('NFD', branch.ten_cn.casefold().replace('đ', 'd'))
        normalized = ''.join(c for c in normalized if unicodedata.category(c) != 'Mn')
        return 'da nang' in normalized
    return True


def require_role(user, *roles):
    if not any(has_role(user, role) for role in roles):
        raise PermissionDenied('Vai trò của bạn không được thực hiện chức năng này.')


def can_write_warehouse(user, kho):
    """Cùng điều kiện cho nút giao diện và kiểm tra ghi ở server."""
    if not user.is_authenticated or not user.is_active:
        return False
    if not is_da_nang_branch(kho.chi_nhanh):
        return False
    if user.is_superuser:
        return True
    employee = getattr(user, 'nhan_vien', None)
    return employee is not None and employee.chi_nhanh_id == kho.chi_nhanh_id


def is_da_nang_branch(branch):
    branch_ids = getattr(settings, 'III_IV_DA_NANG_BRANCH_IDS', None)
    if branch_ids is not None:
        return str(branch.pk) in {str(pk) for pk in branch_ids}
    name = unicodedata.normalize('NFD', branch.ten_cn.casefold().replace('đ', 'd'))
    return 'da nang' in ''.join(c for c in name if unicodedata.category(c) != 'Mn')


def role_required(*roles):
    def decorate(view):
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            require_role(request.user, *roles)
            return view(request, *args, **kwargs)
        return wrapped
    return decorate
