from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from django import template

register = template.Library()


@register.filter(name="tien_vn")
def tien_vn(value):
    """Định dạng số tiền theo chuẩn Việt Nam dùng dấu chấm phân cách hàng nghìn (VD: 600.000.000)."""
    if value is None or value == "":
        return "0"
    try:
        d = Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        n = int(d)
        sign = "-" if n < 0 else ""
        return f"{sign}{abs(n):,}".replace(",", ".")
    except (InvalidOperation, ValueError, TypeError):
        return str(value)
