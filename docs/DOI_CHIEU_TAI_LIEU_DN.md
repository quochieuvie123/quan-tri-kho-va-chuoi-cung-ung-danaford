# Đối chiếu dữ liệu doanh nghiệp

Đã đọc bằng kết nối Drive, chỉ đọc, không chỉnh sửa chứng từ:

- Hóa đơn FVL: https://drive.google.com/file/d/1TyVJ2ltdqehRnllnBAH9d9_4Z8-UybaM/view
  Có số/ký hiệu hóa đơn, ngày, VIN, số máy, năm SX, màu, số lượng chiếc, đơn giá.
  Ánh xạ vào HoaDonNhap, ChiTietNhap, Xe hiện có; không lấy mã số loại làm phiên bản thương mại khi chưa có căn cứ.
- Bảng tồn/phân bổ: https://docs.google.com/spreadsheets/d/1r9mpdBINf-rb6z0XDGnH26n7WMR7bClI/edit
  Có Description, VIN, Color, Engine No, Dealer received date, KHO.
  Phải phân biệt tên màu và mã màu; không tự suy đoán kho khi ô KHO trống.
- Quy trình DN: https://docs.google.com/document/d/1htn-hD68PvTh_pTbwqNpfdqTvgl_JpKP/edit
  Kho thực tế chi nhánh và kho sổ sách có thể khác. Phiếu chọn kho vật lý riêng,
  không ép kho phải cùng chi nhánh hóa đơn. Người thao tác được kiểm tra theo kho vật lý.
- Hóa đơn bán lẻ: https://drive.google.com/file/d/14IgFEpvrqONjR4gIOdWieOUkYN72_N8Q/view
  Chỉ dùng để đối chiếu cấu trúc số hóa đơn, VIN, số máy và tiền thuế.
  Không đưa dữ liệu khách hàng/tài khoản tra cứu vào demo hoặc code.

Không có căn cứ từ các nguồn đã đọc để tự đánh dấu PDI Đạt, người duyệt,
trạng thái hợp đồng hoặc ngày giao thực tế. Những giá trị này phải do người có quyền ghi nhận.
Dữ liệu seed là mô phỏng rõ ràng, không phải bản nhập chính thức từ Drive.
