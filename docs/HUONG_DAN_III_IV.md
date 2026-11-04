# Logic II.3 – Quản lý hợp đồng xe bán và II.4 – Quản lý nhập kho

Bản v3 bám hai tab đặc tả của “Báo cáo giai đoạn 2”. Tên nhánh/file III–IV
được giữ để nối tiếp gói cũ; phạm vi chuẩn là II.3–II.4. Xem thêm
`DOI_CHIEU_DAC_TA_II_3_II_4.md` về 13 use case và các giới hạn.

## 1. Nền dữ liệu

- Repository: https://github.com/quochieuvie123/quan-tri-kho-va-chuoi-cung-ung-danaford.git
- Nền bản sao: commit `3a256ef`. Chưa tự cập nhật lên commit mới hơn của nhóm.
- Giữ khóa/quan hệ và migration gốc. Các bổ sung v2 được giữ: ba bảng
  `PhieuNhapKho`, `KetQuaPDI`, `LichSuNhapKho`; `KetQuaPDI.hang_muc`;
  `Xe.phien_ban`; năm trường `HopDong` về dòng/phiên bản/màu, ngày giao, trạng thái.
- V3 sửa logic/quyền/dữ liệu JSON, không thêm bảng, trường hoặc migration so với v2.
- Chỉ làm backend; các URL chức năng hiện trả JSON.

## 2. Chạy demo riêng trong PyCharm

Mở `E:\Downloads\danaford-work`. Terminal ở thư mục chứa `manage.py`.
Chọn interpreter Python; dùng đúng `requirements.txt` của nhóm.
Không chạy `startproject` hoặc `startapp` lại.

```powershell
python -m pip install -r requirements.txt
python manage.py check
python manage.py test contracts warehouse
python manage.py migrate --settings=config.iii_iv_demo_settings
python manage.py seed_iii_iv_demo --settings=config.iii_iv_demo_settings
python manage.py setup_iii_iv_roles --settings=config.iii_iv_demo_settings
python manage.py createsuperuser --settings=config.iii_iv_demo_settings
python manage.py runserver --settings=config.iii_iv_demo_settings
```

Mọi lệnh dữ liệu demo phải giữ `--settings=config.iii_iv_demo_settings`.
Database demo ở thư mục tạm hệ điều hành `danaford_iii_iv_demo/demo.sqlite3`;
`db.sqlite3` của nhóm giữ nguyên. Seed dùng tiền tố DEMO, không nhập thông tin
khách hàng/tài khoản từ chứng từ DN, không tạo PDI Đạt hoặc cộng tồn.
Chạy lại seed giữ dữ liệu demo đã có.

Đăng nhập http://127.0.0.1:8000/admin/ rồi mở:

- http://127.0.0.1:8000/hop-dong/
- http://127.0.0.1:8000/kho/nhap/
- http://127.0.0.1:8000/kho/xe-co-the-nhap/

Superuser dùng cấu hình/thử API, có thể thao tác mọi vai trò.

## 3. Quyền theo đặc tả

`setup_iii_iv_roles` tạo hoặc bổ sung quyền vào hai nhóm chuyên dụng;
không sửa nhóm Quản lý/Nhân viên cũ hoặc tự gán tài khoản.

| Nhóm | Công việc |
| --- | --- |
| `III-IV Sale Admin` | Xem danh sách/chi tiết hợp đồng, xem phiếu nhập, duyệt nhập và lịch sử |
| `III-IV Nhân viên kho` | Xem danh sách hợp đồng, đề xuất xe, lập nháp, ghi/duyệt PDI, gửi duyệt nhập |

Trong admin, gán nhóm cho hai tài khoản thường. Nhân viên kho phải liên kết
`User.nhan_vien`, nhân viên thuộc Đà Nẵng. Có thể cấu hình
`III_IV_DA_NANG_BRANCH_IDS` bằng mã chi nhánh thật trong settings; nếu chưa
cấu hình, mã nhận diện Đà Nẵng qua tên chi nhánh đã chuẩn hóa dấu.
Không suy vai trò từ `is_staff` hoặc tên đăng nhập.

Người kho chỉ ghi vào kho vật lý cùng chi nhánh. Sale Admin duyệt theo đặc tả,
không bị tự thêm điều kiện chi nhánh nhân viên. Cờ nút và server cùng kiểm tra
vai trò, quyền Django và trạng thái.

## 4. API hợp đồng

