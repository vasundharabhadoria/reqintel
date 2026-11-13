"""
Rendering of project reports (PDF, XLSX, HTML).

This module is pure: it takes already-fetched data and returns file bytes.
It never touches the database, storage or the network, so every format can
be tested in isolation.

Safety rules enforced here:
  * all text comes from uploaded documents and AI output, so it is treated
    as untrusted: HTML is escaped, PDF paragraph markup is escaped, and a
    leading "=" can never become an Excel formula;
  * control characters (e.g. the form-feed that PDF extraction produces)
    are stripped, because they crash openpyxl / reportlab;
  * nothing is invented: a requirement without an analysis is shown as
    "Not analysed", never with a made-up score.
"""

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html import escape as html_escape
from io import BytesIO
from xml.sax.saxutils import escape as xml_escape

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from services.dashboard_service import (
    QUALITY_DIMENSIONS,
    score_quality_assessment,
)

NOT_ANALYSED = "Not analysed"
NOT_AVAILABLE = "Not available"
REQUIREMENT_STATUSES = ("pending", "approved", "rejected", "deprecated")

_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_EXCEL_CELL_LIMIT = 32000
_PRIMARY = "#1c64f2"


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------


def clean(value) -> str:
    """Return a safe plain string: no control characters, no lone surrogates."""

    if value is None:
        return ""

    text = str(value)
    text = _CONTROL_CHARS.sub("", text)
    return text.encode("utf-8", "replace").decode("utf-8")


def format_dt(value) -> str:
    if not isinstance(value, datetime):
        return "—"

    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)

    return value.astimezone(timezone.utc).strftime("%d %b %Y, %H:%M UTC")


def label(value) -> str:
    text = clean(value).replace("_", " ").strip()
    return text[:1].upper() + text[1:] if text else "—"


def parse_issues(raw) -> list[str]:
    """`ai_analysis.recommendations` holds a JSON list of strings."""

    if raw is None or not str(raw).strip():
        return []

    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return [clean(raw)]

    if isinstance(data, list):
        return [clean(item) for item in data if str(item).strip()]

    if isinstance(data, str):
        return [clean(data)] if data.strip() else []

    return [clean(raw)]


def _as_assessment(value):
    if value is None or isinstance(value, dict):
        return value

    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Report data
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReportRequirement:
    code: str
    title: str | None
    status: str
    version_number: int | None
    version_count: int
    text: str | None
    change_summary: str | None
    quality_score: float | None
    quality_labels: dict[str, str]
    ai_summary: str | None
    ai_issues: list[str]
    ambiguity_detected: bool | None
    ai_model: str | None
    analysed_at: datetime | None
    created_at: datetime | None
    updated_at: datetime | None
    suggestions: list[dict] = field(default_factory=list)

    @property
    def is_analysed(self) -> bool:
        return self.ai_summary is not None or self.ai_model is not None


@dataclass(frozen=True)
class ReportData:
    project: dict
    generated_at: datetime
    generated_by_email: str | None
    requirements: list[ReportRequirement]

    @property
    def total(self) -> int:
        return len(self.requirements)

    @property
    def status_counts(self) -> dict[str, int]:
        counts = {name: 0 for name in REQUIREMENT_STATUSES}

        for item in self.requirements:
            counts[item.status] = counts.get(item.status, 0) + 1

        return counts

    @property
    def scored(self) -> list[float]:
        return [
            item.quality_score
            for item in self.requirements
            if item.quality_score is not None
        ]

    @property
    def average_quality(self) -> float | None:
        scores = self.scored
        return round(sum(scores) / len(scores), 1) if scores else None

    @property
    def ambiguous_count(self) -> int:
        return sum(1 for item in self.requirements if item.ambiguity_detected)

    @property
    def suggestion_count(self) -> int:
        return sum(len(item.suggestions) for item in self.requirements)


