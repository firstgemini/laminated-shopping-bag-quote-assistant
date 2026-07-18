from __future__ import annotations

from html import escape
from io import BytesIO
from pathlib import Path
import os

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from quote_app.calculations import CUTTING_COST_CNY, SEWING_COST_CNY
from quote_app.quotation import QuotationReport


FT_PAPER = colors.HexColor("#FFF1E5")
FT_INK = colors.HexColor("#33302E")
FT_CLARET = colors.HexColor("#990F3D")
FT_TEAL = colors.HexColor("#0D7680")
FT_BORDER = colors.HexColor("#C9BEB5")
FT_MUTED = colors.HexColor("#6F6863")
FT_WHITE = colors.HexColor("#FFFDFC")

MATERIAL_EN = {
    "PET材料（丽新布覆膜）": "Laminated PET (Lixin) Material",
    "无纺布覆膜二等材料": "Grade B Laminated Non-woven Material",
    "PP编织覆膜二等材料": "Grade B Laminated Woven PP Material",
    "无纺布覆膜一等材料": "Grade A Laminated Non-woven Material",
    "编织双面OPP覆膜材料": "Double-sided OPP Laminated Woven PP",
    "无纺布双面OPP覆膜材料": "Double-sided OPP Laminated Non-woven Material",
}
HANDLE_EN = {
    "本料手提": "Self-material handles",
    "PP织带": "PP webbing handles",
}
WEBBING_STYLE_EN = {
    "普通花纹": "Regular pattern",
    "普通花纹（加厚）": "Heavy regular pattern",
    "平纹": "Plain weave",
    "美国纹": "American weave",
    "特殊织带（手填价格）": "Special webbing handles",
}


class ReportGenerationError(ValueError):
    """Raised when a report cannot be generated without exposing bad data."""


def _find_cjk_fonts() -> tuple[str, str]:
    custom = os.environ.get("QUOTE_CJK_FONT")
    regular_candidates = [
        custom,
        r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\simsun.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJKsc-Regular.otf",
    ]
    bold_candidates = [
        os.environ.get("QUOTE_CJK_BOLD_FONT"),
        r"C:\Windows\Fonts\msyhbd.ttc",
        r"C:\Windows\Fonts\simhei.ttf",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJKsc-Bold.otf",
    ]

    regular = next(
        (path for path in regular_candidates if path and Path(path).exists()), None
    )
    bold = next(
        (path for path in bold_candidates if path and Path(path).exists()), None
    )
    if not regular:
        raise ReportGenerationError(
            "未找到中文PDF字体。请配置QUOTE_CJK_FONT或安装Noto Sans CJK。"
        )
    return regular, bold or regular


def _register_cjk_fonts() -> tuple[str, str]:
    regular_name = "BagQuoteCJK"
    bold_name = "BagQuoteCJKBold"
    if regular_name not in pdfmetrics.getRegisteredFontNames():
        regular_path, bold_path = _find_cjk_fonts()
        pdfmetrics.registerFont(
            TTFont(regular_name, regular_path, subfontIndex=0)
        )
        pdfmetrics.registerFont(TTFont(bold_name, bold_path, subfontIndex=0))
    return regular_name, bold_name


def _paragraph_text(value: object) -> str:
    return escape(str(value)).replace("\n", "<br/>")


