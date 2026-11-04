from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied, ValidationError

from . import services
from .models import KetQuaPDI, LichSuNhapKho, PhieuNhapKho


def bao_loi(model_admin, request, exc):
    noi_dung = '; '.join(exc.messages) if isinstance(exc, ValidationError) else str(exc)
    model_admin.message_user(request, noi_dung, level=messages.ERROR)


@admin.register(PhieuNhapKho)
class PhieuNhapKhoAdmin(admin.ModelAdmin):
    list_display = ('ma_phieu', 'xe', 'kho', 'ngay_nhap', 'trang_thai', 'nguoi_lap', 'ngay_lap', 'nguoi_duyet')
    list_filter = ('trang_thai', 'kho', 'ngay_nhap')
    search_fields = ('ma_phieu', 'xe__vin', 'xe__ten_xe')
    readonly_fields = ('xe', 'trang_thai', 'nguoi_lap', 'ngay_lap', 'nguoi_duyet', 'thoi_gian_duyet')
    actions = ('gui_cho_duyet', 'duyet_nhap_kho')

    def save_model(self, request, obj, form, change):
        if change:
            obj.full_clean()
            obj.save()
            return
        created = services.create_receipt(request.user, ma_phieu=obj.ma_phieu,
            chi_tiet_nhap_id=obj.chi_tiet_nhap_id, kho_id=obj.kho_id, ngay_nhap=obj.ngay_nhap)
        obj.pk = created.pk
        obj.xe_id = created.xe_id
        obj.trang_thai = created.trang_thai
        obj.nguoi_lap_id = created.nguoi_lap_id
        obj.ngay_lap = created.ngay_lap
        obj._state.adding = False

    @admin.action(description='Gửi các phiếu đã chọn sang chờ duyệt')
    def gui_cho_duyet(self, request, queryset):
        thanh_cong = 0
        for phieu in queryset:
            pdi = services.latest_pdi(phieu)
            try:
                services.submit_receipt(request.user, phieu.pk, pdi_id=pdi.pk if pdi else None)
                thanh_cong += 1
            except (ValidationError, PermissionDenied) as exc:
                bao_loi(self, request, exc)
        if thanh_cong:
            self.message_user(request, f'Đã gửi duyệt {thanh_cong} phiếu.', messages.SUCCESS)

    @admin.action(description='Duyệt nhập kho các phiếu đã chọn')
    def duyet_nhap_kho(self, request, queryset):
        thanh_cong = 0
        for phieu in queryset:
            pdi = services.latest_pdi(phieu)
            try:
                services.approve_receipt(request.user, phieu.pk, pdi_id=pdi.pk if pdi else None)
                thanh_cong += 1
            except (ValidationError, PermissionDenied) as exc:
                bao_loi(self, request, exc)
        if thanh_cong:
            self.message_user(request, f'Đã duyệt nhập kho {thanh_cong} phiếu.', messages.SUCCESS)


@admin.register(KetQuaPDI)
class KetQuaPDIAdmin(admin.ModelAdmin):
    list_display = ('id', 'phieu_nhap', 'ket_qua', 'nguoi_kiem_tra', 'thoi_gian_kiem_tra', 'nguoi_duyet', 'thoi_gian_duyet')
    list_filter = ('ket_qua', 'thoi_gian_kiem_tra')
    search_fields = ('phieu_nhap__ma_phieu', 'phieu_nhap__xe__vin')
    readonly_fields = ('nguoi_kiem_tra', 'thoi_gian_kiem_tra', 'nguoi_duyet', 'thoi_gian_duyet')
    actions = ('duyet_ket_qua_pdi',)

    def save_model(self, request, obj, form, change):
        current = services.latest_pdi(obj.phieu_nhap)
        created = services.record_pdi(request.user, obj.phieu_nhap_id,
            tinh_trang=obj.tinh_trang, ket_qua=obj.ket_qua, ghi_chu=obj.ghi_chu,
            hang_muc=obj.hang_muc, pdi_id=current.pk if current else None)
        obj.pk = created.pk
        obj.nguoi_kiem_tra_id = created.nguoi_kiem_tra_id
        obj.thoi_gian_kiem_tra = created.thoi_gian_kiem_tra
        obj._state.adding = False

    @admin.action(description='Duyệt các kết quả PDI đã chọn')
    def duyet_ket_qua_pdi(self, request, queryset):
        thanh_cong = 0
        for pdi in queryset:
            try:
                services.approve_pdi(request.user, pdi.phieu_nhap_id, pdi_id=pdi.pk)
                thanh_cong += 1
            except (ValidationError, PermissionDenied) as exc:
                bao_loi(self, request, exc)
        if thanh_cong:
            self.message_user(request, f'Đã duyệt {thanh_cong} kết quả PDI.', messages.SUCCESS)

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(LichSuNhapKho)
class LichSuNhapKhoAdmin(admin.ModelAdmin):
    list_display = ('phieu_nhap', 'xe', 'kho', 'nguoi_thuc_hien', 'thoi_gian')
    list_filter = ('kho', 'thoi_gian')
    search_fields = ('phieu_nhap__ma_phieu', 'xe__vin', 'xe__ten_xe')
    readonly_fields = ('phieu_nhap', 'xe', 'kho', 'nguoi_thuc_hien', 'thoi_gian')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return request.method in ('GET', 'HEAD', 'OPTIONS')

    def has_delete_permission(self, request, obj=None):
        return False
