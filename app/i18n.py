"""Bilingual (ID/EN) lexicon + section patterns for the CV reviewer.

Centralized here so pdf_parser, scorer, jd_parser, and feedback all share
the same source of truth. Adding a new language = add a new entry to
LANG_CONFIG.

The English lexicon is the canonical baseline. Indonesian is a curated
additive overlay (we don't translate English, we add parallel patterns).
"""
from __future__ import annotations

from typing import Dict, List, Set


# --------------------------------------------------------------------------- #
# Per-language section header patterns (regex strings, anchored to line)
# --------------------------------------------------------------------------- #

SECTION_PATTERNS_ID: Dict[str, List[str]] = {
    "Contact": [
        r"^\s*(kontak|info(rmasi)?\s+kontak|data\s+pribadi)\s*$",
        r"^\s*(alamat|telepon|email)\s*$",
    ],
    "Summary": [
        r"^\s*(ringkasan|profil(\s+(saya|profesional))?|tentang\s+(saya|anda))\s*$",
        r"^\s*(tujuan\s+(karir|karier)|deskripsi\s+diri)\s*$",
        r"^\s*(rangkuman\s+(diri|saya))\s*$",
    ],
    "Experience": [
        r"^\s*(pengalaman(\s+(kerja|pekerjaan))?|riwayat\s+(pekerjaan|karir|karier))\s*$",
        r"^\s*(pekerjaan|profesi)\s*$",
    ],
    "Skills": [
        r"^\s*(keahlian|keterampilan|kemampuan)(\s+(teknis|inti|utama))?\s*$",
        r"^\s*(kompentensi|kompetensi)\s*$",
        r"^\s*(teknologi|stack(\s+teknologi)?)\s*$",
    ],
    "Education": [
        r"^\s*(pendidikan|riwayat\s+pendidikan|latar\s+belakang\s+pendidikan)\s*$",
        r"^\s*(akademik|edukasi)\s*$",
    ],
    "Projects": [
        r"^\s*(proyek|project|portofolio|portfolio)\s*$",
    ],
    "Certifications": [
        r"^\s*(sertifikat|sertifikasi|lisensi)\s*$",
    ],
    "Links": [
        r"^\s*(tautan|profil\s+online|media\s+sosial|sosial\s+media)\s*$",
    ],
}


# --------------------------------------------------------------------------- #
# Per-language scoring lexica
# --------------------------------------------------------------------------- #

WEAK_VERBS_ID: Set[str] = {
    # English carry-overs
    "responsible for", "worked on", "helped", "assisted", "was tasked",
    "duties included", "involved in", "participated in",
    # Indonesian weak phrasing
    "bertanggung jawab atas", "membantu", "ikut serta dalam",
    "terlibat dalam", "tugasnya adalah", "tugas meliputi",
    "mengerjakan", "bekerja pada", "berperan sebagai",
}

STRONG_VERB_HINTS_ID: Set[str] = {
    # English carry-overs (common in bilingual CVs)
    "led", "architected", "shipped", "delivered", "designed", "built",
    "reduced", "increased", "improved", "optimized", "scaled", "launched",
    "created", "owned", "drove", "negotiated", "mentored", "automated",
    "deployed", "migrated", "implemented", "established", "streamlined",
    # Indonesian strong verbs
    "memimpin", "mengarahkan", "membangun", "merancang", "merancang bangun",
    "mengembangkan", "mengurangi", "meningkatkan", "mengoptimalkan",
    "mempercepat", "meluncurkan", "menciptakan", "mengotomatiskan",
    "mendeploy", "memigrasi", "mengimplementasikan", "mendirikan",
    "menyederhanakan", "menyelamatkan", "menekan", "mencapai",
    "menyelesaikan", "mengelola", "mengawasi", "mengoordinasikan",
}

# Role keywords for the summary detection.
ROLE_KEYWORDS_ID: Set[str] = {
    # English carry-overs
    "engineer", "developer", "manager", "analyst", "architect", "scientist",
    "designer", "lead", "consultant", "specialist",
    # Indonesian role nouns
    "insinyur", "pengembang", "programmer", "manajer", "analis",
    "arsitek", "ilmuwan", "desainer", "konsultan", "spesialis",
    "teknisi", "ahli", "kepala", "direktur", "pemimpin",
}


# --------------------------------------------------------------------------- #
# Language detection (very lightweight — we only need to distinguish ID vs EN)
# --------------------------------------------------------------------------- #

# Common Indonesian function words / morphemes. We don't need full NLP —
# a single hit on these is a strong signal that the document is Indonesian.
ID_SIGNAL_WORDS: Set[str] = {
    "yang", "dan", "di", "dari", "untuk", "dengan", "pada", "telah",
    "sudah", "tidak", "ini", "itu", "juga", "atau", "saat", "oleh",
    "dalam", "atas", "tahun", "bulan", "pengalaman", "pekerjaan",
    "keahlian", "pendidikan", "keterampilan", "saya", "kami", "bertanggung",
    "memimpin", "membangun", "meningkatkan", "pengembangan", "membantu",
    "magang", "sarjana", "diploma", "teknik", "informatika", "sistem",
    "teknologi", "jaringan", "basis", "data",
}


def detect_language(text: str) -> str:
    """Return 'id' or 'en' for the dominant language in the text.

    Heuristic: tokenize, count hits per language signal set. If Indonesian
    signal words appear in >= 8% of the token vocabulary (capped at first
    2000 tokens for speed), treat the document as Indonesian. Otherwise
    default to English.
    """
    if not text or not text.strip():
        return "en"

    # Tokenize: split on whitespace + lowercase, take up to 2000 tokens.
    tokens = text.lower().split()[:2000]
    if not tokens:
        return "en"

    id_hits = sum(1 for t in tokens if t in ID_SIGNAL_WORDS)
    # Use ratio of ID hits to total tokens.
    ratio = id_hits / len(tokens)
    return "id" if ratio >= 0.08 else "en"


# --------------------------------------------------------------------------- #
# Composite accessors used by other modules
# --------------------------------------------------------------------------- #

# English + Indonesian combined sets, used by the scorer.
def combined_weak_verbs() -> Set[str]:
    from app.scorer import WEAK_VERBS
    return WEAK_VERBS | WEAK_VERBS_ID


def combined_strong_verbs() -> Set[str]:
    from app.scorer import STRONG_VERB_HINTS
    return STRONG_VERB_HINTS | STRONG_VERB_HINTS_ID


def combined_role_keywords() -> Set[str]:
    return ROLE_KEYWORDS_ID  # already includes English carry-overs


# Section patterns: English (from pdf_parser) + Indonesian (from this module).
def combined_section_patterns() -> Dict[str, List[str]]:
    from app.pdf_parser import SECTION_PATTERNS
    combined: Dict[str, List[str]] = {}
    for sec, patterns in SECTION_PATTERNS.items():
        combined[sec] = list(patterns)
    for sec, patterns in SECTION_PATTERNS_ID.items():
        combined.setdefault(sec, []).extend(patterns)
    return combined
