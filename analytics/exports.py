"""UC-09.5 Xuất danh sách đề xuất nhập xe (Excel / PDF) theo mẫu kế hoạch nhập xe Dana Ford."""
import io
import os

from django.utils import timezone

from .services import tong_ket

CAC_COT = ["STT", "Mã dòng xe", "Tên xe", "Phiên bản", "Dự báo SARIMA", "Tồn kho", "HĐ chờ giao",
           "Đang vận chuyển", "Chỉ tiêu hãng", "Đề xuất POQ", "SL nhập chính thức", "Đơn giá vốn (VNĐ)",
           "Thành tiền (VNĐ)"]


def _hang(i, d):
    return [i, d.ma_dong_xe, d.ten_ngan, d.phien_ban, round(d.du_bao_sarima, 1), d.ton_kho, d.hop_dong_cho_giao,
            d.dang_van_chuyen, d.chi_tieu if d.chi_tieu is not None else "", d.de_xuat_poq, d.so_luong_nhap,
            float(d.don_gia_von), float(d.thanh_tien)]


def _ghi_chu_dieu_chinh(cac_dong):
    return [f"{d.ten_xe}: {d.ly_do_dieu_chinh}" for d in cac_dong
            if d.so_luong_dieu_chinh is not None and d.ly_do_dieu_chinh]


def tao_xlsx(phien, cac_dong, nguoi_lap, ghi_chu="", kem_bieu_do=False):
    from openpyxl import Workbook
    from openpyxl.chart import BarChart, Reference
    from openpyxl.styles import Alignment, Font, PatternFill

    wb = Workbook()
    ws = wb.active
    ws.title = "Kế hoạch nhập xe"
    ws["A1"] = "KẾ HOẠCH NHẬP XE - DANA FORD"
    ws["A1"].font = Font(bold=True, size=14)
    ws["A2"] = f"Kỳ kế hoạch: tháng {phien.thang:02d}/{phien.nam}"
    ws["A3"] = f"Ngày lập: {timezone.localtime():%d/%m/%Y %H:%M} · Trạng thái: {phien.trang_thai_de_xuat}"
    ws.append([])
    ws.append(CAC_COT)
    dau = ws.max_row
    for c in ws[dau]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="1F4E79")
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    for i, d in enumerate(cac_dong, 1):
        ws.append(_hang(i, d))
        r = ws.max_row
        ws.cell(row=r, column=12).number_format = ws.cell(row=r, column=13).number_format = "#,##0"
    cuoi = ws.max_row
    tk = tong_ket(cac_dong)
    ws.append(["", "TỔNG", "", "", "", "", "", "", tk["tong_chi_tieu"] or "", "", tk["tong_sl"], "", float(tk["tong_von"])])
    for c in ws[ws.max_row]:
        c.font = Font(bold=True)
    ws.cell(row=ws.max_row, column=13).number_format = "#,##0"
    if tk["ty_le"] is not None:
        ws.append(["", f"Tỷ lệ so với chỉ tiêu hãng: {tk['ty_le']}%"])
    if ghi_chu:
        ws.append([]); ws.append(["Ghi chú:", ghi_chu])
    for dong in _ghi_chu_dieu_chinh(cac_dong):
        ws.append(["", f"Điều chỉnh - {dong}"])
    ws.append([]); ws.append([])
    ws.append(["", "Người lập", "", "", "", "", "", "", "Người phê duyệt"])
    ws.append(["", nguoi_lap, "", "", "", "", "", "", "(Ký, ghi rõ họ tên)"])
    for i, w in enumerate([6, 26, 18, 26, 12, 9, 11, 12, 11, 11, 14, 18, 20], 1):
        ws.column_dimensions[chr(64 + i)].width = w
    if kem_bieu_do and cac_dong:
        bd = BarChart()
        bd.title = "Dự báo SARIMA so với số lượng nhập chính thức"
        bd.add_data(Reference(ws, min_col=5, min_row=dau, max_row=cuoi), titles_from_data=True)
        bd.add_data(Reference(ws, min_col=11, min_row=dau, max_row=cuoi), titles_from_data=True)
        bd.set_categories(Reference(ws, min_col=2, min_row=dau + 1, max_row=cuoi))
        bd.width, bd.height = 28, 11
        ws.add_chart(bd, f"B{ws.max_row + 3}")
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