def build_report_data(
    project: dict,
    requirement_rows: list[dict],
    suggestion_rows: list[dict],
    generated_at: datetime,
    generated_by_email: str | None,
) -> ReportData:
    """Assemble ReportData from repository rows. No values are invented."""

    by_analysis: dict[str, list[dict]] = {}

    for row in suggestion_rows:
        by_analysis.setdefault(str(row["ai_analysis_id"]), []).append(
            {
                "type": row["suggestion_type"],
                "status": row["status"],
                "text": row["suggestion_text"],
            }
        )

    requirements: list[ReportRequirement] = []

    for row in requirement_rows:
        assessment = _as_assessment(row.get("quality_assessment"))
        score = score_quality_assessment(assessment)

        labels = (
            {dim: str(assessment[dim]).strip() for dim in QUALITY_DIMENSIONS}
            if score is not None
            else {}
        )

        analysis_id = row.get("ai_analysis_id")

        requirements.append(
            ReportRequirement(
                code=row["requirement_code"],
                title=row.get("title"),
                status=row["status"],
                version_number=row.get("version_number"),
                version_count=int(row.get("version_count") or 0),
                text=row.get("requirement_text"),
                change_summary=row.get("change_summary"),
                quality_score=score,
                quality_labels=labels,
                ai_summary=row.get("analysis_summary"),
                ai_issues=parse_issues(row.get("recommendations")),
                ambiguity_detected=(
                    row.get("ambiguity_detected")
                    if analysis_id is not None
                    else None
                ),
                ai_model=row.get("model_name"),
                analysed_at=row.get("analysed_at"),
                created_at=row.get("created_at"),
                updated_at=row.get("updated_at"),
                suggestions=(
                    by_analysis.get(str(analysis_id), [])
                    if analysis_id is not None
                    else []
                ),
            )
        )

    return ReportData(
        project=project,
        generated_at=generated_at,
        generated_by_email=generated_by_email,
        requirements=requirements,
    )


def _quality_text(item: ReportRequirement) -> str:
    if item.quality_score is None:
        return NOT_ANALYSED if not item.is_analysed else NOT_AVAILABLE

    return f"{item.quality_score:.0f} / 100"


def _ambiguity_text(item: ReportRequirement) -> str:
    if item.ambiguity_detected is None:
        return "—"

    return "Yes" if item.ambiguity_detected else "No"


def _project_rows(data: ReportData) -> list[tuple[str, str]]:
    project = data.project

    return [
        ("Project name", clean(project["name"])),
        ("Client", clean(project.get("client_name")) or "—"),
        ("Project type", clean(project.get("project_type")) or "—"),
        ("Project status", label(project["status"])),
        ("Created", format_dt(project.get("created_at"))),
        ("Last updated", format_dt(project.get("updated_at"))),
        ("Description", clean(project.get("description")) or "—"),
        ("Report generated", format_dt(data.generated_at)),
        ("Generated by", clean(data.generated_by_email) or "—"),
    ]


def _summary_rows(data: ReportData) -> list[tuple[str, str]]:
    counts = data.status_counts
    average = data.average_quality

    rows = [("Total requirements", str(data.total))]
    rows += [(label(name), str(counts.get(name, 0))) for name in REQUIREMENT_STATUSES]
    rows += [
        (
            "Requirements with a quality score",
            f"{len(data.scored)} of {data.total}",
        ),
        (
            "Average quality score",
            f"{average:.1f} / 100" if average is not None else NOT_AVAILABLE,
        ),
        ("Ambiguity flagged by AI", str(data.ambiguous_count)),
        ("AI suggestions", str(data.suggestion_count)),
    ]
    return rows


# ---------------------------------------------------------------------------
# HTML
# ---------------------------------------------------------------------------


def _h(value) -> str:
    """Escape for HTML and keep line breaks."""

    return html_escape(clean(value)).replace("\n", "<br>")