def _styles(*, cjk: bool) -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    if cjk:
        body_font, bold_font = _register_cjk_fonts()
    else:
        body_font, bold_font = "Helvetica", "Helvetica-Bold"
    return {
        "title": ParagraphStyle(
            "ReportTitle",
            parent=base["Title"],
            fontName=bold_font if cjk else "Times-Bold",
            fontSize=20,
            leading=24,
            textColor=FT_INK,
            alignment=TA_LEFT,
            spaceAfter=4 * mm,
        ),
        "subtitle": ParagraphStyle(
            "ReportSubtitle",
            parent=base["BodyText"],
            fontName=body_font,
            fontSize=8.5,
            leading=11,
            textColor=FT_MUTED,
            spaceAfter=4 * mm,
        ),
        "heading": ParagraphStyle(
            "ReportHeading",
            parent=base["Heading2"],
            fontName=bold_font,
            fontSize=11.5,
            leading=14,
            textColor=FT_CLARET,
            spaceBefore=3 * mm,
            spaceAfter=2 * mm,
        ),
        "body": ParagraphStyle(
            "ReportBody",
            parent=base["BodyText"],
            fontName=body_font,
            fontSize=8.5,
            leading=12,
            textColor=FT_INK,
        ),
        "small": ParagraphStyle(
            "ReportSmall",
            parent=base["BodyText"],
            fontName=body_font,
            fontSize=7.5,
            leading=9.5,
            textColor=FT_MUTED,
        ),
        "table": ParagraphStyle(
            "ReportTable",
            parent=base["BodyText"],
            fontName=body_font,
            fontSize=7.5,
            leading=9,
            textColor=FT_INK,
        ),
        "table_header": ParagraphStyle(
            "ReportTableHeader",
            parent=base["BodyText"],
            fontName=bold_font,
            fontSize=7.5,
            leading=9,
            textColor=FT_WHITE,
        ),
    }


def _p(value: object, style: ParagraphStyle) -> Paragraph:
    return Paragraph(_paragraph_text(value), style)


def _table(
    rows: list[list[object]],
    *,
    styles: dict[str, ParagraphStyle],
    widths: list[float] | None = None,
    repeat_rows: int = 1,
) -> Table:
    rendered: list[list[Paragraph]] = []
    for row_index, row in enumerate(rows):
        cell_style = styles["table_header"] if row_index == 0 else styles["table"]
        rendered.append([_p(value, cell_style) for value in row])
    table = Table(rendered, colWidths=widths, repeatRows=repeat_rows, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), FT_CLARET),
                ("BACKGROUND", (0, 1), (-1, -1), FT_WHITE),
                ("GRID", (0, 0), (-1, -1), 0.35, FT_BORDER),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [FT_WHITE, FT_PAPER]),
            ]
        )
    )
    return table


def _page(canvas, document) -> None:
    canvas.saveState()
    width, height = document.pagesize
    canvas.setFillColor(FT_PAPER)
    canvas.rect(0, 0, width, height, stroke=0, fill=1)
    canvas.setStrokeColor(FT_TEAL)
    canvas.setLineWidth(1.1)
    canvas.line(document.leftMargin, 12 * mm, width - document.rightMargin, 12 * mm)
    canvas.setFillColor(FT_MUTED)
    canvas.setFont("Helvetica", 7)
    canvas.drawString(document.leftMargin, 7.5 * mm, "Generated by Bag Quote Assistant")
    canvas.drawRightString(
        width - document.rightMargin, 7.5 * mm, f"Page {document.page}"
    )
    canvas.restoreState()


def _document(buffer: BytesIO, *, title: str) -> SimpleDocTemplate:
    return SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        title=title,
        leftMargin=14 * mm,
        rightMargin=14 * mm,
        topMargin=13 * mm,
        bottomMargin=17 * mm,
    )


def _spec_rows(report: QuotationReport, *, english: bool) -> list[list[object]]:
    draft = report.snapshot.draft
    if english:
        material = MATERIAL_EN.get(draft.material)
        handle = HANDLE_EN.get(draft.handle_type)
        if not material or not handle:
            raise ReportGenerationError("存在未配置英文名称的材料或手提类型。")
        handle_detail = handle
        if draft.webbing_style:
            style = WEBBING_STYLE_EN.get(draft.webbing_style)
            if not style:
                raise ReportGenerationError("存在未配置英文名称的织带样式。")
            handle_detail = (
                style
                if draft.webbing_style == "特殊织带（手填价格）"
                else f"{handle} - {style}"
            )
        return [
            ["Item", "Specification"],
            ["Bag size", f"{draft.width_cm:g} x {draft.height_cm:g} x {draft.gusset_cm:g} cm (W x H x G)"],
            ["Body material", f"{material}, {draft.gsm_label.replace('克', ' gsm')}"],
            ["Handles", handle_detail],
            ["Handle size", f"{draft.handle_width_cm:g} cm wide x {draft.handle_length_cm:g} cm long, 2 pcs/bag"],
            ["Top finish", "3 cm inward fold"],
        ]
    return [
        ["项目", "规格"],
        ["袋子尺寸", f"{draft.width_cm:g} x {draft.height_cm:g} x {draft.gusset_cm:g} cm（宽 x 高 x 侧）"],
        ["袋身材料", f"{draft.material} / {draft.gsm_label}"],
        ["手提", f"{draft.handle_type}{' / ' + draft.webbing_style if draft.webbing_style else ''}"],
        ["手提尺寸", f"宽{draft.handle_width_cm:g}cm x 单条长{draft.handle_length_cm:g}cm / 2条每袋"],
        ["袋口", "内折3cm"],
    ]


