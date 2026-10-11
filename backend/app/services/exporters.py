"""Render report tables to Excel (openpyxl) and PDF (fpdf2, with Marathi text shaping).

A report is a dict:
{
  "title": str, "subtitle": str | None,
  "period": {"start": date, "end": date, "label": str} | None,
  "summary": [{"label": str, "value": any}],
  "sections": [{"title": str, "columns": [{"key": str, "label": str}], "rows": [dict]}],
  "notes": [str],
}
"""

import io
import re
from datetime import date, datetime
from pathlib import Path

from fpdf import FPDF
from fpdf.fonts import FontFace
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from app.core.config import settings
from app.utils.dates import local_tz

FONT_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
PDF = "application/pdf"
BRAND = "7B2D8E"


def _fmt(value) -> str | int | float:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.astimezone(local_tz()).strftime("%d-%m-%Y %H:%M")
    if isinstance(value, date):
        return value.strftime("%d-%m-%Y")
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, (list, tuple)):
        return ", ".join(str(_fmt(v)) for v in value)
    if isinstance(value, dict):
        return ", ".join(f"{k}: {_fmt(v)}" for k, v in value.items())
    if isinstance(value, float):
        return round(value, 2)
    if isinstance(value, str) and _CODE.fullmatch(value):
        return value.replace("_", " ").capitalize()  # status codes like no_recent_activity
    return value


_CODE = re.compile(r"[a-z]+(_[a-z]+)+")


def _generated_line() -> str:
    return f"Generated {datetime.now(local_tz()):%d-%m-%Y %H:%M} · {settings.app_name}"


# ---------------------------------------------------------------- Excel

def to_xlsx(report: dict) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Summary"
    title_font = Font(bold=True, size=14, color=BRAND)
    head_fill = PatternFill("solid", fgColor=BRAND)
    head_font = Font(bold=True, color="FFFFFF")

    ws.append([report["title"]])
    ws["A1"].font = title_font
    if report.get("subtitle"):
        ws.append([report["subtitle"]])
    if report.get("period"):
        ws.append([f"Period: {report['period']['label']}"])
    ws.append([_generated_line()])
    ws.append([])
    if report.get("summary"):
        ws.append(["Indicator", "Value"])
        for cell in ws[ws.max_row]:
            cell.fill, cell.font = head_fill, head_font
        for item in report["summary"]:
            ws.append([item["label"], _fmt(item["value"])])
        ws.append([])
    for note in report.get("notes", []):
        ws.append([note])
    ws.column_dimensions["A"].width = 48
    ws.column_dimensions["B"].width = 22

    used = set()
    for section in report.get("sections", []):
        name = (section["title"][:28] or "Data").replace("/", "-").replace(":", "")
        base, i = name, 2
        while name in used:
            name = f"{base[:25]}-{i}"
            i += 1
        used.add(name)
        sh = wb.create_sheet(name)
        cols = section["columns"]
        sh.append([col["label"] for col in cols])
        for cell in sh[1]:
            cell.fill, cell.font = head_fill, head_font
            cell.alignment = Alignment(wrap_text=True, vertical="center")
        for row in section["rows"]:
            sh.append([_fmt(row.get(col["key"])) for col in cols])
        if section.get("totals"):
            sh.append([_fmt(section["totals"].get(col["key"], "Total" if i == 0 else "")) for i, col in enumerate(cols)])
            for cell in sh[sh.max_row]:
                cell.font = Font(bold=True)
        for idx, col in enumerate(cols, start=1):
            longest = max([len(str(col["label"]))] + [len(str(_fmt(r.get(col["key"])))) for r in section["rows"][:500]])
            sh.column_dimensions[get_column_letter(idx)].width = min(max(10, longest + 2), 60)
        sh.freeze_panes = "A2"
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ---------------------------------------------------------------- PDF