_FONTS = [
    ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf"),
    ("C:/Windows/Fonts/tahoma.ttf", "C:/Windows/Fonts/tahomabd.ttf"),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ("/Library/Fonts/Arial.ttf", "/Library/Fonts/Arial Bold.ttf"),
    ("/System/Library/Fonts/Supplemental/Arial.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
]


def tao_pdf(phien, cac_dong, nguoi_lap, ghi_chu="", kem_bieu_do=False):
    from reportlab.graphics.charts.barcharts import VerticalBarChart
    from reportlab.graphics.shapes import Drawing
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    thuong = dam = None
    for a, b in _FONTS:
        if os.path.exists(a) and os.path.exists(b):
            pdfmetrics.registerFont(TTFont("VN", a)); pdfmetrics.registerFont(TTFont("VN-B", b))
            thuong, dam = "VN", "VN-B"
            break
    if not thuong:
        raise RuntimeError("Không tìm thấy font tiếng Việt (Arial/Tahoma/DejaVu) để tạo PDF.")
    c = ParagraphStyle("c", fontName=thuong, fontSize=7.5, leading=9)
    h = ParagraphStyle("h", fontName=dam, fontSize=7.5, leading=9, textColor=colors.white)
    t1 = ParagraphStyle("t1", fontName=dam, fontSize=14, leading=18)
    norm = ParagraphStyle("n", fontName=thuong, fontSize=9, leading=12)
    rows = [[Paragraph(x, h) for x in CAC_COT]]
    for i, d in enumerate(cac_dong, 1):
        r = _hang(i, d)
        r[11], r[12] = f"{r[11]:,.0f}", f"{r[12]:,.0f}"
        rows.append([Paragraph(str(x), c) for x in r])
    tk = tong_ket(cac_dong)
    rows.append([Paragraph(str(x), ParagraphStyle("b", parent=c, fontName=dam)) for x in
                 ["", "TỔNG", "", "", "", "", "", "", tk["tong_chi_tieu"] or "", "", tk["tong_sl"], "",
                  f"{tk['tong_von']:,.0f}"]])
    bang = Table(rows, repeatRows=1, colWidths=[22, 80, 55, 85, 38, 32, 36, 42, 38, 36, 44, 62, 70])
    bang.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F4E79")),
                              ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#BBBBBB")),
                              ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    ds = [Paragraph("KẾ HOẠCH NHẬP XE - DANA FORD", t1),
          Paragraph(f"Kỳ kế hoạch: tháng {phien.thang:02d}/{phien.nam} · Ngày lập: "
                    f"{timezone.localtime():%d/%m/%Y %H:%M} · {phien.trang_thai_de_xuat}", norm), Spacer(1, 8), bang]
    if tk["ty_le"] is not None:
        ds.append(Paragraph(f"Tỷ lệ so với chỉ tiêu hãng: {tk['ty_le']}%", norm))
    if ghi_chu:
        ds.append(Paragraph(f"Ghi chú: {ghi_chu}", norm))
    for dong in _ghi_chu_dieu_chinh(cac_dong):
        ds.append(Paragraph(f"Điều chỉnh - {dong}", norm))
    if kem_bieu_do and cac_dong:
        dr = Drawing(700, 170)
        bc = VerticalBarChart()
        bc.x, bc.y, bc.width, bc.height = 40, 30, 640, 120
        bc.data = [[d.du_bao_sarima for d in cac_dong], [d.so_luong_nhap for d in cac_dong]]
        bc.categoryAxis.categoryNames = [str(i) for i in range(1, len(cac_dong) + 1)]
        bc.bars[0].fillColor, bc.bars[1].fillColor = colors.HexColor("#9DB7D5"), colors.HexColor("#1F4E79")
        dr.add(bc)
        ds += [Spacer(1, 8), Paragraph("Biểu đồ: dự báo SARIMA (nhạt) so với số lượng nhập chính thức (đậm), "
                                       "trục ngang là STT dòng xe", norm), dr]
    ds += [Spacer(1, 18), Table([[Paragraph("Người lập", norm), Paragraph("Người phê duyệt", norm)],
                                 [Paragraph(nguoi_lap, norm), Paragraph("(Ký, ghi rõ họ tên)", norm)]],
                                colWidths=[350, 350])]
    buf = io.BytesIO()
    SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=24, rightMargin=24, topMargin=26,
                      bottomMargin=26, title="Kế hoạch nhập xe").build(ds)
    return buf.getvalue()
