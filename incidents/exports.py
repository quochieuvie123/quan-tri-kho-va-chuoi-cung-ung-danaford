"""UC-10.2.3 Xuất báo cáo sự cố (Excel .xlsx / PDF)."""
import io
import os

from .models import nhan_trang_thai

TIEU_DE = ["Mã sự cố", "VIN xe", "Dòng xe", "Tên ĐVVC", "Loại sự cố", "Trạng thái",
           "Số tiền bồi thường (VNĐ)", "Ngày lập"]


def _hang(bb):
    ho_so = getattr(bb, "ho_so", None)
    tien = ho_so.so_tien_boi_thuong if ho_so and ho_so.so_tien_boi_thuong is not None else None
    return [bb.ma_pdi, bb.xe_id, bb.xe.ten_xe, bb.hoa_don_nhap.don_vi_van_chuyen.ten_dvvc, bb.loai_su_co,
            nhan_trang_thai(bb.trang_thai_claim), tien, bb.ngay_ghi_nhan]


def _ngay(v):
    from django.utils import timezone
    return timezone.localtime(v).strftime("%d/%m/%Y %H:%M")


def tao_xlsx(danh_sach):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    wb = Workbook()
    ws = wb.active
    ws.title = "Sự cố vận chuyển"
    ws.append(TIEU_DE)
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="1F4E79")
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    for bb in danh_sach:
        h = _hang(bb)
        h[7] = _ngay(h[7])
        ws.append(h)
        if h[6] is not None:
            ws.cell(row=ws.max_row, column=7).number_format = "#,##0"
    for i, w in enumerate([12, 22, 32, 36, 20, 14, 22, 18], 1):
        ws.column_dimensions[chr(64 + i)].width = w
    ws.freeze_panes = "A2"
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


_FONTS = [  # (thường, đậm) - cần font có tiếng Việt
    ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf"),
    ("C:/Windows/Fonts/tahoma.ttf", "C:/Windows/Fonts/tahomabd.ttf"),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ("/Library/Fonts/Arial.ttf", "/Library/Fonts/Arial Bold.ttf"),
    ("/System/Library/Fonts/Supplemental/Arial.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
]


def tao_pdf(danh_sach, tieu_de="BÁO CÁO SỰ CỐ VẬN CHUYỂN"):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    thuong = dam = None
    for a, b in _FONTS:
        if os.path.exists(a) and os.path.exists(b):
            pdfmetrics.registerFont(TTFont("VN", a))
            pdfmetrics.registerFont(TTFont("VN-B", b))
            thuong, dam = "VN", "VN-B"
            break
    if not thuong:
        raise RuntimeError("Không tìm thấy font hỗ trợ tiếng Việt (Arial/Tahoma/DejaVu) để tạo PDF.")

    cell = ParagraphStyle("c", fontName=thuong, fontSize=8, leading=10)
    head = ParagraphStyle("h", fontName=dam, fontSize=8, leading=10, textColor=colors.white)
    rows = [[Paragraph(t, head) for t in TIEU_DE]]
    for bb in danh_sach:
        h = _hang(bb)
        h[6] = "" if h[6] is None else f"{h[6]:,.0f}"
        h[7] = _ngay(h[7])
        rows.append([Paragraph(str(x), cell) for x in h])
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=24, rightMargin=24, topMargin=28, bottomMargin=28,
                            title=tieu_de)
    bang = Table(rows, repeatRows=1, colWidths=[50, 105, 150, 140, 80, 60, 80, 70])
    bang.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F4E79")),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#BBBBBB")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F3F6FA")]),
    ]))
    t = ParagraphStyle("t", fontName=dam, fontSize=14, leading=18)
    doc.build([Paragraph(tieu_de, t), Spacer(1, 8), bang])
    return buf.getvalue()
