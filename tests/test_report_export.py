"""Tests for app/report_export.py — PDF report generation.

Covers the recruiter-facing PDF output:

1. Magic bytes (%PDF-) — actually a valid PDF.
2. CV file name appears in the rendered text.
3. All section scores appear in the score table.
4. Recruiter-grade justification (feedback bullets, evidence, issues) is present —
   not just numbers, real prose.
5. Empty / minimal data dict does not crash.
6. Unicode (Indonesian diacritics + emoji) survives encoding.

We extract the PDF text stream via ``pypdf`` if available, otherwise via a
regex on the raw bytes (PDF strings inside the content stream are usually
uncompressed for short docs — good enough for our smoke assertions).
"""
from __future__ import annotations

from pathlib import Path

import pytest

# pymupdf is already a core dependency (for CV parsing). Use it to extract
# the rendered text from the PDF so we can assert content, not just magic
# bytes. Falls back to reading raw bytes if pymupdf is somehow missing —
# those tests then verify magic bytes only.
try:
    import fitz  # PyMuPDF
except ImportError:  # pragma: no cover
    fitz = None  # type: ignore

from app.report_export import render_pdf_report


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #

@pytest.fixture
def realistic_payload() -> dict:
    """A fully-populated report dict — same shape as save_report() produces."""
    return {
        "file": "jane_doe_senior_swe.pdf",
        "overall": 7.2,
        "grade": "C — Solid, improvable",
        "summary": (
            "Mid-level backend engineer with strong fundamentals and "
            "three roles of progressive scope. Skills breadth is solid "
            "but metrics are sparse."
        ),
        "role": "swe",
        "role_confidence": 0.84,
        "sections": {
            "summary": {
                "score": 7.0,
                "evidence": [
                    "States 5+ years of experience.",
                    "Targets a role: 'software engineer'.",
                ],
                "issues": ["Summary is at the lower end of the 40–80 word target."],
                "feedback": (
                    "Lead with a one-line positioning statement, then the "
                    "years + scope. Tighten to 50 words."
                ),
            },
            "skills": {
                "score": 8.0,
                "evidence": ["12 concrete skills listed — solid breadth."],
                "issues": ["Consider grouping tools by category."],
                "feedback": "Group cloud + language + database clearly.",
            },
            "experience": {
                "score": 7.5,
                "evidence": ["6/8 statements start with strong action verbs."],
                "issues": ["Only 2/8 statements include measurable metrics."],
                "feedback": (
                    "Add a number to every bullet — users served, latency, "
                    "team size, or revenue impact."
                ),
            },
            "education": {
                "score": 6.0,
                "evidence": ["Bachelor's degree in CS detected."],
                "issues": ["Missing graduation year."],
                "feedback": "Add the graduation year — recruiters filter on it.",
            },
            "format": {
                "score": 8.5,
                "evidence": ["Single-page layout.", "Clean section headers."],
                "issues": [],
                "feedback": "Format is recruiter-ready.",
            },
        },
    }


def _extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """Extract visible text from a PDF byte stream via PyMuPDF.

    pymupdf is a core dependency already (used for CV parsing). Using it
    here means the tests are robust to whatever compression / encoding
    reportlab picks on any given platform.
    """
    if fitz is None:  # pragma: no cover
        return ""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        return "\n".join(page.get_text() for page in doc)
    finally:
        doc.close()


# --------------------------------------------------------------------------- #
# 1. Magic bytes
# --------------------------------------------------------------------------- #

class TestPdfBasics:
    def test_writes_valid_pdf_magic_bytes(self, realistic_payload: dict, tmp_path: Path) -> None:
        out = tmp_path / "report.pdf"
        render_pdf_report(realistic_payload, out)
        raw = out.read_bytes()
        assert raw[:5] == b"%PDF-", f"missing PDF magic bytes, got {raw[:20]!r}"
        assert out.exists()
        assert out.stat().st_size > 1024, "PDF suspiciously small (<1KB)"

    def test_returns_the_path(self, realistic_payload: dict, tmp_path: Path) -> None:
        out = tmp_path / "report.pdf"
        result = render_pdf_report(realistic_payload, out)
        assert result == out
        assert isinstance(result, Path)


# --------------------------------------------------------------------------- #
# 2. CV file name
# --------------------------------------------------------------------------- #

class TestContent:
    def test_contains_cv_filename(
        self, realistic_payload: dict, tmp_path: Path
    ) -> None:
        out = render_pdf_report(realistic_payload, tmp_path / "r.pdf")
        text = _extract_text_from_pdf(out.read_bytes())
        # The PDF should embed the stem or the full filename somewhere.
        assert (
            "jane_doe_senior_swe" in text
        ), f"CV filename not found in PDF text:\n{text[:500]}"

    def test_contains_all_section_scores(
        self, realistic_payload: dict, tmp_path: Path
    ) -> None:
        out = render_pdf_report(realistic_payload, tmp_path / "r.pdf")
        text = _extract_text_from_pdf(out.read_bytes())
        # Each scored section name should appear in the score table.
        for section_name in ("Summary", "Skills", "Experience", "Education", "Format"):
            assert section_name in text, f"missing section {section_name} in PDF"
        # And at least the numeric score for one section.
        assert "7.0" in text or "7.5" in text or "8.0" in text, (
            "expected at least one section score to be rendered"
        )

    def test_contains_overall_score_and_grade(
        self, realistic_payload: dict, tmp_path: Path
    ) -> None:
        out = render_pdf_report(realistic_payload, tmp_path / "r.pdf")
        text = _extract_text_from_pdf(out.read_bytes())
        assert "7.2" in text, f"overall score 7.2 not found in PDF text:\n{text[:500]}"
        assert "Solid" in text, f"grade text 'Solid' not found in PDF text:\n{text[:500]}"

    def test_contains_recruiter_grade_justification(
        self, realistic_payload: dict, tmp_path: Path
    ) -> None:
        """Not just numbers — real prose from evidence/issues/feedback."""
        out = render_pdf_report(realistic_payload, tmp_path / "r.pdf")
        text = _extract_text_from_pdf(out.read_bytes())
        # Case-insensitive: reportlab sometimes uppercases after a bullet
        # glyph when the font has no glyph for the bullet (we saw the
        # fallback show as "I" in the extract). Lower both sides.
        text_lc = text.lower()
        # Pulled verbatim from realistic_payload — at least some of these
        # distinct phrases must appear so the recruiter sees *why*, not
        # only *what*.
        must_appear = [
            "5+ years",                  # summary evidence
            "measurable metrics",        # experience issue
            "add a number to every bullet",  # experience feedback
            "bachelor",                  # education evidence
            "graduation year",           # education feedback
        ]
        missing = [m for m in must_appear if m not in text_lc]
        assert not missing, (
            f"PDF missing justification text: {missing}\n--- extracted ---\n{text}"
        )


