"""Deterministic per-section scorer.

We don't trust a 3B model to give reliable numeric scores. Heuristics do.
Each section gets 0–10 based on rule-derived signals, plus a list of
*evidence* items (what passed / what failed) the LLM uses to write feedback.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Dict, List

from .pdf_parser import parse_cv
from .weights import SECTION_WEIGHTS_BY_ROLE

if TYPE_CHECKING:
    from .matcher import JDMatchReport

# Common weak phrases / cliches to flag.
# English baseline; Indonesian equivalents are added at runtime in
# _score_experience() so we don't bloat the static set for the common
# English-only path. See app.i18n.WEAK_VERBS_ID.
WEAK_VERBS = {
    "responsible for", "worked on", "helped", "assisted", "was tasked",
    "duties included", "involved in", "participated in",
}
STRONG_VERB_HINTS = {
    "led", "architected", "shipped", "delivered", "designed", "built",
    "reduced", "increased", "improved", "optimized", "scaled", "launched",
    "created", "owned", "drove", "negotiated", "mentored", "automated",
    "deployed", "migrated", "implemented", "established", "streamlined",
}

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
PHONE_RE = re.compile(r"(\+?\d[\d\s().-]{7,}\d)")
URL_RE = re.compile(r"(https?://|www\.)\S+|linkedin\.com/\S+|github\.com/\S+", re.I)
METRIC_RE = re.compile(
    r"(\d+(\.\d+)?\s*%|\$\s*\d|\d+\s*(users|customers|requests|qps|rps|ms|s|x)|"
    r"team\s+of\s+\d+|over\s+\d+|\d+\s*(years|yrs|months))",
    re.I,
)


@dataclass
class SectionScore:
    name: str
    score: float = 0.0
    max: float = 10.0
    evidence: List[str] = field(default_factory=list)  # observations
    issues: List[str] = field(default_factory=list)  # what's wrong
    strengths: List[str] = field(default_factory=list)  # what's good


@dataclass
class CVReport:
    sections: Dict[str, SectionScore]
    overall: float = 0.0
    grade: str = ""
    # Optional JD-aware data. When score_cv() is called without a JD, this
    # stays None and the rest of the report is identical to v0.1.
    jd_match: "JDMatchReport | None" = None
    jd_grade: str = ""
    # Role-specific KB: which rubric variant was used to weight the
    # sections. ``"general"`` = default. Populated by score_cv().
    role: str = "general"
    role_confidence: float = 0.0


# --------------------------------------------------------------------------- #
# Per-section scorers
# --------------------------------------------------------------------------- #


# Lines that look like a CV summary headline: a role title followed by a
# colon (e.g. "Full Stack Developer:" or "Senior Data Engineer :").
# The colon pattern is loose: any line where a recognizable job title sits
# before a colon AND the post-colon tail is >= 4 words. We use this to
# detect inline summaries that don't have a dedicated "Summary" section.
_ROLE_LINE_RE = re.compile(
    r"""^(
        (?:senior|junior|lead|principal|staff|chief)?\s*
        (?:software|full[\s-]?stack|back[\s-]?end|front[\s-]?end|
           data|machine[\s-]?learning|ml|devops|cloud|site[\s-]?reliability|
           product|project|engineering|qa|test|sdet|security|android|
           ios|mobile|web|platform|infrastructure|security|network|
           data\s+science|data\s+analyst|data\s+engineer|
           ux|ui|ux/ui|graphic|technical|it|systems?)\s*
        (?:developer|engineer|scientist|analyst|designer|architect|
           manager|consultant|specialist|lead|administrator|programmer|
           researcher|officer|associate|intern|coordinator)
    )\s*[:\-]\s*\S.*$""",
    re.VERBOSE | re.IGNORECASE,
)

# Lines that look like a years-of-experience headline (English + Indonesian).
# e.g. "8 years experience in ...", "5+ years building ...", "3 tahun pengalaman"
_YEARS_LINE_RE = re.compile(
    r"""\b(
        \d+\s*\+?\s*(?:years?|yrs?)         # 8 years, 5+ years, 10 yrs
        |
        \d+\s*tahun                         # 8 tahun
    )\b""",
    re.IGNORECASE | re.VERBOSE,
)


def _is_role_or_years_line(line: str) -> bool:
    """True for a single-line summary headline (role+colon or years+experience).

    Used as one of the triggers in ``_looks_like_summary`` to handle
    short summary blocks that are just a role title or just a years
    statement (no 8+ word paragraph).
    """
    s = line.strip()
    if not s or len(s.split()) < 3:
        return False
    if _ROLE_LINE_RE.match(s):
        return True
    if _YEARS_LINE_RE.search(s) and len(s.split()) <= 12:
        return True
    return False


def _is_substantive_line(line: str) -> bool:
    """True for a paragraph-style summary line (>= 8 words)."""
    return len(line.strip().split()) >= 8


def _looks_like_summary(text: str) -> bool:
    """Heuristic: a header block is a summary if it contains ANY of:
    - a substantive paragraph (>=8 words, not contact info)
    - a role-title line ("Senior Engineer: ...")
    - a years-of-experience headline ("8 years experience ...")
    """
    if not text:
        return False
    # Drop obvious contact lines.
    lines = [
        ln.strip() for ln in text.splitlines()
        if ln.strip() and not EMAIL_RE.search(ln) and not PHONE_RE.search(ln)
        and not URL_RE.search(ln) and len(ln.strip()) > 2
    ]
    if any(_is_substantive_line(ln) for ln in lines):
        return True
    if any(_is_role_or_years_line(ln) for ln in lines):
        return True
    return False


def _carve_summary_from_header(header: str) -> tuple[str, str]:
    """Split ``header`` into ``(kept, summary)`` parts.

    Rules:
    1. Drop obvious contact/URL/very-short lines from consideration — they
       stay in the kept side.
    2. The first line that is a role-with-colon or a years-of-experience
       headline starts the summary.
    3. After that first summary line, any consecutive ``_is_substantive_line``
       (>=8 words) is appended to the summary, but we cap the run at the
       first blank line or obvious non-summary line.
    4. The carved lines are removed from the kept side and returned as
       the new Summary text.

    Returns ``(new_header, summary)``. ``summary`` may be empty if no
    summary-style content was found.
    """
    raw_lines = header.splitlines()
    # Classify each line.
    candidates: list[tuple[int, str, str]] = []  # (idx, classification, line)
    for i, ln in enumerate(raw_lines):
        s = ln.strip()
        if not s:
            candidates.append((i, "blank", s))
            continue
        if EMAIL_RE.search(s) or PHONE_RE.search(s) or URL_RE.search(s):
            candidates.append((i, "contact", s))
            continue
        if len(s) <= 2:
            candidates.append((i, "short", s))
            continue
        if _is_role_or_years_line(s):
            candidates.append((i, "headline", s))
        elif _is_substantive_line(s):
            candidates.append((i, "para", s))
        else:
            candidates.append((i, "other", s))

    # Find the first headline OR para — that's where the summary starts.
    start = next(
        (i for i, (_, cls, _) in enumerate(candidates) if cls in ("headline", "para")),
        None,
    )
    if start is None:
        return header, ""

    # Extend the run across consecutive headline/para lines, stopping at
    # the first blank or "other" line.
    end = start
    for j in range(start + 1, len(candidates)):
        cls = candidates[j][1]
        if cls in ("headline", "para"):
            end = j
        else:
            break

    kept_indices = {c[0] for i, c in enumerate(candidates) if i < start or i > end}
    kept_lines = [ln for i, ln in enumerate(raw_lines) if i in kept_indices]
    summary_lines = [candidates[i][2] for i in range(start, end + 1)]
    return "\n".join(kept_lines).strip(), "\n".join(summary_lines).strip()


def _score_contact(text: str, header: str) -> SectionScore:
    s = SectionScore(name="Contact")
    if not text and not header:
        s.score = 0
        s.issues.append("No contact information detected.")
        return s

    blob = f"{header}\n{text}".lower()
    email = EMAIL_RE.search(blob)
    phone = PHONE_RE.search(blob)
    # findall with one capturing group returns a list of tuples; flatten to strings.
    raw_urls = URL_RE.findall(blob)
    urls = []
    for u in raw_urls:
        if isinstance(u, tuple):
            urls.append("".join(u))
        else:
            urls.append(u)

    score = 0
    if email:
        score += 3
        s.evidence.append(f"Email found: {email.group(0)}")
    else:
        s.issues.append("Missing email address.")
    if phone:
        score += 3
        s.evidence.append(f"Phone found.")
    else:
        s.issues.append("Missing phone number.")
    if any(("linkedin" in u.lower()) for u in urls) or ("linkedin" in (header + text).lower()):
        score += 2
        s.evidence.append("LinkedIn URL present.")
    else:
        s.issues.append("No LinkedIn URL detected.")
    if any(("github" in u.lower()) for u in urls) or ("github" in (header + text).lower()):
        score += 1
        s.evidence.append("GitHub/portfolio URL present.")

    # Penalize unprofessional email
    if email and re.search(r"(hotmama|sexy|prince|love|player)\d*@", email.group(0), re.I):
        s.issues.append("Email handle looks unprofessional.")
        score -= 2

    s.score = max(0, min(10, score))
    return s


def _score_summary(text: str) -> SectionScore:
    s = SectionScore(name="Summary")
    if not text.strip():
        s.score = 0
        s.issues.append("No professional summary section found.")
        return s

    words = text.split()
    word_count = len(words)

    if word_count < 20:
        s.score = 2
        s.issues.append(f"Summary too short ({word_count} words). Aim for 40–80.")
    elif word_count > 120:
        s.score = 4
        s.issues.append(f"Summary too long ({word_count} words). Aim for 40–80.")
    else:
        s.score = 7
        s.evidence.append(f"Summary length is appropriate ({word_count} words).")

    # Does it mention years of experience?
    # Bilingual: "years" / "yrs" (EN) or "tahun" (ID) (P1.4).
    if re.search(r"\b(\d+)\+?\s*(years?|yrs?|tahun)\b", text, re.I):
        s.evidence.append("States years of experience.")
        s.score = min(10, s.score + 1.5)
    else:
        s.issues.append("Does not state years of experience.")

    # Does it name a target role?
    # Bilingual: matches English role nouns + Indonesian equivalents (P1.4).
    from .i18n import combined_role_keywords
    has_role = re.search(
        r"\b(" + "|".join(re.escape(w) for w in combined_role_keywords()) + r")\b",
        text,
        re.I,
    )
    if has_role:
        s.evidence.append(f"Targets a role: '{has_role.group(0)}'.")
        s.score = min(10, s.score + 1.5)
    else:
        s.issues.append("No target role / job title mentioned.")

    s.score = round(max(0, min(10, s.score)), 1)
    return s


def _score_experience(text: str) -> SectionScore:
    s = SectionScore(name="Experience")
    if not text.strip():
        s.score = 0
        s.issues.append("No experience section found.")
        return s

    # Check if experience is in bullet format or paragraph format.
    bullet_pattern = re.compile(r"^\s*([-*•●▪]|\d+[.)])\s+", re.M)
    has_bullets = bool(bullet_pattern.search(text))

    # Split into roles by detecting role/company/date headers.
    # A role header is a short line (<= 12 words) that contains a year.
    role_headers = []
    lines = text.splitlines()
    for i, line in enumerate(lines):
        s_line = line.strip()
        if not s_line:
            continue
        if re.search(r"\b(20\d{2}|19\d{2})\b", s_line) and len(s_line.split()) <= 15:
            role_headers.append((i, s_line))

    n_roles = max(1, len(role_headers))

    if has_bullets:
        # Split into bullets — tolerate -, *, •, or numbered lines.
        bullets: list[str] = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            # Strip bullet marker.
            cleaned = re.sub(r"^([-*•●▪]|\d+[.)])\s*", "", line)
            if len(cleaned.split()) >= 3:  # ignore stray short lines (headers, dates)
                bullets.append(cleaned)
            else:
                # Short lines: probably a role/company header.
                bullets.append(f"__META__:{cleaned}")

        n_bullets = sum(1 for b in bullets if not b.startswith("__META__"))
        real_bullets = [b for b in bullets if not b.startswith("__META__")]
    else:
        # Paragraph format: treat each sentence as a "statement" but cap count.
        # Split on sentence boundaries.
        sentences = re.split(r"(?<=[.!?])\s+", text)
        sentences = [s.strip() for s in sentences if len(s.strip().split()) >= 6]
        # Subtract ~1 sentence per role for the opening "As a X..." intro.
        real_bullets = sentences
        n_bullets = len(real_bullets)

    if n_bullets == 0:
        s.score = 1
        s.issues.append("No bullet points or statements detected.")
        return s

    # 1) Action verb check (first strong verb anywhere in statement).
    # Use bilingual set so Indonesian CVs are scored correctly (P1.4).
    from .i18n import combined_strong_verbs, combined_weak_verbs
    strong_verbs = combined_strong_verbs()
    weak_verbs = combined_weak_verbs()

    weak_hits = 0
    strong_hits = 0
    for b in real_bullets:
        low = b.lower()
        if any(low.startswith(w) for w in weak_verbs) or any(w in low.split()[:3] for w in weak_verbs):
            weak_hits += 1
        first_word = re.split(r"\s+", low.strip(), maxsplit=1)[0]
        if first_word.rstrip(".,;:") in strong_verbs:
            strong_hits += 1

    verb_ratio = strong_hits / max(1, n_bullets)

    if verb_ratio >= 0.7:
        s.evidence.append(f"{strong_hits}/{n_bullets} statements start with strong action verbs.")
        s.score = 7
    elif verb_ratio >= 0.4:
        s.score = 5
        s.issues.append(f"Only {strong_hits}/{n_bullets} statements start with strong action verbs.")
    else:
        s.score = 2
        s.issues.append(f"Only {strong_hits}/{n_bullets} statements start with strong action verbs. Most are weak/passive.")
    if weak_hits:
        s.issues.append(f"{weak_hits} statement(s) start with weak phrases like 'Responsible for' or 'Helped'.")

    # 2) Metric check
    metric_hits = sum(1 for b in real_bullets if METRIC_RE.search(b))
    metric_ratio = metric_hits / max(1, n_bullets)
    if metric_ratio >= 0.6:
        s.evidence.append(f"{metric_hits}/{n_bullets} statements include measurable metrics.")
        s.score += 2.5
    elif metric_ratio >= 0.3:
        s.score += 1.5
        s.issues.append(f"Only {metric_hits}/{n_bullets} statements contain metrics — add more.")
    else:
        s.issues.append(f"Only {metric_hits}/{n_bullets} statements contain metrics. Add numbers, percentages, or scale to every bullet.")

    # 3) Format penalty: if paragraph format, suggest bullets.
    if not has_bullets:
        s.score = max(0, s.score - 2)
        s.issues.append("Experience is written in paragraph format. Convert to bullet points — recruiters scan, they don't read prose.")

    # 4) Roles-per-CV (sanity: 3+ roles is healthy)
    if n_roles >= 3:
        s.evidence.append(f"{n_roles} roles detected.")

    s.score = round(max(0, min(10, s.score)), 1)
    return s


def _score_skills(text: str) -> SectionScore:
    s = SectionScore(name="Skills")
    if not text.strip():
        s.score = 0
        s.issues.append("No skills section found.")
        return s

    # Tokenize: comma, pipe, newline.
    raw_tokens = re.split(r"[,;|\n•·]+", text)
    skills = [t.strip() for t in raw_tokens if t.strip() and len(t.strip()) <= 40]
    n = len(skills)

    # Filter vague soft-skill noise.
    vague = {"hard worker", "team player", "problem solving", "problem-solving",
             "self motivated", "self-motivated", "fast learner", "passionate",
             "detail oriented", "detail-oriented", "good communication"}
    concrete = [sk for sk in skills if sk.lower() not in vague and not sk.lower().startswith("etc")]

    # ---- B1: canonical-skill enrichment via skill_dictionary ----
    # Naive comma-split treats "AWS" and "Amazon Web Services" as two
    # different skills and counts "aws, aws" twice. The dictionary
    # collapses aliases and case variants to a canonical name, and
    # lets us show category breakdown ("3 Cloud, 2 Database").
    from .skill_dictionary import extract_skills, skill_category as _cat

    canonical_found = extract_skills(text)
    by_category: dict = {}
    for skill in canonical_found:
        cat = _cat(skill) or "Other"
        by_category[cat] = by_category.get(cat, 0) + 1
    canonical_count = len(canonical_found)

    if n == 0:
        s.score = 1
        s.issues.append("No skills detected — try a comma-separated list.")
        return s

    # Ponytail: score by canonical coverage (alias-normalized, recognized),
    # NOT raw token count. Counting tokens rewards shallow breadth —
    # "React, Git, Docker, Agile, Scrum" outscores a senior's "Kotlin,
    # Coroutines, Flow, Dagger, gRPC". Pearson -0.126 in v0.4 because of
    # exactly this. canonical_count filters unknown / vague tokens.
    canonical_count = len(canonical_found)
    vague_hits = [sk for sk in skills if sk.lower() in vague]
    vague_ratio = len(vague_hits) / max(1, n)

    if canonical_count < 3:
        s.score = 3
        s.issues.append(
            f"Only {canonical_count} recognized technical skills found "
            f"(of {n} listed). List named tools/tech — the scorer checks "
            "alias-normalized coverage, not raw count."
        )
    elif canonical_count < 8:
        s.score = 6
        s.evidence.append(f"{canonical_count} recognized skills listed.")
        s.issues.append("Consider adding 5–10 more role-relevant tools.")
    else:
        s.score = 8
        s.evidence.append(
            f"{canonical_count} recognized skills listed — solid breadth."
        )

    # Soft-skill noise penalty: applies on top of the canonical score.
    if vague_ratio >= 0.5:
        s.score = max(0, s.score - 2)
        s.issues.append(
            f"{int(vague_ratio * 100)}% of listed skills are vague phrases "
            f"({', '.join(vague_hits[:3])}). Replace with named tools."
        )
    elif vague_ratio >= 0.25:
        s.score = max(0, s.score - 1)

    # B1: surface canonical detection evidence (only when dictionary
    # found something the naive split didn't, or when category mix is
    # notably richer than the raw count suggests).
    if canonical_count and canonical_count < len(concrete):
        s.evidence.append(
            f"After alias normalization: {canonical_count} unique recognized skills "
            f"(vs {len(concrete)} raw tokens)."
        )
    if by_category:
        cat_breakdown = ", ".join(
            f"{cnt} {cat}" for cat, cnt in sorted(by_category.items(), key=lambda x: -x[1])
        )
        s.evidence.append(f"By category: {cat_breakdown}.")

    # Grouping check: presence of category headers.
    if re.search(r"\b(languages|frameworks|tools|databases|cloud|platforms)\b", text, re.I):
        s.evidence.append("Skills appear to be grouped by category.")
        s.score = min(10, s.score + 1)

    s.score = round(max(0, min(10, s.score)), 1)
    return s


def _score_education(text: str) -> SectionScore:
    s = SectionScore(name="Education")
    if not text.strip():
        s.score = 0
        s.issues.append("No education section found.")
        return s

    # Match degree: word-bounded keywords OR letter-dot-letter-dot abbreviations
    # (e.g., B.S., M.S., B.A., Ph.D.). Period inside an abbreviation is NOT a
    # word-boundary break in user-facing text, so we use lookarounds.
    has_degree = re.search(
        r"\b(?:bachelor|master|phd|mba|doctorate|sarjana|magister|"
        r"b\.?\s?a\.?|b\.?\s?s\.?|m\.?\s?a\.?|m\.?\s?s\.?|"
        r"ph\.?\s?d\.?)\b",
        text,
        re.I,
    )
    has_year = re.search(r"\b(20\d{2}|19\d{2})\b", text)
    has_institution = len(text.split()) >= 5

    score = 0
    if has_degree:
        score += 4
        s.evidence.append(f"Degree mentioned.")
    else:
        s.issues.append("No clear degree title detected.")
    if has_year:
        score += 3
        s.evidence.append("Graduation year present.")
    else:
        s.issues.append("No graduation year found.")
    if has_institution:
        score += 3
        s.evidence.append("Institution appears to be listed.")
    else:
        s.issues.append("Institution not clearly listed.")

    s.score = round(max(0, min(10, score)), 1)
    return s


def _score_length_formatting(raw_text: str) -> SectionScore:
    """Approximate via word count and presence of section markers."""
    s = SectionScore(name="Length_Formatting")
    words = raw_text.split()
    n_words = len(words)

    if n_words < 200:
        s.score = 3
        s.issues.append(f"CV is very short ({n_words} words). Likely missing content.")
    elif n_words < 400:
        s.score = 7
        s.evidence.append(f"Concise ({n_words} words).")
    elif n_words <= 900:
        s.score = 9
        s.evidence.append(f"Length appropriate ({n_words} words).")
    elif n_words <= 1300:
        s.score = 6
        s.issues.append(f"CV is getting long ({n_words} words). Trim if under 7 years experience.")
    else:
        s.score = 4
        s.issues.append(f"CV is too long ({n_words} words). Cut to 1 page if <7 yrs exp, 2 pages max.")

    # Detect obvious ATS-hostile elements (we can't see formatting but can flag
    # if bullets are missing entirely — sometimes a sign of a poorly-formatted PDF).
    has_bullets = bool(re.search(r"^[-*•●▪]", raw_text, re.M))
    if has_bullets:
        s.evidence.append("Bullet points detected.")
    else:
        s.issues.append("No bullet markers detected — CV may read as a wall of text.")

    return s


# --------------------------------------------------------------------------- #
# Orchestrator
# --------------------------------------------------------------------------- #

def grade_for(overall: float) -> str:
    if overall >= 9:
        return "A — Excellent"
    if overall >= 8:
        return "B — Strong"
    if overall >= 6.5:
        return "C — Solid, improvable"
    if overall >= 5:
        return "D — Weak"
    return "F — Needs rewrite"


def score_cv(
    pdf_path: str,
    jd_text: str | None = None,
    role: str | None = None,
) -> CVReport:
    """Score a CV, optionally against a Job Description and/or role-specific rubric.

    When ``jd_text`` is provided, the report also includes a JDMatchReport
    (keyword coverage, role/years alignment, top gaps), and the Skills +
    Summary section scores are adjusted to reflect JD coverage.

    When ``jd_text`` is None or empty, behavior is identical to v0.1.

    When ``role`` is provided (``"general"``, ``"swe"``, ``"data"``, or
    ``"pm"``), the per-section weighting comes from that role's rubric
    instead of the general default. When ``role`` is None, we auto-detect
    from the CV using ``role_detector.detect_role_from_sections`` and
    fall back to ``"general"`` if confidence is too low.
    """
    sections = parse_cv(pdf_path)
    raw = "\n".join(sections.values())

    # ----- Role detection (P2.0 — task #5) -----
    # Done before scoring weights are computed. ``role`` parameter wins
    # if provided; otherwise we detect from the segmented sections.
    role_confidence = 0.0
    if role is None:
        # Imported here to avoid a circular import (role_detector doesn't
        # import scorer, but we keep this module's import surface small).
        from .role_detector import detect_role_from_sections
        role, role_confidence = detect_role_from_sections(
            skills=sections.get("Skills", ""),
            summary=sections.get("Summary", ""),
            header=sections.get("Header", ""),
            experience=sections.get("Experience", ""),
        )
    else:
        # User-supplied role: treat as high confidence (they know best).
        role_confidence = 1.0

    # Validate role name (defensive — silent fallback is worse than a crash here).
    if role not in SECTION_WEIGHTS_BY_ROLE:
        raise ValueError(
            f"unknown role '{role}'. Supported: {list(SECTION_WEIGHTS_BY_ROLE)}"
        )

    # Fallback 1: Summary not detected as its own section — check if Header
    # block contains a substantive paragraph, a role-with-colon headline,
    # or a years-of-experience statement (i.e. summary is inline).
    if not sections.get("Summary", "").strip() and _looks_like_summary(sections.get("Header", "")):
        new_header, carved = _carve_summary_from_header(sections["Header"])
        if carved:
            sections["Summary"] = carved
            sections["Header"] = new_header

    # Fallback 2: Links section merged into Contact scoring if present.
    links_text = sections.get("Links", "")
    contact_text = (sections.get("Contact", "") + "\n" + sections.get("Header", "") + "\n" + links_text)

    scores: Dict[str, SectionScore] = {
        "Contact": _score_contact(contact_text, ""),
        "Summary": _score_summary(sections.get("Summary", "")),
        "Experience": _score_experience(sections.get("Experience", "")),
        "Skills": _score_skills(sections.get("Skills", "")),
        "Education": _score_education(sections.get("Education", "")),
        "Length_Formatting": _score_length_formatting(raw),
    }

    # ----- Optional JD-aware adjustment (P1.2) -----
    jd_match = None
    jd_grade = ""
    if jd_text and jd_text.strip():
        # Imported here to keep scorer importable without jd_parser deps in v0.1 callers.
        from .jd_parser import parse_jd
        from .matcher import match_cv_to_jd

        jd_match = match_cv_to_jd(sections, parse_jd(jd_text))

        # Skills penalty: if half the required skills are missing, deduct up to 3 points.
        if jd_match.required_total > 0:
            gap_ratio = 1.0 - jd_match.required_match_ratio
            penalty = round(gap_ratio * 3.0, 1)
            if penalty > 0:
                scores["Skills"].score = max(
                    0.0, round(scores["Skills"].score - penalty, 1)
                )
                scores["Skills"].issues.append(
                    f"Missing {len(jd_match.required_missing_list)} of "
                    f"{jd_match.required_total} required JD skills "
                    f"({jd_match.required_match_ratio:.0%} coverage). "
                    f"Top gaps: {', '.join(jd_match.top_gaps) or 'n/a'}."
                )

        # Summary bonus: +1 if role title matches JD role.
        if jd_match.role_match and scores["Summary"].score < 10:
            scores["Summary"].score = min(10.0, round(scores["Summary"].score + 1, 1))
            scores["Summary"].evidence.append(
                "Role title aligns with the Job Description."
            )

        # Years gap surfaced as a new issue on the Experience section.
        if jd_match.years_gap > 0:
            scores["Experience"].issues.append(
                f"Job Description asks for {jd_match.years_required}+ years; "
                f"CV may fall short by ~{jd_match.years_gap} year(s)."
            )

        jd_grade = grade_for(jd_match.overall_jd_score)

    # Per-section weights — single source of truth: kb/rubrics/<role>.json.
    # Regenerate app/weights.py via `python3 scripts/build_weights.py`.
    # Different roles weight the same section differently (e.g. PM weights
    # Skills low; SWE/Data weight Skills high).
    weights = SECTION_WEIGHTS_BY_ROLE[role]
    total_w = sum(weights.get(k, 0.0) for k in scores)
    if total_w <= 0:
        # Defensive fallback if weights module is misconfigured.
        total_w = 1.0
    overall = sum(scores[k].score * weights.get(k, 0.0) for k in scores) / total_w

    report = CVReport(
        sections=scores,
        overall=round(overall, 1),
        grade=grade_for(overall),
        jd_match=jd_match,
        jd_grade=jd_grade,
        role=role,
        role_confidence=role_confidence,
    )
    return report


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("usage: python scorer.py <cv.pdf>")
        sys.exit(1)
    rep = score_cv(sys.argv[1])
    print(f"\nOVERALL: {rep.overall}/10  →  {rep.grade}\n")
    for name, s in rep.sections.items():
        print(f"  {name:<20} {s.score:>5.1f}/10")
        for e in s.evidence:
            print(f"     ✓ {e}")
        for i in s.issues:
            print(f"     ✗ {i}")