# Hoàn thiện hợp đồng và nhập kho

## Trạng thái triển khai

Code có migration mới, chưa áp dụng lên database hiện tại. Không xóa hoặc tạo lại SQLite. Sao lưu và kiểm tra dữ liệu trên bản sao trước khi người phụ trách chủ động chạy migrate.

Ba migration mới: contracts/0001_initial, database/0010_chitiethopdong_yeu_cau_hoadonban_hop_dong, warehouse/0002_phieunhapkho_chi_tiet_luu_chuyen_and_more.

## Dữ liệu và phân quyền

- Trong admin của hợp đồng, bổ sung các dòng Yêu cầu xe: tên xe đúng danh mục, phiên bản, màu sắc, số lượng, ngày giao. Chưa cần VIN. Giữ dữ liệu cũ để tra cứu; không tự đoán phiên bản còn thiếu.
- Hóa đơn bán cần liên kết trực tiếp với hợp đồng và có chi tiết đúng VIN; không tự ghép chứng từ theo khách hàng. Chứng từ cũ đã liên kết qua phiếu xuất vẫn xem được.
- Lệnh setup_hopdong_nhapkho_roles tạo hai nhóm III-IV Sale Admin và III-IV Nhân viên kho. Lệnh không tự gán người dùng. Chỉ chạy sau khi migrations đã được áp dụng và được người quản trị cho phép.
- Nhân viên kho phải gắn hồ sơ nhân viên đúng chi nhánh. Sale Admin duyệt nhập theo quyền approve_phieunhapkho; nhân viên kho không có quyền duyệt nhập dù được cấp nhầm permission này.
- Kho nhận nhập là Đà Nẵng. Có thể cấu hình III_IV_DA_NANG_BRANCH_IDS (mặc định CN01) và III_IV_TRANSFER_BRANCH_IDS (mặc định CN02, CN03) theo mã chi nhánh thực tế.

## Nhập từ hãng

Chọn chứng từ hãng → lưu Nháp → ghi PDI → xác nhận PDI → gửi duyệt → Sale Admin duyệt → cập nhật tồn, trạng thái xe và lịch sử trong một giao dịch. Ngày tiếp nhận mặc định hôm nay theo múi giờ dự án.

## Nhập lưu chuyển

Gửi lệnh: kiểm tra VIN sẵn sàng, ghi tồn nguồn về 0 và chuyển xe sang Đang lưu chuyển. Xác nhận lệnh: chỉ tiếp nhận, chưa cộng tồn đích. Trong màn hình lập phiếu, chọn dòng lệnh đã tiếp nhận → PDI → duyệt nhập như luồng hãng. Mỗi dòng lệnh chỉ được dùng một lần.

Lệnh cũ ở trạng thái Đã gửi nhưng vẫn còn tồn dương tại kho nguồn sẽ bị chặn tiếp nhận. Cần người phụ trách đối chiếu thực tế; code không tự sửa tồn lịch sử. Lệnh đã xác nhận theo luồng cũ không được tự động đổi thành phiếu nhập mới.

## PDI và sự cố

Kết quả Không đạt vẫn được xác nhận, lưu người và thời gian, khóa xe. Từ phiếu nhập có liên kết mở màn hình sự cố, điền VIN/chứng từ khi có. Hồ sơ sự cố vẫn dùng module incidents hiện hữu, yêu cầu mô tả và ảnh. Với lưu chuyển, nhân viên đối chiếu chứng từ nhập gốc của VIN trên màn hình sự cố; không tạo hóa đơn giả nếu hồ sơ gốc chưa có.

Sau khi đóng sự cố phải tạo lần kiểm tra mới Đạt và xác nhận lại. Gửi biểu mẫu cũ không được duyệt PDI mới. Không sửa trực tiếp phiếu nhập/PDI qua admin; các thao tác nghiệp vụ đi qua dịch vụ.

## Hợp đồng nhiều xe

Mỗi dòng yêu cầu có số lượng, VIN chỉ gắn khi lập xuất. Nhu cầu chưa giao được đưa vào dự báo, kể cả chưa chọn VIN. Khi mới giao một phần, hợp đồng tiếp tục Đang xuất kho; giao đủ mới Hoàn tất. Phiếu xuất đã hủy được mở lại cùng mã và giữ các sự kiện trong lịch sử xuất.

## Kiểm thử không dùng SQLite dự án

Chạy bằng Python của .venv:

    .\.venv\Scripts\python.exe -B scripts/test_business_in_memory.py

Script tạo schema từ model trên SQLite :memory:, không chạy migrations và không mở db.sqlite3. Kiểm thử bao gồm phân quyền, nhập hãng/lưu chuyển, rollback, phiên bản PDI, nhu cầu không VIN, giao từng phần, chọn kho, lập lại phiếu xuất đã hủy và các test tồn/xuất hiện có.
