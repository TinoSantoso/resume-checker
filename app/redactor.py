"""PII redaction layer (C1 backlog).

Strips personally-identifiable information from CV text BEFORE it lands in
the vector index or is sent to the LLM. The recruiter-facing UI uses
``unmask()`` to restore the original values when displaying a result.

Design choices:
- Regex-based: no extra ML deps, deterministic, auditable
- Sequential per-category counters (``[EMAIL_1]``, ``EMAIL_2]``...) so a
  single CV with multiple emails gets stable, distinct placeholders
- Idempotent: re-running ``redact()`` on already-redacted text is a no-op
  (the placeholder format is not matched by any PII pattern)
- Whitelist-friendly: version numbers like "Python 3.9" must not match the
  phone regex. We guard via the PHONE pattern (no digit-only sequences
  shorter than 9 chars without a leading ``08`` / ``+62``).

Categories (see ``PII_PATTERNS``):
- EMAIL — RFC-ish, accepts plus/dot in local part
- PHONE — Indonesian mobile (``08`` / ``+62`` prefix, 9–13 digits)
- LINKEDIN — ``linkedin.com/in/<slug>``, with or without protocol
- ADDRESS — common Indonesian street markers (``Jl.``, ``Jalan``, etc.)
- DOB — keyword-triggered (``born``, ``DOB``, ``lahir``, ``tgl lahir``)
  followed by a date expression containing a 4-digit year
"""
from __future__ import annotations

import re
from typing import Dict, Tuple

# --------------------------------------------------------------------------- #
# Pattern registry
# --------------------------------------------------------------------------- #

PII_PATTERNS: Dict[str, str] = {
    # Email — local@domain.tld. Local part: word, dot, plus, hyphen.
    "EMAIL": r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b",

    # Phone — Indonesian mobile numbers.
    #   - prefix: literal "08" or "+62" (with optional space/dash)
    #   - 9 to 13 more digits, optionally separated by space or dash
    #   - NO leading version-number like "Python 3.9" because:
    #       (a) no 08/+62 prefix
    #       (b) only 1–2 digits after the dot
    "PHONE": r"(?:\+62|08)[\s-]?\d{2,4}(?:[\s-]?\d{3,4}){1,3}",

    # LinkedIn profile URL — optional protocol, optional www.
    "LINKEDIN": r"(?:https?://)?(?:www\.)?linkedin\.com/in/[\w-]+",

    # Street address — must start with a known Indonesian street marker
    # followed by a name (greedy, stops at line/semicolon/comma). Match
    # the whole line up to the next stop char.
    "ADDRESS": (
        r"(?:Jl\.?|Jalan|Gedung|Komp(?:leks)?)\s+[A-Za-z0-9][^\n,;]*"
    ),

    # DOB — keyword followed by a date expression containing a 4-digit year.
    # Accepts:
    #   - "Born 12 May 1990"
    #   - "DOB: 01/01/1995"        (date with slashes, no space)
    #   - "lahir: 17 Agustus 1945" (Indonesian)
    #   - "DOB 1990"               (year only)
    # Strategy: keyword + any separator (: or whitespace), then any chars
    # (including spaces, slashes, dashes) until the 4-digit year. Use a
    # lazy quantifier so the match stops at the first 4-digit year.
    "DOB": (
        r"(?:\b(?:born|DOB|lahir|tgl lahir)\b)[:\s]+"
        r"[A-Za-z0-9/\-\. ]{0,40}?\d{4}"
    ),
}


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #

def redact(text: str) -> Tuple[str, Dict[str, str]]:
    """Strip PII from ``text``, returning ``(redacted, mapping)``.

    ``mapping`` maps each placeholder (``"[EMAIL_1]"``, ``"[PHONE_2]"`` ...)
    back to the original PII value, so the recruiter UI can ``unmask()``
    before display.

    Idempotent: running on already-redacted text returns the same output
    because the placeholders are not matched by any pattern.
    """
    if not text:
        return text, {}

    mapping: Dict[str, str] = {}
    counters: Dict[str, int] = {label: 0 for label in PII_PATTERNS}
    redacted = text

    for label, pattern in PII_PATTERNS.items():
        compiled = re.compile(pattern, flags=re.IGNORECASE)

        def _repl(match: re.Match, _label: str = label) -> str:
            counters[_label] += 1
            placeholder = f"[{_label}_{counters[_label]}]"
            mapping[placeholder] = match.group(0)
            return placeholder

        redacted = compiled.sub(_repl, redacted)

    return redacted, mapping


def unmask(text: str, mapping: Dict[str, str]) -> str:
    """Restore original PII placeholders in ``text`` using ``mapping``.

    Replacement is done in mapping-insertion order (Python 3.7+ dict order).
    If a placeholder appears multiple times, all occurrences are replaced.
    """
    if not text or not mapping:
        return text
    for placeholder, original in mapping.items():
        text = text.replace(placeholder, original)
    return text