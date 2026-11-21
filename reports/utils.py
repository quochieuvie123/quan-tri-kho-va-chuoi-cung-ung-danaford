from collections import defaultdict
from datetime import date, datetime, timedelta

from django.core.exceptions import ValidationError
from django.db.models import (
    Case, Count, DateTimeField, F, Max, Min, Prefetch, Q, Sum, When,
)
from django.db.models.functions import TruncMonth
from django.utils import timezone

from database.models import (
    BienBanPDI,
    ChiTietHopDong,
    HopDong,
    Kho,
    PhieuXuatKho,
    TrangThaiHopDong,
    TrangThaiPhieuXuat,
    TrangThaiXe,
    TonKho,
)

from alerts.models import CanhBao
from analytics.models import HOAN_TAT, PhienDuBao
from incidents.models import HoSoSuCo, nhan_trang_thai
from orders.models import VehicleRequest, VehicleRequestItem
from transfers.models import LenhLuuChuyen, ChiTietLenhLuuChuyen
from warehouse.models import PhieuNhapKho
from .forms import MAX_KHOANG_BAO_CAO_THANG


QUYEN_BAO_CAO = (
    "database.view_tonkho",
    "warehouse.view_phieunhapkho",
    "database.view_phieuxuatkho",
    "database.view_hopdong",
    "database.view_bienbanpdi",
)


def lay_kho_duoc_xem(user):
    if (
        user.is_superuser
        or user.groups.filter(name="Quản lý").exists()
    ):
        return (
            Kho.objects
            .select_related("chi_nhanh")
            .order_by("ma_kho")
        )

    nhan_vien = getattr(user, "nhan_vien", None)

    if nhan_vien:
        return Kho.objects.filter(
            chi_nhanh_id=nhan_vien.chi_nhanh_id
        ).order_by("ma_kho")

    return Kho.objects.none()


def loc_ngay(queryset, truong, bo_loc, la_datefield=False):
    if la_datefield:
        ten_truong = truong
    else:
        ten_truong = truong + "__date"

    cac_thang = bo_loc.get("cac_thang")
    if cac_thang:
        q_thang = Q()
        for moc in cac_thang:
            if moc.month == 12:
                thang_sau = date(moc.year + 1, 1, 1)
            else:
                thang_sau = date(moc.year, moc.month + 1, 1)
            ngay_cuoi = thang_sau - timedelta(days=1)
            q_thang |= Q(**{
                ten_truong + "__gte": moc,
                ten_truong + "__lte": ngay_cuoi,
            })
        return queryset.filter(q_thang)

    if bo_loc.get("tu_ngay"):
        queryset = queryset.filter(**{
            ten_truong + "__gte": bo_loc["tu_ngay"],
        })

    if bo_loc.get("den_ngay"):
        queryset = queryset.filter(**{
            ten_truong + "__lte": bo_loc["den_ngay"],
        })

    return queryset


def dinh_dang_ngay(value):
    if not value:
        return ""

    if isinstance(value, datetime):
        if timezone.is_aware(value):
            value = timezone.localtime(value)
        return value.strftime("%d/%m/%Y %H:%M")

    return value.strftime("%d/%m/%Y")


def thong_ke_thang(queryset, truong, phep_tinh):
    rows = (
        queryset
        .filter(**{f"{truong}__isnull": False})
        .order_by()
        .annotate(thang=TruncMonth(truong))
        .values("thang")
        .annotate(tong=phep_tinh)
        .order_by("thang")
    )

    ket_qua = {}

    for dong in rows:
        if dong["thang"] is not None:
            thang = dong["thang"]
            if isinstance(thang, datetime):
                thang = thang.date()
            thang = thang.replace(day=1)
            ket_qua[thang] = dong["tong"]

    return ket_qua


def tao_truc_thang(cac_nhom, bo_loc):
    cac_thang_chon = bo_loc.get("cac_thang")
    if cac_thang_chon:
        return sorted(set(m.replace(day=1) for m in cac_thang_chon))

    cac_moc = []

    for nhom in cac_nhom:
        for moc in nhom:
            cac_moc.append(moc)

    if not cac_moc:
        return []

    dau = bo_loc.get("tu_ngay") or min(cac_moc)
    cuoi = bo_loc.get("den_ngay") or max(cac_moc)

    dau = dau.replace(day=1)
    cuoi = cuoi.replace(day=1)

    bat_dau = dau.year * 12 + dau.month - 1
    ket_thuc = cuoi.year * 12 + cuoi.month - 1

    if ket_thuc - bat_dau + 1 > MAX_KHOANG_BAO_CAO_THANG:
        raise ValidationError(
            "Khoảng thời gian báo cáo không được vượt quá 120 tháng."
        )

    danh_sach_thang = []

    for chi_so in range(bat_dau, ket_thuc + 1):
        nam = chi_so // 12
        thang = chi_so % 12 + 1

        danh_sach_thang.append(date(nam, thang, 1))

    return danh_sach_thang


def lay_phieu_nhap(kho_ids, ten_xe, bo_loc):
    danh_sach = PhieuNhapKho.objects.filter(
        kho_id__in=kho_ids,
        trang_thai__in=[
            PhieuNhapKho.TrangThai.NHAP,
            PhieuNhapKho.TrangThai.CHO_DUYET,
            PhieuNhapKho.TrangThai.DA_DUYET,
        ],
    )

    if ten_xe:
        danh_sach = danh_sach.filter(
            xe__ten_xe__icontains=ten_xe,
        )

    return loc_ngay(
        danh_sach, "ngay_nhap", bo_loc, la_datefield=True,
    )