| Phương thức/URL | Vai trò | Kết quả |
| --- | --- | --- |
| `GET /hop-dong/` | Hai vai trò | Danh sách, tiêu chí xe, ngày giao, trạng thái, cờ thao tác |
| `GET /hop-dong/<ma_hd>/` | Sale Admin | Khách, hợp đồng, mảng VIN/hóa đơn có liên kết |
| `GET /hop-dong/<ma_hd>/xe-phu-hop/` | Người kho Đà Nẵng | Xe còn tồn đúng dòng–phiên bản–màu, vị trí/trạng thái |
| `GET /hop-dong/<ma_hd>/xe-phu-hop/<vin>/` | Người kho Đà Nẵng | Chi tiết xe còn thuộc kết quả đề xuất |

Lọc: `q` (mã HĐ/tên khách), `dong_xe`, `phien_ban`, `mau_sac`,
`ngay_du_kien_giao` (YYYY-MM-DD), `trang_thai`, `chi_nhanh_id`.
Tiêu chí phải cùng một xe; không ghép dòng chiếc này với phiên bản chiếc khác.

Hợp đồng chưa VIN dùng tiêu chí độc lập. Hợp đồng cũ chưa nhập tiêu chí dùng
các xe liên kết qua `ChiTietHopDong`; thiếu dữ liệu thì cảnh báo/chặn đề xuất.
GET không giữ/gán xe hoặc đổi dữ liệu. Hóa đơn chỉ lấy qua
`HoaDonBan → PhieuXuatKho → ChiTietHopDong → HopDong`, không ghép theo khách.
Giao diện xử lý mảng `xe`, `vin_hien_thi`, `hoa_don`, `tieu_chi_xe`.

## 5. API nhập kho/PDI

| Phương thức/URL | Kết quả |
| --- | --- |
| `GET /kho/nhap/` hoặc `/kho/phieu-nhap/` | Danh sách phiếu và cờ thao tác |
| `GET /kho/phieu-nhap/<id>/` | Xe/nguồn/kho/người lập/PDI mới nhất và lịch sử PDI |
| `GET /kho/phieu-nhap/tuy-chon/` | Mã/nhãn kho, kho được phép lập, nguồn theo chứng từ, enum trạng thái |
| `GET /kho/xe-co-the-nhap/` | Xe có chứng từ nhập, loại VIN còn tồn, cảnh báo phiếu đang xử lý |
| `GET /kho/pdi/<id>/` | Hạng mục, kết quả, người/thời gian, cảnh báo, cờ thao tác |
| `GET /kho/phieu-nhap/<id>/lich-su/` | Sự kiện nhập theo VIN, kho, người và thời điểm |
| `GET /kho/hoa-don-nhap/` | Hóa đơn nhập gốc, tách biệt phiếu nhập |
| `GET /kho/nhap/<ma_hdn>/` | Chi tiết hóa đơn gốc và biên bản sự cố `BienBanPDI` |

Lọc phiếu: `q` (mã phiếu/VIN), `kho_id`, `ngay_lap` (YYYY-MM-DD),
`trang_thai` (`NHAP`, `CHO_DUYET`, `DA_DUYET`).
Lọc xe: `vin`, `dong_xe` (hoặc `ten_xe`), `phien_ban`, `mau_sac`, `nguon_xe`
(mã nhà cung cấp), `trang_thai` (`CHUA_NHAP_KHO`, `DANG_CO_PHIEU`).

Tất cả POST dùng JSON, đăng nhập và CSRF token hợp lệ.

**Bước 1 – `POST /kho/phieu-nhap/tao/`: lưu nháp**

```json
{"ma_phieu":"PN-DEMO-001","chi_tiet_nhap_id":1,"kho_id":"DEMO-KHO","ngay_nhap":"2026-11-03"}
```

Lấy `chi_tiet_nhap_id` thật từ API chọn xe, không mặc định bằng 1.
Có thể bỏ mã phiếu để sinh tự động. Lưu `phieu_nhap.id`; chưa cộng tồn.

**Bước 2 – `POST /kho/phieu-nhap/<id>/pdi/`: ghi/cập nhật PDI**

```json
{
  "pdi_id": null,
  "tinh_trang": "Đã kiểm tra ngoại thất, nội thất và vận hành",
  "ket_qua": "DAT",
  "ghi_chu": "",
  "hang_muc": [
    {"hang_muc":"Ngoại thất","tinh_trang":"Không trầy xước","ket_qua":"DAT","ghi_chu":""},
    {"hang_muc":"Nội thất","tinh_trang":"Nguyên vẹn","ket_qua":"DAT","ghi_chu":""},
    {"hang_muc":"Vận hành","tinh_trang":"Hoạt động bình thường","ket_qua":"DAT","ghi_chu":""}
  ]
}
```

