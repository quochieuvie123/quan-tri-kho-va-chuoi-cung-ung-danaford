from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from database.models import TonKho, Xe
from .models import NguongCanhBao
from .utils import cap_nhat_tat_ca_canh_bao


@receiver(post_save, sender=TonKho)
@receiver(post_delete, sender=TonKho)
@receiver(post_save, sender=NguongCanhBao)
@receiver(post_delete, sender=NguongCanhBao)
@receiver(post_save, sender=Xe)
def kiem_tra_canh_bao_sau_thay_doi(sender, **kwargs):
    if kwargs.get("raw", False):
        return

    transaction.on_commit(
        cap_nhat_tat_ca_canh_bao,
        robust=True,
    )
