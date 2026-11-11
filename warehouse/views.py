# warehouse/views.py
import json
from django.db import models
from django.http import JsonResponse
from django.views import View
from django.utils.decorators import method_decorator
from core.iii_iv_access import role_required, SALE_ADMIN
from django.contrib.auth.decorators import permission_required
from django.contrib.auth.mixins import LoginRequiredMixin

from database.models import PhieuXuatKho, TrangThaiPhieuXuat
from .services import XuatKhoService, XuatKhoError

from .inventory_services import InventoryService, InventoryError
from database.models import PhieuKiemKe, TrangThaiKiemKe

class DanhSachPhieuXuatView(LoginRequiredMixin, View):
    """UC-PXK-01: Xem danh sách phiếu xuất kho"""
    def get(self, request, *args, **kwargs):
        trang_thai = request.GET.get('trang_thai')
        ma_kho = request.GET.get('kho', 'KHO01')
        tu_khoa = request.GET.get('q', '').strip()

        qs = PhieuXuatKho.objects.select_related(
            'chi_tiet_hop_dong__hop_dong__khach_hang',
            'chi_tiet_hop_dong__xe',
            'kho',
            'nguoi_lap'
        ).filter(kho_id=ma_kho)

        if trang_thai:
            qs = qs.filter(trang_thai=trang_thai)

        if tu_khoa:
            qs = qs.filter(
                models.Q(ma_pxk__icontains=tu_khoa) |
                models.Q(chi_tiet_hop_dong__hop_dong__ma_hd__icontains=tu_khoa) |
                models.Q(chi_tiet_hop_dong__xe__vin__icontains=tu_khoa) |
                models.Q(chi_tiet_hop_dong__hop_dong__khach_hang__ten_kh__icontains=tu_khoa)
            )

        data = []
        for p in qs:
            hd = p.chi_tiet_hop_dong.hop_dong
            xe = p.chi_tiet_hop_dong.xe
            data.append({
                "ma_pxk": p.ma_pxk,
                "ma_hd": hd.ma_hd,
                "khach_hang": hd.khach_hang.ten_kh,
                "vin": xe.vin,
                "ten_xe": xe.ten_xe,
                "ngay_lap": p.ngay_lap.strftime("%d/%m/%Y %H:%M"),
                "trang_thai": p.trang_thai,
                "trang_thai_display": p.get_trang_thai_display(),
                "nguoi_lap": p.nguoi_lap.ten_nv if p.nguoi_lap else "",
            })

        return JsonResponse({"status": "success", "total": len(data), "data": data})


class ChiTietPhieuXuatView(LoginRequiredMixin, View):
    """UC-PXK-02: Xem chi tiết phiếu xuất kho"""
    def get(self, request, ma_pxk, *args, **kwargs):
        try:
            phieu = PhieuXuatKho.objects.select_related(
                'chi_tiet_hop_dong__hop_dong__khach_hang',
                'chi_tiet_hop_dong__xe',
                'kho',
                'nguoi_lap',
                'nguoi_duyet'
            ).get(ma_pxk=ma_pxk)
        except PhieuXuatKho.DoesNotExist:
            return JsonResponse({"status": "error", "message": "Phiếu xuất kho không tồn tại."}, status=404)

        hd = phieu.chi_tiet_hop_dong.hop_dong
        xe = phieu.chi_tiet_hop_dong.xe

        doi_chieu_info = {}
        try:
            doi_chieu_info = XuatKhoService.doi_chieu_hop_dong_hoa_don(hd.ma_hd)
        except XuatKhoError as e:
            doi_chieu_info = {"hop_le": False, "canh_bao": str(e)}

        return JsonResponse({
            "status": "success",
            "data": {
                "ma_pxk": phieu.ma_pxk,
                "trang_thai": phieu.trang_thai,
                "trang_thai_display": phieu.get_trang_thai_display(),
                "ngay_lap": phieu.ngay_lap.strftime("%d/%m/%Y %H:%M"),
                "nguoi_lap": phieu.nguoi_lap.ten_nv if phieu.nguoi_lap else "",
                "kho_xuat": phieu.kho.ma_kho,
                "nguoi_nhan": phieu.nguoi_nhan,
                "ghi_chu": phieu.ghi_chu,
                "xe": {
                    "vin": xe.vin,
                    "ten_xe": xe.ten_xe,
                    "loai_xe": xe.loai_xe,
                    "so_may": xe.so_may,
                    "mau_sac": xe.mau_sac,
                    "trang_thai_xe": xe.get_trang_thai_display(),
                },
                "hop_dong": {
                    "ma_hd": hd.ma_hd,
                    "khach_hang": hd.khach_hang.ten_kh,
                    "sdt_khach": hd.khach_hang.sdt_kh,
                },
                "doi_chieu": doi_chieu_info,
                "co_the_duyet": phieu.trang_thai == TrangThaiPhieuXuat.CHO_DUYET and doi_chieu_info.get("hop_le", False)
            }
        })