def generate_internal_pdf(report: QuotationReport) -> bytes:
    styles = _styles(cjk=True)
    buffer = BytesIO()
    document = _document(buffer, title="内部核价单")
    draft = report.snapshot.draft
    first = report.tiers[0].result
    date_text = report.snapshot.submitted_at.strftime("%Y-%m-%d %H:%M")

    story: list[object] = [
        _p("开口包内部核价单", styles["title"]),
        _p(
            f"报价日期：{date_text}　汇率：{draft.exchange_rate:g}　价格库版本：{draft.database_fingerprint[:12]}",
            styles["subtitle"],
        ),
    ]
    if draft.customer_info:
        story.extend(
            [
                _p("客户信息", styles["heading"]),
                _p(draft.customer_info, styles["body"]),
            ]
        )

    story.extend(
        [
            _p("产品规格", styles["heading"]),
            _table(_spec_rows(report, english=False), styles=styles, widths=[38 * mm, 220 * mm]),
            _p("每只基础成本", styles["heading"]),
        ]
    )
    cost_rows: list[list[object]] = [
        ["项目", "人民币/个"],
        ["袋身面料", f"¥ {first.body_cost_cny:.4f}"],
        ["包边", f"¥ {first.binding_cost_cny:.4f}"],
        ["手提", f"¥ {first.handle_cost_cny:.4f}"],
        ["车缝", f"¥ {SEWING_COST_CNY:.4f}"],
        ["分切", f"¥ {CUTTING_COST_CNY:.4f}"],
        ["纸箱分摊", f"¥ {first.carton_share_cny:.4f}"],
    ]
    for addon in draft.addons:
        cost_rows.append([f"附加：{addon.internal_name}", f"¥ {addon.unit_cost_cny:.4f}"])
    story.append(_table(cost_rows, styles=styles, widths=[90 * mm, 50 * mm]))

    tier_rows: list[list[object]] = [
        ["数量", "损耗/个", "利润/个", "EXW CNY", "EXW USD", "本地总费", "FOB CNY", "FOB USD", "运输"],
    ]
    for tier in report.tiers:
        result = tier.result
        tier_rows.append(
            [
                f"{tier.quantity:,}",
                f"¥ {result.loss_cny:.3f}",
                f"¥ {result.profit_cny:.3f}",
                f"¥ {result.exw_cny:.3f}",
                f"$ {result.exw_usd:.3f}",
                f"¥ {result.freight.total_cost_cny:,.0f}",
                f"¥ {result.fob_cny:.3f}",
                f"$ {result.fob_usd:.3f}",
                result.freight.mode,
            ]
        )
    story.extend(
        [
            _p("数量阶梯报价", styles["heading"]),
            _table(tier_rows, styles=styles),
            _p(
                f"单色版费：$ {first.plate_fee_usd_per_color:.2f} / color",
                styles["body"],
            ),
            _p("预计装箱数据", styles["title"]),
        ]
    )
    packing_rows: list[list[object]] = [
        ["数量", "箱数", "装箱数", "外箱尺寸 (cm)", "NW/箱", "GW/箱", "总NW", "总GW", "总CBM", "运输"],
    ]
    for tier in report.tiers:
        result = tier.result
        packing_rows.append(
            [
                f"{tier.quantity:,}",
                f"{result.carton_count:,}",
                "100个/箱",
                f"{result.carton_length_cm:g} x {result.carton_width_cm:g} x {result.carton_height_cm:g}",
                f"{result.carton_nw_kg:.2f} kg",
                f"{result.carton_gw_kg:.2f} kg",
                f"{result.total_nw_kg:,.2f} kg",
                f"{result.total_gw_kg:,.2f} kg",
                f"{result.total_cbm:.3f}",
                result.freight.mode,
            ]
        )
    story.extend(
        [
            _table(packing_rows, styles=styles),
            Spacer(1, 3 * mm),
            _p("预计装箱数据用于询价和FOB费用估算，最终以大货实测箱规为准。", styles["small"]),
            _p(
                f"包边路径：4H + 2G + 12cm；本规格包边长度 {first.binding_length_cm:g}cm。",
                styles["small"],
            ),
        ]
    )
    document.build(story, onFirstPage=_page, onLaterPages=_page)
    return buffer.getvalue()