`pdi_id: null` dành cho lần đầu. Cập nhật phải gửi ID PDI mới nhất đang xem.
Mỗi lần tạo một bản ghi kiểm tra mới, giữ lịch sử cũ, đưa phiếu về Nháp.
Lấy ID mới từ `pdi.id` trong phản hồi; không dùng ID phiếu thay ID PDI.
Chỉ nhận `DAT`/`KHONG_DAT`; không kết luận Đạt khi còn hạng mục Không đạt.
Có thể lưu tổng thể chưa có hạng mục để bổ sung; có cảnh báo, chưa được duyệt.

**Bước 3 – `POST /kho/phieu-nhap/<id>/duyet-pdi/`: Nhân viên kho duyệt PDI**

```json
{"pdi_id":1}
```

Thay 1 bằng ID PDI mới nhất. Xác nhận kết quả đang hiển thị.
Không đạt vẫn lưu người/thời điểm duyệt; phiếu tiếp tục nháp.

**Bước 4 – `POST /kho/phieu-nhap/<id>/gui-duyet/`: gửi Sale Admin**

```json
{"pdi_id":1}
```

Người kho chỉ gửi khi PDI mới nhất Đạt/đã duyệt và thông tin xe/nguồn đầy đủ.
Chuyển `NHAP → CHO_DUYET`; chưa cộng tồn.

**Bước 5 – `POST /kho/phieu-nhap/<id>/duyet/`: Sale Admin duyệt nhập**

```json
{"pdi_id":1}
```

Kiểm tra lại quyền/dữ liệu/VIN. Cùng transaction: ghi `TonKho` đúng kho/ngày,
ghi `LichSuNhapKho`, chuyển `DA_DUYET`, lưu người/thời điểm duyệt.
Lưu lỗi thì hoàn tác; phiếu tiếp tục Chờ duyệt.

PDI thay đổi sau lúc mở trang, ID thiếu/null/sai, nhập trùng, duyệt lại hoặc
sai quyền đều bị chặn. Phiếu đã nhập không sửa PDI qua API.
Lỗi API được trả trong `error`; giao diện giữ dữ liệu đang nhập để xử lý.

## 6. Nối giao diện

- Dùng ID để gửi API, tên/nhãn `hien_thi` để hiển thị; định dạng ngày dd/mm/yyyy.
- Hiện `canh_bao`, khóa/ẩn nút theo `thao_tac`; server vẫn kiểm tra lại.
- Hộp xác nhận đề xuất lấy tiêu chí từ dòng HĐ; gọi GET sau xác nhận.
- Sale Admin xem PDI nhúng trong chi tiết phiếu. Endpoint PDI riêng dành cho
  Nhân viên kho theo đặc tả; không tự gắn link gọi endpoint này cho Sale Admin.
- Không tự đổi nhãn còn tồn/đã nhập thành Sẵn sàng bán; cần quy tắc của nhóm.
- Hiện PDI thuộc phiếu nháp: lưu nháp → ghi/duyệt PDI → gửi duyệt.
  Màn Figma có PDI đã duyệt trước lần lưu phiếu đầu cần điều chỉnh luồng hoặc
  đề xuất thay liên kết dữ liệu, được người dùng đồng ý trước khi sửa schema.
- Nguồn hiện lấy nhà cung cấp trên hóa đơn; phối hợp module Lưu chuyển nếu
  cần biểu diễn kho chi nhánh gửi xe như một loại nguồn riêng.

## 7. Kiểm thử và tích hợp

Đã chạy 35 bài kiểm thử hai module, 53 bài toàn dự án; Django system check và
migration check không lỗi. Test dùng database riêng; chưa thử tải đồng thời
hoặc giao diện trình duyệt theo Figma.

Trước tích hợp database nghiệp vụ: kiểm tra nhánh/migration hiện tại và sao lưu
database. Migration đã đổi số/nội dung thì đối chiếu, không ghi đè của người khác.
Không sửa trực tiếp ba bảng mới để bỏ qua kiểm tra service.

Nhánh cục bộ `feature/cam-tu-hop-dong-nhap-kho`; chưa commit/push hoặc sửa
GitHub/main. ZIP là gói bổ sung; không phải toàn bộ dự án.