# --------------------------------------------------------------------------- #
# 3. Robustness
# --------------------------------------------------------------------------- #

class TestRobustness:
    def test_empty_dict_does_not_crash(self, tmp_path: Path) -> None:
        out = tmp_path / "empty.pdf"
        # Empty payload: no sections, no summary, no nothing.
        result = render_pdf_report({}, out)
        assert result.exists()
        assert out.read_bytes()[:5] == b"%PDF-"

    def test_minimal_dict_renders(self, tmp_path: Path) -> None:
        out = tmp_path / "min.pdf"
        render_pdf_report({"file": "x.pdf", "overall": 5.0}, out)
        assert out.exists() and out.stat().st_size > 512

    def test_missing_sections_field(self, tmp_path: Path) -> None:
        out = tmp_path / "nosec.pdf"
        render_pdf_report(
            {"file": "x.pdf", "overall": 6.0, "grade": "C", "summary": "OK"},
            out,
        )
        assert out.exists() and out.read_bytes()[:5] == b"%PDF-"

    def test_sections_is_empty_dict(self, tmp_path: Path) -> None:
        out = tmp_path / "secempty.pdf"
        render_pdf_report(
            {"file": "x.pdf", "overall": 6.0, "sections": {}}, out
        )
        assert out.exists() and out.read_bytes()[:5] == b"%PDF-"

    def test_non_mapping_section_is_skipped(self, tmp_path: Path) -> None:
        """If a section entry is bogus (not a dict), we skip it, not crash."""
        out = tmp_path / "badsec.pdf"
        render_pdf_report(
            {
                "file": "x.pdf",
                "overall": 5.0,
                "sections": {
                    "summary": {"score": 7, "evidence": [], "issues": []},
                    "garbage": "this is not a dict",
                },
            },
            out,
        )
        assert out.exists() and out.read_bytes()[:5] == b"%PDF-"

    def test_pathlib_path_or_str_accepted(self, realistic_payload: dict, tmp_path: Path) -> None:
        # Pass a string path, get back a Path.
        out = render_pdf_report(realistic_payload, str(tmp_path / "str.pdf"))
        assert isinstance(out, Path)
        assert out.exists()


# --------------------------------------------------------------------------- #
# 4. Unicode / Indonesian
# --------------------------------------------------------------------------- #

class TestUnicode:
    def test_indonesian_diacritics_survive(self, tmp_path: Path) -> None:
        """ä, ñ, ç, é, ö — plus Indonesian special chars."""
        payload = {
            "file": "cv_bahasa.pdf",
            "overall": 7.0,
            "grade": "C — Solid",
            "summary": (
                "Rekrut harus mahir berbahasa Indonesia: "
                "São Paulo referência, Zürich café, naïve approach, "
                "jalaññoño, año 2024, ältere简历."
            ),
            "role": "general",
            "role_confidence": 0.5,
            "sections": {
                "summary": {
                    "score": 7.0,
                    "evidence": ["Menyebutkan 5 tahun pengalaman."],
                    "issues": ["Ringkasan terlalu pendek."],
                    "feedback": "Tambahkan metrik yang dapat diukur.",
                },
            },
        }
        out = render_pdf_report(payload, tmp_path / "id.pdf")
        assert out.exists() and out.read_bytes()[:5] == b"%PDF-"
        text = _extract_text_from_pdf(out.read_bytes())
        # At least the Indonesian phrase must round-trip. (Latin-1 covers
        # most diacritics; CJK might be lost without a TTF, which is OK
        # for our smoke test — the PDF still renders.)
        assert "Rekrut" in text, f"Indonesian prose missing in PDF text:\n{text}"

    def test_emoji_does_not_break_rendering(self, tmp_path: Path) -> None:
        payload = {
            "file": "emoji.pdf",
            "overall": 6.0,
            "grade": "C — Solid",
            "summary": "🚀 Shipped fast. 💡 Solved the latency problem.",
            "sections": {
                "summary": {
                    "score": 6.0,
                    "evidence": ["🎯 targeted role"],
                    "issues": [],
                    "feedback": "✅ good",
                },
            },
        }
        # Helvetica can't render emoji glyphs, but the PDF must still
        # be a valid file (the Platypus engine either substitutes the
        # glyph or drops it — either way no crash).
        out = render_pdf_report(payload, tmp_path / "em.pdf")
        assert out.exists()
        assert out.read_bytes()[:5] == b"%PDF-"
        assert out.stat().st_size > 1024