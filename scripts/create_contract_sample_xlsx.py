from pathlib import Path
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

OUTPUT = Path('docs/hop_dong_xe_ban_mau_9_xe.xlsx')
SEP = Path(r'C:\Users\admin\.codex\visualizations\2026\11\11\01a1ca1b-4c4a-7312-9518-31a8909db1ad\phan_bo_mau_thang_09.xlsx')
OCT = Path(r'C:\Users\admin\.codex\visualizations\2026\11\11\01a1ca1b-4c4a-7312-9518-31a8909db1ad\phan_bo_mau_thang_10.xlsx')
HEADERS = ['ma_hop_dong','ma_khach_hang','ten_khach_hang','sdt_khach_hang','mst_khach_hang','ma_chi_nhanh','ngay_ky','so_tien_coc','dong_xe_yeu_cau','phien_ban_yeu_cau','mau_sac_yeu_cau']

def rows(path, count, prefix, names, phones, dates):
    wb = load_workbook(path, read_only=True, data_only=True)
    ws = wb.active
    data = list(ws.iter_rows(min_row=2, max_row=count + 1, values_only=True))
    wb.close()
    result = []
    for i, row in enumerate(data):
        description = str(row[2]).strip()
        version = {'TITANIUM': 'Titanium', 'PLATINUM': 'Platinum', 'TREND': 'Trend', 'ACTIVE': 'Active'}.get(description.rsplit(' ', 1)[-1], description.rsplit(' ', 1)[-1].title())
        result.append([
            f'{prefix}-{i+1:03d}', f'KH-{prefix}-{i+1:03d}', names[i], phones[i], '', 'CN01',
            dates[i][0], 50000000 + i * 5000000, description, version, str(row[5]).strip(),
        ])
    return result

sep = rows(SEP, 4, 'T09', ['Công ty TNHH Xây dựng Miền Trung','Nguyễn Thành Long','Trần Ngọc Bích','Công ty TNHH Du lịch Ánh Dương'], ['0905001001','0905001002','0905001003','0905001004'], [('2026-09-02','2026-09-18'),('2026-09-03','2026-09-19'),('2026-09-04','2026-09-20'),('2026-09-05','2026-09-25')])
oct = rows(OCT, 5, 'T10', ['Công ty CP Vận tải Đại Việt','Lê Minh Quân','Phạm Thị Thu Hà','Công ty TNHH Thương mại Phú Gia','Đỗ Hoàng Nam'], ['0905001011','0905001012','0905001013','0905001014','0905001015'], [('2026-10-01','2026-10-20'),('2026-10-01','2026-10-22'),('2026-10-02','2026-10-24'),('2026-10-02','2026-10-26'),('2026-10-03','2026-10-28')])

wb = Workbook()
ws = wb.active
ws.title = 'HopDongXeBan'
ws.append(HEADERS)
for row in sep + oct:
    ws.append(row)
for cell in ws[1]:
    cell.fill = PatternFill('solid', fgColor='0B66C3')
    cell.font = Font(name='Arial', bold=True, color='FFFFFF')
    cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
for row in ws.iter_rows(min_row=2, max_row=10):
    for cell in row:
        cell.font = Font(name='Arial', size=10)
        cell.alignment = Alignment(vertical='center')
        cell.border = Border(bottom=Side(style='thin', color='D9E2F3'))
    row[6].value = __import__('datetime').date.fromisoformat(row[6].value)
    row[6].number_format = 'yyyy-mm-dd'
    row[7].number_format = '#,##0'
widths = [18,18,34,16,18,12,14,16,52,18,24]
for idx, width in enumerate(widths, 1):
    ws.column_dimensions[chr(64 + idx)].width = width
ws.freeze_panes = 'A2'
ws.auto_filter.ref = 'A1:K10'
ws.sheet_view.showGridLines = False
OUTPUT.parent.mkdir(parents=True, exist_ok=True)
wb.save(OUTPUT)
print(OUTPUT.resolve())
