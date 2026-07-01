"""Tech-skill dictionary + fuzzy matcher (B1 backlog).

Boosts the precision of skill extraction (currently a naive
``comma split`` in ``app.scorer._score_skills``) by recognizing known
tech names, resolving common aliases ("Amazon Web Services" -> "AWS"),
and deduplicating case-insensitive repeats.

Used by:
- ``app.scorer`` to upgrade the Skills section score when canonical
  tools are detected
- ``app.matcher`` (JD matching) to compare skills against JD
  requirements with alias-aware matching

Design:
- Static dict-of-dicts: no DB, no LLM call. ~150 entries cover the
  90th-percentile roles (SWE / Data / PM / DevOps).
- Aliases are lowercased to make matching case-insensitive
- ``normalize_skill`` is the single source of truth: any caller that
  wants "the canonical name for what the candidate typed" goes through
  here. Returns ``None`` for unknown tokens.
- ``extract_skills`` does free-text extraction: splits on
  comma/semicolon/pipe/newline/bullet, then looks up each token via
  ``normalize_skill``. Returns a ``set`` so duplicates collapse.
"""
from __future__ import annotations

import re
from typing import Dict, Optional, Set


# --------------------------------------------------------------------------- #
# Canonical skills + categories
# --------------------------------------------------------------------------- #

#: Canonical skill -> category. Recruiters care about category because
#: a SWE role weights "Cloud" skills higher than "Office".
SKILL_CATEGORIES: Dict[str, str] = {
    # --- Languages ---
    "Python": "Language",
    "JavaScript": "Language",
    "TypeScript": "Language",
    "Java": "Language",
    "Go": "Language",
    "Rust": "Language",
    "C++": "Language",
    "C#": "Language",
    "Ruby": "Language",
    "PHP": "Language",
    "Swift": "Language",
    "Kotlin": "Language",
    "Scala": "Language",
    "R": "Language",
    "Bash": "Language",
    "SQL": "Language",
    "HTML": "Language",
    "CSS": "Language",

    # --- Frameworks / Runtimes ---
    "React": "Framework",
    "Angular": "Framework",
    "Vue.js": "Framework",
    "Next.js": "Framework",
    "Node.js": "Framework",
    "Django": "Framework",
    "Flask": "Framework",
    "FastAPI": "Framework",
    "Spring Boot": "Framework",
    "Express.js": "Framework",
    "Rails": "Framework",
    ".NET": "Framework",
    "Laravel": "Framework",
    "CodeIgniter": "Framework",
    "Symfony": "Framework",
    "TensorFlow": "Framework",
    "PyTorch": "Framework",
    "Keras": "Framework",
    "Scikit-learn": "Framework",
    "Pandas": "Framework",
    "NumPy": "Framework",

    # --- Cloud / Infra ---
    "AWS": "Cloud",
    "GCP": "Cloud",
    "Azure": "Cloud",
    "Docker": "Cloud",
    "Kubernetes": "Cloud",
    "Terraform": "Cloud",
    "Ansible": "Cloud",
    "Jenkins": "Cloud",
    "GitHub Actions": "Cloud",
    "CircleCI": "Cloud",
    "Helm": "Cloud",
    "Istio": "Cloud",

    # --- Databases ---
    "PostgreSQL": "Database",
    "MySQL": "Database",
    "MongoDB": "Database",
    "Redis": "Database",
    "Elasticsearch": "Database",
    "DynamoDB": "Database",
    "BigQuery": "Database",
    "Snowflake": "Database",
    "SQLite": "Database",
    "Oracle": "Database",
    "Cassandra": "Database",

    # --- Data / ML stack ---
    "Spark": "Data",
    "Hadoop": "Data",
    "Kafka": "Data",
    "Airflow": "Data",
    "dbt": "Data",
    "Tableau": "Data",
    "Power BI": "Data",
    "Looker": "Data",
    "Metabase": "Data",
    "Jupyter": "Data",

    # --- Tools / SaaS ---
    "Git": "Tool",
    "GitHub": "Tool",
    "GitLab": "Tool",
    "Jira": "Tool",
    "Confluence": "Tool",
    "Slack": "Tool",
    "Notion": "Tool",
    "Figma": "Tool",

    # --- Search / Other ---
    "Google": "Search",
    "Elastic": "Search",

    # --- Soft skills we explicitly DON'T recognize (kept out so they
    # never land in ``KNOWN_SKILLS``). The scorer still flags these
    # separately via its vague-phrase list.
}


#: Flat set of canonical names for fast membership checks.
KNOWN_SKILLS: Set[str] = set(SKILL_CATEGORIES.keys())


# --------------------------------------------------------------------------- #
# Aliases (lowercase -> canonical)
# --------------------------------------------------------------------------- #

