import logging

from django.db import transaction
from django.utils import timezone

from database.models import Kho, TonKho, Xe
from .models import CanhBao, NguongCanhBao


logger = logging.getLogger(__name__)


def lay_dong_xe(ten_xe):
    cac_tu = (ten_xe or "").strip().split()

    if cac_tu and cac_tu[0].casefold() == "ford":
        cac_tu = cac_tu[1:]

    if not cac_tu:
        return ""

    cac_dong_xe = [
        "Ranger",
        "Everest",
        "Territory",
        "Explorer",
        "Transit",
    ]

    for dong_xe in cac_dong_xe:
        if cac_tu[0].casefold() == dong_xe.casefold():
            return dong_xe

    return ""


def lay_nguong_toi_thieu(dong_xe, mau_sac):
    if dong_xe == "Everest" and mau_sac.casefold() == "trắng tuyết":
        return 3

    return 2


def luu_khi_thay_doi(canh_bao, du_lieu):
    cac_truong = []

    for ten_truong, gia_tri in du_lieu.items():
        if getattr(canh_bao, ten_truong) != gia_tri:
            setattr(canh_bao, ten_truong, gia_tri)
            cac_truong.append(ten_truong)

    if cac_truong:
        canh_bao.save(
            update_fields=cac_truong + ["ngay_cap_nhat"],
        )


@transaction.atomic
def cap_nhat_canh_bao_thieu_hang():
    cac_nhom = set()

    # Nhận diện các nhóm đã xuất hiện trong hồ sơ xe.
    # Nhóm vẫn được theo dõi khi không còn bản ghi tồn kho.
    for xe in Xe.objects.all():
        dong_xe = lay_dong_xe(xe.ten_xe)

        if dong_xe:
            mau_sac = (xe.mau_sac or "").strip()
            cac_nhom.add((dong_xe, mau_sac))
        else:
            logger.warning(
                "Chưa nhận diện được dòng xe: %s",
                xe.ten_xe,
            )

    nhom_da_co = set(
        NguongCanhBao.objects.values_list(
            "ten_xe",
            "mau_sac",
        )
    )

    nguong_moi = []

    for dong_xe, mau_sac in sorted(cac_nhom):
        if (dong_xe, mau_sac) not in nhom_da_co:
            nguong_moi.append(
                NguongCanhBao(
                    ten_xe=dong_xe,
                    mau_sac=mau_sac,
                    ton_toi_thieu=lay_nguong_toi_thieu(
                        dong_xe,
                        mau_sac,
                    ),
                )
            )

    # Thêm cùng lúc các nhóm chưa có cấu hình.
    # Không phát tín hiệu post_save cho từng nhóm.
    if nguong_moi:
        NguongCanhBao.objects.bulk_create(
            nguong_moi,
            ignore_conflicts=True,
        )

    tong_theo_nhom = {}
    kho_theo_nhom = {}

    danh_sach_ton = TonKho.objects.filter(
        so_luong_ton__gt=0,
    ).select_related("xe")

    # Cộng tồn của cùng dòng xe và màu ở toàn bộ kho.
    for ton in danh_sach_ton:
        dong_xe = lay_dong_xe(ton.xe.ten_xe)

        if not dong_xe:
            continue

        mau_sac = (ton.xe.mau_sac or "").strip()
        nhom = (dong_xe, mau_sac)

        if nhom not in tong_theo_nhom:
            tong_theo_nhom[nhom] = 0
            kho_theo_nhom[nhom] = set()

        tong_theo_nhom[nhom] += ton.so_luong_ton
        kho_theo_nhom[nhom].add(ton.kho_id)

    tat_ca_kho = list(
        Kho.objects.values_list("pk", flat=True)
    )

    cac_nguong = list(
        NguongCanhBao.objects.select_for_update().order_by("pk")
    )
    canh_bao_theo_nguong = {}

    cac_canh_bao = CanhBao.objects.filter(
        nguong__isnull=False,
        con_hieu_luc=True,
    ).prefetch_related("cac_kho")

    for canh_bao in cac_canh_bao:
        canh_bao_theo_nguong[canh_bao.nguong_id] = canh_bao

    for nguong in cac_nguong:
        nhom = (nguong.ten_xe, nguong.mau_sac)
        so_luong = tong_theo_nhom.get(nhom, 0)

        ton_toi_thieu = lay_nguong_toi_thieu(
            nguong.ten_xe,
            nguong.mau_sac,
        )

        # Giữ đúng quy tắc ngưỡng đã thống nhất.
        if nguong.ton_toi_thieu != ton_toi_thieu:
            NguongCanhBao.objects.filter(
                pk=nguong.pk,
            ).update(
                ton_toi_thieu=ton_toi_thieu,
            )

        canh_bao = canh_bao_theo_nguong.get(nguong.pk)

        if not nguong.dang_theo_doi or so_luong >= ton_toi_thieu:
            if canh_bao is not None:
                luu_khi_thay_doi(canh_bao, {
                    "so_luong_hien_tai": so_luong,
                    "con_hieu_luc": False,
                })
            continue

        if so_luong == 0:
            loai_canh_bao = CanhBao.Loai.HET_HANG
            cac_kho = set(tat_ca_kho)
        else:
            loai_canh_bao = CanhBao.Loai.DUOI_NGUONG
            cac_kho = kho_theo_nhom[nhom]

        du_lieu = {
            "kho_id": None,
            "loai": loai_canh_bao,
            "so_luong_hien_tai": so_luong,
        }

        if canh_bao is None:
            canh_bao, tao_moi = CanhBao.objects.get_or_create(
                nguong=nguong,
                con_hieu_luc=True,
                defaults=du_lieu,
            )

        luu_khi_thay_doi(canh_bao, du_lieu)

        kho_da_luu = set()
        for kho in canh_bao.cac_kho.all():
            kho_da_luu.add(kho.pk)

        if kho_da_luu != cac_kho:
            canh_bao.cac_kho.set(cac_kho)