def lay_phieu_xuat(kho_ids, ten_xe, bo_loc):
    danh_sach = PhieuXuatKho.objects.filter(
        Q(trang_thai=TrangThaiPhieuXuat.CHO_DUYET)
        | Q(
            trang_thai=TrangThaiPhieuXuat.DA_DUYET,
            ngay_xuat__isnull=False,
        ),
        kho_id__in=kho_ids,
    ).annotate(
        ngay_bao_cao=Case(
            When(
                trang_thai=TrangThaiPhieuXuat.DA_DUYET,
                then=F("ngay_xuat"),
            ),
            default=F("ngay_lap"),
            output_field=DateTimeField(),
        ),
    )

    if ten_xe:
        danh_sach = danh_sach.filter(
            chi_tiet_hop_dong__xe__ten_xe__icontains=ten_xe,
        )

    return loc_ngay(danh_sach, "ngay_bao_cao", bo_loc)


def kiem_tra_khoang_ngay(cac_nguon, bo_loc):
    tu_ngay = bo_loc.get("tu_ngay")
    den_ngay = bo_loc.get("den_ngay")

    # Form đã kiểm tra trường hợp có đủ hai ngày.
    # Không chọn ngày thì không giới hạn dữ liệu chi tiết/Excel.
    if (tu_ngay and den_ngay) or (not tu_ngay and not den_ngay):
        return

    cac_moc = []

    for queryset, truong in cac_nguon:
        if tu_ngay:
            moc = queryset.aggregate(moc=Max(truong))["moc"]
        else:
            moc = queryset.aggregate(moc=Min(truong))["moc"]

        if moc is not None:
            if isinstance(moc, datetime):
                if timezone.is_aware(moc):
                    moc = timezone.localtime(moc)
                moc = moc.date()
            cac_moc.append(moc)

    if not cac_moc:
        return

    if tu_ngay:
        den_ngay = max(cac_moc)
    else:
        tu_ngay = min(cac_moc)

    so_thang = (
        (den_ngay.year - tu_ngay.year) * 12
        + den_ngay.month - tu_ngay.month + 1
    )

    if so_thang > MAX_KHOANG_BAO_CAO_THANG:
        raise ValidationError(
            "Khoảng thời gian báo cáo không được vượt quá 120 tháng. "
            "Vui lòng chọn thêm ngày còn lại để thu hẹp khoảng báo cáo."
        )


