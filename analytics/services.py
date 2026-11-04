"""UC-09.2 Phân tích nhu cầu (SARIMA mô phỏng -> POQ) và UC-09.4 tính lại chỉ số."""
from decimal import Decimal
from statistics import mean

from django.db import transaction
from django.utils import timezone

from . import forecast
from .du_lieu import tach_ten, thu_thap
from .models import DongDuBao, PhienDuBao


def chay_phan_tich(thang, nam, nguoi_tao=None):
    bo = thu_thap(thang, nam)
    canh_bao = list(bo.canh_bao)
    buoc = 1  # luôn dự báo tháng liền sau tháng dữ liệu cuối cùng
    ket_qua = {}
    for ten, dl in bo.dong_xe.items():
        if sum(dl.chuoi) > 0:
            v, pp, cb = forecast.du_bao_sarima(dl.chuoi, bo.nam_cuoi, bo.thang_cuoi, buoc)
            ket_qua[ten] = [v, pp, cb, "", forecast.ton_kho_an_toan(dl.chuoi)]
    # Dòng xe mới ra mắt (chưa có lịch sử): lấy mức nhu cầu trung bình của các dòng cùng phân khúc
    for ten, dl in bo.dong_xe.items():
        if ten in ket_qua:
            continue
        cung = [ket_qua[t][0] for t, d in bo.dong_xe.items() if t in ket_qua and d.loai_xe == dl.loai_xe]
        v = mean(cung) if cung else 0.0
        an_toan = mean([ket_qua[t][4] for t, d in bo.dong_xe.items() if t in ket_qua and d.loai_xe == dl.loai_xe]) if cung else 0.0
        ghi = ("Dòng xe mới, chưa có lịch sử: ước tính theo trung bình các dòng cùng phân khúc "
               f"“{dl.loai_xe}” - Sale Admin cần kiểm tra." if cung else
               "Dòng xe mới và phân khúc chưa có lịch sử: chưa thể ước tính - Sale Admin cần kiểm tra.")
        ket_qua[ten] = [v, "Ước tính theo dòng xe tương đương", [], ghi, an_toan]
        canh_bao.append(f"{ten}: {ghi}")

    with transaction.atomic():
        phien = PhienDuBao.objects.create(
            thang=thang, nam=nam, nguoi_tao=nguoi_tao, tao_luc=timezone.now(), het_han_luc=None,
            canh_bao="\n".join(canh_bao))
        dong = []
        for ten, dl in sorted(bo.dong_xe.items(), key=lambda kv: (kv[1].loai_xe, kv[0])):
            v, pp, cb, ghi, an_toan = ket_qua[ten]
            ten_ngan, phien_ban, ma = tach_ten(ten)
            dong.append(DongDuBao(
                phien=phien, ten_xe=ten, loai_xe=dl.loai_xe, ma_dong_xe=ma, ten_ngan=ten_ngan,
                phien_ban=phien_ban, du_bao_sarima=round(v, 1), phuong_phap=pp, ky_truoc=dl.ky_truoc,
                ton_kho=dl.ton_kho, hop_dong_cho_giao=dl.hop_dong_cho_giao, dang_van_chuyen=dl.dang_van_chuyen,
                chi_tieu=dl.chi_tieu,
                de_xuat_poq=forecast.tinh_poq(v, dl.ton_kho, dl.hop_dong_cho_giao, dl.dang_van_chuyen,
                                              an_toan, dl.chi_tieu),
                don_gia_von=Decimal(str(round(dl.don_gia_von, 2))), ghi_chu=ghi))
        DongDuBao.objects.bulk_create(dong)
    return phien


def tong_ket(cac_dong, so_luong=None):
    """Tổng số lượng, tổng chỉ tiêu, tỷ lệ % so với chỉ tiêu, tổng vốn nhập.

    so_luong: dict {id dòng: số lượng} để tính thử; mặc định lấy số lượng đã lưu.
    """
    tong_sl = tong_von = tong_ct = 0
    co_chi_tieu = False
    for d in cac_dong:
        sl = d.so_luong_nhap if so_luong is None else so_luong.get(d.pk, d.so_luong_nhap)
        tong_sl += sl
        tong_von += sl * d.don_gia_von
        if d.chi_tieu is not None:
            co_chi_tieu = True
            tong_ct += d.chi_tieu
    ty_le = round(tong_sl * 100 / tong_ct, 1) if tong_ct else None
    return {"tong_sl": tong_sl, "tong_chi_tieu": tong_ct if co_chi_tieu else None,
            "ty_le": ty_le, "tong_von": tong_von, "vuot": bool(co_chi_tieu and tong_sl > tong_ct)}