def generate_customer_pdf(report: QuotationReport) -> bytes:
    styles = _styles(cjk=False)
    buffer = BytesIO()
    document = _document(buffer, title="Customer Quotation")
    draft = report.snapshot.draft
    first = report.tiers[0].result
    title = draft.company_name_en or "Laminated Shopping Bag Quotation"
    date_text = report.snapshot.submitted_at.strftime("%d %B %Y")

    story: list[object] = [
        _p(title, styles["title"]),
        _p(f"Quotation date: {date_text}", styles["subtitle"]),
    ]
    if draft.customer_info:
        story.extend(
            [
                _p("Customer Information", styles["heading"]),
                _p(draft.customer_info, styles["body"]),
            ]
        )
    story.extend(
        [
            _p("Product Specifications", styles["heading"]),
            _table(_spec_rows(report, english=True), styles=styles, widths=[48 * mm, 210 * mm]),
        ]
    )

    english_addons = [item.english_name for item in draft.addons if item.english_name]
    if english_addons:
        story.extend(
            [
                _p("Additional Options", styles["heading"]),
                _p("; ".join(english_addons), styles["body"]),
            ]
        )

    tier_rows: list[list[object]] = [
        ["Quantity", "EXW USD/pc", "FOB Ningbo USD/pc", "Cartons", "Total CBM"],
    ]
    for tier in report.tiers:
        result = tier.result
        tier_rows.append(
            [
                f"{tier.quantity:,} pcs",
                f"$ {result.exw_usd:.3f}",
                f"$ {result.fob_usd:.3f}",
                f"{result.carton_count:,}",
                f"{result.total_cbm:.3f}",
            ]
        )
    story.extend(
        [
            _p("Quantity Price Schedule", styles["heading"]),
            _table(tier_rows, styles=styles, widths=[48 * mm, 52 * mm, 62 * mm, 42 * mm, 48 * mm]),
            _p("Plate Charge", styles["heading"]),
            _p(
                f"USD {first.plate_fee_usd_per_color:.2f} per color",
                styles["body"],
            ),
        ]
    )
    story.extend(
        [
            PageBreak(),
            _p("Estimated Packing Information", styles["heading"]),
        ]
    )
    packing_rows: list[list[object]] = [
        ["Quantity", "Packing", "Carton Size (cm)", "NW/Carton", "GW/Carton", "Total CBM", "Suggested Mode"],
    ]
    for tier in report.tiers:
        result = tier.result
        packing_rows.append(
            [
                f"{tier.quantity:,}",
                "100 pcs/carton",
                f"{result.carton_length_cm:g} x {result.carton_width_cm:g} x {result.carton_height_cm:g}",
                f"{result.carton_nw_kg:.2f} kg",
                f"{result.carton_gw_kg:.2f} kg",
                f"{result.total_cbm:.3f}",
                result.freight.mode.replace("拼箱", ""),
            ]
        )
    story.extend(
        [
            _table(packing_rows, styles=styles),
            Spacer(1, 3 * mm),
            _p(
                "Packing information is estimated for quotation purposes. Final figures are subject to actual bulk packing.",
                styles["small"],
            ),
        ]
    )
    if draft.supplier_contact_en:
        story.extend(
            [
                _p("Supplier Contact", styles["heading"]),
                _p(draft.supplier_contact_en, styles["small"]),
            ]
        )
    document.build(story, onFirstPage=_page, onLaterPages=_page)
    return buffer.getvalue()
