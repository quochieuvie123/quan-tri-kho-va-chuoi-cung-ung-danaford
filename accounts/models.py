from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    nhan_vien = models.OneToOneField(
        "database.NhanVien",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="tai_khoan",
        verbose_name="Nhân viên",
    )

    class Meta:
        verbose_name = "Tài khoản"
        verbose_name_plural = "Tài khoản"

    def __str__(self):
        return self.get_full_name() or self.username