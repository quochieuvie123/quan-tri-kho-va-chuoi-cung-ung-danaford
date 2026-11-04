# Đưa bản v3 vào PyCharm

Gói bổ sung II.3 – Quản lý hợp đồng xe bán và II.4 – Quản lý nhập kho.
Nền commit `3a256ef`; gói không phải toàn bộ dự án.

1. Mở `E:\Downloads\danaford-work`; Terminal ở thư mục chứa `manage.py`.
2. Chạy `git status` và `git branch --show-current`. Giữ bản sao chỉnh sửa riêng
   trước khi chép file trùng tên.
3. Tạo nhánh: `git switch -c feature/cam-tu-hop-dong-nhap-kho`.
   Nếu đã có tên này, kiểm tra rồi `git switch feature/cam-tu-hop-dong-nhap-kho`.
   Nhánh của bản sao trợ lý không tự xuất hiện trên máy bạn.
4. Giải nén vào thư mục tạm, xem `DANH_SACH_FILE.md`, chép từng file theo đường
   dẫn tương đối. Không xóa hoặc thay cả thư mục dự án.
5. Nếu nhóm đã có migration `database/0007`, `warehouse/0001` hoặc `0002`,
   đối chiếu trước; không ghi đè migration của nhóm.
6. Chọn interpreter Python; cài `requirements.txt` hiện có.
7. Chạy:

```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test contracts warehouse
```

8. Theo mục 2 của `HUONG_DAN_III_IV.md` để chạy database demo riêng.
   Giữ `--settings=config.iii_iv_demo_settings` trong mọi lệnh dữ liệu demo.
9. Đọc `DOI_CHIEU_DAC_TA_II_3_II_4.md` trước khi nối giao diện Figma.

V3 sửa quyền theo use case, bộ lọc dữ liệu cũ, dữ liệu hiển thị/cảnh báo/cờ nút,
kiểm tra thông tin bắt buộc và PDI đã thay đổi sau khi mở trang.
Các POST cập nhật/duyệt/gửi duyệt dùng `pdi_id` theo hướng dẫn mới.
Không có bảng/trường/migration mới so với v2. Nếu chưa dùng v2, vẫn cần các
migration bổ sung đi kèm gói này.

Chưa làm giao diện; hiện thấy JSON. Chưa commit/push hoặc sửa GitHub/main.
Không cần push để chạy trên máy.
