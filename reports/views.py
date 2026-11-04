from html import escape
from io import BytesIO

import plotly.graph_objects as go
import xlsxwriter

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from .forms import BoLocBaoCaoForm
from .utils import (
    QUYEN_BAO_CAO,
    lay_kho_duoc_xem,
    tao_bao_cao,
)


def chuan_bi(request, kem_thong_ke=False):
    if not request.user.has_perms(QUYEN_BAO_CAO):
        raise PermissionDenied(
            "Bạn chưa được cấp đủ quyền xem báo cáo."
        )

    kho = lay_kho_duoc_xem(request.user)

    if not kho.exists():
        raise PermissionDenied(
            "Tài khoản chưa được phân công kho."
        )

    form = BoLocBaoCaoForm(
        request.GET,
        danh_sach_kho=kho,
    )

    hop_le = form.is_valid()

    data = (
        tao_bao_cao(
            kho,
            form.cleaned_data,
            kem_thong_ke=kem_thong_ke,
        )
        if hop_le
        else {}
    )

    return {
        "form": form,
        "bao_cao": data,
        "hop_le": hop_le,
        "tham_so": request.GET.urlencode(),
        "thoi_diem": timezone.localtime(),
        "kho_da_chon": (
            form.cleaned_data.get("kho")
            if hop_le
            else None
        ),
    }


