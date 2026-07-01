"""PDF report export for recruiter-facing CV review.

Renders the structured ``CVReport`` (post-scorer + post-feedback) into a
printable PDF. Implemented as a *pure* function: takes a plain ``dict``
payload, writes a PDF at ``path``, returns the path. No Streamlit, no
global state — fully unit-testable.

Why a dict and not the dataclass? The same payload is what
``streamlit_app.save_report`` writes to JSON, so we can render a PDF from
the exact same data structure that the user already downloaded. That
also keeps this module decoupled from ``app.scorer`` so the import
graph stays light.

Usage::

    from app.report_export import render_pdf_report

    payload = {
        "file": "jane_doe.pdf",
        "overall": 7.2,
        "grade": "C — Solid, improvable",
        "summary": "Solid mid-level engineer with weak metrics.",
        "role": "swe",
        "role_confidence": 0.84,
        "sections": {
            "summary": {
                "score": 7.0,
                "evidence": ["..."],
                "issues": ["..."],
                "feedback": "...",
            },
            ...
        },
    }
    out = render_pdf_report(payload, Path("/tmp/jane_review.pdf"))
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Mapping, Sequence

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


# --------------------------------------------------------------------------- #
# Style helpers
# --------------------------------------------------------------------------- #

def _build_styles() -> Dict[str, ParagraphStyle]:
    """Build a small set of named styles for the PDF.

    Uses Helvetica (PDF base-14 font, latin-1 safe + Indonesian diacritics)
    so we don't have to register a TTF and we keep the binary portable.
    """
    base = getSampleStyleSheet()
    title = ParagraphStyle(
        "RRTitle",
        parent=base["Title"],
        fontName="Helvetica-Bold",
        fontSize=20,
        leading=24,
        spaceAfter=8,
        textColor=colors.HexColor("#1f2937"),
    )
    subtitle = ParagraphStyle(
        "RRSubtitle",
        parent=base["Normal"],
        fontName="Helvetica",
        fontSize=11,
        leading=14,
        textColor=colors.HexColor("#4b5563"),
        spaceAfter=12,
    )
    h2 = ParagraphStyle(
        "RRH2",
        parent=base["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=13,
        leading=16,
        textColor=colors.HexColor("#1f2937"),
        spaceBefore=10,
        spaceAfter=4,
    )
    body = ParagraphStyle(
        "RRBody",
        parent=base["Normal"],
        fontName="Helvetica",
        fontSize=10,
        leading=13,
        spaceAfter=4,
    )
    bullet = ParagraphStyle(
        "RRBullet",
        parent=body,
        leftIndent=12,
        bulletIndent=0,
        spaceAfter=2,
    )
    metric = ParagraphStyle(
        "RRMetric",
        parent=base["Normal"],
        fontName="Helvetica-Bold",
        fontSize=14,
        leading=18,
        alignment=1,  # CENTER
        textColor=colors.HexColor("#0f766e"),
    )
    return {
        "title": title,
        "subtitle": subtitle,
        "h2": h2,
        "body": body,
        "bullet": bullet,
        "metric": metric,
    }


def _score_color(score: float) -> colors.Color:
    """Map a 0–10 score to a traffic-light color for the table cell."""
    if score >= 8:
        return colors.HexColor("#16a34a")  # green
    if score >= 6:
        return colors.HexColor("#ca8a04")  # amber
    if score >= 4:
        return colors.HexColor("#ea580c")  # orange
    return colors.HexColor("#dc2626")  # red


# --------------------------------------------------------------------------- #
# Story builders
# --------------------------------------------------------------------------- #

def _header_block(data: Mapping[str, Any], styles: Dict[str, ParagraphStyle]) -> list:
    """Title, CV file name, role, generated-at."""
    cv_name = str(data.get("file") or "Unknown CV")
    role = str(data.get("role") or "general").upper()
    confidence = data.get("role_confidence")
    if isinstance(confidence, (int, float)):
        role_line = f"Role rubric: <b>{role}</b> (confidence {confidence:.0%})"
    else:
        role_line = f"Role rubric: <b>{role}</b>"
    generated = datetime.now().strftime("%Y-%m-%d %H:%M")
    return [
        Paragraph("CV Review Report", styles["title"]),
        Paragraph(cv_name, styles["subtitle"]),
        Paragraph(role_line, styles["body"]),
        Paragraph(f"Generated: {generated}", styles["body"]),
        Spacer(1, 0.4 * cm),
    ]


def _summary_block(data: Mapping[str, Any], styles: Dict[str, ParagraphStyle]) -> list:
    """Overall score + grade + recruiter summary text."""
    overall = data.get("overall", 0.0)
    grade = data.get("grade", "—")
    summary = data.get("summary") or "(no executive summary generated)"
    overall_str = f"{overall:.1f}" if isinstance(overall, (int, float)) else "—"

    header = Table(
        [[Paragraph(f"{overall_str}<font size=10> / 10</font>", styles["metric"]),
          Paragraph(f"<b>Grade:</b> {grade}", styles["body"])]],
        colWidths=[4 * cm, 12 * cm],
    )
    header.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), colors.HexColor("#ecfdf5")),
        ("BOX", (0, 0), (-1, -1), 0.75, colors.HexColor("#0f766e")),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#a7f3d0")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    return [
        Paragraph("Executive Summary", styles["h2"]),
        header,
        Spacer(1, 0.3 * cm),
        Paragraph(summary, styles["body"]),
        Spacer(1, 0.4 * cm),
    ]


def _score_table(data: Mapping[str, Any], styles: Dict[str, ParagraphStyle]) -> list:
    """Per-section score table."""
    sections = data.get("sections") or {}
    if not isinstance(sections, Mapping):
        return []

    rows: list = [[Paragraph("<b>Section</b>", styles["body"]),
                   Paragraph("<b>Score</b>", styles["body"]),
                   Paragraph("<b>Status</b>", styles["body"])]]
    for name, sec in sections.items():
        if not isinstance(sec, Mapping):
            continue
        score = sec.get("score", 0.0)
        try:
            score_val = float(score)
        except (TypeError, ValueError):
            score_val = 0.0
        display = name.replace("_", " ").title()
        score_text = f"{score_val:.1f} / 10"
        if score_val >= 8:
            status = "🟢 Strong"
        elif score_val >= 6:
            status = "🟡 Solid"
        elif score_val >= 4:
            status = "🟠 Needs work"
        else:
            status = "🔴 Weak"
        rows.append([
            Paragraph(display, styles["body"]),
            Paragraph(f"<b>{score_text}</b>", styles["body"]),
            Paragraph(status, styles["body"]),
        ])

    if len(rows) == 1:  # only header
        return []

    tbl = Table(rows, colWidths=[7 * cm, 3 * cm, 6 * cm])
    style_cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f3f4f6")),
        ("BOX", (0, 0), (-1, -1), 0.75, colors.HexColor("#9ca3af")),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#d1d5db")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    # Color the score cell per row.
    for i, sec in enumerate(sections.values(), start=1):
        if not isinstance(sec, Mapping):
            continue
        try:
            sv = float(sec.get("score", 0.0))
        except (TypeError, ValueError):
            sv = 0.0
        style_cmds.append(("TEXTCOLOR", (1, i), (1, i), _score_color(sv)))
    tbl.setStyle(TableStyle(style_cmds))

    return [
        Paragraph("Section Scores", styles["h2"]),
        tbl,
        Spacer(1, 0.4 * cm),
    ]


def _feedback_block(
    sections: Mapping[str, Any],
    styles: Dict[str, ParagraphStyle],
) -> list:
    """Per-section feedback bullets."""
    blocks: list = [Paragraph("Detailed Feedback", styles["h2"])]
    if not isinstance(sections, Mapping) or not sections:
        blocks.append(Paragraph("(no sections to show)", styles["body"]))
        return blocks

    for name, sec in sections.items():
        if not isinstance(sec, Mapping):
            continue
        display = name.replace("_", " ").title()
        blocks.append(Paragraph(f"<b>{display}</b>", styles["h2"]))

        evidence: Sequence = sec.get("evidence") or []
        issues: Sequence = sec.get("issues") or []
        feedback = sec.get("feedback") or ""

        if evidence:
            blocks.append(Paragraph("<b>Strengths</b>", styles["body"]))
            for e in evidence:
                if not isinstance(e, str) or not e.strip():
                    continue
                blocks.append(Paragraph(f"• {e}", styles["bullet"]))

        if issues:
            blocks.append(Paragraph("<b>Issues</b>", styles["body"]))
            for i in issues:
                if not isinstance(i, str) or not i.strip():
                    continue
                blocks.append(Paragraph(f"• {i}", styles["bullet"]))

        if isinstance(feedback, str) and feedback.strip():
            blocks.append(Paragraph("<b>Reviewer narrative</b>", styles["body"]))
            # Preserve paragraph breaks from LLM output.
            for para in feedback.strip().split("\n"):
                para = para.strip()
                if not para:
                    continue
                # If the LLM already emitted a bullet, keep it; otherwise prefix one.
                if para.startswith(("•", "-", "*")):
                    blocks.append(Paragraph(para, styles["bullet"]))
                else:
                    blocks.append(Paragraph(f"• {para}", styles["bullet"]))

        if not evidence and not issues and not feedback:
            blocks.append(Paragraph("(no detail recorded)", styles["body"]))

        blocks.append(Spacer(1, 0.25 * cm))

    return blocks


def _recommendation_block(
    data: Mapping[str, Any],
    styles: Dict[str, ParagraphStyle],
) -> list:
    """Final recruiter-facing recommendation."""
    overall = data.get("overall")
    try:
        ov = float(overall) if overall is not None else 0.0
    except (TypeError, ValueError):
        ov = 0.0

    if ov >= 8:
        rec = (
            "<b>Recommendation:</b> Strong candidate — fast-track to phone screen. "
            "Verify any claimed metrics during the interview."
        )
    elif ov >= 6.5:
        rec = (
            "<b>Recommendation:</b> Solid candidate — worth a phone screen. "
            "Probe the weakest section during the interview."
        )
    elif ov >= 5:
        rec = (
            "<b>Recommendation:</b> Borderline — request specific examples "
            "before advancing. The CV needs quantification."
        )
    else:
        rec = (
            "<b>Recommendation:</b> Reject (or hold for re-submission). "
            "Multiple sections fall below the bar; a rewrite is the fastest path forward."
        )

    return [
        Paragraph("Final Recommendation", styles["h2"]),
        Paragraph(rec, styles["body"]),
    ]


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #

def render_pdf_report(data: Mapping[str, Any], path: Path) -> Path:
    """Render ``data`` as a PDF at ``path``. Returns ``path``.

    ``data`` is the same dict shape produced by
    ``streamlit_app.save_report``::

        {
            "file": "jane_doe.pdf",
            "overall": 7.2,
            "grade": "C — Solid, improvable",
            "summary": "...",
            "role": "swe",
            "role_confidence": 0.84,
            "sections": {
                "summary": {"score": ..., "evidence": [...], "issues": [...], "feedback": "..."},
                ...
            },
        }

    Tolerates missing / malformed fields — empty values are rendered as
    "(none)" placeholders, never crash. This is what the recruiter will
    forward to the hiring manager, so graceful degradation matters more
    than strict validation.

    Pure function: no Streamlit, no globals. Safe to call from tests.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Defensive copy — never trust the caller's nested structure.
    safe: Dict[str, Any] = dict(data or {})

    styles = _build_styles()
    sections = safe.get("sections") if isinstance(safe.get("sections"), Mapping) else {}

    story: list = []
    story.extend(_header_block(safe, styles))
    story.extend(_summary_block(safe, styles))
    story.extend(_score_table(safe, styles))
    story.extend(_feedback_block(sections, styles))  # type: ignore[arg-type]
    story.extend(_recommendation_block(safe, styles))

    doc = SimpleDocTemplate(
        str(path),
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
        title="CV Review Report",
        author="CV Reviewer (Local RAG)",
    )
    doc.build(story)
    return path