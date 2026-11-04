from collections import defaultdict
from datetime import date

from django.db.models import Count, Sum
from django.db.models.functions import TruncMonth
from django.utils import timezone

from database.models import (
    BienBanPDI,
    ChiTietHopDong,
    ChiTietNhap,
    HopDong,
    Kho,
    PhieuXuatKho,
    TonKho,
)


QUYEN_BAO_CAO = (
    "database.view_tonkho",
    "database.view_chitietnhap",
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


def loc_ngay(queryset, truong, bo_loc):
    if bo_loc.get("tu_ngay"):
        queryset = queryset.filter(
            **{
                f"{truong}__date__gte": bo_loc["tu_ngay"]
            }
        )

    if bo_loc.get("den_ngay"):
        queryset = queryset.filter(
            **{
                f"{truong}__date__lte": bo_loc["den_ngay"]
            }
        )

    return queryset


def dinh_dang_ngay(value):
    if timezone.is_aware(value):
        value = timezone.localtime(value)

    return value.strftime("%d/%m/%Y %H:%M")


def thong_ke_thang(queryset, truong, phep_tinh):
    rows = (
        queryset
        .order_by()
        .annotate(thang=TruncMonth(truong))
        .values("thang")
        .annotate(tong=phep_tinh)
        .order_by("thang")
    )

    return {
        row["thang"].date().replace(day=1): row["tong"]
        for row in rows
    }


def tao_truc_thang(cac_nhom, bo_loc):
    cac_moc = [
        moc
        for nhom in cac_nhom
        for moc in nhom
    ]

    if not cac_moc:
        return []

    dau = bo_loc.get("tu_ngay") or min(cac_moc)
    cuoi = bo_loc.get("den_ngay") or max(cac_moc)

    dau = dau.replace(day=1)
    cuoi = cuoi.replace(day=1)

    bat_dau = dau.year * 12 + dau.month - 1
    ket_thuc = cuoi.year * 12 + cuoi.month - 1

    return [
        date(i // 12, i % 12 + 1, 1)
        for i in range(bat_dau, ket_thuc + 1)
    ]


def tao_bao_cao(
    kho_duoc_xem,
    bo_loc,
    kem_thong_ke=False,
):
    """
    Chỉ đọc dữ liệu.

    kem_thong_ke=True khi cần dữ liệu vẽ biểu đồ.
    Trang chi tiết và Excel dùng cấu trúc báo cáo như cũ.
    """
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

    nhom_ton = defaultdict(int)
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

        nhom_ton[
            (
                item.kho_id,
                item.xe.ten_xe,
                mau,
            )
        ] += item.so_luong_ton

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
        "nhom": [
            [*key, value]
            for key, value in sorted(nhom_ton.items())
        ],
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

    # Nhập kho.
    nhap = ChiTietNhap.objects.filter(
        hoa_don_nhap__chi_nhanh_id__in=chi_nhanh_ids
    )

    if ten:
        nhap = nhap.filter(
            xe__ten_xe__icontains=ten
        )

    nhap = loc_ngay(
        nhap,
        "hoa_don_nhap__ngay_nhap",
        bo_loc,
    )

    dong = [
        [
            item.hoa_don_nhap_id,
            item.hoa_don_nhap.chi_nhanh_id,
            dinh_dang_ngay(
                item.hoa_don_nhap.ngay_nhap
            ),
            item.xe_id,
            item.xe.ten_xe,
            item.so_luong_nhap,
        ]
        for item in (
            nhap.select_related(
                "hoa_don_nhap",
                "xe",
            ).order_by(
                "hoa_don_nhap__ngay_nhap",
                "pk",
            )
        )
    ]

    data["nhap_kho"] = {
        "ten": "Nhập kho trong kỳ",
        "don_vi": "xe",
        "tong": sum(row[-1] for row in dong),
        "cot": [
            "Hóa đơn nhập",
            "Chi nhánh",
            "Ngày nhập",
            "VIN",
            "Tên xe",
            "Số lượng nhập",
        ],
        "dong": dong,
    }

    # Mỗi phiếu xuất tương ứng một xe.
    xuat = PhieuXuatKho.objects.filter(
        kho_id__in=kho_ids
    )

    if ten:
        xuat = xuat.filter(
            chi_tiet_hop_dong__xe__ten_xe__icontains=ten
        )

    xuat = loc_ngay(
        xuat,
        "ngay_xuat",
        bo_loc,
    )

    dong = [
        [
            item.pk,
            item.kho_id,
            dinh_dang_ngay(item.ngay_xuat),
            item.chi_tiet_hop_dong.xe_id,
            item.chi_tiet_hop_dong.xe.ten_xe,
            1,
        ]
        for item in (
            xuat.select_related(
                "chi_tiet_hop_dong__xe"
            ).order_by(
                "ngay_xuat",
                "pk",
            )
        )
    ]

    data["xuat_kho"] = {
        "ten": "Xuất kho trong kỳ",
        "don_vi": "xe",
        "tong": len(dong),
        "cot": [
            "Phiếu xuất",
            "Kho",
            "Ngày xuất",
            "VIN",
            "Tên xe",
            "Số lượng xuất",
        ],
        "dong": dong,
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
            pk__in=ma_hd
        )

    hop_dong = loc_ngay(
        hop_dong,
        "ngay_ky",
        bo_loc,
    )

    dong = [
        [
            item.pk,
            item.chi_nhanh_id,
            dinh_dang_ngay(item.ngay_ky),
            item.khach_hang.ten_kh,
        ]
        for item in (
            hop_dong.select_related(
                "khach_hang"
            ).order_by(
                "ngay_ky",
                "pk",
            )
        )
    ]

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
    }

    # PDI theo trạng thái hiện tại.
    pdi = BienBanPDI.objects.filter(
        hoa_don_nhap__chi_nhanh_id__in=chi_nhanh_ids
    )

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

        dong.append([
            item.pk,
            item.hoa_don_nhap.chi_nhanh_id,
            dinh_dang_ngay(item.ngay_ghi_nhan),
            item.xe_id,
            item.xe.ten_xe,
            item.loai_su_co,
            state,
        ])

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
    }

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

        # Tổng hợp nghiệp vụ theo năm và tháng.
        nhap_thang = thong_ke_thang(
            nhap,
            "hoa_don_nhap__ngay_nhap",
            Sum("so_luong_nhap", default=0),
        )

        xuat_thang = thong_ke_thang(
            xuat,
            "ngay_xuat",
            Count("pk", distinct=True),
        )

        hd_thang = thong_ke_thang(
            hop_dong,
            "ngay_ky",
            Count("pk", distinct=True),
        )

        truc_nhap_xuat = tao_truc_thang(
            [nhap_thang, xuat_thang],
            bo_loc,
        )

        truc_hop_dong = tao_truc_thang(
            [hd_thang],
            bo_loc,
        )

        data["nhap_kho"]["theo_thang"] = [
            [
                moc.strftime("%m/%Y"),
                nhap_thang.get(moc, 0),
                xuat_thang.get(moc, 0),
            ]
            for moc in truc_nhap_xuat
        ]

        data["hop_dong"]["theo_thang"] = [
            [
                moc.strftime("%m/%Y"),
                hd_thang.get(moc, 0),
            ]
            for moc in truc_hop_dong
        ]

    return data