_HTML_CSS = f"""
body {{ font-family: Segoe UI, Roboto, Arial, sans-serif; color:#1f2937;
        margin:0; background:#f3f4f6; }}
main {{ max-width: 980px; margin: 0 auto; padding: 32px 24px 64px;
        background:#fff; }}
h1 {{ margin:0 0 4px; font-size:26px; color:#111827; }}
h2 {{ margin:32px 0 12px; font-size:18px; color:{_PRIMARY};
      border-bottom:2px solid #e2e8f0; padding-bottom:6px; }}
h3 {{ margin:0 0 6px; font-size:16px; }}
.sub {{ color:#6b7280; margin:0 0 8px; }}
table {{ width:100%; border-collapse:collapse; margin:8px 0 16px; }}
th, td {{ text-align:left; padding:8px 10px; border:1px solid #e2e8f0;
          font-size:14px; vertical-align:top; overflow-wrap:anywhere; }}
th {{ background:#f9fafb; font-size:12px; text-transform:uppercase;
      letter-spacing:.4px; color:#6b7280; }}
.kv th {{ width:240px; }}
.req {{ border:1px solid #e2e8f0; border-radius:8px; padding:14px 16px;
        margin:0 0 14px; page-break-inside:avoid; }}
.meta {{ color:#6b7280; font-size:13px; margin:0 0 8px; }}
.muted {{ color:#6b7280; }}
.label {{ font-weight:600; margin:10px 0 2px; font-size:13px; }}
ul {{ margin:4px 0 0 20px; padding:0; }}
.empty {{ padding:20px; background:#f9fafb; border:1px dashed #cbd5e1;
          border-radius:8px; color:#6b7280; }}
@media print {{ body {{ background:#fff; }} main {{ padding:0; }} }}
"""


def _html_kv(rows: list[tuple[str, str]]) -> str:
    body = "".join(
        f"<tr><th>{_h(key)}</th><td>{_h(value)}</td></tr>" for key, value in rows
    )
    return f'<table class="kv">{body}</table>'


def build_html(data: ReportData) -> bytes:
    parts: list[str] = [
        "<!DOCTYPE html>",
        '<html lang="en"><head><meta charset="utf-8">',
        '<meta http-equiv="Content-Security-Policy" '
        "content=\"default-src 'none'; style-src 'unsafe-inline'\">",
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>{_h(data.project['name'])} — Requirement Analysis Report</title>",
        f"<style>{_HTML_CSS}</style></head><body><main>",
        "<h1>Requirement Analysis Report</h1>",
        f'<p class="sub">{_h(data.project["name"])}</p>',
        "<h2>Project Information</h2>",
        _html_kv(_project_rows(data)),
        "<h2>Summary</h2>",
        _html_kv(_summary_rows(data)),
    ]

    if not data.requirements:
        parts.append(
            '<div class="empty">This project has no requirements yet.</div>'
        )
    else:
        parts.append("<h2>Requirements Overview</h2>")
        parts.append(
            "<table><thead><tr><th>Code</th><th>Title</th><th>Status</th>"
            "<th>Version</th><th>Quality</th></tr></thead><tbody>"
        )

        for item in data.requirements:
            version = f"v{item.version_number}" if item.version_number else "—"
            parts.append(
                f"<tr><td>{_h(item.code)}</td><td>{_h(item.title) or '—'}</td>"
                f"<td>{_h(label(item.status))}</td><td>{_h(version)}</td>"
                f"<td>{_h(_quality_text(item))}</td></tr>"
            )

        parts.append("</tbody></table>")
        parts.append("<h2>Requirement Details</h2>")

        for item in data.requirements:
            version = (
                f"Version {item.version_number} of {item.version_count}"
                if item.version_number
                else "No version recorded"
            )
            parts.append('<div class="req">')
            parts.append(
                f"<h3>{_h(item.code)} — {_h(item.title) or '(untitled)'}</h3>"
            )
            parts.append(
                f'<p class="meta">Status: {_h(label(item.status))} · '
                f"{_h(version)} · Quality: {_h(_quality_text(item))}</p>"
            )
            parts.append(
                f"<p>{_h(item.text) if item.text else '<span class=muted>No requirement text recorded.</span>'}</p>"
            )

            if item.change_summary:
                parts.append(
                    f'<p class="label">Change summary</p><p>{_h(item.change_summary)}</p>'
                )

            if item.quality_labels:
                dims = ", ".join(
                    f"{label(dim)}: {value}"
                    for dim, value in item.quality_labels.items()
                )
                parts.append(f'<p class="label">Quality assessment</p><p>{_h(dims)}</p>')

            if item.ai_summary:
                parts.append(
                    f'<p class="label">AI analysis summary</p><p>{_h(item.ai_summary)}</p>'
                )
                parts.append(
                    f'<p class="meta">Ambiguity flagged: {_h(_ambiguity_text(item))} · '
                    f"Analysed: {_h(format_dt(item.analysed_at))}</p>"
                )

            if item.ai_issues:
                parts.append('<p class="label">Issues identified</p><ul>')
                parts.extend(f"<li>{_h(issue)}</li>" for issue in item.ai_issues)
                parts.append("</ul>")

            if item.suggestions:
                parts.append('<p class="label">AI suggestions</p><ul>')
                parts.extend(
                    f"<li>[{_h(label(s['type']))} · {_h(label(s['status']))}] "
                    f"{_h(s['text'])}</li>"
                    for s in item.suggestions
                )
                parts.append("</ul>")

            if not item.is_analysed:
                parts.append(f'<p class="muted">AI analysis: {NOT_ANALYSED}.</p>')

            parts.append("</div>")

    parts.append("</main></body></html>")
    return "".join(parts).encode("utf-8")