class TraCuuXeKhaDungView(LoginRequiredMixin, View):
    """UC-LPXK-03: Tra cứu xe sẵn sàng trong kho Đà Nẵng"""
    def get(self, request, *args, **kwargs):
        ma_hd = request.GET.get('ma_hd')
        ma_kho = request.GET.get('kho', 'KHO01')
        if not ma_hd:
            return JsonResponse({"status": "error", "message": "Vui lòng cung cấp mã hợp đồng."}, status=400)
        try:
            danh_sach_xe = XuatKhoService.lay_danh_sach_xe_kha_dung(ma_hd=ma_hd, ma_kho=ma_kho)
            data = [{
                "vin": x.vin,
                "ten_xe": x.ten_xe,
                "loai_xe": x.loai_xe,
                "so_may": x.so_may,
                "mau_sac": x.mau_sac,
                "trang_thai": x.get_trang_thai_display()
            } for x in danh_sach_xe]
            return JsonResponse({"status": "success", "total": len(data), "data": data})
        except Exception as e:
            return JsonResponse({"status": "error", "message": str(e)}, status=400)


@method_decorator(role_required(SALE_ADMIN), name='dispatch')
@method_decorator(permission_required('database.add_phieuxuatkho', raise_exception=True), name='dispatch')
class LapPhieuXuatKhoActionView(LoginRequiredMixin, View):
    """UC-LPXK-01: Lập phiếu xuất kho"""
    def post(self, request, *args, **kwargs):
        try:
            payload = json.loads(request.body)
            ma_hd = payload.get("ma_hd")
            vin = payload.get("vin")
            ma_kho = payload.get("kho", "KHO01")
            nguoi_nhan = payload.get("nguoi_nhan")
            ghi_chu = payload.get("ghi_chu", "")

            nhan_vien = getattr(request.user, "nhan_vien", None)
            if not nhan_vien:
                return JsonResponse({"status": "error", "message": "Tài khoản hiện tại chưa được gán hồ sơ nhân viên."}, status=403)

            phieu = XuatKhoService.lap_phieu_xuat_kho(
                ma_hd=ma_hd,
                vin=vin,
                ma_kho=ma_kho,
                ma_nv_lap=nhan_vien.ma_nv,
                nguoi_nhan=nguoi_nhan,
                ghi_chu=ghi_chu
            )

            return JsonResponse({
                "status": "success",
                "message": "Lập phiếu xuất kho thành công. Xe đã được giữ chỗ và chuyển sang Chờ duyệt.",
                "ma_pxk": phieu.ma_pxk
            }, status=201)
        except XuatKhoError as e:
            return JsonResponse({"status": "error", "message": str(e)}, status=400)
        except Exception as e:
            return JsonResponse({"status": "error", "message": f"Lỗi hệ thống: {str(e)}"}, status=500)


