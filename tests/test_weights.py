"""Tests for app/weights.py: per-role rubric -> section weight derivation."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from app.weights import SECTION_WEIGHTS, SECTION_WEIGHTS_BY_ROLE, RUBRIC_DIR
from app.rubric_registry import RUBRIC_ROLES, load_rubric


GENERAL_RUBRIC_PATH = Path(RUBRIC_DIR) / "general.json"


class TestWeightsIntegrity:
    """Backward-compat: SECTION_WEIGHTS (default = 'general' role) must
    keep the v0.x shape — six canonical sections, sums to 1.0, Experience
    is the heaviest."""

    def test_rubric_dir_exists(self):
        assert Path(RUBRIC_DIR).exists(), f"rubric dir missing at {RUBRIC_DIR}"

    def test_rubric_dir_portable_across_cwd(self):
        """RUBRIC_DIR must resolve correctly even when the caller's CWD
        differs from the project root — critical for CI runners where
        pytest may be invoked from a different working directory than
        the source tree."""
        import os
        import subprocess
        import sys
        from app.weights import RUBRIC_DIR as weights_dir
        # Resolve via __file__-relative computation that weights.py uses
        from pathlib import Path as _P
        expected = (_P(__file__).resolve().parent.parent / "kb" / "rubrics")
        assert _P(weights_dir).resolve() == expected, (
            f"RUBRIC_DIR {weights_dir!r} does not resolve to project root "
            f"({expected}). CI will fail when cwd != project root."
        )

    def test_six_canonical_sections_present_in_default(self):
        for sec in ["Contact", "Summary", "Experience", "Skills", "Education", "Length_Formatting"]:
            assert sec in SECTION_WEIGHTS, f"section '{sec}' missing from default weights"

    def test_weights_sum_to_one(self):
        assert abs(sum(SECTION_WEIGHTS.values()) - 1.0) < 1e-6

    def test_all_weights_positive(self):
        for sec, w in SECTION_WEIGHTS.items():
            assert w > 0, f"section '{sec}' has non-positive weight {w}"

    def test_experience_is_heaviest_in_default(self):
        # Experience aggregates R4 (action verbs) + R5 (metrics) + R6 (chronology)
        # which are the 3 highest-weight rules in the general rubric.
        for sec, w in SECTION_WEIGHTS.items():
            if sec == "Experience":
                continue
            assert w <= SECTION_WEIGHTS["Experience"], (
                f"{sec} ({w}) should not be heavier than Experience ({SECTION_WEIGHTS['Experience']})"
            )


class TestWeightsMatchRubric:
    """Re-derive weights by hand and confirm they match the module output."""

    def test_experience_matches_r4_r5_r6(self):
        # Hand-computed: (R4:2.0 + R5:2.5 + R6:1.0) / 12.6
        rules = json.loads(GENERAL_RUBRIC_PATH.read_text(encoding="utf-8"))
        total = sum(r["weight"] for r in rules)
        exp_rules = [r for r in rules if r["id"] in ("R4", "R5", "R6")]
        exp_weight = sum(r["weight"] for r in exp_rules) / total
        assert abs(SECTION_WEIGHTS["Experience"] - round(exp_weight, 4)) < 1e-3

    def test_contact_matches_r1_r2(self):
        rules = json.loads(GENERAL_RUBRIC_PATH.read_text(encoding="utf-8"))
        total = sum(r["weight"] for r in rules)
        contact_rules = [r for r in rules if r["id"] in ("R1", "R2")]
        expected = sum(r["weight"] for r in contact_rules) / total
        assert abs(SECTION_WEIGHTS["Contact"] - round(expected, 4)) < 1e-3


class TestPerRoleWeights:
    """All roles must:
    - exist in SECTION_WEIGHTS_BY_ROLE
    - have positive weights summing to 1.0
    - have at least the canonical six sections (plus optional Projects)"""

    @pytest.mark.parametrize("role", list(RUBRIC_ROLES))
    def test_role_present(self, role):
        assert role in SECTION_WEIGHTS_BY_ROLE

    @pytest.mark.parametrize("role", list(RUBRIC_ROLES))
    def test_role_weights_sum_to_one(self, role):
        total = sum(SECTION_WEIGHTS_BY_ROLE[role].values())
        assert abs(total - 1.0) < 1e-3, f"{role} weights sum to {total}"

    @pytest.mark.parametrize("role", list(RUBRIC_ROLES))
    def test_role_weights_all_positive(self, role):
        for sec, w in SECTION_WEIGHTS_BY_ROLE[role].items():
            assert w > 0, f"{role}/{sec} has non-positive weight {w}"

    @pytest.mark.parametrize("role", list(RUBRIC_ROLES))
    def test_role_has_canonical_sections(self, role):
        weights = SECTION_WEIGHTS_BY_ROLE[role]
        for sec in ("Contact", "Summary", "Experience", "Skills", "Education", "Length_Formatting"):
            assert sec in weights, f"{role} missing canonical section {sec}"

    def test_pm_emphasizes_experience(self):
        """Per the PM rubric, Experience is the dominant section (impact bullets
        carry PM scoring more than any other section)."""
        pm_exp = SECTION_WEIGHTS_BY_ROLE["pm"]["Experience"]
        for role in ("general", "swe", "data"):
            assert pm_exp > SECTION_WEIGHTS_BY_ROLE[role]["Experience"], (
                f"PM Experience ({pm_exp}) should be heaviest, but "
                f"{role} has {SECTION_WEIGHTS_BY_ROLE[role]['Experience']}"
            )

    def test_pm_deemphasizes_skills(self):
        """Per the PM rubric, soft skills are *less* weighted than core
        sections (Experience, Summary) even after the v2 weight re-tune
        bumped Skills from 0.052 -> 0.112 to address PM under-scoring.

        Specifically: Skills must not exceed Summary, and Experience must
        remain heavier than Skills (Experience is still the dominant PM
        signal). This guards against accidentally over-correcting."""
        pm = SECTION_WEIGHTS_BY_ROLE["pm"]
        assert pm["Experience"] > pm["Skills"], (
            f"PM Experience ({pm['Experience']}) should still be heavier than "
            f"Skills ({pm['Skills']})"
        )
        assert pm["Skills"] <= pm["Summary"], (
            f"PM Skills ({pm['Skills']}) should not exceed Summary ({pm['Summary']})"
        )

    def test_swe_data_emphasize_skills(self):
        """SWE and Data both need named tools — Skills weight should be high."""
        for role in ("swe", "data"):
            sk = SECTION_WEIGHTS_BY_ROLE[role]["Skills"]
            gen_sk = SECTION_WEIGHTS_BY_ROLE["general"]["Skills"]
            assert sk >= gen_sk, f"{role} Skills ({sk}) should >= general Skills ({gen_sk})"

    def test_role_specific_sections_exist(self):
        """SWE/Data/PM rubrics include a 'Projects' section; general doesn't."""
        assert "Projects" not in SECTION_WEIGHTS_BY_ROLE["general"]
        for role in ("swe", "data", "pm"):
            assert "Projects" in SECTION_WEIGHTS_BY_ROLE[role], (
                f"{role} should have a Projects section in its rubric"
            )


