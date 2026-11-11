from django.db import models
from django.conf import settings
class Allocation(models.Model):
    order_number = models.CharField(max_length=50,verbose_name="Số đơn đặt hàng")
    vehicle_code = models.CharField(max_length=50,verbose_name="Mã dòng xe")
    description = models.TextField(blank=True,verbose_name="Mô tả")
    vin = models.CharField(max_length=50,unique=True,verbose_name="VIN")
    color_code = models.CharField(max_length=20,verbose_name="Mã màu")
    exterior_color = models.CharField(max_length=100,verbose_name="Màu ngoại thất")
    mau_sac = models.CharField(max_length=50,blank=True,default="",verbose_name="Màu sắc")
    engine_number = models.CharField(max_length=50,verbose_name="Số máy")
    expected_ship_date = models.DateField(null=True,blank=True,verbose_name="Ngày dự kiến ship")
    contractual_delivery_date = models.DateField(null=True,blank=True,verbose_name="Ngày dự kiến giao theo hợp đồng")
    allocation_month = models.DateField(null=True,blank=True,verbose_name="Tháng phân bổ")
    quantity = models.PositiveIntegerField(default=1,verbose_name="Số lượng")
#ặt xe

class VehicleRequest(models.Model):

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Bản nháp"
        PENDING = "PENDING", "Đã gửi - Chờ xử lý"
        ACCEPTED = "ACCEPTED", "Yêu cầu đã được chấp nhận"

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        verbose_name="Người lập phiếu"
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Ngày lập phiếu"
    )

    sent_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Ngày gửi phiếu"
    )

    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.DRAFT,
        verbose_name="Trạng thái yêu cầu"
    )

    @property
    def request_number(self):
        if self.pk is None:
            return ""
        return f"PYC{self.pk:05d}"

    def __str__(self):
        return self.request_number


class VehicleRequestItem(models.Model):

    vehicle_request = models.ForeignKey(
        VehicleRequest,
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name="Phiếu yêu cầu đặt xe"
    )

    allocation = models.ForeignKey(
        Allocation,
        on_delete=models.PROTECT,
        verbose_name="Xe được chọn"
    )

    quantity = models.PositiveIntegerField(
        verbose_name="Số lượng yêu cầu"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["vehicle_request", "allocation"],
                name="unique_vehicle_per_request"
            ),
            models.CheckConstraint(
                condition=models.Q(quantity__gt=0),
                name="vehicle_request_quantity_gt_zero"
            ),
        ]

    def __str__(self):
        return (
            f"{self.allocation.vehicle_code} "
            f"- SL: {self.quantity}"
        )
