"""CV ↔ Job Description matcher.

Compares a parsed CV (sections dict from pdf_parser) against a parsed JD
(from jd_parser). Produces a JDMatchReport with:

- ``required_match_ratio``: 0–1, fraction of required skills present in CV
- ``required_matched``: list of required skills found in CV
- ``required_missing``: list of required skills NOT in CV
- ``nice_matched`` / ``nice_missing``: same for nice-to-haves
- ``section_distribution``: where in the CV each matched skill lives
  (useful to flag "matched but buried in Skills section, not in Experience")
- ``years_gap``: positive if CV is short of required years
- ``role_match``: True if CV Summary role title matches JD role title
- ``overall_jd_score``: 0–10, derived heuristic combining above

Heuristics only, no LLM. The LLM in feedback.py can use this as input.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Set

from .jd_parser import JDParsed


# --------------------------------------------------------------------------- #
# Dataclasses
# --------------------------------------------------------------------------- #

@dataclass
class SkillLocation:
    """One instance of a skill being present in a CV section."""
    section: str
    snippet: str = ""   # ~10 words of context around the match


@dataclass
class JDMatchReport:
    role_match: bool = False
    years_gap: int = 0          # positive = CV short of required years
    years_required: int = 0     # copied from JDParsed for convenience

    required_total: int = 0
    required_matched: int = 0
    required_match_ratio: float = 0.0
    required_matched_list: List[str] = field(default_factory=list)
    required_missing_list: List[str] = field(default_factory=list)

    nice_total: int = 0
    nice_matched: int = 0
    nice_match_ratio: float = 0.0
    nice_matched_list: List[str] = field(default_factory=list)
    nice_missing_list: List[str] = field(default_factory=list)

    # Map: skill -> list of locations in CV
    section_distribution: Dict[str, List[SkillLocation]] = field(default_factory=dict)

    # 0–10, weighted blend of required + nice + years + role
    overall_jd_score: float = 0.0

    @property
    def top_gaps(self) -> List[str]:
        """Top 3-5 missing required skills, in JD-frequency order."""
        return self.required_missing_list[:5]


# --------------------------------------------------------------------------- #
# Match helpers
# --------------------------------------------------------------------------- #

def _text_contains_skill(text: str, skill: str) -> bool:
    if not text:
        return False
    pattern = r"\b" + re.escape(skill.lower()) + r"\b"
    return re.search(pattern, text.lower()) is not None


def _snippet(text: str, skill: str, window: int = 6) -> str:
    """Pull ~`window` words of context around the first match of `skill`."""
    if not text:
        return ""
    low = text.lower()
    pattern = r"\b" + re.escape(skill.lower()) + r"\b"
    m = re.search(pattern, low)
    if not m:
        return ""
    words = text.split()
    # Find the word index corresponding to the match start.
    char_pos = m.start()
    word_idx = len(text[:char_pos].split())
    start = max(0, word_idx - window)
    end = min(len(words), word_idx + window + 1)
    return " ".join(words[start:end])


# --------------------------------------------------------------------------- #
# Main match
# --------------------------------------------------------------------------- #

def match_cv_to_jd(cv_sections: Dict[str, str], jd: JDParsed) -> JDMatchReport:
    """Compute JD match signals for a parsed CV.

    Args:
        cv_sections: output of pdf_parser.parse_cv() — {section_name: text}.
        jd: a JDParsed instance.
    """
    rep = JDMatchReport()

    if not jd.has_minimum_info:
        # No useful JD info — return empty report with overall=0.
        return rep

    # ---------- Role title match ----------
    # Bilingual role token matching (P1.4): strip English seniority words
    # AND Indonesian equivalents, then check token overlap.
    cv_role_text = (
        cv_sections.get("Summary", "") + " " + cv_sections.get("Header", "")
    ).lower()
    if jd.role_title and cv_role_text.strip():
        from .i18n import combined_role_keywords
        seniority_strip = {
            "senior", "junior", "staff", "principal", "lead", "intern",
            "magang", "tamatan", "fresh", "graduate",
        }
        jd_role_tokens = [
            t.lower() for t in re.findall(r"[A-Za-z]+", jd.role_title)
            if t.lower() not in seniority_strip
        ]
        # Also keep tokens that are in combined_role_keywords (e.g. "lead"
        # appears in role keywords but we still want to strip from seniority).
        jd_role_tokens = [t for t in jd_role_tokens if t in combined_role_keywords()]
        if jd_role_tokens:
            hits = sum(1 for t in jd_role_tokens if t in cv_role_text)
            rep.role_match = hits >= max(1, len(jd_role_tokens) // 2)

    # ---------- Skill match (required + nice) ----------
    rep.required_total = len(jd.required_skills)
    rep.nice_total = len(jd.nice_to_have)

    def _scan(skill_list: List[str]) -> tuple[List[str], List[str], Dict[str, List[SkillLocation]]]:
        matched: List[str] = []
        missing: List[str] = []
        dist: Dict[str, List[SkillLocation]] = {}
        for skill in skill_list:
            locations: List[SkillLocation] = []
            for sec_name, sec_text in cv_sections.items():
                if _text_contains_skill(sec_text, skill):
                    locations.append(
                        SkillLocation(section=sec_name, snippet=_snippet(sec_text, skill))
                    )
            if locations:
                matched.append(skill)
                dist[skill] = locations
            else:
                missing.append(skill)
        return matched, missing, dist

    req_matched, req_missing, req_dist = _scan(jd.required_skills)
    nice_matched, nice_missing, nice_dist = _scan(jd.nice_to_have)

    rep.required_matched = len(req_matched)
    rep.required_missing_list = req_missing
    rep.required_matched_list = req_matched
    rep.required_match_ratio = (
        rep.required_matched / rep.required_total if rep.required_total else 0.0
    )

    rep.nice_matched = len(nice_matched)
    rep.nice_missing_list = nice_missing
    rep.nice_matched_list = nice_matched
    rep.nice_match_ratio = (
        rep.nice_matched / rep.nice_total if rep.nice_total else 0.0
    )

    rep.section_distribution = {**req_dist, **nice_dist}

    # ---------- Years of experience gap ----------
    # Pull years from Summary or Experience using same regex as scorer.
    # Bilingual: "years" (EN) or "tahun" (ID) (P1.4).
    rep.years_required = jd.years_required
    if jd.years_required > 0:
        years_text = (
            cv_sections.get("Summary", "") + "\n" + cv_sections.get("Experience", "")
        )
        m = re.search(r"(\d{1,2})\s*\+?\s*(?:years?|yrs?|tahun)", years_text, re.I)
        cv_years = int(m.group(1)) if m else 0
        rep.years_gap = max(0, jd.years_required - cv_years)

    # ---------- Overall JD score (0–10) ----------
    # Weighted blend: 70% required match + 15% nice match + 10% role + 5% years.
    req_score = rep.required_match_ratio * 10
    nice_score = rep.nice_match_ratio * 10
    role_score = 10.0 if rep.role_match else 5.0  # partial credit if no JD role
    if jd.years_required > 0:
        years_score = max(0.0, 10.0 - (rep.years_gap * 2))  # -2 per missing year
    else:
        years_score = 10.0  # no JD requirement = no penalty

    rep.overall_jd_score = round(
        req_score * 0.70
        + nice_score * 0.15
        + role_score * 0.10
        + years_score * 0.05,
        2,
    )

    return rep
