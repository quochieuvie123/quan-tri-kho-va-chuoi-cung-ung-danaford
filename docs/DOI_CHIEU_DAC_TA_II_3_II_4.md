# Đối chiếu II.3 – Quản lý hợp đồng xe bán và II.4 – Quản lý nhập kho

Ngày rà soát: 03/11/2026. Bản code: v3, nền commit `3a256ef`.

## 1. Căn cứ và kết luận

**Đặc tả II.3–II.4 là căn cứ chính cho hành vi và quyền.** API hiện có các luồng
tra cứu hợp đồng, đề xuất xe, lưu nháp, PDI, gửi duyệt và duyệt nhập nguyên tử.
Có 35 bài kiểm thử của hai module và 53 bài kiểm thử toàn dự án đạt.
Chưa có giao diện để xác nhận hiển thị hay tương tác giống bản demo Figma.

Nguồn đã đối chiếu:

- [Báo cáo giai đoạn 2 – tab hợp đồng](https://docs.google.com/document/d/1oGF6JGJgVR-H5j-l_jTH_Gwys7dsxd-uPb3Yq4U_HwM/edit?tab=t.o7e8cmx34o0h): mục 3.2.1–3.2.4, bốn use case.
- [Báo cáo giai đoạn 2 – tab nhập kho](https://docs.google.com/document/d/1oGF6JGJgVR-H5j-l_jTH_Gwys7dsxd-uPb3Yq4U_HwM/edit?tab=t.y0qscrlfdkkh): mục 4.1.2 và 4.2.2, chín use case.
- [Figma – Hợp đồng xe bán](https://www.figma.com/design/v2MofbewgNx9iHWT4GUBTl/?node-id=35-4) và [Nhập kho và PDI](https://www.figma.com/design/v2MofbewgNx9iHWT4GUBTl/?node-id=35-5): đã đọc cấu trúc các frame của hai phần, xem ảnh màn chi tiết phiếu nhập.
- [Ảnh ERD](https://drive.google.com/file/d/1FJZ42BhJ3j8wwH2jj_M0SNTjq6ujmkYe/view): tham khảo quan hệ; code/model GitHub và các phần bổ sung đã thống nhất là nền triển khai.
- [Repository nhóm](https://github.com/quochieuvie123/quan-tri-kho-va-chuoi-cung-ung-danaford.git): dùng bản sao tại commit trên; chưa khẳng định đã đồng bộ các thay đổi mới hơn trên GitHub.

Không sử dụng bản “Nháp Database”. Không chỉnh Google Docs hoặc Figma.
Các chứng từ DN đã đọc trước đó chỉ giúp hiểu dữ liệu, không thay đặc tả II.3–II.4.

## 2. II.3 – Bốn use case hợp đồng xe bán

| Mục / ID trong tài liệu | Yêu cầu chính và actor | Triển khai / bằng chứng | Kết luận |
| --- | --- | --- | --- |
| 3.2.1 / UC-HDB-01 | Hai vai trò xem, tìm/lọc; có mã, khách, dòng, phiên bản, màu, ngày giao, trạng thái; thao tác đúng quyền | `GET /hop-dong/`; lọc từ khóa và các trường, dữ liệu `tieu_chi_xe`, `thao_tac`; thử dữ liệu cũ, kết quả rỗng và sai quyền | Đã có backend. Dữ liệu cũ thiếu ngày giao/trạng thái được để trống; phải bổ sung từ nguồn thật |
| 3.2.2 / UC-HDB-02 | Chỉ Sale Admin xem chi tiết, VIN nếu có; đọc, không sửa | `GET /hop-dong/<ma_hd>/`; chặn Nhân viên kho, có khách hàng và mảng VIN/hóa đơn; thử không tồn tại và hóa đơn cùng khách nhưng chưa liên kết | Đã có backend. Hóa đơn chỉ xuất hiện khi có liên kết thật qua phiếu xuất |
| 3.2.3 / UC-HDB-03 | Nhân viên kho Đà Nẵng xác nhận tiêu chí, xem đề xuất và chi tiết xe; không giữ/gán xe | API xe phù hợp và chi tiết xe trong kết quả; kiểm thử đúng phiên bản, tồn bằng 0, thiếu tiêu chí, sai quyền và không đổi dữ liệu | Đã có backend. Hộp xác nhận/quay lại thuộc bước dựng giao diện |
| 3.2.4 / UC-HDB-04 | Tra cứu nội bộ theo tiêu chí hợp đồng; trả VIN, trạng thái, vị trí; cảnh báo dữ liệu thiếu | `criteria_for`, `find_suitable`, `stock_data`; dùng đồng thời dòng–phiên bản–màu, trả vị trí và trạng thái có căn cứ | Đã có backend. Trạng thái “Sẵn sàng” chưa có đủ căn cứ dữ liệu; xem lưu ý A |

## 3. II.4 – Chín use case nhập kho

| Mục / ID trong tài liệu | Yêu cầu chính và actor | Triển khai / bằng chứng | Kết luận |
| --- | --- | --- | --- |
| 4.1.2.1 / UC-PNK01 | Hai vai trò xem danh sách: mã phiếu, VIN, xe, ngày lập, kho, người lập, trạng thái; tìm/lọc | `/kho/nhap/` và `/kho/phieu-nhap/`; trả tên/nhãn, cờ lập và thao tác, thông báo rỗng; kiểm thử vai trò và bộ lọc | Đã có backend |
| 4.1.2.2 / UC-PNK03 | Hai vai trò xem chi tiết; Sale Admin có thể duyệt phiếu Chờ duyệt | `/kho/phieu-nhap/<id>/`; xe/nguồn/ngày/kho/người lập, PDI và cờ thao tác; thử tài khoản thường và sai quyền | Đã có backend |
| 4.1.2.3 / UC-PNK-03 | Sale Admin xác nhận phiếu hợp lệ, PDI đạt, VIN chưa nhập; không duyệt lặp; lỗi tồn giữ Chờ duyệt | `approve_receipt`; kiểm tra lại quyền, phiên bản PDI đang xem, dữ liệu và tồn; kiểm thử người kho không duyệt, duyệt lặp, VIN trùng và lỗi ghi lịch sử | Đã có backend |
| 4.1.2.4 / UC-PNK-04 | Hệ thống cập nhật vị trí, tồn, trạng thái và lịch sử VIN trong quá trình duyệt | `TonKho` + `LichSuNhapKho` + trạng thái phiếu lưu cùng transaction; kiểm thử không tăng tồn sớm và rollback | Đã có backend. Trạng thái được phản ánh từ phiếu/tồn/lịch sử, chưa có enum sẵn sàng bán riêng |
| 4.2.2.1 / UC-LPNK01 | Nhân viên kho lập phiếu, tự điền theo xe; PDI chưa đạt vẫn nháp và chưa nhập | POST tạo phiếu lưu Nháp; lấy dữ liệu xe/chứng từ; bổ sung PDI, gửi Chờ duyệt khi đạt/đã duyệt; thử tạo bằng tài khoản thường | Có luồng chạy được; thứ tự PDI và lần lưu đầu có khác Figma, xem B |
| 4.2.2.2 / UC-LPNK02 | Nhân viên kho lọc/chọn VIN, dòng, phiên bản, màu, nguồn, trạng thái; loại đã nhập và cảnh báo phiếu khác | `/kho/xe-co-the-nhap/`; lọc không phân biệt hoa thường, cảnh báo/khóa VIN đã có phiếu, loại xe còn tồn ở bất kỳ kho nào | Đã có với xe có `ChiTietNhap`; xe chưa có chứng từ chưa lập được phiếu, xem C |
| 4.2.2.3 / UC-LPNK03 | Nhân viên kho duyệt kết quả Đạt/Không đạt, lưu người/thời gian; thiếu PDI không duyệt | POST `duyet-pdi`; xác nhận đúng kết quả đang xem bằng `pdi_id`; có hạng mục mới được duyệt; kết quả Không đạt giữ nháp | Đã có sau khi tạo phiếu nháp. Không tự sửa kết quả kiểm tra trong thao tác duyệt; muốn đổi dùng cập nhật PDI |
| 4.2.2.4 / UC-LPNK04 | Nhân viên kho xem hạng mục, tình trạng, kết quả, ghi chú; thiếu thông tin phải cảnh báo | `/kho/pdi/<id>/`; trả nhãn, hạng mục, dữ liệu duyệt, cảnh báo; PDI cũ đọc được, không có nút xử lý tiếp | Đã có backend |
| 4.2.2.5 / UC-LPNK05 | Cập nhật PDI khi được phép, lưu người/thời gian, cập nhật khả năng tiếp tục; lỗi giữ dữ liệu cũ | POST `pdi`; tạo lần kiểm tra mới với người/thời điểm, giữ lịch sử cũ, đưa phiếu về Nháp để duyệt lại; chặn PDI cũ và phiếu đã nhập | Đã có backend |

Tên và ID được giữ theo tài liệu. Tài liệu dùng `UC-PNK03` cho xem chi tiết và
`UC-PNK-03` cho duyệt phiếu; cần giữ thêm số mục khi phân công để tránh nhầm ID.

## 4. Những điểm đã sửa sau v2

1. Tách quyền hợp đồng: Nhân viên kho không xem endpoint chi tiết dành cho Sale
   Admin; Sale Admin không dùng endpoint đề xuất dành cho Nhân viên kho.
2. Cờ thao tác kiểm tra cả vai trò và quyền Django; cờ ghi PDI/gửi duyệt kiểm tra
   chi nhánh kho giống service. `is_staff` không tự tạo quyền nghiệp vụ.
3. Bộ lọc hợp đồng cũ dùng đúng dữ liệu tiêu chí đang hiển thị; không ghép dòng
   xe của chiếc này với phiên bản của chiếc khác trong hợp đồng nhiều VIN.
4. Bổ sung dữ liệu hiển thị cho chi tiết phiếu/PDI, nguồn, tên kho, tên người,
   lịch sử và trạng thái có căn cứ; API tùy chọn trả các kho/nhãn đúng dữ liệu.
5. Thêm cảnh báo dữ liệu thiếu và tách PDI lịch sử khỏi PDI mới nhất.
6. Cập nhật/duyệt PDI, gửi duyệt và duyệt nhập yêu cầu xác nhận PDI đang xem;
   PDI cũ, ID thiếu/null/sai bị chặn để tránh dùng kết quả đã thay đổi.
7. Thiếu thông tin xe/nguồn thì chặn gửi/duyệt nhập; PDI chưa có hạng mục thì
   vẫn có thể lưu để bổ sung nhưng chưa được duyệt.
8. Giữ thứ tự khóa VIN trước chứng từ, kiểm tra trùng ở server và lưu nguyên tử.
   Đây chưa phải bằng chứng chịu tải đồng thời; vẫn cần kiểm thử riêng trước triển khai thật.
9. Chuẩn hóa lỗi API: sai dữ liệu 400, sai quyền 403, không có đối tượng 404,
   sai phương thức 405, trùng ràng buộc 409, lỗi truy cập database 503.
   Lỗi database trả thông báo chung, không trả SQL/traceback trong JSON.

Không thêm bảng, trường hoặc migration so với v2 trong lần rà soát này.

## 5. Những điểm chưa được xem là hoàn tất hoặc giống Figma

### A. Nhãn “Sẵn sàng”

Figma dùng “Sẵn sàng” cho xe đề xuất và sau duyệt nhập. Nền dữ liệu hiện có
không thể kết luận xe không bị giữ/gán cho giao dịch khác chỉ từ `TonKho > 0`.
API trả “Còn tồn — cần kiểm tra trạng thái” hoặc “Đã nhập kho” nếu có lịch sử
phù hợp. Giao diện hiển thị đúng nhãn này; nhóm cần thống nhất ý nghĩa và nguồn
trạng thái trước khi dùng nhãn Sẵn sàng. Không tự bổ sung schema cho trạng thái đó.

### B. PDI trước lần lưu phiếu đầu

`KetQuaPDI.phieu_nhap` là FK bắt buộc trong phần đã bổ sung. Vì vậy backend hiện
chạy theo thứ tự: lưu phiếu nháp → ghi/duyệt PDI → gửi Sale Admin → duyệt nhập.
Figma có cảnh xác nhận lập phiếu đã có PDI Đạt/Đã duyệt, rồi kết quả Chờ duyệt.
Chưa thể thực hiện nguyên xi cảnh đó cho một xe hoàn toàn chưa có phiếu.

Khi dựng UI cần phân biệt “Lưu nháp” với “Gửi duyệt” trên phiếu đã có. Nếu nhóm
muốn PDI tồn tại độc lập trước cả phiếu nháp, phải thiết kế thay đổi liên kết và
được người dùng đồng ý trước khi sửa model/migration. Lượt này chưa thay đổi.

### C. Nguồn xe và chứng từ đầu vào

Phiếu nhập tham chiếu `ChiTietNhap` hiện có. Xe chỉ có bản ghi `Xe` nhưng chưa
có chi tiết chứng từ nhập chưa đi được toàn luồng. Nguồn xe đang hiển thị
`HoaDonNhap.nha_cung_cap.ten_ncc`, không tự coi chi nhánh trên hóa đơn là kho
vật lý hoặc kho gửi xe. Cần phối hợp module Lưu chuyển để chuẩn hóa dữ liệu nguồn
nếu muốn hiển thị các kho gửi như một loại nguồn riêng.

### D. Hợp đồng, hóa đơn và nhiều VIN

Các trường tiêu chí/ngày giao/trạng thái bổ sung trong v2 được để nullable cho
dữ liệu cũ. Cần nhập dữ liệu thật; không tự đoán phiên bản, trạng thái hoặc ngày.
Figma minh họa hợp đồng chưa VIN vẫn có mã hóa đơn. Code chỉ trả hóa đơn khi có
liên kết thật qua phiếu xuất; không tự gắn hóa đơn cùng khách vào hợp đồng.
Mô hình GitHub cho phép nhiều xe/hợp đồng nên UI không được tự lấy VIN đầu
tiên để đại diện cho cả hợp đồng. Trường trống cần hiển thị “—”/“Chưa gán”.

### E. Giao diện và triển khai

Chưa xây HTML/CSS hay chạy thao tác màn hình theo Figma. Backend có dữ liệu
cho phần lớn ô/bảng/hộp thoại; cần tạo form, hiển thị lỗi, xác nhận và quay lại.
Chưa thử nhiều người dùng đồng thời. Chưa commit/push; chưa chạy migration vào
database nghiệp vụ. Nhánh cục bộ là `feature/cam-tu-hop-dong-nhap-kho`.

## 6. Ánh xạ dữ liệu cho giao diện

| Màn / frame Figma | API / trường cần dùng | Lưu ý |
| --- | --- | --- |
| Danh sách HĐ / 17:1399 | `/hop-dong/`: `ma_hd`, `khach_hang__ten_kh`, bộ tiêu chí, ngày giao, trạng thái, `thao_tac` | Hiển thị khác thao tác theo hai vai trò |
| Chi tiết HĐ / 17:1669 | `/hop-dong/<ma_hd>/`: `xe`, `vin_hien_thi`, `hoa_don`, thông tin khách | Mảng VIN/hóa đơn, không ghép hóa đơn tùy ý |
| Xe phù hợp / 17:1753; chi tiết / 17:1848 | API xe phù hợp và xe cụ thể: VIN, dòng/phiên bản/màu, `vi_tri_kho`, `trang_thai_hien_thi` | Nhãn trạng thái theo dữ liệu thật |
| DS phiếu / 17:1885 | API phiếu: mã, VIN, xe, `ngay_lap`, `ten_kho`, `nguoi_lap`, `trang_thai_danh_sach_hien_thi` | Dùng enum để gửi lọc, nhãn để hiển thị |
| Chi tiết / 17:2031; nháp / 158:4 | API chi tiết: `dong_xe`, `phien_ban`, `mau_sac`, `nguon_xe`, ngày/kho, `pdi_moi_nhat`, `thao_tac` | Mã PDI hiển thị khác ID; Sale Admin đọc PDI nhúng trong chi tiết phiếu |
| Lập phiếu / 17:2228 | API xe chọn + tùy chọn kho + POST tạo | Ban đầu lưu nháp; PDI cần phiếu đã tồn tại |
| Chọn VIN / 17:2386 | `/kho/xe-co-the-nhap/`: `id`, VIN, nguồn, trạng thái, `co_the_tao`, cảnh báo | Dùng `id` làm `chi_tiet_nhap_id` |
| PDI / 17:2514; duyệt / 17:2606; sửa / 17:2657 | API PDI: `hang_muc`, `tinh_trang`, kết quả, ghi chú, trạng thái, người/thời gian, cờ; POST có `pdi_id` | Chỉ xử lý PDI mới nhất, giữ lịch sử kiểm tra lại |
| Kết quả duyệt / 17:2114 | Phản hồi POST duyệt và API lịch sử | Không tăng tồn ở frontend; lỗi thì hiện trạng thái server trả về |

## 7. Kiểm thử đã thực hiện

| Kiểm tra | Kết quả |
| --- | --- |
| `python manage.py test contracts warehouse` | 35 bài kiểm thử đạt |
| `python manage.py test` | 53 bài kiểm thử toàn dự án đạt |
| `python manage.py check` | Không có lỗi system check |
| `python manage.py makemigrations --check --dry-run` | Không thiếu migration |
| `python manage.py migrate --plan --settings=config.iii_iv_demo_settings` | Database demo đã ở migration hiện có, không có thao tác còn chờ |

Nhóm kiểm thử có: danh sách/chi tiết/lọc, hợp đồng chưa VIN và dữ liệu cũ,
đề xuất đúng phiên bản/không ghi dữ liệu, hóa đơn đúng liên kết, hai vai trò
thường, sai chi nhánh, toàn luồng POST, CSRF/phương thức, thiếu/sai dữ liệu,
PDI Không đạt/chưa duyệt/chưa có hạng mục, cập nhật lại và PDI cũ, VIN trùng
ở chứng từ khác, duyệt lặp và rollback khi lưu lịch sử/database lỗi.

Các kết quả trên xác nhận phạm vi kiểm thử đã nêu; không đồng nghĩa đã kiểm
thử giao diện Figma, tải đồng thời hoặc tích hợp database thật của nhóm.
