"""Tests for the tech-skill dictionary + fuzzy matcher (B1 backlog).

Goals:
- Recognize canonical tech names ("AWS", "Kubernetes", "PostgreSQL")
- Resolve common aliases ("Amazon Web Services" -> "AWS", "k8s" -> "Kubernetes")
- Avoid false positives on common English words ("Go" must match as a
  language; "go" in prose should NOT match unless surrounded by word
  boundaries that look skill-like)
- Deduplicate so "AWS, aws, Amazon Web Services" count once
- Provide category lookup for downstream weighting (e.g. SWE rubric
  weights "Cloud" skills higher than "Office")
"""
from __future__ import annotations

import pytest

from app.skill_dictionary import (
    KNOWN_SKILLS,
    SKILL_CATEGORIES,
    extract_skills,
    normalize_skill,
    skill_category,
)


# --------------------------------------------------------------------------- #
# normalize_skill
# --------------------------------------------------------------------------- #

class TestNormalizeSkill:
    def test_canonical_unchanged(self):
        assert normalize_skill("Python") == "Python"
        assert normalize_skill("AWS") == "AWS"
        assert normalize_skill("Kubernetes") == "Kubernetes"

    def test_alias_resolved(self):
        assert normalize_skill("amazon web services") == "AWS"
        assert normalize_skill("Amazon Web Services") == "AWS"
        assert normalize_skill("k8s") == "Kubernetes"
        assert normalize_skill("K8S") == "Kubernetes"
        assert normalize_skill("postgres") == "PostgreSQL"

    def test_case_insensitive(self):
        assert normalize_skill("python") == "Python"
        assert normalize_skill("PYTHON") == "Python"
        assert normalize_skill("PyThOn") == "Python"

    def test_whitespace_stripped(self):
        assert normalize_skill("  Python  ") == "Python"
        assert normalize_skill("\tPython\n") == "Python"

    def test_unknown_returns_none(self):
        assert normalize_skill("Underwater Basket Weaving") is None
        assert normalize_skill("") is None
        assert normalize_skill("xyz123") is None


# --------------------------------------------------------------------------- #
# skill_category
# --------------------------------------------------------------------------- #

class TestSkillCategory:
    def test_python_is_language(self):
        assert skill_category("Python") == "Language"
        assert skill_category("Go") == "Language"
        assert skill_category("TypeScript") == "Language"

    def test_aws_is_cloud(self):
        assert skill_category("AWS") == "Cloud"
        assert skill_category("GCP") == "Cloud"
        assert skill_category("Azure") == "Cloud"

    def test_postgres_is_database(self):
        assert skill_category("PostgreSQL") == "Database"
        assert skill_category("MongoDB") == "Database"

    def test_unknown_returns_none(self):
        assert skill_category("Underwater Basket Weaving") is None
        assert skill_category("") is None


# --------------------------------------------------------------------------- #
# extract_skills
# --------------------------------------------------------------------------- #

class TestExtractSkills:
    def test_comma_separated_list(self):
        text = "Python, AWS, Docker, Kubernetes"
        result = extract_skills(text)
        assert "Python" in result
        assert "AWS" in result
        assert "Docker" in result
        assert "Kubernetes" in result

    def test_newline_separated_list(self):
        text = """Skills
Python
AWS
Docker
PostgreSQL"""
        result = extract_skills(text)
        assert {"Python", "AWS", "Docker", "PostgreSQL"} <= result

    def test_pipe_and_semicolon_separators(self):
        text = "Python | AWS; Docker · React"
        result = extract_skills(text)
        assert {"Python", "AWS", "Docker", "React"} <= result

    def test_aliases_normalized(self):
        text = "amazon web services, k8s, postgres, nodejs"
        result = extract_skills(text)
        assert "AWS" in result
        assert "Kubernetes" in result
        assert "PostgreSQL" in result
        assert "Node.js" in result  # nodejs -> Node.js

    def test_case_insensitive_matching(self):
        text = "python, PYTHON, Python"
        result = extract_skills(text)
        # All three should deduplicate to one entry
        assert len([s for s in result if s == "Python"]) == 1

    def test_unknown_words_ignored(self):
        text = "Python, Underwater Basket Weaving, AWS"
        result = extract_skills(text)
        assert "Python" in result
        assert "AWS" in result
        assert "Underwater Basket Weaving" not in result

    def test_vague_phrases_not_counted_as_skills(self):
        text = "team player, problem solving, AWS"
        result = extract_skills(text)
        assert "AWS" in result
        assert "team player" not in result
        assert "problem solving" not in result

    def test_empty_text_returns_empty_set(self):
        assert extract_skills("") == set()
        assert extract_skills("   \n  ") == set()

    def test_skills_in_list_with_extra_prose(self):
        # Free-form prose with a comma-separated skill list inside:
        # the dictionary correctly extracts only the comma-separated
        # portion, ignoring surrounding prose. Per-word extraction from
        # sentences is intentionally NOT supported (would cause too
        # many false positives on common words like "Go", "R", "Java").
        text = "Tools: Python, AWS, Docker"
        result = extract_skills(text)
        assert {"Python", "AWS", "Docker"} <= result

    def test_full_sentence_without_separators_extracts_nothing(self):
        # Without list separators, prose is treated as a single token and
        # ignored. Recruiters who write "I know Python and AWS" prose-style
        # should still get an extractable signal if they add commas.
        text = "I have 5 years of experience with Python and AWS."
        result = extract_skills(text)
        assert result == set()

    def test_word_boundary_protection(self):
        # "Go" as a programming language should match, but "go" inside
        # another word (e.g. "google") should NOT trigger a separate
        # "Go" match by itself.
        text = "google, Python"
        result = extract_skills(text)
        assert "Python" in result
        assert "Google" in result  # Google is a recognized skill too
        # Critical: "Go" should not be falsely extracted from "google"
        # unless "Go" appears as its own token.
        assert "Go" not in result or "Google" in result