# ---------------------------------------------------------------------------
# XLSX
# ---------------------------------------------------------------------------


def _set(ws, row: int, column: int, value, *, bold: bool = False, wrap: bool = True):
    """Write a cell; text is cleaned, truncated and never becomes a formula."""

    cell = ws.cell(row=row, column=column)

    if isinstance(value, bool) or value is None:
        cell.value = "" if value is None else ("Yes" if value else "No")
    elif isinstance(value, (int, float)):
        cell.value = value
    else:
        text = clean(value)

        if len(text) > _EXCEL_CELL_LIMIT:
            text = text[: _EXCEL_CELL_LIMIT - 1] + "…"

        cell.value = text

        if text.startswith("="):
            cell.data_type = "s"

    if bold:
        cell.font = Font(bold=True)

    cell.alignment = Alignment(wrap_text=wrap, vertical="top")
    return cell


def _header(ws, headers: list[str], widths: list[int]) -> None:
    fill = PatternFill("solid", fgColor=_PRIMARY.lstrip("#"))

    for index, (title, width) in enumerate(zip(headers, widths), start=1):
        cell = _set(ws, 1, index, title, wrap=False)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = fill
        ws.column_dimensions[get_column_letter(index)].width = width

    ws.freeze_panes = "A2"


def build_xlsx(data: ReportData) -> bytes:
    workbook = Workbook()

    # ---- Summary ---------------------------------------------------------
    summary = workbook.active
    summary.title = "Summary"
    summary.column_dimensions["A"].width = 38
    summary.column_dimensions["B"].width = 80

    row = 1
    _set(summary, row, 1, "Requirement Analysis Report", bold=True, wrap=False)
    summary.cell(row=row, column=1).font = Font(bold=True, size=14)
    row += 2

    _set(summary, row, 1, "Project Information", bold=True, wrap=False)
    row += 1

    for key, value in _project_rows(data):
        _set(summary, row, 1, key, bold=True)
        _set(summary, row, 2, value)
        row += 1

    row += 1
    _set(summary, row, 1, "Summary", bold=True, wrap=False)
    row += 1

    for key, value in _summary_rows(data):
        _set(summary, row, 1, key, bold=True)
        _set(summary, row, 2, value)
        row += 1

    # ---- Requirements ----------------------------------------------------
    sheet = workbook.create_sheet("Requirements")
    headers = (
        ["Code", "Title", "Status", "Current Version", "Total Versions",
         "Requirement Text", "Change Summary", "Quality Score (0-100)"]
        + [label(dim) for dim in QUALITY_DIMENSIONS]
        + ["Ambiguity Flagged", "AI Analysis Summary", "Issues Identified",
           "AI Model", "Analysed At", "Created", "Last Updated"]
    )
    widths = (
        [14, 32, 12, 10, 10, 60, 30, 14]
        + [14] * len(QUALITY_DIMENSIONS)
        + [12, 50, 50, 20, 22, 22, 22]
    )
    _header(sheet, headers, widths)

    for index, item in enumerate(data.requirements, start=2):
        values = (
            [item.code, item.title or "", label(item.status),
             item.version_number if item.version_number else "",
             item.version_count, item.text or "", item.change_summary or "",
             item.quality_score if item.quality_score is not None
             else (NOT_ANALYSED if not item.is_analysed else NOT_AVAILABLE)]
            + [item.quality_labels.get(dim, "") for dim in QUALITY_DIMENSIONS]
            + [_ambiguity_text(item), item.ai_summary or "",
               "\n".join(f"• {issue}" for issue in item.ai_issues),
               item.ai_model or "", format_dt(item.analysed_at)
               if item.analysed_at else "",
               format_dt(item.created_at), format_dt(item.updated_at)]
        )

        for column, value in enumerate(values, start=1):
            _set(sheet, index, column, value)

    if data.requirements:
        sheet.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{len(data.requirements) + 1}"

    # ---- AI Suggestions --------------------------------------------------
    suggestions = workbook.create_sheet("AI Suggestions")
    _header(
        suggestions,
        ["Requirement Code", "Type", "Status", "Suggestion"],
        [18, 26, 12, 100],
    )

    row = 2

    for item in data.requirements:
        for suggestion in item.suggestions:
            _set(suggestions, row, 1, item.code)
            _set(suggestions, row, 2, label(suggestion["type"]))
            _set(suggestions, row, 3, label(suggestion["status"]))
            _set(suggestions, row, 4, suggestion["text"])
            row += 1

    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------