class _PDF(FPDF):
    report_title = ""

    def header(self):
        self.set_font("NotoSans", "B", 9)
        self.set_text_color(123, 45, 142)
        self.cell(0, 6, f"{settings.app_name} — {self.report_title}", new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(0, 0, 0)
        self.ln(1)

    def footer(self):
        self.set_y(-12)
        self.set_font("NotoSans", "", 7)
        self.set_text_color(120, 120, 120)
        self.cell(0, 8, f"{_generated_line()}   ·   Page {self.page_no()}/{{nb}}", align="C")


def _new_pdf(title: str, landscape: bool) -> _PDF:
    pdf = _PDF(orientation="L" if landscape else "P", unit="mm", format="A4")
    pdf.report_title = title
    pdf.add_font("NotoSans", "", str(FONT_DIR / "NotoSans-Regular.ttf"))
    pdf.add_font("NotoSans", "B", str(FONT_DIR / "NotoSans-Bold.ttf"))
    pdf.add_font("NotoDeva", "", str(FONT_DIR / "NotoSansDevanagari-Regular.ttf"))
    pdf.add_font("NotoDeva", "B", str(FONT_DIR / "NotoSansDevanagari-Bold.ttf"))
    pdf.set_fallback_fonts(["NotoDeva"])
    pdf.set_text_shaping(True)
    pdf.set_auto_page_break(True, margin=15)
    pdf.alias_nb_pages()
    pdf.add_page()
    return pdf


def _pdf_table(pdf: _PDF, columns: list[dict], rows: list[dict], totals: dict | None = None):
    pdf.set_font("NotoSans", "", 7.5 if len(columns) > 7 else 8.5)
    head = FontFace(emphasis="BOLD", color=(255, 255, 255), fill_color=(123, 45, 142))
    # Size columns to their content (clamped), instead of equal widths.
    weights = []
    for col in columns:
        longest = max([len(str(col["label"]))] + [len(str(_fmt(r.get(col["key"])))) for r in rows[:300]])
        weights.append(min(max(longest, 7), 40))
    with pdf.table(headings_style=head, line_height=5, text_align="LEFT", padding=1, col_widths=tuple(weights),
                   cell_fill_color=(246, 240, 248), cell_fill_mode="ROWS") as table:
        hr = table.row()
        for col in columns:
            hr.cell(str(col["label"]))
        for r in rows:
            tr = table.row()
            for col in columns:
                tr.cell(str(_fmt(r.get(col["key"]))))
        if totals:
            tr = table.row()
            for i, col in enumerate(columns):
                tr.cell(str(_fmt(totals.get(col["key"], "Total" if i == 0 else ""))),
                        style=FontFace(emphasis="BOLD"))


def to_pdf(report: dict) -> bytes:
    widest = max([len(s["columns"]) for s in report.get("sections", [])] + [0])
    pdf = _new_pdf(report["title"], landscape=widest > 6)
    pdf.set_font("NotoSans", "B", 15)
    pdf.multi_cell(0, 8, report["title"], new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("NotoSans", "", 9.5)
    if report.get("subtitle"):
        pdf.multi_cell(0, 5, report["subtitle"], new_x="LMARGIN", new_y="NEXT")
    if report.get("period"):
        pdf.multi_cell(0, 5, f"Period: {report['period']['label']}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)
    if report.get("summary"):
        pdf.set_font("NotoSans", "B", 11)
        pdf.cell(0, 7, "Key indicators", new_x="LMARGIN", new_y="NEXT")
        _pdf_table(pdf, [{"key": "label", "label": "Indicator"}, {"key": "value", "label": "Value"}], report["summary"])
        pdf.ln(4)
    for section in report.get("sections", []):
        if not section["rows"]:
            continue
        pdf.set_font("NotoSans", "B", 11)
        pdf.cell(0, 7, section["title"], new_x="LMARGIN", new_y="NEXT")
        rows = section["rows"]
        truncated = len(rows) > 2000
        _pdf_table(pdf, section["columns"], rows[:2000], section.get("totals"))
        if truncated:
            pdf.set_font("NotoSans", "", 8)
            pdf.cell(0, 6, f"Showing first 2000 of {len(rows)} rows. Use the Excel export for the full list.",
                     new_x="LMARGIN", new_y="NEXT")
        pdf.ln(4)
    if report.get("notes"):
        pdf.set_font("NotoSans", "B", 10)
        pdf.cell(0, 6, "Notes", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("NotoSans", "", 8.5)
        for note in report["notes"]:
            pdf.multi_cell(0, 5, f"• {note}", new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())


def render(report: dict, fmt: str) -> tuple[bytes, str, str]:
    if fmt == "xlsx":
        return to_xlsx(report), XLSX, "xlsx"
    return to_pdf(report), PDF, "pdf"


# ---------------------------------------------------------------- event report

def event_report(ev: dict, fmt: str) -> tuple[bytes, str, str]:
    """ev is the serialized output of GET /events/{id}."""
    att = ev.get("attendance_summary", {})
    report_part = ev.get("report") or {}
    summary = [
        {"label": "Event", "value": ev["title"]},
        {"label": "Type", "value": ev["event_type"]},
        {"label": "Village", "value": (ev.get("village") or {}).get("name")},
        {"label": "Location", "value": ev.get("location_name")},
        {"label": "Date", "value": ev["local_date"]},
        {"label": "Time", "value": f"{ev.get('start_time') or ''} - {ev.get('end_time') or ''}"},
        {"label": "Status", "value": ev["display_status"]},
        {"label": "Responsible volunteer", "value": (ev.get("responsible_volunteer") or {}).get("name")},
        {"label": "Objective", "value": ev.get("objective")},
        {"label": "Expected participants", "value": att.get("expected")},
        {"label": "Girls present", "value": att.get("girls_present")},
        {"label": "Other participants", "value": att.get("other_participants")},
        {"label": "Total expenditure (₹)", "value": (ev.get("expenditure") or {}).get("total")},
        {"label": "Photos / media", "value": len(ev.get("media") or [])},
    ]
    sections = [
        {"title": "Post-event report", "columns": [{"key": "k", "label": "Item"}, {"key": "v", "label": "Details"}],
         "rows": [{"k": label, "v": report_part.get(key)} for key, label in (
             ("activities_conducted", "Activities conducted"), ("outcomes", "Outcomes"),
             ("observations", "Observations"), ("issues", "Issues"), ("follow_up_actions", "Follow-up actions"))]},
        {"title": "Attendance", "columns": [{"key": "girl_code", "label": "Girl ID"}, {"key": "name", "label": "Name"},
                                            {"key": "present", "label": "Present"}],
         "rows": ev.get("attendance") or []},
        {"title": "Pre-event checklist", "columns": [{"key": "item", "label": "Item"}, {"key": "done", "label": "Done"},
                                                     {"key": "notes", "label": "Notes"}],
         "rows": ev.get("pre_checklist") or []},
        {"title": "Post-event checklist", "columns": [{"key": "item", "label": "Item"}, {"key": "done", "label": "Done"},
                                                      {"key": "notes", "label": "Notes"}],
         "rows": ev.get("post_checklist") or []},
        {"title": "Expenditure", "columns": [{"key": "item", "label": "Item"}, {"key": "category", "label": "Category"},
                                             {"key": "quantity", "label": "Qty"}, {"key": "unit_cost", "label": "Unit cost"},
                                             {"key": "amount", "label": "Amount"}],
         "rows": (ev.get("expenditure") or {}).get("items") or [],
         "totals": {"amount": (ev.get("expenditure") or {}).get("total")}},
    ]
    report = {"title": f"Event Report: {ev['title']}", "subtitle": None, "period": None,
              "summary": summary, "sections": sections, "notes": []}
    return render(report, fmt)
