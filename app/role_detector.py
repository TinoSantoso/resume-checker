"""Role classifier for CVs.

Detects whether a CV is targeting an SWE (Software Engineering), Data
(analyst/scientist/engineer), or PM (Product Management) role, based on
keyword signals in the Skills and Summary sections.

The detector is intentionally lightweight and rule-based — we don't use
the LLM for this because (a) the LLM is too slow for a synchronous
classification step, and (b) a 3B model would over-confidently misclassify
niche roles like 'DevOps' or 'ML engineer' as one of our three buckets.

Strategy
--------
1. Concatenate Skills + Summary + Header text into a single corpus.
2. Tokenize to lowercase words, plus bigrams for multi-word terms
   ("machine learning", "data science", etc.).
3. Score each role (swe, data, pm) by counting role-signal keyword hits.
4. If a role scores strictly higher than the runner-up by a margin,
   return that role with high confidence. Otherwise return 'general'.

The signals were picked from real CV keyword distributions in our
validation set (v_strong_ml, v_good_pm, v_medium_backend) plus common
variants seen in the wild.
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Dict, Iterable, Tuple


# --------------------------------------------------------------------------- #
# Role signal sets (lowercase, exact-token match unless noted otherwise).
# --------------------------------------------------------------------------- #

SWE_SIGNALS: set[str] = {
    # Languages
    "python", "java", "golang", "rust", "c++", "typescript", "javascript",
    "kotlin", "swift", "ruby", "php", "scala", "elixir", "objective-c",
    # Frameworks / runtimes
    "react", "vue", "angular", "node.js", "django", "flask",
    "fastapi", "spring", "rails", "laravel", "express", "nestjs", "gin",
    # Infrastructure / SWE primitives
    "kubernetes", "docker", "terraform", "ansible", "helm", "jenkins",
    "github actions", "ci/cd", "microservices", "rest api", "graphql",
    "grpc", "kafka", "rabbitmq", "redis", "memcached",
    # Tools of the SWE trade
    "git", "github", "gitlab", "bitbucket",
    # Domain terms
    "backend", "frontend", "full-stack", "fullstack", "devops", "sre",
    "platform", "infrastructure", "embedded", "mobile", "ios", "android",
    "web developer", "software engineer", "software developer",
    "engineering manager", "tech lead", "staff engineer", "principal engineer",
    # Methodologies
    "agile", "scrum", "tdd", "bdd", "code review",
}

DATA_SIGNALS: set[str] = {
    # Languages / libs
    "python", "r", "sql", "scala", "julia", "sas",
    "pandas", "numpy", "scipy", "scikit-learn", "sklearn",
    "pytorch", "tensorflow", "keras", "xgboost", "lightgbm",
    "matplotlib", "seaborn", "plotly", "streamlit",
    # Data infrastructure
    "spark", "hadoop", "hive", "presto", "trino", "airflow", "dagster",
    "dbt", "snowflake", "bigquery", "redshift", "databricks",
    "kafka", "flink", "beam", "dataflow",
    # ML / Stats
    "machine learning", "deep learning", "neural network", "nlp",
    "computer vision", "reinforcement learning", "statistics",
    "statistical modeling", "a/b testing", "experiment design",
    "bayesian", "time series", "forecasting",
    # BI / viz
    "tableau", "looker", "power bi", "metabase", "superset",
    "amplitude", "mixpanel", "segment",
    # Roles / titles
    "data scientist", "data analyst", "data engineer", "analytics engineer",
    "ml engineer", "machine learning engineer", "bi analyst",
    "business intelligence", "research scientist", "quantitative",
    "kaggle",
    # Notebook / modeling tools
    "jupyter", "notebook", "colab",
}

PM_SIGNALS: set[str] = {
    # PM-specific titles
    "product manager", "product owner", "product lead", "head of product",
    "vp product", "vp of product", "cpo", "chief product",
    "program manager", "technical product manager", "tpm",
    "growth product manager", "platform product manager",
    # Strategy / craft terms
    "roadmap", "product strategy", "go-to-market", "gtm",
    "product-market fit", "user research", "user interviews",
    "stakeholder", "cross-functional", "prd", "mrd",
    "okrs", "kpis", "north star", "product vision",
    # Business metrics PMs claim
    "arr", "mrr", "nps", "ltv", "cac", "retention",
    "dau", "mau", "wau", "conversion", "funnel", "activation",
    "cohort", "engagement", "monetization",
    # PM-adjacent tools
    "figma", "miro", "notion", "jira", "asana", "trello", "productboard",
    "amplitude", "mixpanel", "heap", "pendo",
    "optimizely", "launchdarkly",
    # Domains
    "b2b", "b2c", "saas", "marketplace", "fintech", "edtech", "healthtech",
    "0 to 1", "0-to-1", "1 to 10", "10 to 100",
    # Outcomes PMs emphasize
    "launched", "shipped", "drove growth", "increased engagement",
}


# Signals that ONLY belong to one role — if we see these we can be very
# confident even if other signals are weak. Used as tie-breakers.
_DISAMBIGUATORS: dict[str, str] = {
    "product manager": "pm",
    "product owner": "pm",
    "head of product": "pm",
    "vp product": "pm",
    "vp of product": "pm",
    "cpo": "pm",
    "chief product": "pm",
    "program manager": "pm",
    "okrs": "pm",
    "north star": "pm",
    "go-to-market": "pm",
    "gtm": "pm",
    "roadmap": "pm",
    "user research": "pm",
    "prd": "pm",
    "mrd": "pm",
    "data scientist": "data",
    "data analyst": "data",
    "data engineer": "data",
    "analytics engineer": "data",
    "ml engineer": "data",
    "machine learning engineer": "data",
    "research scientist": "data",
    "bi analyst": "data",
    "business intelligence": "data",
    "kaggle": "data",
    "tableau": "data",
    "looker": "data",
    "power bi": "data",
    "snowflake": "data",
    "bigquery": "data",
    "redshift": "data",
    "dbt": "data",
    "software engineer": "swe",
    "software developer": "swe",
    "full-stack": "swe",
    "fullstack": "swe",
    "backend": "swe",
    "frontend": "swe",
    "devops": "swe",
    "sre": "swe",
    "site reliability": "swe",
    "kubernetes": "swe",
    "terraform": "swe",
    "microservices": "swe",
    "rest api": "swe",
    "graphql": "swe",
    "grpc": "swe",
    "tech lead": "swe",
    "staff engineer": "swe",
    "principal engineer": "swe",
}


# --------------------------------------------------------------------------- #
# Tokenization helpers
# --------------------------------------------------------------------------- #

# A token is a lowercase word, or a hyphen/slash/dot-joined phrase preserved
# as one token so things like "ci/cd" and "next.js" survive intact.
_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9+#./\-]*", re.I)


def _strip_terminal_punct(token: str) -> str:
    """Strip trailing sentence punctuation that .findall() leaves attached.

    PyMuPDF and pdf_parser often keep periods, commas, semicolons attached
    to the last word of a sentence. Stripping them lets our phrase lookup
    match ``product manager`` even when the text says ``product manager.``.
    """
    return token.rstrip(".,;:!?")


def _tokenize(text: str) -> list[str]:
    """Lowercase tokenize a corpus, preserving tech-specific phrases.

    Compared to ``str.split()``, this keeps ``ci/cd``, ``node.js``,
    ``c++``, ``next.js``, ``vue.js``, ``power-bi`` as single tokens.

    Trailing sentence punctuation is stripped from each token so phrase
    matching tolerates ``product manager.`` at the end of a sentence.
    """
    if not text:
        return []
    return [_strip_terminal_punct(t).lower() for t in _TOKEN_RE.findall(text)]


def _bigrams(tokens: Iterable[str]) -> list[str]:
    """Generate bigrams (2-word phrases) so we can match 'machine learning'
    even though the unigram 'machine' is too ambiguous."""
    toks = list(tokens)
    return [f"{a} {b}" for a, b in zip(toks, toks[1:])]


def _normalize_for_phrase_match(text: str) -> set[str]:
    """Build a set of phrases (unigrams + bigrams) ready for phrase lookup.

    Returns both single tokens AND bigrams after stripping terminal
    punctuation, so ``detect_role`` can match ``product manager`` whether
    it appears as ``"product manager"``, ``"product manager."`` at end of
    sentence, or with any sentence-final punctuation.
    """
    tokens = _tokenize(text)
    return set(tokens) | set(_bigrams(tokens))


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #

VALID_ROLES = ("general", "swe", "data", "pm")


def score_role(text: str) -> Dict[str, int]:
    """Return raw hit counts per role for the given text.

    Args:
        text: Concatenated corpus (skills + summary + header typically).

    Returns:
        Dict with keys ``swe``, ``data``, ``pm``. ``general`` is always 0.
        Counts reflect unique role-signal tokens/bigrams seen.

    Note:
        Overlapping signals (e.g. ``python`` is in both SWE and Data) are
        counted toward BOTH roles, which is correct — a Python data
        scientist's CV should score well on both SWE and Data axes.
        Disambiguation is handled by ``detect_role`` via _DISAMBIGUATORS.
    """
    tokens = _tokenize(text)
    phrases = set(tokens) | set(_bigrams(tokens))

    counts = {"swe": 0, "data": 0, "pm": 0}
    for phrase in phrases:
        if phrase in SWE_SIGNALS:
            counts["swe"] += 1
        if phrase in DATA_SIGNALS:
            counts["data"] += 1
        if phrase in PM_SIGNALS:
            counts["pm"] += 1
    return counts


def detect_role(
    text: str,
    *,
    confidence_threshold: int = 3,
    margin: int = 2,
) -> Tuple[str, float]:
    """Detect the role a CV is targeting.

    Args:
        text: Concatenated corpus (skills + summary + header typically).
        confidence_threshold: Minimum absolute score for the winning role
            to count as a confident detection. Below this, returns
            ``"general"``.
        margin: Minimum gap (winner - runner-up) for a confident pick.
            A tie or near-tie falls back to ``"general"``.

    Returns:
        Tuple ``(role, confidence)`` where ``role`` is one of
        ``"general"``, ``"swe"``, ``"data"``, ``"pm"`` and ``confidence``
        is a float in ``[0.0, 1.0]`` representing how certain we are.

    Algorithm:
        1. Score each role.
        2. Check for strong disambiguators — if found, the disambiguator
           wins immediately (with high confidence).
        3. Otherwise, the role with the highest score wins, provided the
           score exceeds both ``confidence_threshold`` AND ``margin``
           over the runner-up.
        4. If no role clears both bars, return ``("general", low_conf)``.
    """
    counts = score_role(text)

    # 1) Check disambiguators — strong unique signals.
    low_tokens = _normalize_for_phrase_match(text)
    disambig_hits: Counter[str] = Counter()
    for phrase, role in _DISAMBIGUATORS.items():
        if phrase in low_tokens:
            disambig_hits[role] += 1

    if disambig_hits:
        top_role, top_count = disambig_hits.most_common(1)[0]
        if top_count >= 1:
            # Confidence scales with disambiguator count (more unique
            # role-specific phrases = higher confidence). Cap at 0.99
            # so we don't claim 100% certainty from heuristics.
            conf = min(0.99, 0.7 + 0.1 * top_count)
            return top_role, conf

    # 2) Fall back to scoring the whole role signal set.
    ranked = sorted(counts.items(), key=lambda kv: -kv[1])
    winner, win_score = ranked[0]
    runner_up_score = ranked[1][1] if len(ranked) > 1 else 0

    if (
        win_score >= confidence_threshold
        and (win_score - runner_up_score) >= margin
    ):
        # Confidence is high if the winner is well clear of the runner-up.
        gap = win_score - runner_up_score
        conf = min(0.95, 0.5 + 0.05 * win_score + 0.05 * gap)
        return winner, round(conf, 2)

    # 3) No clear winner — fall back to general rubric.
    #    Even here we can hint at confidence (e.g. if all roles scored 0,
    #    we have very low confidence in 'general' too).
    max_score = max(counts.values())
    conf = 0.3 if max_score == 0 else round(0.3 + 0.05 * max_score, 2)
    return "general", conf


def detect_role_from_sections(
    skills: str,
    summary: str,
    header: str = "",
    experience: str = "",
) -> Tuple[str, float]:
    """Convenience wrapper: build the corpus from segmented CV sections.

    Experience text is included because role-specific action verbs (e.g.
    "shipped the dashboard" vs "shipped the auth service") can tip the
    scale, but it's down-weighted by being concatenated last.
    """
    corpus_parts = [skills, summary, header, experience]
    corpus = "\n".join(p for p in corpus_parts if p and p.strip())
    return detect_role(corpus)


if __name__ == "__main__":
    # Quick smoke test against known-good role corpora.
    samples = {
        "ml": "Senior Data Scientist with 8 years experience in Python, PyTorch, "
              "TensorFlow, scikit-learn. Built ML models on Snowflake and BigQuery. "
              "Kaggle competitions, Jupyter notebooks.",
        "swe": "Senior Software Engineer. Python, Go, Kubernetes, Docker, AWS. "
               "Built microservices with FastAPI, gRPC, Kafka. GitHub, CI/CD, "
               "Terraform. Backend and platform work.",
        "pm": "Senior Product Manager. Owned roadmap for B2B SaaS platform. "
              "Drove 40% MAU growth via onboarding redesign. Cross-functional "
              "with Eng, Design, Data. OKRs, North Star, KPIs. Figma, Amplitude, Mixpanel.",
        "generic": "Hardworking professional with 5 years of experience. "
                   "Team player, fast learner, problem solver.",
    }
    for label, text in samples.items():
        role, conf = detect_role(text)
        counts = score_role(text)
        print(f"[{label:7s}] detected={role:<7s} conf={conf:.2f}  counts={counts}")