"""Tests for app/role_detector.py: keyword-based CV role classification."""
from __future__ import annotations

import pytest

from app.role_detector import (
    DATA_SIGNALS,
    PM_SIGNALS,
    SWE_SIGNALS,
    VALID_ROLES,
    detect_role,
    detect_role_from_sections,
    score_role,
)


# --------------------------------------------------------------------------- #
# Tokenization + scoring primitives
# --------------------------------------------------------------------------- #

class TestScoreRole:
    def test_swe_signals_count(self):
        text = "Python, Go, Kubernetes, Docker, AWS, microservices"
        counts = score_role(text)
        assert counts["swe"] >= 4

    def test_data_signals_count(self):
        text = "Python, PyTorch, TensorFlow, scikit-learn, Snowflake, BigQuery"
        counts = score_role(text)
        assert counts["data"] >= 4

    def test_pm_signals_count(self):
        text = "Roadmap, OKRs, MAU, ARR, Figma, Amplitude, Mixpanel"
        counts = score_role(text)
        assert counts["pm"] >= 5

    def test_overlapping_python_both_axes(self):
        # "python" appears in both SWE and Data signal sets, so it should
        # count for both. This is intentional — a Python data scientist's
        # CV is a real signal on both axes.
        counts = score_role("python")
        assert counts["swe"] >= 1
        assert counts["data"] >= 1

    def test_empty_text_zeros(self):
        counts = score_role("")
        assert counts == {"swe": 0, "data": 0, "pm": 0}

    def test_unrelated_text_zeros(self):
        counts = score_role("Lorem ipsum dolor sit amet")
        assert counts == {"swe": 0, "data": 0, "pm": 0}

    def test_tech_phrases_preserved_as_single_tokens(self):
        # 'ci/cd' and 'next.js' should tokenize as single phrases so they
        # match SWE_SIGNALS. A naive split() would lose these.
        counts = score_role("Built CI/CD pipelines with Next.js and Node.js")
        assert counts["swe"] >= 2  # ci/cd + node.js at minimum


# --------------------------------------------------------------------------- #
# detect_role — happy path
# --------------------------------------------------------------------------- #

class TestDetectRole:
    def test_strong_ml_signal_goes_to_data(self):
        text = (
            "Senior Data Scientist. Built ML models in production using "
            "PyTorch, TensorFlow, scikit-learn. Snowflake, BigQuery, "
            "Airflow pipelines. Jupyter notebooks, Kaggle competitions."
        )
        role, conf = detect_role(text)
        assert role == "data"
        assert conf >= 0.7

    def test_strong_swe_signal_goes_to_swe(self):
        text = (
            "Senior Software Engineer. Python, Go, TypeScript. Built "
            "microservices on Kubernetes with Docker. GitHub, CI/CD, "
            "Terraform. React, FastAPI, gRPC, Kafka."
        )
        role, conf = detect_role(text)
        assert role == "swe"
        assert conf >= 0.7

    def test_strong_pm_signal_goes_to_pm(self):
        text = (
            "Senior Product Manager. Owned roadmap for B2B SaaS. Drove "
            "40% MAU growth via onboarding redesign. Cross-functional with "
            "Eng, Design. OKRs, North Star, KPIs. Figma, Amplitude."
        )
        role, conf = detect_role(text)
        assert role == "pm"
        assert conf >= 0.7

    def test_generic_text_falls_back_to_general(self):
        text = "Hardworking professional. Team player. Fast learner."
        role, conf = detect_role(text)
        assert role == "general"
        # Low confidence is fine for the fallback path.
        assert 0.0 <= conf <= 0.5

    def test_empty_text_returns_general(self):
        role, conf = detect_role("")
        assert role == "general"


# --------------------------------------------------------------------------- #
# Disambiguators — strong unique signals
# --------------------------------------------------------------------------- #

class TestDisambiguators:
    @pytest.mark.parametrize("phrase,expected_role", [
        ("Product Manager", "pm"),
        ("Product Owner", "pm"),
        ("Senior Product Manager", "pm"),
        ("Data Scientist", "data"),
        ("Data Analyst", "data"),
        ("Data Engineer", "data"),
        ("ML Engineer", "data"),
        ("Software Engineer", "swe"),
        ("Tech Lead", "swe"),
        ("Staff Engineer", "swe"),
        ("DevOps", "swe"),
        ("SRE", "swe"),
    ])
    def test_role_title_disambiguates(self, phrase, expected_role):
        """A role title alone should resolve the role with high confidence,
        even if the rest of the CV is generic."""
        text = f"Worked at Acme Corp. {phrase}. Did stuff. Handled things."
        role, conf = detect_role(text)
        assert role == expected_role, f"'{phrase}' should detect {expected_role}, got {role}"
        assert conf >= 0.7, f"confidence should be high for title, got {conf}"


