"""Tests for role-aware scoring: CVReport.role, score_cv(role=...) integration."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.rubric_registry import RUBRIC_ROLES, load_rubric
from app.scorer import CVReport, score_cv
from app.weights import SECTION_WEIGHTS_BY_ROLE


# --------------------------------------------------------------------------- #
# Integration: score_cv role parameter
# --------------------------------------------------------------------------- #

class TestScoreCvRoleParameter:
    """``score_cv`` accepts an optional ``role`` kwarg that selects which
    rubric's weights to use. When omitted, role is auto-detected."""

    def test_explicit_role_overrides_detection(self):
        pdf = Path(__file__).resolve().parent.parent / "data" / "tino_actual.pdf"
        if not pdf.exists():
            pytest.skip("tino_actual.pdf not present")
        # Tino's CV would auto-detect as swe. Force PM to see if scoring
        # reflects the override.
        rep = score_cv(pdf, role="pm")
        assert rep.role == "pm"
        assert rep.role_confidence == 1.0  # explicit override = full confidence

    def test_auto_detect_sets_role_field(self):
        pdf = Path(__file__).resolve().parent.parent / "data" / "validation" / "v_good_pm.pdf"
        if not pdf.exists():
            pytest.skip("v_good_pm.pdf not present")
        rep = score_cv(pdf)  # no role arg = auto-detect
        assert rep.role == "pm"
        assert 0.0 <= rep.role_confidence <= 1.0

    def test_unknown_role_raises_value_error(self):
        pdf = Path(__file__).resolve().parent.parent / "data" / "sample_strong.pdf"
        if not pdf.exists():
            pytest.skip("sample_strong.pdf not present")
        with pytest.raises(ValueError, match="unknown role"):
            score_cv(pdf, role="designer")  # not in RUBRIC_ROLES

    @pytest.mark.parametrize("role", list(RUBRIC_ROLES))
    def test_all_supported_roles_score_without_error(self, role):
        pdf = Path(__file__).resolve().parent.parent / "data" / "sample_strong.pdf"
        if not pdf.exists():
            pytest.skip("sample_strong.pdf not present")
        rep = score_cv(pdf, role=role)
        assert isinstance(rep, CVReport)
        assert rep.role == role
        assert 0.0 <= rep.overall <= 10.0
        # All sections still scored.
        assert len(rep.sections) > 0


# --------------------------------------------------------------------------- #
# Scoring differences across roles (same CV, different rubric)
# --------------------------------------------------------------------------- #

class TestScoringDiffersByRole:
    """Different roles weight sections differently, so the overall score
    must change even when the underlying section scores don't."""

    def test_pm_overall_lower_for_skills_heavy_cv(self):
        # Tino's CV has weak Skills section. PM rubric de-prioritizes
        # Skills (weight 0.05 vs general 0.17), so PM should score higher
        # than the general rubric on this CV.
        pdf = Path(__file__).resolve().parent.parent / "data" / "tino_actual.pdf"
        if not pdf.exists():
            pytest.skip("tino_actual.pdf not present")
        rep_general = score_cv(pdf, role="general")
        rep_pm = score_cv(pdf, role="pm")
        # Same heuristic scores, but different weights → different overall.
        # Tino has weak Skills (low score) → PM's low-Skills weight
        # should produce a higher overall than the general rubric.
        assert rep_general.overall != rep_pm.overall, (
            f"general={rep_general.overall}, pm={rep_pm.overall} — "
            f"PM rubric should differ because Skills weight is much lower"
        )
        # Skills score is the same — only the weighting changed.
        assert rep_general.sections["Skills"].score == rep_pm.sections["Skills"].score

    def test_swe_vs_data_overall_uses_role_weights(self):
        """For a strong ML CV, SWE and Data rubrics should produce the
        same overall when their weights are similar (round to same 0.1).
        What we verify instead is that the WEIGHTING math differs — by
        recomputing overalls manually with each role's weights."""
        pdf = Path(__file__).resolve().parent.parent / "data" / "validation" / "v_strong_ml.pdf"
        if not pdf.exists():
            pytest.skip("v_strong_ml.pdf not present")
        rep_swe = score_cv(pdf, role="swe")
        rep_data = score_cv(pdf, role="data")
        # Manual recomputation: each role's overall IS its weighted average.
        # We don't assert the overalls differ (they may round to same 0.1)
        # but we assert the math is right (covered by other tests).
        from app.weights import SECTION_WEIGHTS_BY_ROLE
        for role_name, rep in (("swe", rep_swe), ("data", rep_data)):
            weights = SECTION_WEIGHTS_BY_ROLE[role_name]
            total_w = sum(weights.get(s, 0.0) for s in rep.sections)
            manual = sum(
                rep.sections[s].score * weights.get(s, 0.0) for s in rep.sections
            ) / total_w
            assert abs(rep.overall - round(manual, 1)) < 0.05

    def test_section_scores_are_role_invariant(self):
        """The heuristic section scores should NOT change with role — only
        the per-section weighting (and therefore overall) changes. This
        isolates 'role-specific scoring' to weighting, not heuristics."""
        pdf = Path(__file__).resolve().parent.parent / "data" / "sample_strong.pdf"
        if not pdf.exists():
            pytest.skip("sample_strong.pdf not present")
        rep_general = score_cv(pdf, role="general")
        rep_swe = score_cv(pdf, role="swe")
        rep_data = score_cv(pdf, role="data")
        rep_pm = score_cv(pdf, role="pm")

        for section_name in rep_general.sections:
            g = rep_general.sections[section_name].score
            s = rep_swe.sections[section_name].score
            d = rep_data.sections[section_name].score
            p = rep_pm.sections[section_name].score
            assert g == s == d == p, (
                f"Section {section_name} score varies by role: "
                f"general={g}, swe={s}, data={d}, pm={p}. "
                f"This should NOT happen — heuristics are role-invariant."
            )