def tao_bao_cao(
    kho_duoc_xem,
    bo_loc,
    kem_thong_ke=False,
    user=None,
):

    if bo_loc.get("kho"):
        kho_duoc_xem = kho_duoc_xem.filter(
            pk=bo_loc["kho"].pk
        )

    kho_ids = list(
        kho_duoc_xem.values_list("pk", flat=True)
    )

    chi_nhanh_ids = list(
        kho_duoc_xem.values_list(
            "chi_nhanh_id",
            flat=True,
        )
    )

    ten = bo_loc.get("ten_xe", "")
    today = timezone.localdate()
    data = {}

    # Tồn kho hiện tại.
    ton_qs = TonKho.objects.filter(
        kho_id__in=kho_ids,
        so_luong_ton__gt=0,
    )

    if ten:
        ton_qs = ton_qs.filter(
            xe__ten_xe__icontains=ten
        )

    ton = list(
        ton_qs.select_related("xe").order_by(
            "kho_id",
            "xe__ten_xe",
            "xe_id",
        )
    )

    nhom_tuoi = [0, 0, 0, 0]

    dong_ton = []
    dong_tuoi = []

    for item in ton:
        mau = item.xe.mau_sac or "Chưa có màu"
        tuoi = (today - item.ngay_vao_kho).days

        if tuoi < 0:
            nhom = 3
            tuoi_hien_thi = "Ngày vào kho không hợp lệ"
        else:
            if tuoi <= 30:
                nhom = 0
            elif tuoi <= 60:
                nhom = 1
            else:
                nhom = 2

            tuoi_hien_thi = tuoi

        nhom_tuoi[nhom] += item.so_luong_ton

        dong_ton.append([
            item.kho_id,
            item.xe_id,
            item.xe.ten_xe,
            mau,
            item.so_luong_ton,
        ])

        dong_tuoi.append([
            item.kho_id,
            item.xe_id,
            item.xe.ten_xe,
            item.ngay_vao_kho.strftime("%d/%m/%Y"),
            tuoi_hien_thi,
            item.so_luong_ton,
        ])

    tong_ton = sum(
        item.so_luong_ton for item in ton
    )
    so_san_sang = sum(
        item.so_luong_ton for item in ton if item.xe.trang_thai == TrangThaiXe.SAN_SANG
    )
    so_giu_cho = sum(
        item.so_luong_ton for item in ton if item.xe.trang_thai == TrangThaiXe.GIU_CHO_XUAT
    )
    so_khac = tong_ton - so_san_sang - so_giu_cho
    ghi_chu_ton = f"Sẵn sàng: {so_san_sang}; Giữ chỗ xuất: {so_giu_cho}"
    if so_khac:
        ghi_chu_ton += f"; Khác: {so_khac}"

    data["ton_kho"] = {
        "ten": "Tồn kho hiện tại",
        "don_vi": "xe",
        "tong": tong_ton,
        "cot": [
            "Kho",
            "VIN",
            "Tên xe",
            "Màu sắc",
            "Số lượng tồn",
        ],
        "dong": dong_ton,
        "ghi_chu": ghi_chu_ton,
    }

    data["tuoi_ton"] = {
        "ten": "Tuổi tồn hiện tại",
        "don_vi": "xe",
        "tong": tong_ton,
        "cot": [
            "Kho",
            "VIN",
            "Tên xe",
            "Ngày vào kho",
            "Số ngày tồn",
            "Số lượng tồn",
        ],
        "dong": dong_tuoi,
        "nhom": list(zip(
            [
                "Từ 0 đến 30 ngày",
                "Từ 31 đến 60 ngày",
                "Trên 60 ngày",
                "Ngày vào kho không hợp lệ",
            ],
            nhom_tuoi,
        )),
        "ton_lau": nhom_tuoi[2],
        "ty_le_ton_lau": (
            round(nhom_tuoi[2] * 100 / tong_ton, 1)
            if tong_ton
            else 0
        ),
        "ngay_khong_hop_le": nhom_tuoi[3],
    }

    # Phiếu nhập theo trạng thái hiện tại.
    nhap = lay_phieu_nhap(kho_ids, ten, bo_loc)
    danh_sach_nhap = nhap.select_related("xe").order_by(
        "ngay_nhap", "pk",
    )

    dong = []
    dem_nhap = {"Nháp": 0, "Chờ duyệt": 0, "Đã duyệt": 0}

    for phieu in danh_sach_nhap:
        trang_thai = phieu.get_trang_thai_display()
        dem_nhap[trang_thai] += 1

        dong.append([
            phieu.ma_phieu,
            phieu.kho_id,
            dinh_dang_ngay(phieu.ngay_lap),
            dinh_dang_ngay(phieu.ngay_nhap),
            phieu.xe_id,
            phieu.xe.ten_xe,
            trang_thai,
            1,
        ])

    data["nhap_kho"] = {
        "ten": "Phiếu nhập trong kỳ",
        "don_vi": "phiếu",
        "tong": len(dong),
        "cot": [
            "Phiếu nhập", "Kho", "Ngày lập", "Ngày nhập trên phiếu",
            "VIN", "Tên xe", "Trạng thái", "Số xe trên phiếu",
        ],
        "dong": dong,
        "ghi_chu": (
            f"Nháp: {dem_nhap['Nháp']}; "
            f"Chờ duyệt: {dem_nhap['Chờ duyệt']}; "
            f"Đã duyệt: {dem_nhap['Đã duyệt']}"
        ),
    }

    # Phiếu xuất: chờ duyệt theo ngày lập, đã duyệt theo ngày xuất.
    xuat = lay_phieu_xuat(kho_ids, ten, bo_loc)
    danh_sach_xuat = xuat.select_related(
        "chi_tiet_hop_dong__xe",
    ).order_by("ngay_bao_cao", "pk")

    dong = []
    dem_xuat = {"Chờ duyệt": 0, "Đã duyệt": 0}

    for phieu in danh_sach_xuat:
        trang_thai = phieu.get_trang_thai_display()
        dem_xuat[trang_thai] += 1
        ngay_xuat = None

        if phieu.trang_thai == TrangThaiPhieuXuat.DA_DUYET:
            ngay_xuat = phieu.ngay_xuat

        dong.append([
            phieu.pk,
            phieu.kho_id,
            dinh_dang_ngay(phieu.ngay_lap),
            dinh_dang_ngay(ngay_xuat),
            phieu.chi_tiet_hop_dong.xe_id,
            phieu.chi_tiet_hop_dong.xe.ten_xe,
            trang_thai,
            1,
        ])

    data["xuat_kho"] = {
        "ten": "Phiếu xuất trong kỳ",
        "don_vi": "phiếu",
        "tong": len(dong),
        "cot": [
            "Phiếu xuất", "Kho", "Ngày lập", "Ngày xuất thực tế",
            "VIN", "Tên xe", "Trạng thái", "Số xe trên phiếu",
        ],
        "dong": dong,
        "ghi_chu": (
            f"Chờ duyệt: {dem_xuat['Chờ duyệt']}; "
            f"Đã duyệt: {dem_xuat['Đã duyệt']}"
        ),
    }

    # Hợp đồng được đếm một lần.
    hop_dong = HopDong.objects.filter(
        chi_nhanh_id__in=chi_nhanh_ids
    )

    if ten:
        ma_hd = ChiTietHopDong.objects.filter(
            xe__ten_xe__icontains=ten
        ).values("hop_dong_id")

        hop_dong = hop_dong.filter(
            Q(pk__in=ma_hd)
            | Q(dong_xe_yeu_cau__icontains=ten)
            | Q(phien_ban_yeu_cau__icontains=ten)
        )

    hop_dong = loc_ngay(
        hop_dong,
        "ngay_ky",
        bo_loc,
    )

    dong = []
    so_cho_xu_ly = 0
    so_hoan_tat_hd = 0
    for item in (
        hop_dong.select_related(
            "khach_hang"
        ).order_by(
            "ngay_ky",
            "pk",
        )
    ):
        if item.trang_thai in (TrangThaiHopDong.CHO_XU_LY, TrangThaiHopDong.CHO_PHAN_BO):
            so_cho_xu_ly += 1
        else:
            so_hoan_tat_hd += 1
        dong.append([
            item.pk,
            item.chi_nhanh_id,
            dinh_dang_ngay(item.ngay_ky),
            item.khach_hang.ten_kh,
        ])

    data["hop_dong"] = {
        "ten": "Hợp đồng ký trong kỳ",
        "don_vi": "hợp đồng",
        "tong": len(dong),
        "cot": [
            "Mã hợp đồng",
            "Chi nhánh",
            "Ngày ký",
            "Khách hàng",
        ],
        "dong": dong,
        "ghi_chu": f"Chờ xử lý: {so_cho_xu_ly}; Hoàn tất: {so_hoan_tat_hd}",
    }

    # PDI theo trạng thái hiện tại (bao gồm cả sự cố từ hóa đơn nhập hãng và từ lệnh lưu chuyển nội bộ).
    pdi = BienBanPDI.objects.filter(
        Q(hoa_don_nhap__chi_nhanh_id__in=chi_nhanh_ids)
        | Q(lenh_luu_chuyen__kho_nhap__chi_nhanh_id__in=chi_nhanh_ids)
    ).distinct()

    if ten:
        pdi = pdi.filter(
            xe__ten_xe__icontains=ten
        )

    pdi = loc_ngay(
        pdi,
        "ngay_ghi_nhan",
        bo_loc,
    )

    dong = []
    trang_thai = defaultdict(int)

    for item in (
        pdi.select_related(
            "xe",
            "hoa_don_nhap",
            "lenh_luu_chuyen__kho_nhap",
        ).order_by(
            "ngay_ghi_nhan",
            "pk",
        )
    ):
        state = (
            item.trang_thai_claim
            or "Chưa xác định"
        )

        trang_thai[state] += 1
        cn_id = (
            item.hoa_don_nhap.chi_nhanh_id
            if item.hoa_don_nhap_id
            else (item.lenh_luu_chuyen.kho_nhap.chi_nhanh_id if item.lenh_luu_chuyen_id and item.lenh_luu_chuyen.kho_nhap else "CN01")
        )

        dong.append([
            item.pk,
            cn_id,
            dinh_dang_ngay(item.ngay_ghi_nhan),
            item.xe_id,
            item.xe.ten_xe,
            item.loai_su_co,
            state,
        ])

    ghi_chu_pdi = (
        "; ".join(f"{k}: {v}" for k, v in sorted(trang_thai.items()))
        if trang_thai
        else "Chưa xử lý: 0; Đã xử lý: 0"
    )
    data["pdi"] = {
        "ten": "Biên bản PDI trong kỳ",
        "don_vi": "biên bản",
        "tong": len(dong),
        "cot": [
            "Mã PDI",
            "Chi nhánh",
            "Ngày ghi nhận",
            "VIN",
            "Tên xe",
            "Loại sự cố",
            "Trạng thái hiện tại",
        ],
        "dong": dong,
        "nhom": sorted(trang_thai.items()),
        "ghi_chu": ghi_chu_pdi,
    }

    kiem_tra_khoang_ngay([
        (nhap, "ngay_nhap"),
        (xuat, "ngay_bao_cao"),
        (hop_dong, "ngay_ky"),
        (pdi, "ngay_ghi_nhan"),
    ], bo_loc)

    if kem_thong_ke:
        # Tổng tồn theo tên xe.
        theo_ten = (
            ton_qs.order_by()
            .values("xe__ten_xe")
            .annotate(
                tong=Sum("so_luong_ton", default=0)
            )
            .order_by("-tong", "xe__ten_xe")
        )

        data["ton_kho"]["theo_ten"] = [
            [row["xe__ten_xe"], row["tong"]]
            for row in theo_ten
        ]

        # Bao gồm cả kho có tồn bằng 0.
        theo_kho = (
            ton_qs.order_by()
            .values("kho_id")
            .annotate(
                tong=Sum("so_luong_ton", default=0)
            )
        )

        tong_theo_kho = {
            row["kho_id"]: row["tong"]
            for row in theo_kho
        }

        data["ton_kho"]["theo_kho"] = [
            [ma_kho, tong_theo_kho.get(ma_kho, 0)]
            for ma_kho in kho_ids
        ]

        # Mỗi trạng thái có một bảng tổng hợp theo tháng.
        nhap_theo_trang_thai = {}
        xuat_theo_trang_thai = {}
        cac_nhom_thang = []

        for trang_thai in [
            PhieuNhapKho.TrangThai.NHAP,
            PhieuNhapKho.TrangThai.CHO_DUYET,
            PhieuNhapKho.TrangThai.DA_DUYET,
        ]:
            ket_qua = thong_ke_thang(
                nhap.filter(trang_thai=trang_thai),
                "ngay_nhap",
                Count("pk", distinct=True),
            )
            nhap_theo_trang_thai[trang_thai] = ket_qua
            cac_nhom_thang.append(ket_qua)

        for trang_thai in [
            TrangThaiPhieuXuat.CHO_DUYET,
            TrangThaiPhieuXuat.DA_DUYET,
        ]:
            ket_qua = thong_ke_thang(
                xuat.filter(trang_thai=trang_thai),
                "ngay_bao_cao",
                Count("pk", distinct=True),
            )
            xuat_theo_trang_thai[trang_thai] = ket_qua
            cac_nhom_thang.append(ket_qua)

        truc_nhap_xuat = tao_truc_thang(cac_nhom_thang, bo_loc)
        dong_theo_thang = []

        for moc in truc_nhap_xuat:
            dong_theo_thang.append([
                moc.strftime("%m/%Y"),
                nhap_theo_trang_thai[PhieuNhapKho.TrangThai.NHAP].get(moc, 0),
                nhap_theo_trang_thai[PhieuNhapKho.TrangThai.CHO_DUYET].get(moc, 0),
                nhap_theo_trang_thai[PhieuNhapKho.TrangThai.DA_DUYET].get(moc, 0),
                xuat_theo_trang_thai[TrangThaiPhieuXuat.CHO_DUYET].get(moc, 0),
                xuat_theo_trang_thai[TrangThaiPhieuXuat.DA_DUYET].get(moc, 0),
            ])

        data["nhap_kho"]["theo_thang"] = dong_theo_thang

        # Giữ nguyên thống kê hợp đồng theo tháng.
        hd_thang = thong_ke_thang(
            hop_dong,
            "ngay_ky",
            Count("pk", distinct=True),
        )

        truc_hop_dong = tao_truc_thang([hd_thang], bo_loc)

        data["hop_dong"]["theo_thang"] = [
            [
                moc.strftime("%m/%Y"),
                hd_thang.get(moc, 0),
            ]
            for moc in truc_hop_dong
        ]

    if user is not None:
        if user.has_perm(QUYEN_XEM_TUNG_BAO_CAO["dat_xe"]):
            data["dat_xe"] = tao_bao_cao_dat_xe(
                user, bo_loc, kem_thong_ke,
            )

        if user.has_perm(QUYEN_XEM_TUNG_BAO_CAO["luu_chuyen"]):
            data["luu_chuyen"] = tao_bao_cao_luu_chuyen(
                kho_duoc_xem, bo_loc, kem_thong_ke,
            )

        if user.has_perm(QUYEN_XEM_TUNG_BAO_CAO["canh_bao"]):
            data["canh_bao"] = tao_bao_cao_canh_bao(
                kho_duoc_xem, bo_loc,
            )

        if user.has_perm(QUYEN_XEM_TUNG_BAO_CAO["du_bao"]):
            data["du_bao"] = tao_bao_cao_du_bao(
                bo_loc, kem_thong_ke,
            )

        if user.has_perm(QUYEN_XEM_TUNG_BAO_CAO["su_co"]):
            data["su_co"] = tao_bao_cao_su_co(
                kho_duoc_xem, bo_loc, kem_thong_ke,
            )

    return data