# --------------------------------------------------------------------------- #
# Bigram handling — multi-word phrases
# --------------------------------------------------------------------------- #

class TestBigrams:
    def test_machine_learning_phrase(self):
        # "machine learning" is a bigram signal for data role.
        text = "Worked on machine learning projects with the team."
        role, _ = detect_role(text)
        # If only this signal exists we may fall to general, but the
        # scoring axis should show data signal.
        counts = score_role(text)
        assert counts["data"] >= 1

    def test_kaggle_word(self):
        # kaggle is a single-word data disambiguator.
        text = "Competed on Kaggle and improved model accuracy by 20%."
        role, conf = detect_role(text)
        assert role == "data"
        assert conf >= 0.7

    def test_roadmap_word(self):
        # roadmap is a single-word PM disambiguator.
        text = "Owned the product roadmap and worked with engineers."
        role, conf = detect_role(text)
        assert role == "pm"
        assert conf >= 0.7


# --------------------------------------------------------------------------- #
# detect_role_from_sections wrapper
# --------------------------------------------------------------------------- #

class TestDetectRoleFromSections:
    def test_skills_heavy_text_drives_detection(self):
        skills = "Python, PyTorch, TensorFlow, scikit-learn, Pandas, SQL"
        summary = ""
        role, conf = detect_role_from_sections(skills, summary)
        assert role == "data"
        assert conf >= 0.7

    def test_summary_drives_detection_when_skills_empty(self):
        skills = ""
        summary = "Senior Product Manager with 8 years experience. Owned roadmap."
        role, conf = detect_role_from_sections(skills, summary)
        assert role == "pm"
        assert conf >= 0.7

    def test_empty_sections_returns_general(self):
        role, conf = detect_role_from_sections("", "", "", "")
        assert role == "general"

    def test_all_empty_strings_returns_general(self):
        # None-style fallback (all sections empty).
        role, _ = detect_role_from_sections("", "")
        assert role == "general"


# --------------------------------------------------------------------------- #
# Confidence calibration
# --------------------------------------------------------------------------- #

class TestConfidenceCalibration:
    def test_strong_pm_above_90_percent(self):
        # Many PM signals → very high confidence.
        text = (
            "Senior Product Manager. Roadmap. OKRs. North Star. KPIs. "
            "DAU, MAU, ARR. Figma, Amplitude, Mixpanel, Segment. "
            "Cross-functional with Eng, Design, Data. B2B SaaS."
        )
        _, conf = detect_role(text)
        assert conf >= 0.9, f"expected high confidence, got {conf}"

    def test_weak_signal_low_confidence(self):
        # Only 1-2 weak signals → low confidence, possibly general.
        text = "Built some features in Python."
        role, conf = detect_role(text)
        # Could resolve to swe (python) but confidence should be modest.
        assert conf <= 0.95

    def test_confidence_is_clamped_below_1(self):
        # Even with all 3 role signal sets present, we should never claim
        # 100% certainty from heuristics.
        text = (
            "Software Engineer, Data Scientist, Product Manager. "
            "Python, PyTorch, Figma, Amplitude, Kubernetes, Snowflake, "
            "Roadmap, OKRs, DAU, ARR."
        )
        _, conf = detect_role(text)
        assert conf <= 0.99, f"confidence should be < 1.0, got {conf}"


# --------------------------------------------------------------------------- #
# Signal set sanity
# --------------------------------------------------------------------------- #

class TestSignalSets:
    def test_signal_sets_non_empty(self):
        assert len(SWE_SIGNALS) >= 30
        assert len(DATA_SIGNALS) >= 30
        assert len(PM_SIGNALS) >= 30

    def test_valid_roles_matches_registry(self):
        # VALID_ROLES is the detector's role namespace. It should match
        # what the rubric_registry supports (excluding 'general' which the
        # detector returns as a fallback).
        from app.rubric_registry import RUBRIC_ROLES
        assert set(VALID_ROLES) == set(RUBRIC_ROLES)

    def test_no_duplicate_signals_within_a_set(self):
        # Defensive: a duplicate signal in a set would still work but is
        # a sign of a sloppy copy-paste. Catch it here.
        assert len(SWE_SIGNALS) == len(set(SWE_SIGNALS))
        assert len(DATA_SIGNALS) == len(set(DATA_SIGNALS))
        assert len(PM_SIGNALS) == len(set(PM_SIGNALS))

    def test_no_empty_string_signals(self):
        for s in SWE_SIGNALS | DATA_SIGNALS | PM_SIGNALS:
            assert s.strip(), f"empty signal: {s!r}"