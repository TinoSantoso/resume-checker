"""PDF layout analysis — detect columns and reconstruct reading order.

PyMuPDF's ``page.get_text("text")`` flattens text in PDF reading order, which
works for single-column layouts but scrambles 2-column resumes: "Skills" list
in the right column ends up next to "Experience" bullets in the left column.

This module uses ``page.get_text("dict")`` to get bounding boxes per span,
clusters spans into columns, and re-emits text in true reading order
(top-to-bottom per column, columns ordered left-to-right).

Used only by the PDF path. DOCX already has explicit structure from the
author so it bypasses this module.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, List, Tuple

import pymupdf


# --------------------------------------------------------------------------- #
# Data model
# --------------------------------------------------------------------------- #

@dataclass
class TextSpan:
    text: str
    bbox: Tuple[float, float, float, float]  # (x0, y0, x1, y1)
    block_no: int
    line_no: int
    span_no: int
    font: str = ""
    size: float = 0.0


@dataclass
class PageLayout:
    page_no: int
    width: float
    height: float
    n_columns: int
    spans: List[TextSpan]


# --------------------------------------------------------------------------- #
# Span extraction
# --------------------------------------------------------------------------- #

def _extract_spans(page: pymupdf.Page) -> List[TextSpan]:
    """Flatten all spans on a page from the 'dict' format."""
    raw = page.get_text("dict")
    spans: List[TextSpan] = []
    for block in raw.get("blocks", []):
        if block.get("type", 0) != 0:  # 0 = text block, 1 = image
            continue
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                txt = span.get("text", "")
                if not txt or not txt.strip():
                    continue
                bbox = tuple(span.get("bbox", (0, 0, 0, 0)))
                spans.append(
                    TextSpan(
                        text=txt,
                        bbox=bbox,  # type: ignore[assignment]
                        block_no=block.get("number", 0),
                        line_no=line.get("number", 0) if "number" in line else 0,
                        span_no=span.get("number", 0) if "number" in span else 0,
                        font=span.get("font", ""),
                        size=span.get("size", 0.0),
                    )
                )
    return spans


# --------------------------------------------------------------------------- #
# Column detection
# --------------------------------------------------------------------------- #

def _detect_columns(spans: List[TextSpan], page_width: float) -> int:
    """Detect number of text columns on a page.

    Heuristic: if there are at least 2 distinct "left edges" of text spans
    (x0 positions) and the right column starts at >= 45% of page width, the
    page is 2-column. Otherwise 1.

    Why spans, not blocks: PyMuPDF can put spans from 2 visual columns into
    the same text block (they're on the same y-coordinate). Block-level
    x0 misses this case. Span-level x0 catches it.

    For 3+ columns: detect as 2 (we don't support 3-column CVs in v1; they're
    rare in practice and the user can still get useful parsing).
    """
    if not spans:
        return 1

    # Use span-level x0 positions, deduplicated to the nearest pixel.
    # We cluster x0 into "columns" by looking for the largest gap.
    span_lefts = sorted({round(s.bbox[0]) for s in spans})
    if len(span_lefts) < 2:
        return 1

    # Find the largest gap between sorted x0 positions.
    gaps: List[Tuple[float, int, int]] = []  # (gap_size, idx_left, idx_right)
    for i in range(len(span_lefts) - 1):
        gap = span_lefts[i + 1] - span_lefts[i]
        gaps.append((gap, i, i + 1))

    if not gaps:
        return 1
    max_gap, idx_l, idx_r = max(gaps, key=lambda t: t[0])

    # The gap must be meaningful: at least 15% of page width apart.
    if max_gap < page_width * 0.15:
        return 1

    # The right column must start past the page midpoint (otherwise the gap
    # is just a slight indent, not a real column boundary).
    right_col_start = span_lefts[idx_r]
    if right_col_start < page_width * 0.45:
        return 1

    return 2


# --------------------------------------------------------------------------- #
# Reading order reconstruction
# --------------------------------------------------------------------------- #

def _column_for_span(span: TextSpan, column_boundaries: List[float]) -> int:
    """Assign a span to a column index based on its bbox center x."""
    if len(column_boundaries) <= 1:
        return 0
    cx = (span.bbox[0] + span.bbox[2]) / 2
    for i in range(1, len(column_boundaries)):
        if cx >= column_boundaries[i]:
            return i
    return 0


def _line_key(spans: List[TextSpan], y_tolerance: float = 2.0) -> List[List[TextSpan]]:
    """Group spans that are on the same visual line (similar y, same column).

    Returns a list of lines; each line is a list of spans in left-to-right order.
    """
    if not spans:
        return []
    sorted_spans = sorted(spans, key=lambda s: (s.bbox[1], s.bbox[0]))
    lines: List[List[TextSpan]] = []
    current: List[TextSpan] = [sorted_spans[0]]
    for s in sorted_spans[1:]:
        if abs(s.bbox[1] - current[0].bbox[1]) <= y_tolerance:
            current.append(s)
        else:
            current.sort(key=lambda x: x.bbox[0])
            lines.append(current)
            current = [s]
    current.sort(key=lambda x: x.bbox[0])
    lines.append(current)
    return lines


def _column_boundaries(spans: List[TextSpan], n_columns: int, page_width: float) -> List[float]:
    """Return the x0 thresholds for column assignment (length n_columns).

    For 1 column: just [0].
    For 2 columns: [0, midpoint] where midpoint is derived from observed x0s.
    """
    if n_columns <= 1:
        return [0.0]
    # Use the gap we found: midpoint between leftmost and rightmost span x0s.
    span_lefts = sorted({round(s.bbox[0]) for s in spans})
    if len(span_lefts) < 2:
        return [0.0]
    # Find the largest gap.
    gaps = [(span_lefts[i + 1] - span_lefts[i], i) for i in range(len(span_lefts) - 1)]
    max_gap, idx = max(gaps, key=lambda t: t[0])
    midpoint = (span_lefts[idx] + span_lefts[idx + 1]) / 2
    return [0.0, midpoint]


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #

def analyze_page(page: pymupdf.Page, page_no: int) -> PageLayout:
    """Build a PageLayout (columns + ordered spans) for one page."""
    spans = _extract_spans(page)
    rect = page.rect
    n_columns = _detect_columns(spans, rect.width)
    return PageLayout(
        page_no=page_no,
        width=rect.width,
        height=rect.height,
        n_columns=n_columns,
        spans=spans,
    )


def text_from_layout(layout: PageLayout) -> str:
    """Reconstruct reading-order text from a PageLayout.

    Algorithm:
    1. Determine column boundaries from observed x0 positions.
    2. Assign each span to a column.
    3. Group spans by (column, visual line).
    4. Emit lines in column-major order (column 0 top-to-bottom, then column 1).

    Spans within a line are joined with a single space so bullets that
    PyMuPDF stores as a separate span (e.g. "•" on its own) don't get
    glued to the following word. We then strip + rstrip per line.
    """
    if not layout.spans:
        return ""

    boundaries = _column_boundaries(layout.spans, layout.n_columns, layout.width)
    if layout.n_columns <= 1:
        # Single column: emit in natural line order.
        lines = _line_key(layout.spans)
        out: List[str] = []
        for line in lines:
            text = " ".join(s.text for s in line).strip()
            # Collapse multiple internal spaces that come from
            # already-spaced spans.
            text = re.sub(r"\s+", " ", text).rstrip()
            if text:
                out.append(text)
        return "\n".join(out)

    # Multi-column: split spans by column, then emit each column's lines.
    column_lines: List[List[List[TextSpan]]] = [[] for _ in range(layout.n_columns)]
    for col_idx in range(layout.n_columns):
        col_spans = [s for s in layout.spans if _column_for_span(s, boundaries) == col_idx]
        column_lines[col_idx] = _line_key(col_spans)

    out_lines: List[str] = []
    for col_lines in column_lines:
        for line in col_lines:
            text = " ".join(s.text for s in line).strip()
            text = re.sub(r"\s+", " ", text).rstrip()
            if text:
                out_lines.append(text)
    return "\n".join(out_lines)


def extract_text_with_layout(pdf_path) -> str:
    """Drop-in replacement for pdf_parser.extract_text() that respects columns.

    For single-column pages, behavior is equivalent to PyMuPDF's native
    ``get_text("text")``. For multi-column pages, spans are reordered into
    proper reading order.
    """
    doc = pymupdf.open(pdf_path)
    chunks: List[str] = []
    try:
        for page_no, page in enumerate(doc):
            layout = analyze_page(page, page_no)
            page_text = text_from_layout(layout)
            if page_text:
                chunks.append(page_text)
    finally:
        doc.close()
    return "\n".join(chunks)


# --------------------------------------------------------------------------- #
# Diagnostics
# --------------------------------------------------------------------------- #

def page_layout_summary(pdf_path) -> List[Tuple[int, int, int]]:
    """Return [(page_no, n_columns, n_spans), ...] for diagnostic output.

    Used by tests + by the scorer to surface a 'mixed layout' warning when
    a single PDF has both 1-column and 2-column pages.
    """
    doc = pymupdf.open(pdf_path)
    out: List[Tuple[int, int, int]] = []
    try:
        for page_no, page in enumerate(doc):
            layout = analyze_page(page, page_no)
            out.append((page_no, layout.n_columns, len(layout.spans)))
    finally:
        doc.close()
    return out
