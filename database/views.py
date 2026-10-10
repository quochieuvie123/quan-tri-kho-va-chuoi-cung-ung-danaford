from django.shortcuts import render
from .models import NhaCungCap


def danh_sach_nha_cung_cap(request):
    danh_sach = NhaCungCap.objects.all().order_by("ma_ncc")
    return render(request, "database/nha_cung_cap.html", {"danh_sach": danh_sach})
