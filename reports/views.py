from html import escape
from io import BytesIO

import plotly.graph_objects as go
import xlsxwriter

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404, HttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from alerts.utils import cap_nhat_tat_ca_canh_bao

from .forms import BoLocBaoCaoForm
from .utils import (
    QUYEN_BAO_CAO,
    QUYEN_XEM_TUNG_BAO_CAO,
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

    data = {}
    kho_da_chon = None

    if hop_le:
        try:
            if request.user.has_perm(QUYEN_XEM_TUNG_BAO_CAO["canh_bao"]):
                cap_nhat_tat_ca_canh_bao()

            data = tao_bao_cao(
                kho,
                form.cleaned_data,
                kem_thong_ke=kem_thong_ke,
                user=request.user,
            )
        except ValidationError as loi:
            form.add_error(None, loi)
            hop_le = False
        else:
            kho_da_chon = form.cleaned_data.get("kho")

    context = {
        "form": form,
        "bao_cao": data,
        "hop_le": hop_le,
        "tham_so": request.GET.urlencode(),
        "thoi_diem": timezone.localtime(),
        "kho_da_chon": kho_da_chon,
    }

    return context


def them_bieu_do(
    cac_bieu_do,
    tieu_de,
    figure=None,
    mo_ta="",
    chieu_cao=360,
):
    da_nap_plotly = False

    for bieu_do in cac_bieu_do:
        if bieu_do["html"] is not None:
            da_nap_plotly = True
            break

    html = None

    if figure is not None:
        figure.update_layout(
            template="plotly_white",
            autosize=True,
            height=chieu_cao,
            font={
                "family": "Montserrat, sans-serif",
                "size": 11,
                "color": "#243b53",
            },
            margin={
                "l": 30,
                "r": 20,
                "t": 60,
                "b": 50,
            },
            legend={
                "orientation": "h",
                "yanchor": "bottom",
                "y": 1.02,
                "xanchor": "center",
                "x": 0.5,
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

    cac_bieu_do.append({
        "tieu_de": tieu_de,
        "html": html,
        "mo_ta": mo_ta,
    })


def them_bieu_do_bo_sung(cac_bieu_do, data):
    mau_sac = [
        "#0866c6", "#23825c", "#f3b340", "#e12d39", "#829ab1",
        "#627d98", "#9f7aea", "#ed64a6", "#38b2ac", "#dd6b20"
    ]

    for key in ["dat_xe", "luu_chuyen"]:
        if key not in data:
            continue

        bao_cao = data[key]
        thong_ke = bao_cao["theo_thang"]
        figure = None

        if thong_ke["thang"]:
            figure = go.Figure()

            # Lọc chỉ hiển thị các trạng thái có số lượng > 0 trong kỳ để chú thích ngắn gọn, không che biểu đồ
            nhom_co_du_lieu = [nhom for nhom in thong_ke["cac_nhom"] if any(v > 0 for v in nhom.get("so_luong", []))]
            nhom_ve = nhom_co_du_lieu if nhom_co_du_lieu else thong_ke["cac_nhom"]

            for vi_tri, nhom in enumerate(nhom_ve):
                figure.add_trace(go.Bar(
                    name=nhom["ten"],
                    x=thong_ke["thang"],
                    y=nhom["so_luong"],
                    marker_color=mau_sac[vi_tri % len(mau_sac)],
                ))

            figure.update_layout(barmode="stack")
            figure.update_xaxes(title_text="Tháng lập", type="category")
            figure.update_yaxes(
                title_text=bao_cao["don_vi"].capitalize(),
                tickformat="d", rangemode="tozero",
            )

        them_bieu_do(
            cac_bieu_do, bao_cao["ten"], figure,
            "Đếm theo ngày lập và trạng thái hiện tại.",
        )

    if "canh_bao" in data:
        bao_cao = data["canh_bao"]

        for key, tieu_de in [
            ("theo_loai", "Cảnh báo theo loại"),
            ("theo_xu_ly", "Cảnh báo theo trạng thái xử lý"),
        ]:
            figure = None

            if bao_cao["tong"]:
                figure = go.Figure(go.Bar(
                    x=list(bao_cao[key].keys()),
                    y=list(bao_cao[key].values()),
                    marker_color="#0866c6",
                ))
                figure.update_yaxes(
                    title_text="Số cảnh báo",
                    tickformat="d", rangemode="tozero",
                )
                figure.update_xaxes(type="category")

            them_bieu_do(
                cac_bieu_do, tieu_de, figure,
                "Mỗi mã cảnh báo chỉ được đếm một lần. "
                "Trạng thái xử lý khác với hiệu lực cảnh báo.",
            )


def tao_cac_bieu_do(data):
    cac_bieu_do = []

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
            cac_bieu_do,
            "Tồn kho theo tên xe",
            figure,
            "Số lượng tồn hiện tại, sắp xếp giảm dần.",
            chieu_cao=max(360, len(rows) * 18 + 70),
        )
    else:
        them_bieu_do(cac_bieu_do, "Tồn kho theo tên xe")

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
            cac_bieu_do,
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
        cac_bieu_do,
        "Cơ cấu tuổi tồn",
        figure,
        "Tỷ lệ tính trên các xe có ngày vào kho hợp lệ.",
    )

    # Nhập và xuất theo tháng, tách màu theo trạng thái.
    rows = data["nhap_kho"]["theo_thang"]
    figure = None

    if rows:
        cac_thang = []
        cac_loai = []
        so_nhap = []
        so_cho_duyet = []
        so_da_duyet = []

        for row in rows:
            cac_thang.extend([row[0], row[0]])
            cac_loai.extend(["Nhập", "Xuất"])
            so_nhap.extend([row[1], 0])
            so_cho_duyet.extend([row[2], row[4]])
            so_da_duyet.extend([row[3], row[5]])

        figure = go.Figure()
        cac_nhom = [
            ("Nháp", so_nhap, "#829ab1"),
            ("Chờ duyệt", so_cho_duyet, "#f3b340"),
            ("Đã duyệt", so_da_duyet, "#0866c6"),
        ]

        for ten_nhom, so_luong, mau in cac_nhom:
            figure.add_trace(go.Bar(
                name=ten_nhom,
                x=[cac_thang, cac_loai],
                y=so_luong,
                marker_color=mau,
                hovertemplate=(
                    ten_nhom + ": %{y} phiếu"
                    "<extra></extra>"
                ),
            ))

        figure.update_layout(barmode="stack")
        figure.update_xaxes(
            title_text="Tháng và loại phiếu",
            type="multicategory",
        )
        figure.update_yaxes(
            title_text="Số phiếu",
            tickformat="d",
            rangemode="tozero",
        )

    them_bieu_do(
        cac_bieu_do,
        "Phiếu nhập và xuất theo tháng",
        figure,
        "Theo trạng thái hiện tại. Nhập theo ngày nhập trên phiếu; "
        "xuất chờ duyệt theo ngày lập, đã duyệt theo ngày xuất.",
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
        cac_bieu_do,
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
        cac_bieu_do,
        "Biên bản PDI theo trạng thái",
        figure,
        "Các biên bản phát sinh trong kỳ, theo trạng thái hiện tại.",
    )

    them_bieu_do_bo_sung(cac_bieu_do, data)

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
                    "ghi_chu": report.get("ghi_chu", ""),
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
        "dat_xe",
        "luu_chuyen",
        "canh_bao",
    }

    if loai not in cac_loai:
        raise Http404(
            "Loại báo cáo không tồn tại."
        )

    quyen = QUYEN_XEM_TUNG_BAO_CAO.get(loai)
    if quyen and not request.user.has_perm(quyen):
        raise PermissionDenied("Bạn chưa được cấp quyền xem báo cáo này.")

    context = chuan_bi(request)
    context["loai_bao_cao"] = loai

    context["chi_tiet"] = (
        context["bao_cao"].get(loai)
    )

    if context["hop_le"]:
        context["page_title"] = context["chi_tiet"]["ten"]
    else:
        context["page_title"] = "Chi tiết báo cáo"

    return render(
        request,
        "reports/chi_tiet.html",
        context,
    )


@login_required
@never_cache
@require_GET
def xuat_excel(request):
    loai = request.GET.get("loai")
    quyen = QUYEN_XEM_TUNG_BAO_CAO.get(loai)
    if quyen and not request.user.has_perm(quyen):
        raise PermissionDenied("Bạn chưa được cấp quyền xem báo cáo này.")

    context = chuan_bi(request)

    if not context["hop_le"]:
        context["page_title"] = "Thống kê và báo cáo"

        return render(
            request,
            "reports/tong_quan.html",
            context,
            status=400,
        )

    cac_bao_cao = context["bao_cao"]
    loai = request.GET.get("loai")

    if loai is not None:
        if loai not in cac_bao_cao:
            raise Http404("Loại báo cáo không tồn tại.")

        cac_bao_cao = {
            loai: cac_bao_cao[loai],
        }

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

        for key, report in cac_bao_cao.items():
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

            tong_ket = f"Tổng: {report['tong']} {report['don_vi']}"
            if report.get("ghi_chu"):
                tong_ket += "; " + report["ghi_chu"]

            sheet.write_string(4, 0, tong_ket)

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
