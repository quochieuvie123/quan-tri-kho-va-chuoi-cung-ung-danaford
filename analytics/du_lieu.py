"""UC-09.1 Thu thập dữ liệu: gom và làm sạch dữ liệu đầu vào cho mô hình dự báo."""
from collections import defaultdict
from datetime import date
from dataclasses import dataclass, field

from django.db.models import Avg, Count, Sum
from django.db.models.functions import TruncMonth

from database.models import ChiTietBan, ChiTietHopDong, ChiTietNhap, TonKho, Xe

from . import forecast
from .models import ChiTieuPhanBo

SO_THANG_TOI_DA = 36


@dataclass
class DongXeDL:
    ten_xe: str
    loai_xe: str
    chuoi: list = field(default_factory=list)      # số xe bán theo tháng, đã làm sạch
    ky_truoc: int = 0
    ton_kho: int = 0
    hop_dong_cho_giao: int = 0
    dang_van_chuyen: int = 0
    chi_tieu: int | None = None
    don_gia_von: float = 0.0


@dataclass
class BoDuLieu:
    nam: int
    thang: int
    dong_xe: dict = field(default_factory=dict)
    nam_cuoi: int = 0
    thang_cuoi: int = 0
    canh_bao: list = field(default_factory=list)


def tach_ten(ten_xe):
    """'Ford Ranger XLS 2.0L 4x2 AT' -> ('Ford Ranger', 'XLS 2.0L 4x2 AT', 'RANGER-XLS-2.0L-4X2-AT')."""
    t = ten_xe.split()
    if len(t) <= 2:
        return ten_xe, "", ten_xe.upper().replace(" ", "-")
    return " ".join(t[:2]), " ".join(t[2:]), "-".join(t[1:]).upper()[:60]


def thu_thap(thang, nam):
    """Truy xuất 5 nguồn dữ liệu và tiền xử lý. Dự báo cho (thang, nam); lịch sử đến tháng liền trước."""
    bo = BoDuLieu(nam=nam, thang=thang)
    nam_cuoi, thang_cuoi = forecast.cong_thang(nam, thang, -1)
    bo.nam_cuoi, bo.thang_cuoi = nam_cuoi, thang_cuoi
    han_tren = forecast.cong_thang(nam_cuoi, thang_cuoi, 1)          # đầu tháng dự báo (loại trừ)

    # (0) Tất cả dòng xe đang quản lý
    for ten, loai in Xe.objects.values_list("ten_xe", "loai_xe").distinct():
        bo.dong_xe.setdefault(ten, DongXeDL(ten_xe=ten, loai_xe=loai))

    # (1) Lịch sử bán theo tháng (24-36 tháng gần nhất)
    ban = (ChiTietBan.objects
           .filter(hoa_don_ban__ngay_ban__date__lt=date(*han_tren, 1))
           .annotate(thang=TruncMonth("hoa_don_ban__ngay_ban"))
           .values("xe__ten_xe", "thang").annotate(sl=Sum("so_luong_ban")))
    theo_xe = defaultdict(dict)
    tong_thang = defaultdict(int)
    for r in ban:
        k = (r["thang"].year, r["thang"].month)
        theo_xe[r["xe__ten_xe"]][k] = r["sl"]
        tong_thang[k] += r["sl"]
    if tong_thang:
        dau = min(tong_thang)
        dau = max(dau, forecast.cong_thang(nam_cuoi, thang_cuoi, -(SO_THANG_TOI_DA - 1)))
        cac_thang = []
        k = dau
        while k <= (nam_cuoi, thang_cuoi):
            cac_thang.append(k)
            k = forecast.cong_thang(*k, 1)
        # tháng toàn hệ thống không có giao dịch nào = dữ liệu bị gián đoạn (khác với tháng bán 0 xe thật)
        thieu = {i for i, k in enumerate(cac_thang) if tong_thang.get(k, 0) == 0}
        if thieu:
            ds = ", ".join(f"{cac_thang[i][1]:02d}/{cac_thang[i][0]}" for i in sorted(thieu))
            bo.canh_bao.append(f"Dữ liệu bán hàng bị gián đoạn ở các tháng: {ds}. Đã điền khuyết bằng trung bình "
                               "trượt; độ tin cậy dự báo có thể giảm sút.")
        if len(cac_thang) < forecast.TOI_THIEU_MUA_VU:
            bo.canh_bao.append(f"Chỉ có {len(cac_thang)} tháng lịch sử (khuyến nghị 24-36 tháng).")
        for ten, dl in bo.dong_xe.items():
            goc = [theo_xe[ten].get(k, 0) for k in cac_thang]
            dl.chuoi = forecast.dien_khuyet(goc, thieu)
            dl.ky_truoc = theo_xe[ten].get((nam_cuoi, thang_cuoi), 0)
    else:
        bo.canh_bao.append("Chưa có dữ liệu bán hàng nào trong hệ thống.")

    # (2) Tồn kho khả dụng
    for r in TonKho.objects.values("xe__ten_xe").annotate(n=Sum("so_luong_ton")):
        bo.dong_xe[r["xe__ten_xe"]].ton_kho = r["n"] or 0
    # (3) Hợp đồng đã ký chờ giao xe (chưa có phiếu xuất kho)
    # Phiếu xuất kho có trạng thái: chỉ phiếu đã duyệt (xe đã rời kho) mới hết "chờ giao"
    for r in (ChiTietHopDong.objects.exclude(phieuxuatkho__trang_thai="DA_DUYET")
              .values("xe__ten_xe").annotate(n=Count("id"))):
        bo.dong_xe[r["xe__ten_xe"]].hop_dong_cho_giao = r["n"]
    # (4) Xe đang vận chuyển: đã có trên hóa đơn nhập nhưng chưa vào tồn kho và chưa bán
    dang_ve = (ChiTietNhap.objects
               .exclude(xe__in=TonKho.objects.filter(so_luong_ton__gt=0).values("xe"))
               .exclude(xe__in=ChiTietBan.objects.values("xe")))
    for r in dang_ve.values("xe__ten_xe").annotate(n=Sum("so_luong_nhap")):
        bo.dong_xe[r["xe__ten_xe"]].dang_van_chuyen = r["n"] or 0
    # (5) Chỉ tiêu phân bổ của hãng + đơn giá vốn bình quân
    for c in ChiTieuPhanBo.objects.filter(nam=nam, thang=thang):
        if c.ten_xe in bo.dong_xe:
            bo.dong_xe[c.ten_xe].chi_tieu = c.so_luong
    # Đồng bộ bổ sung từ bảng Allocation nếu dòng xe chưa được gán chỉ tiêu
    try:
        from orders.models import Allocation
        for a in (Allocation.objects
                  .filter(allocation_month__year=nam, allocation_month__month=thang)
                  .values("description").annotate(tong=Sum("quantity"))):
            dx = a["description"]
            if dx in bo.dong_xe and bo.dong_xe[dx].chi_tieu == 0:
                bo.dong_xe[dx].chi_tieu = a["tong"] or 0
    except Exception:
        pass
    for r in ChiTietNhap.objects.values("xe__ten_xe").annotate(g=Avg("don_gia")):
        bo.dong_xe[r["xe__ten_xe"]].don_gia_von = float(r["g"] or 0)
    return bo