# Quyền xem tương ứng với từng loại báo cáo.
QUYEN_XEM_TUNG_BAO_CAO = {
    "dat_xe": "orders.view_vehiclerequest",
    "luu_chuyen": "transfers.view_lenhluuchuyen",
    "canh_bao": "alerts.view_canhbao",
    "du_bao": "analytics.view_phiendubao",
    "su_co": "incidents.view_hososuco",
}


def thong_ke_thang_theo_trang_thai(
    queryset, truong_ngay, truong_trang_thai, cac_trang_thai, bo_loc,
):
    cac_ket_qua = []
    cac_moc = []

    for ma, ten in cac_trang_thai:
        ket_qua = thong_ke_thang(
            queryset.filter(**{truong_trang_thai: ma}),
            truong_ngay,
            Count("pk", distinct=True),
        )
        cac_ket_qua.append((ten, ket_qua))
        cac_moc.append(ket_qua)

    truc_thang = tao_truc_thang(cac_moc, bo_loc)
    cac_nhom = []

    for ten, ket_qua in cac_ket_qua:
        so_luong = []
        for moc in truc_thang:
            so_luong.append(ket_qua.get(moc, 0))
        cac_nhom.append({"ten": ten, "so_luong": so_luong})

    return {
        "thang": [moc.strftime("%m/%Y") for moc in truc_thang],
        "cac_nhom": cac_nhom,
    }