@method_decorator(role_required(SALE_ADMIN), name='dispatch')
@method_decorator(permission_required('database.change_phieuxuatkho', raise_exception=True), name='dispatch')
class DuyetPhieuXuatKhoActionView(LoginRequiredMixin, View):
    """UC-PXK-03: Duyệt phiếu xuất kho và tự động cập nhật tồn kho"""
    def post(self, request, ma_pxk, *args, **kwargs):
        try:
            nhan_vien = getattr(request.user, "nhan_vien", None)
            if not nhan_vien:
                return JsonResponse({"status": "error", "message": "Tài khoản chưa được gán hồ sơ nhân viên."}, status=403)

            phieu = XuatKhoService.duyet_phieu_xuat_kho(ma_pxk=ma_pxk, ma_nv_duyet=nhan_vien.ma_nv)

            return JsonResponse({
                "status": "success",
                "message": f"Duyệt phiếu xuất kho {phieu.ma_pxk} thành công. Tồn kho và trạng thái xe đã được cập nhật.",
                "ma_pxk": phieu.ma_pxk,
                "ngay_xuat": phieu.ngay_xuat.strftime("%d/%m/%Y %H:%M")
            })
        except XuatKhoError as e:
            return JsonResponse({"status": "error", "message": str(e)}, status=400)
        except Exception as e:
            return JsonResponse({"status": "error", "message": f"Lỗi xử lý duyệt phiếu: {str(e)}"}, status=500)


@method_decorator(role_required(SALE_ADMIN), name='dispatch')
@method_decorator(permission_required('database.change_phieuxuatkho', raise_exception=True), name='dispatch')
class HuyPhieuXuatKhoActionView(LoginRequiredMixin, View):
    """Hủy phiếu xuất kho"""
    def post(self, request, ma_pxk, *args, **kwargs):
        try:
            payload = json.loads(request.body or "{}")
            ly_do = payload.get("ly_do", "Người dùng yêu cầu hủy")
            nhan_vien = getattr(request.user, "nhan_vien", None)
            if not nhan_vien:
                return JsonResponse({"status": "error", "message": "Tài khoản chưa được gán hồ sơ nhân viên."}, status=403)

            phieu = XuatKhoService.huy_phieu_xuat_kho(
                ma_pxk=ma_pxk,
                ma_nv_huy=nhan_vien.ma_nv,
                ly_do=ly_do
            )

            return JsonResponse({
                "status": "success",
                "message": f"Đã hủy phiếu {phieu.ma_pxk}. Xe đã được hoàn trả về trạng thái Sẵn sàng.",
                "ma_pxk": phieu.ma_pxk
            })
        except XuatKhoError as e:
            return JsonResponse({"status": "error", "message": str(e)}, status=400)


class XuatFilePhieuXuatView(LoginRequiredMixin, View):
    """UC-PXK-05: Xuất dữ liệu in/file"""
    def get(self, request, ma_pxk, *args, **kwargs):
        try:
            data = XuatKhoService.trich_xuat_du_lieu_in(ma_pxk=ma_pxk)
            return JsonResponse({"status": "success", "data": data})
        except XuatKhoError as e:
            return JsonResponse({"status": "error", "message": str(e)}, status=400)

class DanhSachTonKhoView(LoginRequiredMixin, View):
    """UC-TK-01 & UC-TK-03: Xem danh sách và lọc xe tồn kho"""
    def get(self, request, *args, **kwargs):
        ma_kho = request.GET.get('kho', 'KHO01')
        bo_loc = {
            "loai_xe": request.GET.get('loai_xe'),
            "mau_sac": request.GET.get('mau_sac'),
            "vin": request.GET.get('vin'),
            "trang_thai": request.GET.get('trang_thai')
        }
        data = InventoryService.lay_danh_sach_ton_kho(ma_kho=ma_kho, bo_loc=bo_loc)
        return JsonResponse({"status": "success", "total": len(data), "data": data})
class ChiTietXeTonKhoView(LoginRequiredMixin, View):
    """UC-TK-02: Xem chi tiết xe tồn kho & tuổi tồn"""
    def get(self, request, vin, *args, **kwargs):
        ma_kho = request.GET.get('kho', 'KHO01')
        try:
            data = InventoryService.lay_chi_tiet_xe_ton(vin=vin, ma_kho=ma_kho)
            return JsonResponse({"status": "success", "data": data})
        except InventoryError as e:
            return JsonResponse({"status": "error", "message": str(e)}, status=404)
