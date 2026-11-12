"""Logic khớp xe và tiêu chí hợp đồng (Dòng xe, Phiên bản, Màu sắc) linh hoạt và thông minh."""
import re

COLOR_GROUPS = [
    {'black', 'den', 'đen', 'đen ánh kim', 'đen bóng', 'absolute black', 'shadow black', 'agate black'},
    {'white', 'trang', 'trắng', 'trắng tuyết', 'trắng ngọc trai', 'frozen white', 'snow flake white pearl mc', 'oxford white'},
    {'orange', 'cam', 'cam luxe', 'vàng luxe', 'vang luxe', 'luxe yellow', 'sedona orange'},
    {'blue', 'xanh', 'xanh dương', 'xanh lam', 'xanh arctic', 'arctic blue', 'lightning blue'},
    {'grey', 'gray', 'xam', 'xám', 'xám meteor', 'meteor grey', 'carbonized gray'},
    {'red', 'do', 'đỏ', 'đỏ ngọc ruby', 'đỏ cam', 'ruby red', 'race red'},
    {'silver', 'bac', 'bạc', 'ánh bạc', 'moondust silver', 'diffused silver'},
    {'brown', 'nau', 'nâu', 'nâu đồng', 'equestrian brown'},
]

MODEL_KEYWORDS = ['territory', 'everest', 'ranger', 'explorer', 'transit']
TRIM_KEYWORDS = [
    'titanium x', 'titanium+', 'titanium', 'wildtrak', 'raptor',
    'trend', 'sport', 'active', 'platinum', 'limited', 'ambiente',
    'xls', 'xlt', 'limousine'
]


def normalize_text(text):
    if not text:
        return ""
    text = text.lower().strip()
    return re.sub(r'\s+', ' ', text)


def colors_match(c1, c2):
    s1 = normalize_text(c1)
    s2 = normalize_text(c2)
    if not s1 or not s2:
        return True
    if s1 == s2 or s1 in s2 or s2 in s1:
        return True
    for grp in COLOR_GROUPS:
        m1 = any(alias in s1 for alias in grp)
        m2 = any(alias in s2 for alias in grp)
        if m1 and m2:
            return True
    return False


def get_model(text):
    t = normalize_text(text)
    for m in MODEL_KEYWORDS:
        if m in t:
            return m
    return t


def get_trim(text):
    t = normalize_text(text)
    for tr in TRIM_KEYWORDS:
        if tr in t:
            return tr
    return t


def car_matches_criterion(car, req, strict_color=False):
    """
    Kiểm tra xem xe có thỏa mãn tiêu chí dòng xe, phiên bản và màu sắc không.
    Trả về (match: bool, is_exact_color: bool).
    """
    req_dong = req.get('dong_xe', '')
    req_phien_ban = req.get('phien_ban', '')
    req_mau = req.get('mau_sac', '')

    car_name = getattr(car, 'ten_xe', '') or ''
    car_phien_ban = getattr(car, 'phien_ban', '') or ''
    car_mau = getattr(car, 'mau_sac', '') or ''
    car_loai = getattr(car, 'loai_xe', '') or ''

    # 1. Khớp Dòng xe (Family: Territory, Everest, Ranger, Explorer, Transit)
    m_req = get_model(req_dong)
    m_car = get_model(car_name) or get_model(car_loai)
    if m_req and m_car and m_req != m_car:
        return False, False

    # 2. Khớp Phiên bản (Trim: Trend, Titanium X, Titanium, Wildtrak, Sport, Active, ...)
    tr_req = get_trim(req_phien_ban) or get_trim(req_dong)
    tr_car = get_trim(car_phien_ban) or get_trim(car_name)
    if tr_req and tr_car and tr_req != tr_car:
        return False, False

    # 3. Khớp Màu sắc
    c_match = colors_match(req_mau, car_mau)
    if strict_color and not c_match:
        return False, False

    return True, c_match


def matches_contract_smart(car, contract):
    """Thay thế matches_contract cứng nhắc cũ."""
    req = {
        'dong_xe': contract.dong_xe_yeu_cau,
        'phien_ban': contract.phien_ban_yeu_cau,
        'mau_sac': contract.mau_sac_yeu_cau,
    }
    match, _ = car_matches_criterion(car, req, strict_color=False)
    return match