def tao_bao_cao_dat_xe(user, bo_loc, kem_thong_ke=False):
    phieu = VehicleRequest.objects.all()

    if not user.is_superuser:
        phieu = phieu.filter(created_by=user)

    ten = bo_loc.get("ten_xe", "")
    chi_tiet = VehicleRequestItem.objects.select_related("allocation")

    if ten:
        chi_tiet = chi_tiet.filter(
            Q(allocation__description__icontains=ten)
            | Q(allocation__vehicle_code__icontains=ten)
        )
        phieu = phieu.filter(
            pk__in=chi_tiet.values("vehicle_request_id"),
        )

    phieu = loc_ngay(phieu, "created_at", bo_loc)
    kiem_tra_khoang_ngay([(phieu, "created_at")], bo_loc)

    danh_sach = phieu.select_related("created_by").prefetch_related(
        Prefetch("items", queryset=chi_tiet, to_attr="chi_tiet_bao_cao"),
    ).order_by("created_at", "pk")

    dong = []
    tong_phieu = 0
    tong_xe = 0

    for item in danh_sach:
        tong_phieu += 1
        trang_thai = item.get_status_display()

        if not item.chi_tiet_bao_cao:
            dong.append([
                item.request_number, dinh_dang_ngay(item.created_at),
                item.created_by.get_username(), "", "", "", "", 0,
                trang_thai,
            ])

        for ct in item.chi_tiet_bao_cao:
            xe = ct.allocation
            tong_xe += ct.quantity
            dong.append([
                item.request_number, dinh_dang_ngay(item.created_at),
                item.created_by.get_username(), xe.vehicle_code,
                xe.description, xe.vin, xe.exterior_color,
                ct.quantity, trang_thai,
            ])

    ket_qua = {
        "ten": "Yêu cầu đặt xe trong kỳ",
        "don_vi": "phiếu",
        "tong": tong_phieu,
        "cot": [
            "Mã phiếu", "Ngày lập", "Người lập", "Mã dòng xe",
            "Mô tả xe", "VIN", "Màu", "Số lượng yêu cầu", "Trạng thái",
        ],
        "dong": dong,
        "ghi_chu": (
            f"Tổng số xe yêu cầu: {tong_xe}. "
            "Bộ lọc kho không áp dụng cho phiếu đặt xe."
        ),
    }

    if kem_thong_ke:
        ket_qua["theo_thang"] = thong_ke_thang_theo_trang_thai(
            phieu, "created_at", "status",
            VehicleRequest.Status.choices, bo_loc,
        )

    return ket_qua