def tao_cac_bieu_do(data):
    cac_bieu_do = []
    da_nap_plotly = False

    def them_bieu_do(
        tieu_de,
        figure=None,
        mo_ta="",
        chieu_cao=360,
    ):
        nonlocal da_nap_plotly

        html = None

        if figure is not None:
            figure.update_layout(
                template="plotly_white",
                autosize=True,
                height=chieu_cao,
                font={
                    "family": "Arial, sans-serif",
                    "size": 13,
                    "color": "#102b46",
                },
                margin={
                    "l": 20,
                    "r": 20,
                    "t": 35,
                    "b": 45,
                },
                legend={
                    "orientation": "h",
                    "y": 1.15,
                },
            )

            html = figure.to_html(
                full_html=False,
                include_plotlyjs=not da_nap_plotly,
                config={
                    "responsive": True,
                    "displaylogo": False,
                    "displayModeBar": False,
                },
            )

            da_nap_plotly = True

        cac_bieu_do.append({
            "tieu_de": tieu_de,
            "html": html,
            "mo_ta": mo_ta,
        })

    # Tồn kho theo tên xe.
    rows = data["ton_kho"]["theo_ten"]

    if rows:
        figure = go.Figure(
            go.Bar(
                x=[row[1] for row in rows],
                y=[
                    escape(str(row[0]))
                    for row in rows
                ],
                orientation="h",
                marker_color="#0866c6",
                text=[row[1] for row in rows],
                textposition="auto",
                hovertemplate=(
                    "%{y}<br>Số lượng tồn: %{x} xe"
                    "<extra></extra>"
                ),
            )
        )

        figure.update_xaxes(
            title_text="Số lượng xe",
            tickformat="d",
            rangemode="tozero",
        )

        figure.update_yaxes(
            autorange="reversed",
            automargin=True,
        )

        them_bieu_do(
            "Tồn kho theo tên xe",
            figure,
            "Số lượng tồn hiện tại, sắp xếp giảm dần.",
            chieu_cao=max(360, len(rows) * 45 + 100),
        )
    else:
        them_bieu_do("Tồn kho theo tên xe")

    # Chỉ so sánh kho khi có ít nhất hai kho.
    rows = data["ton_kho"]["theo_kho"]

    if len(rows) > 1:
        figure = None

        if any(row[1] for row in rows):
            figure = go.Figure(
                go.Bar(
                    x=[
                        escape(str(row[0]))
                        for row in rows
                    ],
                    y=[row[1] for row in rows],
                    marker_color="#0866c6",
                    text=[row[1] for row in rows],
                    textposition="auto",
                    hovertemplate=(
                        "Kho %{x}<br>Số lượng tồn: %{y} xe"
                        "<extra></extra>"
                    ),
                )
            )

            figure.update_xaxes(
                title_text="Kho",
                type="category",
            )

            figure.update_yaxes(
                title_text="Số lượng xe",
                tickformat="d",
                rangemode="tozero",
            )

        them_bieu_do(
            "Tồn kho theo kho",
            figure,
            "Chỉ hiển thị các kho thuộc phạm vi được phép xem.",
        )

    # Cơ cấu tuổi tồn hợp lệ.
    rows = data["tuoi_ton"]["nhom"][:3]
    figure = None

    if sum(row[1] for row in rows):
        figure = go.Figure(
            go.Pie(
                labels=[row[0] for row in rows],
                values=[row[1] for row in rows],
                hole=0.55,
                sort=False,
                marker={
                    "colors": [
                        "#0866c6",
                        "#f3b340",
                        "#d64545",
                    ]
                },
                textinfo="value+percent",
                hovertemplate=(
                    "%{label}<br>%{value} xe"
                    "<br>Tỷ lệ: %{percent}"
                    "<extra></extra>"
                ),
            )
        )

        figure.update_layout(
            showlegend=True,
        )

    them_bieu_do(
        "Cơ cấu tuổi tồn",
        figure,
        "Tỷ lệ tính trên các xe có ngày vào kho hợp lệ.",
    )

    # Nhập và xuất theo tháng.
    rows = data["nhap_kho"]["theo_thang"]
    figure = None

    if rows:
        labels = [row[0] for row in rows]

        figure = go.Figure()

        figure.add_trace(
            go.Bar(
                name="Nhập kho",
                x=labels,
                y=[row[1] for row in rows],
                marker_color="#0866c6",
                hovertemplate=(
                    "%{x}<br>Nhập: %{y} xe"
                    "<extra></extra>"
                ),
            )
        )

        figure.add_trace(
            go.Bar(
                name="Xuất kho",
                x=labels,
                y=[row[2] for row in rows],
                marker_color="#20a486",
                hovertemplate=(
                    "%{x}<br>Xuất: %{y} xe"
                    "<extra></extra>"
                ),
            )
        )

        figure.update_layout(barmode="group")

        figure.update_xaxes(
            title_text="Tháng",
            type="category",
            tickangle=-35,
        )

        figure.update_yaxes(
            title_text="Số lượng xe",
            tickformat="d",
            rangemode="tozero",
        )

    them_bieu_do(
        "Nhập và xuất kho theo tháng",
        figure,
        "Áp dụng bộ lọc ngày, kho và tên xe.",
    )

    # Hợp đồng theo tháng.
    rows = data["hop_dong"]["theo_thang"]
    figure = None

    if rows:
        figure = go.Figure(
            go.Scatter(
                x=[row[0] for row in rows],
                y=[row[1] for row in rows],
                mode="lines+markers",
                line={
                    "color": "#0866c6",
                    "width": 3,
                },
                marker={"size": 8},
                hovertemplate=(
                    "%{x}<br>Số hợp đồng: %{y}"
                    "<extra></extra>"
                ),
            )
        )

        figure.update_xaxes(
            title_text="Tháng ký",
            type="category",
            tickangle=-35,
        )

        figure.update_yaxes(
            title_text="Số hợp đồng",
            tickformat="d",
            rangemode="tozero",
        )

    them_bieu_do(
        "Hợp đồng ký theo tháng",
        figure,
        "Mỗi hợp đồng chỉ được đếm một lần.",
    )

    # PDI theo trạng thái.
    rows = data["pdi"]["nhom"]
    figure = None

    if rows:
        figure = go.Figure(
            go.Bar(
                x=[row[1] for row in rows],
                y=[
                    escape(str(row[0]))
                    for row in rows
                ],
                orientation="h",
                marker_color="#20a486",
                text=[row[1] for row in rows],
                textposition="auto",
                hovertemplate=(
                    "%{y}<br>Số biên bản: %{x}"
                    "<extra></extra>"
                ),
            )
        )

        figure.update_xaxes(
            title_text="Số biên bản",
            tickformat="d",
            rangemode="tozero",
        )

        figure.update_yaxes(
            autorange="reversed",
            automargin=True,
        )

    them_bieu_do(
        "Biên bản PDI theo trạng thái",
        figure,
        "Các biên bản phát sinh trong kỳ, theo trạng thái hiện tại.",
    )

    return cac_bieu_do


