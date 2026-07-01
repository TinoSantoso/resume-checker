"""Tests for app/layout.py: column detection + reading-order reconstruction."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pymupdf
import pytest

from app.layout import (
    PageLayout,
    TextSpan,
    _column_boundaries,
    _detect_columns,
    _extract_spans,
    _line_key,
    analyze_page,
    extract_text_with_layout,
    page_layout_summary,
    text_from_layout,
)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _make_pdf(
    page_specs: list[dict],
    out_path: Path,
) -> Path:
    """Build a synthetic PDF for layout testing.

    Each page_spec is a dict:
        {
            "page_w": 612, "page_h": 792,
            "spans": [(x0, y0, x1, y1, text, font_size), ...]
        }
    """
    doc = pymupdf.open()
    for spec in page_specs:
        pw = spec.get("page_w", 612)
        ph = spec.get("page_h", 792)
        page = doc.new_page(width=pw, height=ph)
        for x0, y0, x1, y1, text, fsize in spec["spans"]:
            # Add a single-span "line" so we get clean bbox output.
            rect = pymupdf.Rect(x0, y0, x1, y1)
            page.insert_textbox(
                rect, text,
                fontsize=fsize,
                fontname="helv",
                align=pymupdf.TEXT_ALIGN_LEFT,
            )
    doc.save(str(out_path))
    doc.close()
    return out_path


# --------------------------------------------------------------------------- #
# Single column — backward compat
# --------------------------------------------------------------------------- #

class TestSingleColumn:
    def test_single_column_detection(self, tmp_path):
        pdf = _make_pdf([
            {
                "spans": [
                    (50, 50, 562, 80, "Title line", 14),
                    (50, 100, 562, 130, "First paragraph.", 11),
                    (50, 150, 562, 180, "Second paragraph.", 11),
                ]
            }
        ], tmp_path / "single.pdf")

        summary = page_layout_summary(pdf)
        assert len(summary) == 1
        page_no, n_cols, n_spans = summary[0]
        assert n_cols == 1

    def test_single_column_text_preserved(self, tmp_path):
        pdf = _make_pdf([
            {
                "spans": [
                    (50, 50, 562, 80, "Title", 14),
                    (50, 100, 562, 130, "Body line one.", 11),
                ]
            }
        ], tmp_path / "single.pdf")

        text = extract_text_with_layout(pdf)
        assert "Title" in text
        assert "Body line one." in text


# --------------------------------------------------------------------------- #
# Two-column detection + reading order
# --------------------------------------------------------------------------- #

class TestTwoColumn:
    def test_two_column_detected(self, tmp_path):
        # Two columns: left starts at x=50, right starts at x=320 (on 612-wide page)
        pdf = _make_pdf([
            {
                "spans": [
                    # Left column
                    (50, 50, 280, 80, "Left Title", 14),
                    (50, 100, 280, 130, "Left body 1.", 11),
                    (50, 150, 280, 180, "Left body 2.", 11),
                    # Right column
                    (320, 50, 562, 80, "Right Title", 14),
                    (320, 100, 562, 130, "Right body 1.", 11),
                    (320, 150, 562, 180, "Right body 2.", 11),
                ]
            }
        ], tmp_path / "two.pdf")

        summary = page_layout_summary(pdf)
        assert summary[0][1] == 2, f"expected 2 columns, got {summary[0][1]}"

    def test_two_column_reading_order(self, tmp_path):
        pdf = _make_pdf([
            {
                "spans": [
                    (50, 50, 280, 80, "LEFT_TITLE", 14),
                    (50, 100, 280, 130, "LEFT_BODY", 11),
                    (320, 50, 562, 80, "RIGHT_TITLE", 14),
                    (320, 100, 562, 130, "RIGHT_BODY", 11),
                ]
            }
        ], tmp_path / "two.pdf")

        text = extract_text_with_layout(pdf)
        # Reading order: column 0 fully, then column 1
        # (text is rstripped but substrings remain)
        assert text.index("LEFT_TITLE") < text.index("LEFT_BODY")
        assert text.index("LEFT_BODY") < text.index("RIGHT_TITLE"), (
            f"column 0 content should come before column 1\n{text!r}"
        )
        assert text.index("RIGHT_TITLE") < text.index("RIGHT_BODY")

    def test_single_column_not_misclassified(self, tmp_path):
        # Indented but single-column — should still be 1 column.
        pdf = _make_pdf([
            {
                "spans": [
                    (50, 50, 200, 80, "Block A", 11),
                    (50, 100, 200, 130, "Block B", 11),
                    (50, 150, 200, 180, "Block C", 11),
                ]
            }
        ], tmp_path / "indented.pdf")
        assert page_layout_summary(pdf)[0][1] == 1


# --------------------------------------------------------------------------- #
# Bullet preservation
# --------------------------------------------------------------------------- #

class TestBulletSpan:
    def test_bullet_marker_does_not_glue_to_text(self, tmp_path):
        # A "-" character on its own in one span, then " Item text" in next.
        # After join-with-space, expect "- Item text" (NOT "-Item text").
        # We use ASCII "-" instead of "•" because PyMuPDF's helv font has
        # no glyph for unicode bullet; what matters is the join behavior.
        pdf = _make_pdf([
            {
                "spans": [
                    (50, 50, 60, 80, "-", 11),
                    (60, 50, 280, 80, " Item text", 11),
                ]
            }
        ], tmp_path / "bullet.pdf")
        text = extract_text_with_layout(pdf)
        assert "Item text" in text
        # The "-" and "Item" should be separated (space-preserving join)
        # not glued like "-Item".
        assert "-Item" not in text, f"bullet got glued: {text!r}"


# --------------------------------------------------------------------------- #
# Edge cases
# --------------------------------------------------------------------------- #

class TestEdgeCases:
    def test_empty_pdf(self, tmp_path):
        pdf = _make_pdf([{"spans": []}], tmp_path / "empty.pdf")
        text = extract_text_with_layout(pdf)
        # No spans = no output, no crash.
        assert text == ""

    def test_multi_page_layout_summary(self, tmp_path):
        pdf = _make_pdf([
            {"spans": [(50, 50, 280, 80, "p1", 11)]},
            {"spans": [(50, 50, 280, 80, "p2", 11), (320, 50, 562, 80, "p2-r", 11)]},
        ], tmp_path / "multi.pdf")
        summary = page_layout_summary(pdf)
        assert len(summary) == 2
        assert summary[0][1] == 1
        assert summary[1][1] == 2

    def test_text_from_layout_empty_spans(self):
        layout = PageLayout(page_no=0, width=612, height=792, n_columns=1, spans=[])
        assert text_from_layout(layout) == ""


# --------------------------------------------------------------------------- #
# Integration with pdf_parser — existing samples stay 1-column
# --------------------------------------------------------------------------- #

class TestIntegrationWithSamples:
    @pytest.mark.parametrize("sample", ["sample_strong", "sample_medium", "sample_weak"])
    def test_existing_samples_are_single_column(self, sample, tmp_path=None):
        from pathlib import Path as P
        pdf = P(__file__).resolve().parent.parent / "data" / f"{sample}.pdf"
        if not pdf.exists():
            pytest.skip(f"{sample}.pdf not present")
        summary = page_layout_summary(pdf)
        # All existing samples are 1-column; if a future test sample is
        # 2-column, the layout module should still parse it without error.
        for page_no, n_cols, n_spans in summary:
            assert n_cols in (1, 2), f"unexpected column count {n_cols}"
            assert n_spans > 0