def tao_bao_cao_luu_chuyen(kho_duoc_xem, bo_loc, kem_thong_ke=False):
    if bo_loc.get("kho"):
        kho_duoc_xem = kho_duoc_xem.filter(pk=bo_loc["kho"].pk)

    lenh = LenhLuuChuyen.objects.filter(
        Q(kho_xuat__in=kho_duoc_xem) | Q(kho_nhap__in=kho_duoc_xem),
    ).distinct()

    ten = bo_loc.get("ten_xe", "")
    chi_tiet = ChiTietLenhLuuChuyen.objects.select_related("xe")

    if ten:
        chi_tiet = chi_tiet.filter(xe__ten_xe__icontains=ten)
        lenh = lenh.filter(pk__in=chi_tiet.values("lenh_id"))

    lenh = loc_ngay(lenh, "ngay_lap", bo_loc)
    kiem_tra_khoang_ngay([(lenh, "ngay_lap")], bo_loc)

    danh_sach = lenh.select_related("kho_xuat", "kho_nhap").prefetch_related(
        Prefetch("chi_tiet", queryset=chi_tiet, to_attr="chi_tiet_bao_cao"),
    ).order_by("ngay_lap", "pk")

    dong = []
    tong_lenh = 0
    tong_xe = 0
    xe_da_xac_nhan = 0

    for item in danh_sach:
        tong_lenh += 1
        ma_lenh = item.ma_lenh or f"LLC{item.pk}"
        trang_thai = item.get_trang_thai_display()

        if not item.chi_tiet_bao_cao:
            dong.append([
                ma_lenh, item.kho_xuat_id, item.kho_nhap_id,
                dinh_dang_ngay(item.ngay_lap), "", "", 0, trang_thai,
            ])

        for ct in item.chi_tiet_bao_cao:
            tong_xe += ct.so_luong
            if item.trang_thai in ("DA_XAC_NHAN", LenhLuuChuyen.TrangThai.HOAN_TAT):
                xe_da_xac_nhan += ct.so_luong

            dong.append([
                ma_lenh, item.kho_xuat_id, item.kho_nhap_id,
                dinh_dang_ngay(item.ngay_lap), ct.xe_id,
                ct.xe.ten_xe, ct.so_luong, trang_thai,
            ])

    ket_qua = {
        "ten": "Lệnh lưu chuyển trong kỳ",
        "don_vi": "lệnh",
        "tong": tong_lenh,
        "cot": [
            "Mã lệnh", "Kho xuất", "Kho nhận", "Ngày lập",
            "VIN", "Tên xe", "Số lượng", "Trạng thái",
        ],
        "dong": dong,
        "ghi_chu": (
            f"Số xe trên các lệnh: {tong_xe}; "
            f"trong đó đã xác nhận: {xe_da_xac_nhan}."
        ),
    }

    if kem_thong_ke:
        ket_qua["theo_thang"] = thong_ke_thang_theo_trang_thai(
            lenh, "ngay_lap", "trang_thai",
            LenhLuuChuyen.TRANG_THAI, bo_loc,
        )

    return ket_qua


def tao_bao_cao_canh_bao(kho_duoc_xem, bo_loc):
    if bo_loc.get("kho"):
        kho_duoc_xem = kho_duoc_xem.filter(pk=bo_loc["kho"].pk)

    danh_sach = CanhBao.objects.filter(
        Q(kho__in=kho_duoc_xem) | Q(cac_kho__in=kho_duoc_xem),
    ).distinct()

    ten = bo_loc.get("ten_xe", "")
    if ten:
        danh_sach = danh_sach.filter(
            Q(xe__ten_xe__icontains=ten)
            | Q(nguong__ten_xe__icontains=ten),
        )

    danh_sach = loc_ngay(danh_sach, "ngay_phat_sinh", bo_loc)
    kiem_tra_khoang_ngay([(danh_sach, "ngay_phat_sinh")], bo_loc)

    theo_loai = dict.fromkeys(CanhBao.Loai.labels, 0)
    theo_xu_ly = dict.fromkeys(CanhBao.TrangThai.labels, 0)
    theo_loai_va_xu_ly = {
        loai_label: dict.fromkeys(CanhBao.TrangThai.labels, 0)
        for loai_label in CanhBao.Loai.labels
    }
    dong = []
    con_hieu_luc = 0

    for cb in danh_sach.select_related("xe", "nguong", "kho").prefetch_related("cac_kho"):
        loai = cb.get_loai_display()
        xu_ly = cb.get_trang_thai_display()
        theo_loai[loai] += 1
        theo_xu_ly[xu_ly] += 1
        theo_loai_va_xu_ly.setdefault(loai, dict.fromkeys(CanhBao.TrangThai.labels, 0))
        theo_loai_va_xu_ly[loai][xu_ly] = theo_loai_va_xu_ly[loai].get(xu_ly, 0) + 1

        if cb.con_hieu_luc:
            con_hieu_luc += 1

        if cb.loai == CanhBao.Loai.TON_LAU:
            doi_tuong = f"{cb.xe_id} ({cb.xe.ten_xe})"
            so_lieu = f"{cb.so_ngay_ton} ngày"
        else:
            mau = cb.nguong.mau_sac or "Chưa có màu"
            doi_tuong = f"{cb.nguong.ten_xe} ({mau})"
            so_lieu = f"{cb.so_luong_hien_tai} xe"

        dong.append([
            f"CB{cb.pk}", loai, cb.kho_hien_thi, doi_tuong, so_lieu,
            "Còn hiệu lực" if cb.con_hieu_luc else "Hết hiệu lực",
            xu_ly, dinh_dang_ngay(cb.ngay_phat_sinh),
        ])

    return {
        "ten": "Cảnh báo phát sinh trong kỳ",
        "don_vi": "cảnh báo",
        "tong": len(dong),
        "cot": [
            "Mã cảnh báo", "Loại", "Kho liên quan", "Đối tượng",
            "Số liệu hiện tại", "Hiệu lực", "Trạng thái xử lý", "Ngày phát sinh",
        ],
        "dong": dong,
        "ghi_chu": (
            f"Còn hiệu lực: {con_hieu_luc}; "
            f"hết hiệu lực: {len(dong) - con_hieu_luc}. "
            "Hiển thị trạng thái hiện tại của cảnh báo phát sinh trong kỳ."
        ),
        "theo_loai": theo_loai,
        "theo_xu_ly": theo_xu_ly,
        "theo_loai_va_xu_ly": theo_loai_va_xu_ly,
    }


