"""Tính toán dự báo - Python thuần, KHÔNG phụ thuộc Django (dễ kiểm thử, dễ thay thế).

* du_bao_sarima(): MÔ PHỎNG SARIMA = xu hướng tuyến tính + chỉ số mùa vụ chu kỳ 12 tháng.
  Đây không phải ước lượng SARIMA(p,d,q)(P,D,Q)12 thật. Muốn dùng bản thật, chỉ cần viết lại
  đúng hàm này bằng statsmodels (SARIMAX) và giữ nguyên kiểu dữ liệu vào/ra.
* tinh_poq(): số lượng đặt tối ưu theo công thức POQ của đặc tả UC-09.2.
"""
import math
from statistics import mean, pstdev

SO_THANG_MUA_VU = 12
TOI_THIEU_MUA_VU = 24      # cần >= 24 quan sát (2 chu kỳ) mới ước lượng được mùa vụ
LEAD_TIME_THANG = 1        # thời gian giao hàng của hãng (tháng)
HE_SO_AN_TOAN = 1.0        # k trong tồn kho an toàn = k * sigma * sqrt(lead time)


def cong_thang(nam, thang, so_thang):
    """(nam, thang) + so_thang tháng."""
    t = nam * 12 + (thang - 1) + so_thang
    return t // 12, t % 12 + 1


def dien_khuyet(gia_tri, thieu):
    """Điền các vị trí thiếu (thieu = tập chỉ số) bằng trung bình trượt của tối đa 3 giá trị
    hợp lệ gần nhất phía trước; nếu chưa có giá trị trước đó thì dùng các giá trị hợp lệ phía sau."""
    ket_qua = list(gia_tri)
    hop_le = [i for i in range(len(gia_tri)) if i not in thieu]
    if not hop_le:
        return ket_qua
    for i in sorted(thieu):
        truoc = [ket_qua[j] for j in hop_le if j < i][-3:]
        sau = [ket_qua[j] for j in hop_le if j > i][:3]
        ket_qua[i] = mean(truoc or sau)
    return ket_qua


def _hoi_quy_tuyen_tinh(y):
    n = len(y)
    xb, yb = (n - 1) / 2, mean(y)
    mau = sum((i - xb) ** 2 for i in range(n)) or 1
    b = sum((i - xb) * (v - yb) for i, v in enumerate(y)) / mau
    return yb - b * xb, b          # a, b: y = a + b*t


def du_bao_sarima(chuoi, nam_cuoi, thang_cuoi, so_buoc):
    """Dự báo nhu cầu sau `so_buoc` tháng kể từ tháng cuối của chuỗi.

    chuoi: danh sách số xe bán theo tháng liên tiếp, phần tử cuối là (nam_cuoi, thang_cuoi).
    Trả về (gia_tri_du_bao: float >= 0, phuong_phap: str, canh_bao: list[str]).
    """
    n = len(chuoi)
    canh_bao = []
    if n == 0:
        return 0.0, "Không có dữ liệu", ["Không có lịch sử bán hàng."]
    nam_dich, thang_dich = cong_thang(nam_cuoi, thang_cuoi, so_buoc)
    if n >= TOI_THIEU_MUA_VU:
        a, b = _hoi_quy_tuyen_tinh(chuoi)
        ty_so = {m: [] for m in range(1, 13)}
        for i, v in enumerate(chuoi):
            xu_huong = a + b * i
            if xu_huong > 0:
                _, m = cong_thang(nam_cuoi, thang_cuoi, i - (n - 1))
                ty_so[m].append(v / xu_huong)
        chi_so = {m: (mean(x) if x else 1.0) for m, x in ty_so.items()}
        tb = mean(chi_so.values()) or 1.0
        chi_so = {m: v / tb for m, v in chi_so.items()}
        gia_tri = (a + b * (n - 1 + so_buoc)) * chi_so[thang_dich]
        return max(0.0, gia_tri), "SARIMA (mô phỏng: xu hướng + mùa vụ 12 tháng)", canh_bao
    canh_bao.append(f"Chỉ có {n} tháng dữ liệu (< {TOI_THIEU_MUA_VU}) nên không ước lượng được mùa vụ; "
                    "dùng trung bình trượt, độ tin cậy dự báo thấp.")
    if n >= 4:
        m = min(n, 6)
        a, b = _hoi_quy_tuyen_tinh(chuoi[-m:])
        du_phong = a + b * (m - 1 + so_buoc)           # ngoại suy xu hướng gần đây
        gia_tri = 0.5 * du_phong + 0.5 * mean(chuoi[-3:])  # pha với mức trung bình để tránh phóng đại
    else:
        gia_tri = mean(chuoi)
    return max(0.0, gia_tri), "Trung bình trượt (thiếu dữ liệu mùa vụ)", canh_bao


def do_lech_chuan(chuoi):
    if len(chuoi) >= 2:
        return pstdev(chuoi)
    return math.sqrt(mean(chuoi)) if chuoi else 0.0


def ton_kho_an_toan(chuoi, lead_time=LEAD_TIME_THANG, k=HE_SO_AN_TOAN):
    return k * do_lech_chuan(chuoi) * math.sqrt(lead_time)


def tinh_poq(du_bao, ton_kho, hop_dong_cho_giao, dang_van_chuyen, an_toan, chi_tieu=None):
    """Số lượng đặt tối ưu (số nguyên >= 0).

    Nhu cầu = dự báo + hợp đồng chờ giao + tồn kho an toàn
    Nguồn   = tồn kho thực tế + xe đang vận chuyển
    Đặt     = max(0, làm tròn(Nhu cầu - Nguồn)); nếu hãng có chỉ tiêu phân bổ thì không vượt chỉ tiêu.
    (Xe thuộc hợp đồng chờ giao vẫn nằm trong tồn kho đến khi lập phiếu xuất, nên được cộng vào
    nhu cầu để không tính trùng nguồn.)
    """
    can_dat = max(0, round(du_bao + hop_dong_cho_giao + an_toan - ton_kho - dang_van_chuyen))
    if chi_tieu is not None:
        can_dat = min(can_dat, chi_tieu)
    return int(can_dat)