@login_required
@never_cache
@require_GET
def tong_quan(request):
    context = chuan_bi(
        request,
        kem_thong_ke=True,
    )

    context["page_title"] = "Thống kê và báo cáo"

    if context["hop_le"]:
        data = context["bao_cao"]
        tuoi_ton = data["tuoi_ton"]

        cac_chi_so = []

        for key, report in data.items():
            if key == "tuoi_ton":
                cac_chi_so.append({
                    "loai": key,
                    "ten": "Xe tồn trên 60 ngày",
                    "tong": tuoi_ton["ton_lau"],
                    "don_vi": "xe",
                    "ghi_chu": (
                        f"{tuoi_ton['ty_le_ton_lau']}% "
                        "tổng tồn hiện tại"
                    ),
                })
            else:
                cac_chi_so.append({
                    "loai": key,
                    "ten": report["ten"],
                    "tong": report["tong"],
                    "don_vi": report["don_vi"],
                    "ghi_chu": "",
                })

        context["cac_chi_so"] = cac_chi_so
        context["cac_bieu_do"] = tao_cac_bieu_do(data)

    return render(
        request,
        "reports/tong_quan.html",
        context,
    )


@login_required
@never_cache
@require_GET
def chi_tiet(request, loai):
    cac_loai = {
        "ton_kho",
        "tuoi_ton",
        "nhap_kho",
        "xuat_kho",
        "hop_dong",
        "pdi",
    }

    if loai not in cac_loai:
        raise Http404(
            "Loại báo cáo không tồn tại."
        )

    context = chuan_bi(request)

    context["chi_tiet"] = (
        context["bao_cao"].get(loai)
    )

    context["page_title"] = (
        context["chi_tiet"]["ten"]
        if context["hop_le"]
        else "Chi tiết báo cáo"
    )

    return render(
        request,
        "reports/chi_tiet.html",
        context,
    )


@login_required
@never_cache
@require_GET
def xuat_excel(request):
    context = chuan_bi(request)

    if not context["hop_le"]:
        context["page_title"] = "Thống kê và báo cáo"

        return render(
            request,
            "reports/tong_quan.html",
            context,
            status=400,
        )

    output = BytesIO()

    options = {
        "in_memory": True,
        "strings_to_formulas": False,
        "strings_to_urls": False,
    }

    with xlsxwriter.Workbook(
        output,
        options,
    ) as workbook:
        header = workbook.add_format({
            "bold": True,
            "bg_color": "#DCEAF7",
            "border": 1,
        })

        text = workbook.add_format({
            "text_wrap": True,
            "valign": "top",
        })

        form_data = context["form"].cleaned_data
        kho = form_data.get("kho")

        mo_ta = (
            f"Kho: {kho.pk if kho else 'Tất cả kho được phép xem'}; "
            f"Tên xe: {form_data.get('ten_xe') or 'Tất cả'}; "
            f"Từ ngày: {form_data.get('tu_ngay') or 'Không giới hạn'}; "
            f"Đến ngày: {form_data.get('den_ngay') or 'Không giới hạn'}"
        )

        thoi_diem = context["thoi_diem"].strftime(
            "%d/%m/%Y %H:%M:%S"
        )

        for key, report in context["bao_cao"].items():
            sheet = workbook.add_worksheet(key)

            sheet.write_string(
                0, 0, report["ten"], header
            )

            sheet.write_string(
                1, 0,
                "Thời điểm tổng hợp: " + thoi_diem,
            )

            sheet.write_string(
                2, 0, mo_ta
            )

            sheet.write_string(
                3, 0,
                "Tồn kho và tuổi tồn là số liệu hiện tại. "
                "Bộ lọc ngày áp dụng cho nghiệp vụ phát sinh.",
            )

            sheet.write_string(
                4, 0,
                f"Tổng: {report['tong']} {report['don_vi']}",
            )

            sheet.write_row(
                6, 0, report["cot"], header
            )

            for row_index, row in enumerate(
                report["dong"],
                start=7,
            ):
                for column, value in enumerate(row):
                    if isinstance(value, (int, float)):
                        sheet.write_number(
                            row_index,
                            column,
                            value,
                        )
                    else:
                        sheet.write_string(
                            row_index,
                            column,
                            str(value),
                            text,
                        )

            sheet.set_column(
                0,
                len(report["cot"]) - 1,
                25,
            )

            sheet.freeze_panes(7, 0)

            sheet.autofilter(
                6,
                0,
                6 + len(report["dong"]),
                len(report["cot"]) - 1,
            )

    response = HttpResponse(
        output.getvalue(),
        content_type=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        ),
    )

    response["Content-Disposition"] = (
        'attachment; filename="bao_cao_dana_ford.xlsx"'
    )

    return response