def _dinh_dang_tien_vn(so_tien):
    """Định dạng số tiền VNĐ phân tách hàng nghìn bằng dấu chấm."""
    return f"{int(round(so_tien)):,}".replace(",", ".")


def _phien_khop_bo_loc(phien, bo_loc):
    """Kiểm tra kỳ dự báo (tháng/năm) có nằm trong bộ lọc thời gian hay không."""
    if not (1 <= phien.thang <= 12):
        return False

    cac_thang = bo_loc.get("cac_thang")
    if cac_thang:
        return any(m.year == phien.nam and m.month == phien.thang for m in cac_thang)

    dau_ky = date(phien.nam, phien.thang, 1)
    thang_sau = (
        date(phien.nam + 1, 1, 1)
        if phien.thang == 12
        else date(phien.nam, phien.thang + 1, 1)
    )
    cuoi_ky = thang_sau - timedelta(days=1)

    tu_ngay = bo_loc.get("tu_ngay")
    den_ngay = bo_loc.get("den_ngay")
    if tu_ngay and cuoi_ky < tu_ngay:
        return False
    if den_ngay and dau_ky > den_ngay:
        return False
    return True


def tao_bao_cao_du_bao(bo_loc, kem_thong_ke=False):
    """Tổng hợp số liệu dự báo nhu cầu từ module analytics theo bộ lọc báo cáo."""
    phien_qs = (
        PhienDuBao.objects
        .filter(trang_thai=HOAN_TAT)
        .prefetch_related("dong")
        .order_by("-nam", "-thang", "-tao_luc", "-pk")
    )

    # Mỗi kỳ (năm, tháng) chỉ lấy phiên hoàn tất mới nhất để tránh cộng trùng khi phân tích lại.
    cac_phien = []
    ky_da_lay = set()
    for phien in phien_qs:
        ky = (phien.nam, phien.thang)
        if ky in ky_da_lay or not _phien_khop_bo_loc(phien, bo_loc):
            continue
        ky_da_lay.add(ky)
        cac_phien.append(phien)

    tu_ngay = bo_loc.get("tu_ngay")
    den_ngay = bo_loc.get("den_ngay")
    if not bo_loc.get("cac_thang") and (bool(tu_ngay) != bool(den_ngay)) and cac_phien:
        cac_moc = [date(p.nam, p.thang, 1) for p in cac_phien]
        moc_dau = tu_ngay or min(cac_moc)
        moc_cuoi = den_ngay or max(cac_moc)
        so_thang = (moc_cuoi.year - moc_dau.year) * 12 + moc_cuoi.month - moc_dau.month + 1
        if so_thang > MAX_KHOANG_BAO_CAO_THANG:
            raise ValidationError(
                "Khoảng thời gian báo cáo không được vượt quá 120 tháng. "
                "Vui lòng chọn thêm ngày còn lại để thu hẹp khoảng báo cáo."
            )

    ten = (bo_loc.get("ten_xe") or "").strip().lower()
    dong = []
    tong_du_bao_raw = 0.0
    tong_ky_truoc = 0
    tong_nhap = 0
    hang_bieu_do = []
    ky_bieu_do = ""

    for chi_so, phien in enumerate(cac_phien):
        ky_nhan = f"{phien.thang:02d}/{phien.nam}"
        cac_dong = [
            d for d in phien.dong.all()
            if not ten or ten in d.ten_xe.lower()
        ]
        if chi_so == 0 and cac_dong:
            ky_bieu_do = ky_nhan

        for d in cac_dong:
            du_bao = round(d.du_bao_sarima, 1)
            tong_du_bao_raw += d.du_bao_sarima
            tong_ky_truoc += d.ky_truoc
            tong_nhap += d.so_luong_nhap

            dong.append([
                ky_nhan,
                d.ma_dong_xe,
                d.ten_xe,
                d.loai_xe,
                d.ky_truoc,
                du_bao,
                d.ton_kho,
                d.de_xuat_poq,
                d.so_luong_nhap,
                phien.trang_thai_de_xuat,
            ])

            if chi_so == 0 and kem_thong_ke:
                hang_bieu_do.append({
                    "ten": f"{d.ten_ngan} {d.phien_ban}".strip() or d.ten_xe,
                    "ky_truoc": d.ky_truoc,
                    "du_bao": du_bao,
                    "de_xuat": d.so_luong_nhap,
                })

    tong_du_bao = round(tong_du_bao_raw, 1)
    if float(tong_du_bao).is_integer():
        tong_du_bao = int(tong_du_bao)

    if cac_phien:
        phien_moi = cac_phien[0]
        ghi_chu = (
            f"Kỳ mới nhất {phien_moi.thang:02d}/{phien_moi.nam} ({len(cac_phien)} kỳ); "
            f"Bán tháng trước: {tong_ky_truoc}; Đề xuất nhập: {tong_nhap} xe. "
            "Bộ lọc kho không áp dụng cho dự báo nhu cầu."
        )
    else:
        ghi_chu = "Chưa có phiên dự báo phù hợp. Bộ lọc kho không áp dụng cho dự báo nhu cầu."

    ket_qua = {
        "ten": "Nhu cầu dự báo trong kỳ",
        "don_vi": "xe",
        "tong": tong_du_bao,
        "cot": [
            "Kỳ dự báo", "Mã dòng xe", "Tên xe", "Phân khúc",
            "Bán tháng trước", "Dự báo SARIMA", "Tồn kho khả dụng",
            "Đề xuất POQ", "SL nhập dự kiến", "Trạng thái phiên",
        ],
        "dong": dong,
        "ghi_chu": ghi_chu,
    }

    if kem_thong_ke:
        ket_qua["so_sanh"] = {
            "ky": ky_bieu_do,
            "so_ky": len(cac_phien),
            "hang": hang_bieu_do,
        }

    return ket_qua


