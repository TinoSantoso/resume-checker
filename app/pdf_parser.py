"""CV parser — extract raw text + naive section segmentation.

Supports PDF (via PyMuPDF, with layout-aware column handling) and DOCX
(via python-docx). Both formats are normalized to the same
``"\\n".join(line)`` shape so downstream section segmentation works
identically.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Union

import pymupdf  # PyMuPDF

from .redactor import redact, unmask


# --------------------------------------------------------------------------- #
# Parsed result container
# --------------------------------------------------------------------------- #

@dataclass
class ParsedCV:
    """Result of parsing a CV file.

    Attributes:
        sections: dict of section_name -> section_text. PII has been
            redacted (replaced with placeholders like ``[EMAIL_1]``).
        pii_map: mapping from placeholder back to original value, so the
            recruiter-facing UI can ``unmask()`` before display.

    Iterating over a ``ParsedCV`` yields ``(section_name, text)`` tuples
    for backward compatibility with code that treated the parse result
    as a dict.
    """

    sections: Dict[str, str] = field(default_factory=dict)
    pii_map: Dict[str, str] = field(default_factory=dict)

    def __iter__(self):
        return iter(self.sections.items())

    def __getitem__(self, key: str) -> str:
        return self.sections[key]

    def __setitem__(self, key: str, value: str) -> None:
        """Allow score-time mutation (e.g. carving Summary out of Header)."""
        self.sections[key] = value

    def __contains__(self, key: str) -> bool:
        return key in self.sections

    def get(self, key: str, default: str = "") -> str:
        """dict.get() compatibility — used by scorer.py."""
        return self.sections.get(key, default)

    def __len__(self) -> int:
        return len(self.sections)

    def keys(self):
        return self.sections.keys()

    def values(self):
        return self.sections.values()

    def items(self):
        return self.sections.items()

    def render_unmasked(self) -> Dict[str, str]:
        """Return sections with original PII restored (for recruiter UI)."""
        return {k: unmask(v, self.pii_map) for k, v in self.sections.items()}

# Heuristic section headers (case-insensitive). Order matters for priority.
SECTION_PATTERNS = {
    "Contact": [
        r"^\s*contact(\s+info(rmation)?)?\s*$",
        r"^\s*personal\s+(info(rmation)?|details)\s*$",
    ],
    "Summary": [
        r"^\s*(professional\s+)?summary\s*$",
        r"^\s*profile\s*$",
        r"^\s*objective\s*$",
        r"^\s*about(\s+me)?\s*$",
    ],
    "Experience": [
        r"^\s*(work\s+)?experience\s*$",
        r"^\s*employment(\s+history)?\s*$",
        r"^\s*professional\s+experience\s*$",
        r"^\s*career\s+history\s*$",
    ],
    "Skills": [
        r"^\s*(technical\s+)?skills\s*$",
        r"^\s*technologies\s*$",
        r"^\s*tech(nical)?\s+stack\s*$",
    ],
    "Education": [
        r"^\s*education(al)?(\s+background)?\s*$",
        r"^\s*academic(\s+background)?\s*$",
    ],
    "Projects": [
        r"^\s*(side\s+)?projects\s*$",
        r"^\s*key\s+projects\s*$",
    ],
    "Certifications": [
        r"^\s*certifications?\s*$",                                # certification / certifications
        r"^\s*licenses?(\s+(&|and)\s+certifications?)?\s*$",       # license / licenses, optionally + certifications
        r"^\s*certifications?\s+(&|and)\s+licenses?\s*$",
    ],
    "Links": [
        r"^\s*(social\s+media|links?|profiles?|online\s+presence)\s*$",
    ],
}


# --------------------------------------------------------------------------- #
# Extractors
# --------------------------------------------------------------------------- #

def extract_text(pdf_path: Union[str, Path]) -> str:
    """Pull all text from a PDF, one paragraph per line.

    Uses layout-aware extraction (app.layout) so 2-column PDFs come out in
    proper reading order. Single-column PDFs produce identical output to
    PyMuPDF's native ``get_text("text")`` for the spans we keep, but the
    layout module is the single source of truth for both.
    """
    from .layout import extract_text_with_layout
    return extract_text_with_layout(pdf_path)


def _extract_docx_text(docx_path: Union[str, Path]) -> str:
    """Pull text from a DOCX, one paragraph per line.

    Uses python-docx. Tables are rendered row-by-row (cells joined with
    " | " so a 2-column layout doesn't smear together). Empty paragraphs
    are dropped, matching the PDF extractor's behavior.

    Bullet-style paragraphs (``List Bullet``, ``List Number``, etc.) are
    prefixed with a ``• `` marker so the downstream experience heuristic
    (which looks for ``^\\s*([-*•●▪]|\\d+[.)])``) can detect them. Without
    this, a real Word-style bulleted experience section would be flagged
    as "paragraph format" and penalized.
    """
    try:
        import docx  # python-docx
    except ImportError as e:  # pragma: no cover - import guard
        raise ImportError(
            "python-docx is required to parse .docx files. "
            "Install it with: pip install python-docx"
        ) from e

    document = docx.Document(str(docx_path))
    lines: list[str] = []

    # python-docx paragraph style names that should be rendered as bullets.
    # Match by case-insensitive substring so locale variants ("Daftar Bullet")
    # are also caught when Word is set to Indonesian.
    _BULLET_STYLE_HINTS = ("list bullet", "list paragraph", "daftar")

    def _is_bullet_style(p) -> bool:
        try:
            name = (p.style.name or "").lower()
        except Exception:
            return False
        return any(hint in name for hint in _BULLET_STYLE_HINTS)

    def _is_numbered_style(p) -> bool:
        try:
            name = (p.style.name or "").lower()
        except Exception:
            return False
        return "list number" in name

    # Walk the document body in order — paragraphs and tables alternate.
    # We use the underlying body element to preserve order.
    from docx.oxml.ns import qn

    body = document.element.body
    for child in body.iterchildren():
        tag = child.tag
        if tag == qn("w:p"):
            # Paragraph — find the matching docx.Paragraph object.
            for p in document.paragraphs:
                if p._element is child:
                    text = p.text.strip()
                    if not text:
                        break
                    if _is_bullet_style(p):
                        lines.append(f"• {text}")
                    elif _is_numbered_style(p):
                        # Numbered list — leave as-is; the heuristic's
                        # `\\d+[.)]` pattern will catch it downstream.
                        lines.append(text)
                    else:
                        lines.append(text)
                    break
        elif tag == qn("w:tbl"):
            # Table — join cells with " | " per row.
            for table in document.tables:
                if table._element is child:
                    for row in table.rows:
                        cells = [cell.text.strip() for cell in row.cells]
                        # Drop empty cells but keep the joiner.
                        non_empty = [c for c in cells if c]
                        if non_empty:
                            lines.append(" | ".join(non_empty))
                    break

    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Section segmentation (format-agnostic; operates on raw text)
# --------------------------------------------------------------------------- #

def _classify_line(line: str) -> str | None:
    """Return section name if line looks like a section header, else None.

    Supports both English and Indonesian section headers (see
    ``app.i18n.SECTION_PATTERNS_ID``).
    """
    low = line.lower().strip()
    for section, patterns in SECTION_PATTERNS.items():
        for pat in patterns:
            if re.match(pat, low):
                return section
    # Indonesian section headers (P1.4)
    from .i18n import SECTION_PATTERNS_ID
    for section, patterns in SECTION_PATTERNS_ID.items():
        for pat in patterns:
            if re.match(pat, low):
                return section
    return None


def segment_sections(raw_text: str) -> Dict[str, str]:
    """Walk text line-by-line, bucket content into detected sections.

    Anything before the first detected header goes into 'Header' (usually
    contact info / name block).
    """
    sections: Dict[str, list[str]] = {
        "Header": [],
        "Contact": [],
        "Summary": [],
        "Experience": [],
        "Skills": [],
        "Education": [],
        "Projects": [],
        "Certifications": [],
        "Links": [],
        "Other": [],
    }
    current = "Header"

    for line in raw_text.splitlines():
        sec = _classify_line(line)
        if sec:
            current = sec
            continue
        sections[current].append(line)

    # Drop empty sections, return as dict[str, str]
    return {k: "\n".join(v).strip() for k, v in sections.items() if v}


# --------------------------------------------------------------------------- #
# Public dispatcher
# --------------------------------------------------------------------------- #

_SUPPORTED_SUFFIXES = {".pdf", ".docx"}


def parse_cv(
    cv_path: Union[str, Path],
    *,
    redact_pii: bool = True,
) -> Union[ParsedCV, Dict[str, str]]:
    """One-shot helper: extract + segment. Supports PDF and DOCX.

    Args:
        cv_path: path to ``.pdf`` or ``.docx`` file.
        redact_pii: when True (default), PII (email, phone, LinkedIn,
            street address, DOB) is replaced with stable placeholders
            and a mapping is kept so the recruiter UI can ``unmask()``
            before display. Set False only for debugging — production
            code should leave redaction on.

    Returns:
        ``ParsedCV`` with ``.sections`` (redacted) and ``.pii_map``.
        Iterating yields ``(section_name, text)`` tuples so callers that
        treated the old dict return value as iterable still work.
    """
    path = Path(cv_path)
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        text = extract_text(path)
    elif suffix == ".docx":
        text = _extract_docx_text(path)
    else:
        raise ValueError(
            f"Unsupported CV format '{suffix}'. Supported: {sorted(_SUPPORTED_SUFFIXES)}"
        )

    sections = segment_sections(text)

    if not redact_pii:
        # Return a ParsedCV with empty map (no unmask possible).
        return ParsedCV(sections=sections, pii_map={})

    # Redact per-section so the mapping accumulates correctly across the
    # whole document (placeholders stay globally unique, not per-section).
    full_redacted = "\n".join(
        f"{name}\n{body}" for name, body in sections.items()
    )
    redacted_text, pii_map = redact(full_redacted)

    # Re-segment after redaction. The section headers themselves don't
    # contain PII so the boundaries are preserved.
    redacted_sections = segment_sections(redacted_text)

    return ParsedCV(sections=redacted_sections, pii_map=pii_map)


if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) < 2:
        print("usage: python pdf_parser.py <cv.pdf|cv.docx>")
        sys.exit(1)
    result = parse_cv(sys.argv[1])
    print(json.dumps(
        {k: v[:200] + ("..." if len(v) > 200 else "") for k, v in result.items()},
        indent=2,
    ))