class TaoPhieuKiemKeView(LoginRequiredMixin, View):
    """UC-KK-01: Tạo phiếu kiểm kê và chụp snapshot hệ thống"""
    def post(self, request, *args, **kwargs):
        try:
            payload = json.loads(request.body)
            ma_kho = payload.get("kho", "KHO01")
            ky = payload.get("ky_kiem_ke")
            pham_vi = payload.get("pham_vi", "Toàn kho")
            ghi_chu = payload.get("ghi_chu", "")
            nhan_vien = getattr(request.user, "nhan_vien", None)
            if not nhan_vien:
                return JsonResponse({"status": "error", "message": "Chưa gán hồ sơ nhân viên."}, status=403)
            phieu = InventoryService.tao_phieu_kiem_ke(
                ma_kho=ma_kho, ma_nv=nhan_vien.ma_nv, ky_kiem_ke=ky, pham_vi=pham_vi, ghi_chu=ghi_chu
            )
            return JsonResponse({
                "status": "success",
                "message": f"Tạo phiếu kiểm kê {phieu.ma_pkk} thành công. Đã chụp số liệu tồn kho.",
                "ma_pkk": phieu.ma_pkk
            }, status=201)
        except InventoryError as e:
            return JsonResponse({"status": "error", "message": str(e)}, status=400)
class GhiNhanKiemDemView(LoginRequiredMixin, View):
    """UC-KK-02 & UC-KK-03: Ghi nhận quét VIN kiểm đếm và tự động phân loại"""
    def post(self, request, ma_pkk, *args, **kwargs):
        try:
            payload = json.loads(request.body)
            danh_sach_vin = payload.get("danh_sach_vin", [])
            vi_tri_map = payload.get("vi_tri_map", {})
            result = InventoryService.ghi_nhan_kiem_dem_thuc_te(
                ma_pkk=ma_pkk, danh_sach_vin_quet=danh_sach_vin, vi_tri_map=vi_tri_map
            )
            return JsonResponse({"status": "success", "data": result})
        except InventoryError as e:
            return JsonResponse({"status": "error", "message": str(e)}, status=400)
class XuLyChenhLechView(LoginRequiredMixin, View):
    """UC-KK-04 & UC-KK-05: Ghi nhận nguyên nhân chênh lệch"""
    def post(self, request, ma_pkk, *args, **kwargs):
        try:
            payload = json.loads(request.body)
            danh_sach = payload.get("danh_sach_xu_ly", [])
            nhan_vien = getattr(request.user, "nhan_vien", None)
            InventoryService.xu_ly_chenh_lech(ma_pkk=ma_pkk, ma_nv_xuly=nhan_vien.ma_nv, danh_sach_xu_ly=danh_sach)
            return JsonResponse({"status": "success", "message": "Đã ghi nhận nguyên nhân xử lý chênh lệch."})
        except InventoryError as e:
            return JsonResponse({"status": "error", "message": str(e)}, status=400)
class DuyetPhieuKiemKeView(LoginRequiredMixin, View):
    """UC-KK-06 & UC-KK-07: Duyệt kiểm kê và điều chỉnh tồn kho tự động"""
    def post(self, request, ma_pkk, *args, **kwargs):
        try:
            nhan_vien = getattr(request.user, "nhan_vien", None)
            phieu = InventoryService.duyet_phieu_kiem_ke(ma_pkk=ma_pkk, ma_nv_duyet=nhan_vien.ma_nv)
            return JsonResponse({
                "status": "success",
                "message": f"Duyệt kiểm kê {phieu.ma_pkk} hoàn tất. Số liệu tồn kho đã được điều chỉnh theo thực tế."
            })
        except InventoryError as e:
            return JsonResponse({"status": "error", "message": str(e)}, status=400)
class LichSuKiemKeView(LoginRequiredMixin, View):
    """UC-KK-08: Xem lịch sử kiểm kê"""
    def get(self, request, *args, **kwargs):
        ma_kho = request.GET.get('kho', 'KHO01')
        qs = PhieuKiemKe.objects.filter(kho_id=ma_kho, trang_thai=TrangThaiKiemKe.HOAN_TAT).select_related('nhan_vien', 'nguoi_duyet')
        data = [{
            "ma_pkk": p.ma_pkk,
            "ky_kiem_ke": p.ky_kiem_ke,
            "pham_vi": p.pham_vi,
            "ngay_kiem_ke": p.ngay_kiem_ke.strftime("%d/%m/%Y"),
            "nguoi_lap": p.nhan_vien.ten_nv,
            "nguoi_duyet": p.nguoi_duyet.ten_nv if p.nguoi_duyet else ""
        } for p in qs]
        return JsonResponse({"status": "success", "data": data})