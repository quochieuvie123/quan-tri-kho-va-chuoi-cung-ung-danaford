"""
warehouse/inventory_services.py
Quản lý Tồn kho & Kiểm kê hàng hóa (Đặc tả Mục 6 Báo cáo giai đoạn 2).
Bảo đảm an toàn dữ liệu và cơ chế phát hiện 'Xe đang xử lý nghiệp vụ'.
"""
import uuid
from datetime import date
from django.db import transaction
from django.utils import timezone
from django.db.models import Q

from database.models import (
    Kho, Xe, TonKho, PhieuKiemKe, ChiTietKiemKe, PhieuXuatKho,
    BienBanPDI, TrangThaiXe, TrangThaiPhieuXuat,
    TrangThaiKiemKe, PhanLoaiKiemKe
)


class InventoryError(Exception):
    pass


class InventoryService:

    @staticmethod
    def tinh_tuoi_ton(ngay_vao_kho: date) -> dict:
        """
        Tính tuổi tồn kho theo quy định trang 73, 91, 95 của Báo cáo:
        - 0-30 ngày: Tồn bình thường
        - 31-60 ngày: Cần theo dõi
        - Trên 60 ngày: Tồn lâu
        """
        so_ngay = (date.today() - ngay_vao_kho).days
        if so_ngay < 0:
            so_ngay = 0

        if so_ngay <= 30:
            nhom = "Tồn bình thường"
        elif so_ngay <= 60:
            nhom = "Cần theo dõi"
        else:
            nhom = "Tồn lâu"

        return {"so_ngay_ton": so_ngay, "nhom_tuoi_ton": nhom}

    @classmethod
    def lay_danh_sach_ton_kho(cls, ma_kho: str = "KHO01", bo_loc: dict = None) -> list:
        """
        Nghiệp vụ UC-TK-01 & UC-TK-03: Xem danh sách & tra cứu xe tồn kho
        """
        qs = TonKho.objects.filter(so_luong_ton__gt=0).select_related('xe', 'kho', 'kho__chi_nhanh')
        if ma_kho and ma_kho != "ALL":
            qs = qs.filter(kho_id=ma_kho)

        if bo_loc:
            if bo_loc.get("loai_xe"):
                qs = qs.filter(xe__loai_xe__icontains=bo_loc["loai_xe"])
            if bo_loc.get("mau_sac"):
                qs = qs.filter(xe__mau_sac__icontains=bo_loc["mau_sac"])
            if bo_loc.get("vin"):
                qs = qs.filter(xe__vin__icontains=bo_loc["vin"])
            if bo_loc.get("trang_thai"):
                qs = qs.filter(xe__trang_thai=bo_loc["trang_thai"])

        ket_qua = []
        for item in qs:
            tuoi = cls.tinh_tuoi_ton(item.ngay_vao_kho)
            ket_qua.append({
                "vin": item.xe.vin,
                "ten_xe": item.xe.ten_xe,
                "loai_xe": item.xe.loai_xe,
                "so_may": item.xe.so_may,
                "mau_sac": item.xe.mau_sac,
                "vi_tri": item.vi_tri,
                "ngay_vao_kho": item.ngay_vao_kho.strftime("%d/%m/%Y"),
                "so_luong_ton": item.so_luong_ton,
                "so_ngay_ton": tuoi["so_ngay_ton"],
                "nhom_tuoi_ton": tuoi["nhom_tuoi_ton"],
                "trang_thai": item.xe.trang_thai,
                "trang_thai_display": item.xe.get_trang_thai_display(),
                "kho_id": item.kho_id,
                "ten_kho": item.kho.chi_nhanh.ten_cn if hasattr(item.kho, 'chi_nhanh') and item.kho.chi_nhanh else item.kho_id
            })
        return ket_qua

    @classmethod
    def lay_chi_tiet_xe_ton(cls, vin: str, ma_kho: str = "KHO01") -> dict:
        """
        Nghiệp vụ UC-TK-02: Xem chi tiết xe tồn kho và lịch sử
        """
        try:
            if ma_kho and ma_kho != "ALL":
                ton = TonKho.objects.select_related('xe', 'kho', 'kho__chi_nhanh').get(xe__vin=vin, kho_id=ma_kho)
            else:
                ton = TonKho.objects.select_related('xe', 'kho', 'kho__chi_nhanh').filter(xe__vin=vin).first()
                if not ton:
                    raise TonKho.DoesNotExist
        except TonKho.DoesNotExist:
            raise InventoryError(f"Xe có số VIN {vin} không tồn tại trong kho (có thể đã xuất).")

        tuoi = cls.tinh_tuoi_ton(ton.ngay_vao_kho)
        return {
            "vin": ton.xe.vin,
            "ten_xe": ton.xe.ten_xe,
            "loai_xe": ton.xe.loai_xe,
            "so_may": ton.xe.so_may,
            "mau_sac": ton.xe.mau_sac,
            "nam_sx": ton.xe.nam_sx,
            "vi_tri": ton.vi_tri,
            "ngay_vao_kho": ton.ngay_vao_kho.strftime("%d/%m/%Y"),
            "so_ngay_ton": tuoi["so_ngay_ton"],
            "nhom_tuoi_ton": tuoi["nhom_tuoi_ton"],
            "trang_thai": ton.xe.trang_thai,
            "trang_thai_display": ton.xe.get_trang_thai_display(),
            "kho": ton.kho.ma_kho
        }

    # =========================================================================
    # PHẦN NGHIỆP VỤ KIỂM KÊ TỒN KHO (UC-KK-01 ĐẾN UC-KK-08)
    # =========================================================================

    @classmethod
    def tao_phieu_kiem_ke(cls, ma_kho: str, ma_nv: str, ky_kiem_ke: str, pham_vi: str = "Toàn kho",
                          ghi_chu: str = "") -> PhieuKiemKe:
        """
        Nghiệp vụ UC-KK-01: Tạo phiếu kiểm kê.
        *** CHỐNG XUNG ĐỘT ***:
        1. Kiểm tra không cho tạo 2 phiếu kiểm kê đang mở cho cùng 1 kho.
        2. Tự động chụp Snapshot toàn bộ danh sách xe đang có trong kho vào ChiTietKiemKe.
        """
        if not ky_kiem_ke or not ky_kiem_ke.strip():
            raise InventoryError("Kỳ kiểm kê không được để trống (VD: Tháng 10/2026).")

        with transaction.atomic():
            # Chống xung đột: Đang có phiếu kiểm kê chưa đóng
            phieu_dang_mo = PhieuKiemKe.objects.filter(
                kho_id=ma_kho,
                trang_thai__in=[TrangThaiKiemKe.DANG_KIEM_KE, TrangThaiKiemKe.CHO_XU_LY]
            ).first()

            if phieu_dang_mo:
                raise InventoryError(
                    f"Kho {ma_kho} hiện đang có phiếu kiểm kê {phieu_dang_mo.ma_pkk} chưa hoàn tất. Không thể tạo phiếu mới.")

            # Lấy danh sách tồn kho hiện tại để snapshot
            danh_sach_ton = TonKho.objects.filter(kho_id=ma_kho, so_luong_ton__gt=0).select_related('xe')
            if not danh_sach_ton.exists():
                raise InventoryError(f"Kho {ma_kho} hiện không có xe nào trong tồn kho để kiểm kê.")

            ma_pkk = f"KK-{timezone.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
            phieu = PhieuKiemKe.objects.create(
                ma_pkk=ma_pkk,
                kho_id=ma_kho,
                nhan_vien_id=ma_nv,
                ngay_kiem_ke=timezone.now(),  # <-- THÊM DÒNG NÀY
                ky_kiem_ke=ky_kiem_ke.strip(),
                pham_vi=pham_vi,
                ghi_chu=ghi_chu,
                trang_thai=TrangThaiKiemKe.DANG_KIEM_KE
            )

            # Tạo bản ghi Snapshot chi tiết kiểm kê
            chi_tiet_records = []
            for ton in danh_sach_ton:
                chi_tiet_records.append(
                    ChiTietKiemKe(
                        phieu_kiem_ke=phieu,
                        xe=ton.xe,
                        ton_he_thong=ton.so_luong_ton,
                        ton_thuc_te=0,  # Ban đầu chưa quét đếm
                        vi_tri_he_thong=ton.vi_tri,
                        phan_loai=PhanLoaiKiemKe.THIEU  # Ban đầu xem như chưa đếm thấy
                    )
                )
            ChiTietKiemKe.objects.bulk_create(chi_tiet_records)

            return phieu

    @classmethod
    def ghi_nhan_kiem_dem_thuc_te(cls, ma_pkk: str, danh_sach_vin_quet: list, vi_tri_map: dict = None) -> dict:
        """
        Nghiệp vụ UC-KK-02 & UC-KK-03: Ghi nhận quét đếm và Tự động đối chiếu.
        *** CHỐNG XUNG ĐỘT QUAN TRỌNG NHẤT ***:
        Kiểm tra xe có đang dính nghiệp vụ Xuất kho (chờ duyệt) / Lưu chuyển / Sự cố PDI không?
        Nếu có -> Gắn nhãn 'DANG_XU_LY_NGHIEP_VU' để không bị coi là chênh lệch sai!
        """
        vi_tri_map = vi_tri_map or {}

        with transaction.atomic():
            try:
                phieu = PhieuKiemKe.objects.select_for_update().get(ma_pkk=ma_pkk)
            except PhieuKiemKe.DoesNotExist:
                raise InventoryError(f"Phiếu kiểm kê {ma_pkk} không tồn tại.")

            if phieu.trang_thai != TrangThaiKiemKe.DANG_KIEM_KE:
                raise InventoryError("Chỉ có thể ghi nhận kiểm đếm cho phiếu ở trạng thái 'Đang kiểm kê'.")

            # Danh sách VIN xe đang dính nghiệp vụ chưa hoàn tất
            # 1. Xe đang nằm trong phiếu xuất chờ duyệt
            vin_dang_xuat = set(PhieuXuatKho.objects.filter(
                trang_thai=TrangThaiPhieuXuat.CHO_DUYET
            ).values_list('chi_tiet_hop_dong__xe__vin', flat=True))

            # 2. Xe đang gặp sự cố PDI chưa đóng
            vin_dang_pdi = set(BienBanPDI.objects.exclude(
                trang_thai_claim="Đã xử lý"
            ).values_list('xe__vin', flat=True))

            vin_dang_nghiep_vu = vin_dang_xuat.union(vin_dang_pdi)

            vin_da_quet_set = set(danh_sach_vin_quet)

            # Duyệt qua các dòng chi tiết hệ thống
            chi_tiet_items = ChiTietKiemKe.objects.filter(phieu_kiem_ke=phieu).select_related('xe')

            for ct in chi_tiet_items:
                vin = ct.xe.vin
                vt_thuc_te = vi_tri_map.get(vin, ct.vi_tri_he_thong)
                ct.vi_tri_thuc_te = vt_thuc_te

                # Nếu xe đang vướng nghiệp vụ xuất kho/chuyển kho/PDI
                if vin in vin_dang_nghiep_vu:
                    ct.phan_loai = PhanLoaiKiemKe.DANG_XU_LY_NGHIEP_VU
                    ct.ton_thuc_te = 1 if vin in vin_da_quet_set else 0
                    ct.nguyen_nhan = "Xe đang xử lý nghiệp vụ xuất kho/lưu chuyển/PDI dở dang"
                    ct.phuong_an_xu_ly = "Giữ nguyên, không điều chỉnh"
                elif vin in vin_da_quet_set:
                    ct.ton_thuc_te = 1
                    # Kiểm tra vị trí
                    if vt_thuc_te and vt_thuc_te != ct.vi_tri_he_thong:
                        ct.phan_loai = PhanLoaiKiemKe.SAI_VI_TRI
                    else:
                        ct.phan_loai = PhanLoaiKiemKe.KHOP
                else:
                    ct.ton_thuc_te = 0
                    ct.phan_loai = PhanLoaiKiemKe.THIEU

                ct.save()

            # Chuyển phiếu sang Chờ xử lý chênh lệch
            phieu.trang_thai = TrangThaiKiemKe.CHO_XU_LY
            phieu.save(update_fields=['trang_thai'])

            return {"ma_pkk": phieu.ma_pkk, "tong_so_xe": chi_tiet_items.count(), "trang_thai": phieu.trang_thai}

    @classmethod
    def xu_ly_chenh_lech(cls, ma_pkk: str, ma_nv_xuly: str, danh_sach_xu_ly: list) -> bool:
        """
        Nghiệp vụ UC-KK-04 & UC-KK-05: Ghi nhận nguyên nhân và phương án xử lý chênh lệch.
        Mỗi dòng chênh lệch (Thiếu, Thừa, Sai vị trí) bắt buộc phải có nguyên nhân & phương án xử lý.
        danh_sach_xu_ly = [{'vin': '...', 'nguyen_nhan': '...', 'phuong_an_xu_ly': '...'}]
        """
        with transaction.atomic():
            phieu = PhieuKiemKe.objects.select_for_update().get(ma_pkk=ma_pkk)
            if phieu.trang_thai != TrangThaiKiemKe.CHO_XU_LY:
                raise InventoryError("Chỉ có thể xử lý chênh lệch khi phiếu ở trạng thái 'Chờ xử lý'.")

            for item in danh_sach_xu_ly:
                vin = item.get("vin")
                nguyen_nhan = item.get("nguyen_nhan", "").strip()
                phuong_an = item.get("phuong_an_xu_ly", "").strip()

                if not nguyen_nhan or not phuong_an:
                    raise InventoryError(f"Xe {vin} chưa nhập đủ nguyên nhân hoặc phương án xử lý.")

                ChiTietKiemKe.objects.filter(phieu_kiem_ke=phieu, xe__vin=vin).update(
                    nguyen_nhan=nguyen_nhan,
                    phuong_an_xu_ly=phuong_an
                )

            return True

    @classmethod
    def duyet_phieu_kiem_ke(cls, ma_pkk: str, ma_nv_duyet: str) -> PhieuKiemKe:
        """
        Nghiệp vụ UC-KK-06 & UC-KK-07: Duyệt phiếu kiểm kê và Tự động Điều chỉnh tồn kho.
        *** AN TOÀN DỮ LIỆU ***:
        1. Kiểm tra tất cả dòng chênh lệch phải có nguyên nhân.
        2. Tự động cập nhật vị trí và số lượng trong TonKho.
        3. Bỏ qua các xe đang ở trạng thái 'DANG_XU_LY_NGHIEP_VU'.
        """
        with transaction.atomic():
            try:
                phieu = PhieuKiemKe.objects.select_for_update().get(ma_pkk=ma_pkk)
            except PhieuKiemKe.DoesNotExist:
                raise InventoryError(f"Phiếu kiểm kê {ma_pkk} không tồn tại.")

            if phieu.trang_thai != TrangThaiKiemKe.CHO_XU_LY:
                raise InventoryError("Phiếu kiểm kê không ở trạng thái 'Chờ xử lý'.")

            # Kiểm tra: Còn dòng chênh lệch nào chưa có nguyên nhân không?
            dong_chua_xu_ly = ChiTietKiemKe.objects.filter(
                phieu_kiem_ke=phieu,
                phan_loai__in=[PhanLoaiKiemKe.THIEU, PhanLoaiKiemKe.THUA, PhanLoaiKiemKe.SAI_VI_TRI]
            ).filter(Q(nguyen_nhan__isnull=True) | Q(nguyen_nhan="")).exists()

            if dong_chua_xu_ly:
                raise InventoryError("Vẫn còn dòng chênh lệch chưa được ghi nhận nguyên nhân. Chưa thể duyệt!")

            # THỰC HIỆN ĐIỀU CHỈNH TỒN KHO TỰ ĐỘNG (UC-KK-07)
            chi_tiets = ChiTietKiemKe.objects.filter(phieu_kiem_ke=phieu).select_related('xe')
            for ct in chi_tiets:
                # Bỏ qua xe đang có nghiệp vụ chưa hoàn tất
                if ct.phan_loai == PhanLoaiKiemKe.DANG_XU_LY_NGHIEP_VU:
                    continue

                ton, _ = TonKho.objects.get_or_create(
                    kho=phieu.kho,
                    xe=ct.xe,
                    defaults={'ngay_vao_kho': date.today(), 'so_luong_ton': ct.ton_thuc_te}
                )

                # Điều chỉnh số lượng và vị trí theo thực tế
                ton.so_luong_ton = ct.ton_thuc_te
                if ct.vi_tri_thuc_te:
                    ton.vi_tri = ct.vi_tri_thuc_te
                ton.save()

            # Hoàn tất phiếu
            phieu.trang_thai = TrangThaiKiemKe.HOAN_TAT
            phieu.nguoi_duyet_id = ma_nv_duyet
            phieu.ngay_duyet = timezone.now()
            phieu.save(update_fields=['trang_thai', 'nguoi_duyet', 'ngay_duyet'])

            return phieu