def _pdf_text(value) -> str:
    """Safe text for a reportlab Paragraph using the built-in Helvetica font.

    Characters outside Windows-1252 cannot be drawn by the standard fonts
    and would render as black boxes, so they are replaced with '?'.
    """

    text = clean(value).encode("cp1252", "replace").decode("cp1252")
    return xml_escape(text).replace("\n", "<br/>")


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()

    return {
        "title": ParagraphStyle(
            "RTitle", parent=base["Title"], alignment=TA_LEFT, fontSize=22,
            textColor=colors.HexColor("#111827"), spaceAfter=2,
        ),
        "sub": ParagraphStyle(
            "RSub", parent=base["Normal"], fontSize=12,
            textColor=colors.HexColor("#6b7280"), spaceAfter=10,
        ),
        "h2": ParagraphStyle(
            "RH2", parent=base["Heading2"], fontSize=14,
            textColor=colors.HexColor(_PRIMARY), spaceBefore=14, spaceAfter=6,
        ),
        "h3": ParagraphStyle(
            "RH3", parent=base["Heading3"], fontSize=11, spaceBefore=10,
            spaceAfter=2, keepWithNext=1,
        ),
        "body": ParagraphStyle(
            "RBody", parent=base["BodyText"], fontSize=9.5, leading=13,
        ),
        "meta": ParagraphStyle(
            "RMeta", parent=base["BodyText"], fontSize=8.5, leading=11,
            textColor=colors.HexColor("#6b7280"),
        ),
        "label": ParagraphStyle(
            "RLabel", parent=base["BodyText"], fontSize=8.5, leading=11,
            textColor=colors.HexColor("#374151"), spaceBefore=4,
        ),
        "cell": ParagraphStyle(
            "RCell", parent=base["BodyText"], fontSize=8.5, leading=11,
            wordWrap="CJK",
        ),
        "cellh": ParagraphStyle(
            "RCellH", parent=base["BodyText"], fontSize=8, leading=10,
            textColor=colors.white, fontName="Helvetica-Bold", wordWrap="CJK",
        ),
    }


def _kv_table(rows, styles, width) -> Table:
    table = Table(
        [
            [Paragraph(f"<b>{_pdf_text(k)}</b>", styles["cell"]),
             Paragraph(_pdf_text(v), styles["cell"])]
            for k, v in rows
        ],
        colWidths=[width * 0.32, width * 0.68],
    )
    table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#e2e8f0")),
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f9fafb")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return table