class TestRubricFilesOnDisk:
    """Each supported role must have a corresponding rubric JSON file."""

    @pytest.mark.parametrize("role", list(RUBRIC_ROLES))
    def test_rubric_file_exists(self, role):
        path = Path(RUBRIC_DIR) / f"{role}.json"
        assert path.exists(), f"rubric file missing for role '{role}': {path}"

    @pytest.mark.parametrize("role", list(RUBRIC_ROLES))
    def test_rubric_has_ten_rules(self, role):
        """All rubrics are exactly 10 rules — keeps the LLM prompt bounded."""
        rules = load_rubric(role)
        assert len(rules) == 10, f"{role} has {len(rules)} rules, expected 10"

    @pytest.mark.parametrize("role", list(RUBRIC_ROLES))
    def test_rubric_rule_ids_unique(self, role):
        rules = load_rubric(role)
        ids = [r["id"] for r in rules]
        assert len(ids) == len(set(ids)), f"{role} has duplicate rule ids: {ids}"

    @pytest.mark.parametrize("role", list(RUBRIC_ROLES))
    def test_rubric_rule_ids_use_role_prefix(self, role):
        """Each role's rule IDs use the role prefix: R for general, S for SWE,
        D for Data, P for PM. This is what makes the per-role retrieval work
        cleanly in the LLM prompt (no ID collisions)."""
        prefix = {"general": "R", "swe": "S", "data": "D", "pm": "P"}[role]
        rules = load_rubric(role)
        for r in rules:
            assert r["id"].startswith(prefix), (
                f"{role} rule {r['id']} should start with '{prefix}'"
            )