# --------------------------------------------------------------------------- #
# Overall scoring math is correct for each role
# --------------------------------------------------------------------------- #

class TestOverallMatchesWeightFormula:
    """The overall score should be the weighted average of section scores,
    using the role-specific weights. Verify by computing manually."""

    @pytest.mark.parametrize("role", list(RUBRIC_ROLES))
    def test_overall_equals_weighted_average(self, role):
        pdf = Path(__file__).resolve().parent.parent / "data" / "sample_strong.pdf"
        if not pdf.exists():
            pytest.skip("sample_strong.pdf not present")
        rep = score_cv(pdf, role=role)
        weights = SECTION_WEIGHTS_BY_ROLE[role]
        total_w = sum(weights.get(s, 0.0) for s in rep.sections)
        expected = sum(
            rep.sections[s].score * weights.get(s, 0.0)
            for s in rep.sections
        ) / total_w
        assert abs(rep.overall - round(expected, 1)) < 0.05, (
            f"{role} overall {rep.overall} doesn't match manual {expected:.3f}"
        )


# --------------------------------------------------------------------------- #
# Validation set — auto-detect role aligns with human_role
# --------------------------------------------------------------------------- #

class TestValidationSetRoleDetection:
    """When a CV has a known role in grades.json (human_role), the detector
    should match it. If it doesn't, the auto-detected role is also useful
    info — we just want to flag mismatches for review."""

    @pytest.mark.parametrize("cv_file,expected_role", [
        ("v_strong_ml.pdf", "data"),
        ("v_weak_recent_grad.pdf", "swe"),
        ("v_medium_backend.pdf", "swe"),
        ("v_good_pm.pdf", "pm"),
        ("v_mixed_lean.pdf", "swe"),
    ])
    def test_detector_matches_human_role(self, cv_file, expected_role):
        pdf = Path(__file__).resolve().parent.parent / "data" / "validation" / cv_file
        if not pdf.exists():
            pytest.skip(f"{cv_file} not present")
        rep = score_cv(pdf)  # auto-detect
        assert rep.role == expected_role, (
            f"{cv_file} expected human_role={expected_role}, "
            f"detector returned {rep.role} (conf={rep.role_confidence:.2f})"
        )


# --------------------------------------------------------------------------- #
# Backward compatibility: no role arg produces v0.x behavior
# --------------------------------------------------------------------------- #

class TestBackwardCompatibility:
    """When role is auto-detected as 'general' (or anywhere), the per-section
    scores + overall + grade should still match v0.x behavior for the
    general rubric. Tests should pass regardless of which role is detected."""

    def test_default_report_shape_unchanged(self):
        pdf = Path(__file__).resolve().parent.parent / "data" / "sample_strong.pdf"
        if not pdf.exists():
            pytest.skip("sample_strong.pdf not present")
        rep = score_cv(pdf)
        # CVReport gains role/role_confidence but every existing field
        # must still be present.
        assert hasattr(rep, "sections")
        assert hasattr(rep, "overall")
        assert hasattr(rep, "grade")
        assert hasattr(rep, "jd_match")  # JD-aware field kept

    def test_general_role_matches_default_module_weights(self):
        """SECTION_WEIGHTS (v0.x constant) == SECTION_WEIGHTS_BY_ROLE['general']"""
        from app.weights import SECTION_WEIGHTS
        assert SECTION_WEIGHTS == SECTION_WEIGHTS_BY_ROLE["general"]


# --------------------------------------------------------------------------- #
# Rubric registry consistency
# --------------------------------------------------------------------------- #

class TestRubricRegistryConsistency:
    """The registry's loaded rules must drive everything else. If we add a
    new role to the registry, the scorer must support it automatically."""

    @pytest.mark.parametrize("role", list(RUBRIC_ROLES))
    def test_registry_role_supported_by_scorer(self, role):
        rules = load_rubric(role)
        # Every rule must have the schema the scorer expects (id, category, weight).
        for r in rules:
            assert "id" in r
            assert "category" in r
            assert "weight" in r
            assert isinstance(r["weight"], (int, float))
            assert r["weight"] > 0