def build_pdf(data: ReportData) -> bytes:
    styles = _styles()
    buffer = BytesIO()
    footer_label = (
        clean(f"ReqIntel — {data.project['name']}")
        .encode("cp1252", "replace")
        .decode("cp1252")[:90]
    )

    document = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm,
        topMargin=18 * mm, bottomMargin=18 * mm,
        title=clean(f"{data.project['name']} — Requirement Analysis Report"),
        author="ReqIntel",
    )
    width = A4[0] - 36 * mm

    def draw_footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillGray(0.45)
        canvas.drawString(18 * mm, 10 * mm, footer_label)
        canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, f"Page {doc.page}")
        canvas.restoreState()

    story = [
        Paragraph("Requirement Analysis Report", styles["title"]),
        Paragraph(_pdf_text(data.project["name"]), styles["sub"]),
        Paragraph("Project Information", styles["h2"]),
        _kv_table(_project_rows(data), styles, width),
        Paragraph("Summary", styles["h2"]),
        _kv_table(_summary_rows(data), styles, width),
    ]

    if not data.requirements:
        story += [
            Spacer(1, 10),
            Paragraph("This project has no requirements yet.", styles["body"]),
        ]
    else:
        story.append(Paragraph("Requirements Overview", styles["h2"]))

        head = ["Code", "Title", "Status", "Version", "Quality"]
        rows = [[Paragraph(h, styles["cellh"]) for h in head]]

        for item in data.requirements:
            rows.append([
                Paragraph(_pdf_text(item.code), styles["cell"]),
                Paragraph(_pdf_text(item.title) or "—", styles["cell"]),
                Paragraph(_pdf_text(label(item.status)), styles["cell"]),
                Paragraph(
                    f"v{item.version_number}" if item.version_number else "—",
                    styles["cell"],
                ),
                Paragraph(_pdf_text(_quality_text(item)), styles["cell"]),
            ])

        overview = Table(
            rows, repeatRows=1,
            colWidths=[width * 0.14, width * 0.38, width * 0.16,
                       width * 0.12, width * 0.20],
        )
        overview.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(_PRIMARY)),
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#e2e8f0")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1),
                     [colors.white, colors.HexColor("#f9fafb")]),
                ]
            )
        )
        story.append(overview)
        story.append(Paragraph("Requirement Details", styles["h2"]))

        for item in data.requirements:
            version = (
                f"Version {item.version_number} of {item.version_count}"
                if item.version_number
                else "No version recorded"
            )
            story.append(
                Paragraph(
                    f"{_pdf_text(item.code)} — {_pdf_text(item.title) or '(untitled)'}",
                    styles["h3"],
                )
            )
            story.append(
                Paragraph(
                    f"Status: {_pdf_text(label(item.status))} &nbsp;|&nbsp; "
                    f"{_pdf_text(version)} &nbsp;|&nbsp; "
                    f"Quality: {_pdf_text(_quality_text(item))}",
                    styles["meta"],
                )
            )
            story.append(
                Paragraph(
                    _pdf_text(item.text) if item.text
                    else "No requirement text recorded.",
                    styles["body"],
                )
            )

            if item.change_summary:
                story.append(Paragraph("<b>Change summary</b>", styles["label"]))
                story.append(Paragraph(_pdf_text(item.change_summary), styles["body"]))

            if item.quality_labels:
                dims = ", ".join(
                    f"{label(dim)}: {value}"
                    for dim, value in item.quality_labels.items()
                )
                story.append(Paragraph("<b>Quality assessment</b>", styles["label"]))
                story.append(Paragraph(_pdf_text(dims), styles["body"]))

            if item.ai_summary:
                story.append(Paragraph("<b>AI analysis summary</b>", styles["label"]))
                story.append(Paragraph(_pdf_text(item.ai_summary), styles["body"]))
                story.append(
                    Paragraph(
                        f"Ambiguity flagged: {_pdf_text(_ambiguity_text(item))} "
                        f"&nbsp;|&nbsp; Analysed: {_pdf_text(format_dt(item.analysed_at))}",
                        styles["meta"],
                    )
                )

            if item.ai_issues:
                story.append(Paragraph("<b>Issues identified</b>", styles["label"]))
                for issue in item.ai_issues:
                    story.append(Paragraph(f"• {_pdf_text(issue)}", styles["body"]))

            if item.suggestions:
                story.append(Paragraph("<b>AI suggestions</b>", styles["label"]))
                for s in item.suggestions:
                    story.append(
                        Paragraph(
                            f"• [{_pdf_text(label(s['type']))} / "
                            f"{_pdf_text(label(s['status']))}] {_pdf_text(s['text'])}",
                            styles["body"],
                        )
                    )

            if not item.is_analysed:
                story.append(
                    Paragraph(f"AI analysis: {NOT_ANALYSED}.", styles["meta"])
                )

            story.append(Spacer(1, 6))

    document.build(story, onFirstPage=draw_footer, onLaterPages=draw_footer)
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

FORMAT_INFO = {
    "pdf": {"extension": "pdf", "content_type": "application/pdf",
            "builder": build_pdf},
    "xlsx": {
        "extension": "xlsx",
        "content_type": (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        "builder": build_xlsx,
    },
    "html": {"extension": "html", "content_type": "text/html",
             "builder": build_html},
}