@transaction.atomic
def cap_nhat_canh_bao_ton_lau():
    hom_nay = timezone.localdate()
    tuoi_ton_theo_xe = {}
    doi_tuong_co_ngay_loi = set()
    canh_bao_theo_xe = {}

    cac_canh_bao = (
        CanhBao.objects.select_for_update()
        .filter(loai=CanhBao.Loai.TON_LAU, con_hieu_luc=True)
        .order_by("pk")
    )

    for canh_bao in cac_canh_bao:
        doi_tuong = (canh_bao.kho_id, canh_bao.xe_id)
        canh_bao_theo_xe[doi_tuong] = canh_bao

    danh_sach_ton = TonKho.objects.filter(so_luong_ton__gt=0)

    for ton in danh_sach_ton:
        doi_tuong = (ton.kho_id, ton.xe_id)

        if ton.ngay_vao_kho is None or ton.ngay_vao_kho > hom_nay:
            doi_tuong_co_ngay_loi.add(doi_tuong)
            logger.warning(
                "Bỏ qua tính cảnh báo tồn lâu do ngày vào kho "
                "không hợp lệ: xe %s, kho %s.",
                ton.xe_id,
                ton.kho_id,
            )
            continue

        so_ngay = (hom_nay - ton.ngay_vao_kho).days
        tuoi_ton_theo_xe[doi_tuong] = so_ngay

        if so_ngay > 60:
            canh_bao = canh_bao_theo_xe.get(doi_tuong)

            if canh_bao is None:
                canh_bao, tao_moi = CanhBao.objects.get_or_create(
                    kho_id=ton.kho_id,
                    xe_id=ton.xe_id,
                    loai=CanhBao.Loai.TON_LAU,
                    con_hieu_luc=True,
                    defaults={"so_ngay_ton": so_ngay},
                )

            luu_khi_thay_doi(canh_bao, {"so_ngay_ton": so_ngay})

    for doi_tuong, canh_bao in canh_bao_theo_xe.items():
        if doi_tuong in doi_tuong_co_ngay_loi:
            continue

        so_ngay = tuoi_ton_theo_xe.get(doi_tuong)

        if so_ngay is None or so_ngay <= 60:
            du_lieu = {"con_hieu_luc": False}
            if so_ngay is not None:
                du_lieu["so_ngay_ton"] = so_ngay
            luu_khi_thay_doi(canh_bao, du_lieu)


@transaction.atomic
def cap_nhat_tat_ca_canh_bao():
    cap_nhat_canh_bao_thieu_hang()
    cap_nhat_canh_bao_ton_lau()