# Each entry is ``"alias" : "Canonical"``. Matched case-insensitively,
# after stripping surrounding whitespace. Add new aliases here as they
# show up in real CVs — keep the registry the single source of truth.
_ALIASES: Dict[str, str] = {
    # Cloud
    "amazon web services": "AWS",
    "amazonaws": "AWS",
    "amazon aws": "AWS",
    "aws lambda": "AWS",
    "google cloud": "GCP",
    "google cloud platform": "GCP",
    "microsoft azure": "Azure",
    "k8s": "Kubernetes",
    "kube": "Kubernetes",
    "kubernetes engine": "Kubernetes",
    "gke": "Kubernetes",
    "eks": "Kubernetes",
    "aks": "Kubernetes",

    # Languages / runtimes
    "py": "Python",
    "python3": "Python",
    "python2": "Python",
    "js": "JavaScript",
    "javascript": "JavaScript",
    "node": "Node.js",
    "nodejs": "Node.js",
    "node js": "Node.js",
    "ts": "TypeScript",
    "typescript": "TypeScript",
    "golang": "Go",
    "c plus plus": "C++",
    "cpp": "C++",
    "c-sharp": "C#",
    "c sharp": "C#",
    "dotnet": ".NET",
    ".net": ".NET",

    # Frameworks
    "react.js": "React",
    "reactjs": "React",
    "vue": "Vue.js",
    "vuejs": "Vue.js",
    "next": "Next.js",
    "nextjs": "Next.js",
    "express": "Express.js",
    "expressjs": "Express.js",
    "spring": "Spring Boot",
    "springboot": "Spring Boot",
    "tf": "TensorFlow",
    "tensorflow": "TensorFlow",
    "pytorch": "PyTorch",
    "torch": "PyTorch",
    "sklearn": "Scikit-learn",
    "scikit learn": "Scikit-learn",
    "scikitlearn": "Scikit-learn",

    # Databases
    "postgres": "PostgreSQL",
    "postgresql": "PostgreSQL",
    "psql": "PostgreSQL",
    "mongo": "MongoDB",
    "mongodb": "MongoDB",
    "elastic": "Elasticsearch",
    "opensearch": "Elasticsearch",
    "big query": "BigQuery",
    "bigquery": "BigQuery",

    # Data
    "apache spark": "Spark",
    "pyspark": "Spark",
    "apache kafka": "Kafka",
    "apache airflow": "Airflow",
    "google bigquery": "BigQuery",
    "powerbi": "Power BI",
    "power bi": "Power BI",

    # Tools
    "gh": "GitHub",
    "github actions": "GitHub Actions",
    "gha": "GitHub Actions",
}


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #

def normalize_skill(token: str) -> Optional[str]:
    """Return the canonical name for ``token``, or ``None`` if unknown.

    Resolution order:
    1. Direct canonical lookup (case-insensitive)
    2. Alias lookup (case-insensitive)
    3. ``None``
    """
    if not token:
        return None
    cleaned = token.strip()
    if not cleaned:
        return None
    lower = cleaned.lower()

    # 1. Direct match (case-insensitive). Also handles things like "Python"
    # that we registered as canonical.
    for canonical in KNOWN_SKILLS:
        if canonical.lower() == lower:
            return canonical

    # 2. Alias match
    if lower in _ALIASES:
        return _ALIASES[lower]

    return None


def skill_category(canonical: str) -> Optional[str]:
    """Return the category for ``canonical`` (must be from ``KNOWN_SKILLS``)."""
    return SKILL_CATEGORIES.get(canonical)


# Free-text extraction: split on common separators, then normalize each token.
# Whitespace inside multi-word skills ("Spring Boot") is preserved by only
# splitting on the punctuation below — words within a token stay together.
_TOKEN_SPLIT_RE = re.compile(r"[,;|\n•·]+")


def _clean_token(token: str) -> str:
    """Strip a leading label off a token like ``"Tools: Python"`` -> ``"Python"``.

    Many CVs write:
      - ``"Skills: Python, AWS"``        (colon label)
      - ``"PHP - Advanced"``              (dash + proficiency)
      - ``"Python (3 years)"``            (parens with years)

    We strip everything after ``:``, ``-``, ``(``, ``/`` (when followed
    by a non-letter) so the dictionary lookup sees just the skill name.
    Also strips trailing punctuation.
    """
    cleaned = token.strip()
    # Strip leading "Label: " — only the LAST colon, so "Tools: Python:"
    # -> "Python:" -> "Python".
    if ": " in cleaned:
        cleaned = cleaned.rsplit(": ", 1)[-1]
    # Strip " - <proficiency>" suffix: "PHP - Advanced" -> "PHP"
    cleaned = re.sub(r"\s+[-–—]\s+\S.*$", "", cleaned)
    # Strip " (anything)" suffix: "Python (3 years)" -> "Python"
    cleaned = re.sub(r"\s+\(.*\)$", "", cleaned)
    # Strip " / <alternative>" suffix: "Java / Scala" -> "Java"
    cleaned = re.sub(r"\s+/\s+\S.*$", "", cleaned)
    # Strip trailing punctuation (commas already split, but periods etc.
    # can survive).
    cleaned = cleaned.strip(" .;:()[]\"'")
    return cleaned


def extract_skills(text: str) -> Set[str]:
    """Extract canonical skills from free-form ``text``.

    Splits on commas / semicolons / pipes / newlines / bullets, strips
    any leading ``"Label: "`` prefix on each token (so ``"Tools: Python"``
    still extracts ``Python``), normalizes each token via
    :func:`normalize_skill`, and returns the set of canonical names
    (duplicates like ``"AWS, aws"`` collapse to one).
    """
    if not text:
        return set()
    found: Set[str] = set()
    for raw in _TOKEN_SPLIT_RE.split(text):
        token = _clean_token(raw)
        if not token:
            continue
        canonical = normalize_skill(token)
        if canonical is not None:
            found.add(canonical)
    return found