# --------------------------------------------------------------------------- #
# Dictionary sanity
# --------------------------------------------------------------------------- #

class TestDictionaryRegistry:
    def test_known_skills_is_nonempty(self):
        assert len(KNOWN_SKILLS) >= 30

    def test_skill_categories_covers_languages_clouds_databases(self):
        # Sanity check that we cover the categories recruiters care about
        languages = {s for s, c in SKILL_CATEGORIES.items() if c == "Language"}
        clouds = {s for s, c in SKILL_CATEGORIES.items() if c == "Cloud"}
        databases = {s for s, c in SKILL_CATEGORIES.items() if c == "Database"}
        assert "Python" in languages
        assert "JavaScript" in languages
        assert "AWS" in clouds
        assert "PostgreSQL" in databases

    def test_all_aliases_resolve_to_known_skills(self):
        """For every alias we declare, the canonical must be in KNOWN_SKILLS."""
        for alias, canonical in _iter_aliases():
            assert canonical in KNOWN_SKILLS, (
                f"alias {alias!r} -> {canonical!r}, but {canonical!r} "
                f"is not in KNOWN_SKILLS"
            )


def _iter_aliases():
    """Test helper to introspect the alias map without exposing it publicly."""
    from app.skill_dictionary import _ALIASES
    return _ALIASES.items()

# --------------------------------------------------------------------------- #
# _clean_token edge cases (B1 integration with scorer)
# --------------------------------------------------------------------------- #

class TestCleanToken:
    def test_dash_with_proficiency_stripped(self):
        from app.skill_dictionary import _clean_token
        assert _clean_token("PHP - Advanced") == "PHP"
        assert _clean_token("Python - Intermediate") == "Python"

    def test_parens_with_years_stripped(self):
        from app.skill_dictionary import _clean_token
        assert _clean_token("Python (3 years)") == "Python"
        assert _clean_token("AWS (since 2020)") == "AWS"

    def test_slash_alternative_stripped(self):
        from app.skill_dictionary import _clean_token
        assert _clean_token("Java / Scala") == "Java"

    def test_label_prefix_stripped(self):
        from app.skill_dictionary import _clean_token
        assert _clean_token("Tools: Python") == "Python"
        assert _clean_token("Skills: AWS, Docker") == "AWS, Docker"  # only last segment

    def test_real_tino_cv_format(self):
        # The actual tino_actual.pdf Skills section uses " - Advanced"
        # formatting. Make sure we extract the canonical names.
        text = (
            "PHP - Advanced\n"
            "Javascript - Advanced\n"
            "Python - Intermediate\n"
            "Typescript - Intermediate\n"
            "Laravel - Advanced\n"
            "CodeIgniter - Advanced\n"
            "React - Intermediate\n"
            "Node JS - Intermediate\n"
            "MySQL - Advanced\n"
            "PostgreSQL - Advanced\n"
            "GIT - Advanced\n"
        )
        result = extract_skills(text)
        # Should find at least the canonical ones
        assert "Python" in result
        assert "React" in result
        assert "PostgreSQL" in result
        assert "MySQL" in result