def tao_bao_cao_su_co(kho_duoc_xem, bo_loc, kem_thong_ke=False):
    """Tổng hợp sự cố vận chuyển từ module incidents/BienBanPDI theo bộ lọc báo cáo."""
    if bo_loc.get("kho"):
        kho_duoc_xem = kho_duoc_xem.filter(pk=bo_loc["kho"].pk)

    chi_nhanh_ids = list(kho_duoc_xem.values_list("chi_nhanh_id", flat=True))
    qs = BienBanPDI.objects.filter(
        Q(hoa_don_nhap__chi_nhanh_id__in=chi_nhanh_ids)
        | Q(lenh_luu_chuyen__kho_nhap__chi_nhanh_id__in=chi_nhanh_ids)
    ).distinct()

    ten = (bo_loc.get("ten_xe") or "").strip()
    if ten:
        qs = qs.filter(xe__ten_xe__icontains=ten)

    qs = loc_ngay(qs, "ngay_ghi_nhan", bo_loc)
    kiem_tra_khoang_ngay([(qs, "ngay_ghi_nhan")], bo_loc)

    danh_sach = qs.select_related(
        "xe",
        "hoa_don_nhap__don_vi_van_chuyen",
        "lenh_luu_chuyen__kho_nhap",
        "lenh_luu_chuyen__don_vi_van_chuyen",
        "ho_so",
    ).order_by("ngay_ghi_nhan", "pk")

    dong = []
    dang_xu_ly_count = 0
    da_dong_count = 0
    tong_boi_thuong = 0
    theo_loai = defaultdict(lambda: [0, 0])

    for item in danh_sach:
        trang_thai_xl = nhan_trang_thai(item.trang_thai_claim)
        loai = (item.loai_su_co or "Khác").strip()

        if trang_thai_xl == "Đã đóng":
            da_dong_count += 1
            theo_loai[loai][1] += 1
        else:
            dang_xu_ly_count += 1
            theo_loai[loai][0] += 1

        try:
            ho_so = item.ho_so
        except HoSoSuCo.DoesNotExist:
            ho_so = None

        hinh_thuc = (
            ho_so.get_hinh_thuc_khac_phuc_display()
            if ho_so and ho_so.hinh_thuc_khac_phuc
            else "—"
        )
        tien_bt = ho_so.so_tien_boi_thuong if ho_so and ho_so.so_tien_boi_thuong is not None else 0
        tong_boi_thuong += tien_bt

        cn_id = (
            item.hoa_don_nhap.chi_nhanh_id
            if item.hoa_don_nhap_id
            else (
                item.lenh_luu_chuyen.kho_nhap.chi_nhanh_id
                if item.lenh_luu_chuyen_id and item.lenh_luu_chuyen.kho_nhap
                else "CN01"
            )
        )

        dong.append([
            item.pk,
            cn_id,
            item.don_vi_van_chuyen or "—",
            dinh_dang_ngay(item.ngay_ghi_nhan),
            item.xe_id,
            item.xe.ten_xe,
            loai,
            trang_thai_xl,
            hinh_thuc,
            int(round(tien_bt)) if tien_bt else 0,
        ])

    ket_qua = {
        "ten": "Sự cố vận chuyển trong kỳ",
        "don_vi": "sự cố",
        "tong": len(dong),
        "cot": [
            "Mã sự cố", "Chi nhánh", "ĐVVC", "Ngày ghi nhận",
            "VIN", "Tên xe", "Loại sự cố", "Trạng thái xử lý",
            "Hình thức khắc phục", "Tiền bồi thường (VNĐ)",
        ],
        "dong": dong,
        "ghi_chu": (
            f"Đang xử lý: {dang_xu_ly_count}; Đã đóng: {da_dong_count}; "
            f"Bồi thường: {_dinh_dang_tien_vn(tong_boi_thuong)} đ"
        ),
    }

    if kem_thong_ke:
        ket_qua["theo_loai"] = sorted(
            [(loai, dem[0], dem[1]) for loai, dem in theo_loai.items()],
            key=lambda row: (-(row[1] + row[2]), row[0]),
        )

    return ket_qua

