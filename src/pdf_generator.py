from datetime import datetime
from html import escape
from pathlib import Path
import re

from fpdf import FPDF
from fpdf.fonts import FontFace
from src.utils import format_event_date

GFW_LOGO_URL = "https://www.globalfundforwomen.org/wp-content/themes/gffw-theme/img/logo-footer.svg"
BRAND_PRIMARY = (65, 19, 66)
BRAND_ACCENT = (210, 40, 244)
BRAND_MUTED = (110, 110, 110)
PAGE_MARGIN = 16


class PDFReport(FPDF):
    def header(self):
        self.set_draw_color(*BRAND_PRIMARY)
        self.set_text_color(*BRAND_PRIMARY)

        try:
            self.image(GFW_LOGO_URL, x=PAGE_MARGIN, y=10, w=34)
        except Exception:
            self.set_font("Arial", "B", 12)
            self.cell(0, 8, "Global Fund for Women", align="L")

        self.set_font("Arial", "B", 18)
        self.set_xy(PAGE_MARGIN, 24)
        self.cell(0, 8, "Event Source Reporter", align="L")

        self.set_font("Arial", "", 9)
        self.set_text_color(*BRAND_MUTED)
        self.set_xy(PAGE_MARGIN, 32)
        self.cell(0, 5, "Analytical report generated from uploaded event data.", align="L")

        self.set_draw_color(*BRAND_ACCENT)
        self.line(PAGE_MARGIN, 40, self.w - PAGE_MARGIN, 40)
        self.ln(24)

    def footer(self):
        self.set_y(-14)
        self.set_draw_color(220, 220, 220)
        self.line(PAGE_MARGIN, self.get_y() - 2, self.w - PAGE_MARGIN, self.get_y() - 2)
        self.set_font("Arial", "I", 8)
        self.set_text_color(*BRAND_MUTED)
        self.cell(0, 8, f"Generated {format_event_date(datetime.now())} | Page {self.page_no()}", align="C")


def safe_text(text: str) -> str:
    return str(text).encode("latin-1", "replace").decode("latin-1")


def format_inline_markdown(text: str) -> str:
    escaped = escape(safe_text(text))
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escaped)
    escaped = re.sub(r"`(.+?)`", r"<font face='Courier'>\1</font>", escaped)
    return escaped


def markdown_table_to_html(table_lines: list[str]) -> str:
    rows = []
    for line in table_lines:
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [format_inline_markdown(cell.strip()) for cell in stripped.strip("|").split("|")]
        rows.append(cells)

    if len(rows) < 2:
        return ""

    header = rows[0]
    body = [
        row for row in rows[1:]
        if not all(set(cell.replace(" ", "")) <= {"-", ":"} for cell in row)
    ]

    html_rows = [
        "<table border='1' width='100%' cellpadding='4'>",
        "<thead><tr>" + "".join(f"<th>{cell}</th>" for cell in header) + "</tr></thead>",
        "<tbody>",
    ]
    for row in body:
        padded = row + [""] * (len(header) - len(row))
        html_rows.append("<tr>" + "".join(f"<td>{cell}</td>" for cell in padded[: len(header)]) + "</tr>")
    html_rows.append("</tbody></table>")
    return "".join(html_rows)


def markdown_to_html(markdown_text: str) -> str:
    lines = safe_text(markdown_text).splitlines()
    html_parts = []
    paragraph_buffer = []
    list_buffer = []
    table_buffer = []

    def flush_paragraph():
        nonlocal paragraph_buffer
        if paragraph_buffer:
            paragraph = " ".join(part.strip() for part in paragraph_buffer if part.strip())
            if paragraph:
                html_parts.append(f"<p>{format_inline_markdown(paragraph)}</p>")
            paragraph_buffer = []

    def flush_list():
        nonlocal list_buffer
        if list_buffer:
            html_parts.append("<ul>" + "".join(f"<li>{format_inline_markdown(item)}</li>" for item in list_buffer) + "</ul>")
            list_buffer = []

    def flush_table():
        nonlocal table_buffer
        if table_buffer:
            table_html = markdown_table_to_html(table_buffer)
            if table_html:
                html_parts.append(table_html)
            table_buffer = []

    for raw_line in lines:
        line = raw_line.rstrip()
        stripped = line.strip()

        if stripped.startswith("|") and stripped.endswith("|"):
            flush_paragraph()
            flush_list()
            table_buffer.append(stripped)
            continue
        flush_table()

        if not stripped:
            flush_paragraph()
            flush_list()
            continue

        if stripped.startswith("### "):
            flush_paragraph()
            flush_list()
            html_parts.append(f"<h3>{format_inline_markdown(stripped[4:])}</h3>")
            continue
        if stripped.startswith("## "):
            flush_paragraph()
            flush_list()
            html_parts.append(f"<h2>{format_inline_markdown(stripped[3:])}</h2>")
            continue
        if stripped.startswith("# "):
            flush_paragraph()
            flush_list()
            html_parts.append(f"<h1>{format_inline_markdown(stripped[2:])}</h1>")
            continue
        if stripped.startswith("- "):
            flush_paragraph()
            list_buffer.append(stripped[2:])
            continue

        paragraph_buffer.append(stripped)

    flush_table()
    flush_paragraph()
    flush_list()
    return "".join(html_parts)


def build_pdf(country: str, report_text: str) -> PDFReport:
    pdf = PDFReport()
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.set_margins(PAGE_MARGIN, 12, PAGE_MARGIN)
    pdf.add_page()

    pdf.set_text_color(*BRAND_PRIMARY)
    pdf.set_font("Arial", "B", 15)
    pdf.cell(0, 8, safe_text(f"Analysis for: {country}"), new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("Arial", "", 10)
    pdf.set_text_color(*BRAND_MUTED)
    pdf.cell(0, 6, safe_text(f"Generated on: {format_event_date(datetime.now())}"), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    html_text = markdown_to_html(report_text)
    pdf.write_html(
        html_text,
        tag_styles={
            "h1": FontFace(family="Arial", emphasis="B", size_pt=16, color=BRAND_PRIMARY),
            "h2": FontFace(family="Arial", emphasis="B", size_pt=13, color=BRAND_PRIMARY),
            "h3": FontFace(family="Arial", emphasis="B", size_pt=11, color=BRAND_ACCENT),
            "p": FontFace(family="Arial", size_pt=10.5, color=(30, 30, 30)),
            "li": FontFace(family="Arial", size_pt=10.5, color=(30, 30, 30)),
        },
    )
    return pdf


def generate_pdf_report(country: str, report_text: str, output_path: str):
    pdf = build_pdf(country, report_text)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(output_path)


def generate_pdf_bytes(country: str, report_text: str) -> bytes:
    pdf = build_pdf(country, report_text)
    raw_output = pdf.output(dest="S")
    return bytes(raw_output) if isinstance(raw_output, (bytes, bytearray)) else str(raw_output).encode("latin-1")
