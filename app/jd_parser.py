"""Job Description parser — extract structured signals from raw JD text.

Output: ``JDParsed`` dataclass with required_skills, role_title, years_req,
and nice_to_have list. Keeps the surface small so the matcher can stay
focused on comparison logic, not NLP.

Heuristics only — no LLM call. Same philosophy as pdf_parser.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Set


# --------------------------------------------------------------------------- #
# Common technical skills / tools lexicon
# --------------------------------------------------------------------------- #
# Curated, not exhaustive. We bias toward named tools (Python, AWS, K8s) so
# the matcher can produce a meaningful gap list. Add to this list as new
# domains come up. Lowercase match.
TECH_LEXICON: Set[str] = {
    # languages
    "python", "go", "golang", "rust", "typescript", "javascript", "java",
    "kotlin", "swift", "ruby", "php", "scala", "c++", "c#", "sql", "bash",
    "r", "matlab", "perl", "elixir", "haskell", "clojure",
    # frameworks / runtimes
    "fastapi", "flask", "django", "gin", "express", "react", "vue", "angular",
    "next.js", "nextjs", "svelte", "rails", "spring", "springboot", "node.js",
    "nodejs", ".net", "laravel",
    # data / ml
    "spark", "hadoop", "kafka", "airflow", "dbt", "snowflake", "databricks",
    "redshift", "bigquery", "pandas", "numpy", "pytorch", "tensorflow",
    "scikit-learn", "sklearn", "llm", "rag", "mlops",
    # infra / cloud
    "aws", "gcp", "azure", "kubernetes", "k8s", "docker", "terraform",
    "ansible", "jenkins", "github actions", "gitlab ci", "argocd", "helm",
    "prometheus", "grafana", "elk", "elasticsearch", "opentelemetry",
    # databases
    "postgresql", "postgres", "mysql", "mongodb", "redis", "cassandra",
    "dynamodb", "sqlite", "oracle", "mariadb", "neo4j",
    # web / api
    "rest", "graphql", "grpc", "websocket", "kafka", "rabbitmq",
    # mobile
    "ios", "android", "react native", "flutter",
    # soft / role (used to detect role title and seniority)
    "engineer", "developer", "architect", "manager", "lead", "principal",
    "senior", "junior", "staff", "intern", "consultant", "analyst",
    "scientist", "designer", "specialist",
}

# Common boilerplate / stopwords to ignore when scanning for "skills".
STOPWORDS: Set[str] = {
    "the", "and", "or", "with", "for", "to", "of", "in", "a", "an", "on",
    "at", "as", "by", "is", "are", "be", "this", "that", "we", "you",
    "our", "your", "will", "can", "may", "should", "must", "have", "has",
    "from", "all", "their", "they", "them", "it", "its", "if", "else",
    "than", "then", "but", "not", "no", "yes", "do", "does", "did", "via",
    "using", "use", "used", "etc", "i.e", "e.g", "such", "any", "some",
    "more", "most", "other", "into", "out", "up", "down", "over", "under",
    "between", "after", "before", "during", "while", "about", "also",
    "well", "good", "great", "nice", "best", "strong", "solid",
    "experience", "knowledge", "familiarity", "ability", "skills", "skill",
    "years", "year", "months", "minimum", "maximum", "plus", "bonus",
}


# --------------------------------------------------------------------------- #
# Pattern helpers
# --------------------------------------------------------------------------- #

# Matches "5+ years", "at least 3 years", "minimum 7 years of",
# OR "5+ tahun" (Indonesian) (P1.4).
YEARS_RE = re.compile(
    r"(?:at\s+least|minimum|min\.?|\+)?\s*"
    r"(\d{1,2})\s*\+?\s*"
    r"(?:years?|yrs?|tahun)",
    re.I,
)

# Matches "Senior Software Engineer", "Lead Data Engineer", "Staff Backend Dev",
# OR Indonesian role titles like "Pengembang Senior", "Arsitek Data" (P1.4).
# Heuristic: capitalized phrase ending with a role noun from lexicon,
# OR Indonesian role nouns prefixed by an optional adjective.
ROLE_RE = re.compile(
    r"\b((?:senior|junior|staff|principal|lead|intern|graduate)?\s*"
    r"(?:[A-Z][a-z]+\s+){0,3}"
    r"(?:Engineer|Developer|Architect|Manager|Scientist|Analyst|Designer|Consultant|Specialist|"
    r"Pengembang|Insinyur|Programer|Manajer|Analis|Arsitek|Ilmuwan|Desainer|Konsultan|Spesialis))",
)


# --------------------------------------------------------------------------- #
# Dataclass
# --------------------------------------------------------------------------- #

@dataclass
class JDParsed:
    raw_text: str
    role_title: str = ""
    years_required: int = 0
    required_skills: List[str] = field(default_factory=list)   # ordered by frequency
    nice_to_have: List[str] = field(default_factory=list)

    @property
    def has_minimum_info(self) -> bool:
        """A JD with no extracted role title and no skills is probably not a real JD."""
        return bool(self.role_title) or len(self.required_skills) >= 1


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #

def _extract_skills(text: str) -> List[str]:
    """Find technical-skill tokens from the lexicon that appear in text.

    Order: by occurrence count (descending), so high-frequency skills bubble
    up as "must-haves". Lowercased, deduped.
    """
    low = text.lower()
    counts: dict[str, int] = {}
    for skill in TECH_LEXICON:
        # Use word boundaries to avoid partial matches ("go" inside "google").
        pattern = r"\b" + re.escape(skill) + r"\b"
        n = len(re.findall(pattern, low))
        if n > 0:
            counts[skill] = n
    return [s for s, _ in sorted(counts.items(), key=lambda kv: -kv[1])]


def _extract_role(text: str) -> str:
    """First capitalized role-like phrase in the JD."""
    # Limit to first ~500 chars — role title usually appears near the top.
    head = text[:500]
    m = ROLE_RE.search(head)
    if m:
        return m.group(1).strip()
    # Fallback: look for any role noun (English or Indonesian) in the head.
    m2 = re.search(
        r"\b((?:senior|junior|staff|principal|lead|intern|magang)?\s*"
        r"(?:[A-Za-z]+\s+){0,2}"
        r"(?:engineer|developer|architect|manager|scientist|analyst|designer|consultant|specialist|"
        r"pengembang|insinyur|programer|manajer|analis|arsitek|ilmuwan|desainer|konsultan|spesialis))",
        head,
        re.I,
    )
    if m2:
        return m2.group(1).strip()
    return ""


def _extract_years(text: str) -> int:
    """Largest years-of-experience requirement mentioned."""
    matches = YEARS_RE.findall(text)
    if not matches:
        return 0
    try:
        return max(int(m) for m in matches)
    except ValueError:
        return 0


def _split_must_vs_nice(text: str) -> tuple[Set[str], Set[str]]:
    """Naive split: skills in 'Requirements' section are must, 'Nice to have' / 'Bonus' are nice.

    Falls back to "all required" if neither section is found.
    """
    low = text.lower()
    # Find section boundaries.
    must_start = low.find("requirement")
    if must_start < 0:
        must_start = low.find("qualification")
    nice_start = low.find("nice to have")
    if nice_start < 0:
        nice_start = low.find("bonus")
    if nice_start < 0:
        nice_start = low.find("preferred")

    if must_start < 0:
        # No clear split — everything is "required".
        all_skills = set(_extract_skills(text))
        return all_skills, set()

    # Slice text into must and nice regions.
    must_end = nice_start if nice_start > must_start else len(text)
    must_text = text[must_start:must_end]
    nice_text = text[nice_start:] if nice_start > must_start else ""

    return set(_extract_skills(must_text)), set(_extract_skills(nice_text))


def parse_jd(jd_text: str) -> JDParsed:
    """Parse a raw JD string into structured signals."""
    text = jd_text.strip()
    if not text:
        return JDParsed(raw_text="")

    role = _extract_role(text)
    years = _extract_years(text)
    must_skills, nice_skills = _split_must_vs_nice(text)
    all_skills = _extract_skills(text)

    # If _split_must_vs_nice returned nothing (no "Requirements" header),
    # treat all detected skills as required.
    if not must_skills:
        required = all_skills
        nice = []
    else:
        required = [s for s in all_skills if s in must_skills and s not in nice_skills]
        nice = [s for s in all_skills if s in nice_skills]

    return JDParsed(
        raw_text=text,
        role_title=role,
        years_required=years,
        required_skills=required,
        nice_to_have=nice,
    )
