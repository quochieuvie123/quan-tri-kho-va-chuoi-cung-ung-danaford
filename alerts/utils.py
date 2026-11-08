from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone

from database.models import TonKho
from .models import CanhBao, NguongCanhBao
import logging

logger = logging.getLogger(__name__)

@transaction.atomic
def cap_nhat_canh_bao_thieu_hang():
    danh_sach_nguong = NguongCanhBao.objects.all()

    for nguong in danh_sach_nguong:
        canh_bao_hien_tai = CanhBao.objects.filter(
            nguong=nguong,
            con_hieu_luc=True,
        )

        if not nguong.dang_theo_doi:
            canh_bao_hien_tai.update(
                con_hieu_luc=False,
                ngay_cap_nhat=timezone.now(),
            )
            continue

        ton_kho = TonKho.objects.filter(
            kho=nguong.kho,
            xe__ten_xe=nguong.ten_xe,
        )

        if nguong.mau_sac:
            ton_kho = ton_kho.filter(
                xe__mau_sac=nguong.mau_sac,
            )
        else:
            ton_kho = ton_kho.filter(
                Q(xe__mau_sac="") | Q(xe__mau_sac__isnull=True)
            )

        so_luong = ton_kho.aggregate(
            tong=Sum("so_luong_ton", default=0)
        )["tong"]

        if so_luong >= nguong.ton_toi_thieu:
            canh_bao_hien_tai.update(
                so_luong_hien_tai=so_luong,
                con_hieu_luc=False,
                ngay_cap_nhat=timezone.now(),
            )
            continue

        if so_luong == 0:
            loai_canh_bao = CanhBao.Loai.HET_HANG
        else:
            loai_canh_bao = CanhBao.Loai.DUOI_NGUONG

        CanhBao.objects.update_or_create(
            nguong=nguong,
            con_hieu_luc=True,
            defaults={
                "kho": nguong.kho,
                "loai": loai_canh_bao,
                "so_luong_hien_tai": so_luong,
            },
        )


@transaction.atomic
def cap_nhat_canh_bao_ton_lau():
    hom_nay = timezone.localdate()
    danh_sach_ton = TonKho.objects.filter(so_luong_ton__gt=0)
    tuoi_ton_theo_xe = {}
    doi_tuong_co_ngay_loi = set()

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
            CanhBao.objects.update_or_create(
                kho_id=ton.kho_id,
                xe_id=ton.xe_id,
                loai=CanhBao.Loai.TON_LAU,
                con_hieu_luc=True,
                defaults={
                    "so_ngay_ton": so_ngay,
                },
            )

    canh_bao_hien_tai = CanhBao.objects.filter(
        loai=CanhBao.Loai.TON_LAU,
        con_hieu_luc=True,
    )

    for canh_bao in canh_bao_hien_tai:
        doi_tuong = (canh_bao.kho_id, canh_bao.xe_id)

        if doi_tuong in doi_tuong_co_ngay_loi:
            continue

        so_ngay = tuoi_ton_theo_xe.get(doi_tuong)

        if so_ngay is None or so_ngay <= 60:
            canh_bao.con_hieu_luc = False

            if so_ngay is not None:
                canh_bao.so_ngay_ton = so_ngay

            canh_bao.save(
                update_fields=[
                    "con_hieu_luc",
                    "so_ngay_ton",
                    "ngay_cap_nhat",
                ]
            )


@transaction.atomic
def cap_nhat_tat_ca_canh_bao():
    cap_nhat_canh_bao_thieu_hang()
    cap_nhat_canh_bao_ton_lau()
