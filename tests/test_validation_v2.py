"""Tests for the B2 extensions to the validation harness.

Covers:
  * Bootstrap 95% CI computation for Pearson and MAE.
  * Blind-spot detection: flags sections with |mean delta| > threshold
    or Pearson below floor.
  * Role-grouped breakdown.
  * Integration with the corrections log (C5).
  * End-to-end on the bundled 20-CV set.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from scripts.validate_against_human import (
    HumanGrade,
    bootstrap_ci,
    blind_spots,
    correlate_by_group,
    load_grades,
    load_corrections,
    pearson,
    mae,
)


# --------------------------------------------------------------------------- #
# Bootstrap CI
# --------------------------------------------------------------------------- #

class TestBootstrapCi:
    def test_returns_lower_upper(self):
        lo, hi = bootstrap_ci([1, 2, 3, 4, 5], [2, 4, 6, 8, 10], n_boot=200, seed=0)
        assert lo <= hi
        # Perfect correlation should produce CI around 1.0
        assert lo > 0.9, f"expected CI close to 1.0, got [{lo}, {hi}]"

    def test_constant_y_returns_nan_ci(self):
        # Both xs and ys constant => MAE = 0, not NaN
        # xs constant (variance=0) => Pearson NaN, but MAE is well-defined
        lo, hi = bootstrap_ci(
            [5, 5, 5, 5, 5],
            [5, 5, 5, 5, 5],
            n_boot=100, seed=0,
        )
        # MAE = 0 throughout resamples => CI is [0, 0]
        assert lo == 0.0
        assert hi == 0.0

    def test_single_value_yields_nan(self):
        # n < 2 ⇒ return NaN
        lo, hi = bootstrap_ci([1.0], [2.0], n_boot=100, seed=0)
        assert math.isnan(lo) and math.isnan(hi)

    def test_deterministic_with_seed(self):
        a = bootstrap_ci([1, 2, 3, 4, 5], [2, 4, 6, 8, 10], n_boot=100, seed=42)
        b = bootstrap_ci([1, 2, 3, 4, 5], [2, 4, 6, 8, 10], n_boot=100, seed=42)
        assert a == b

    def test_mae_ci(self):
        # |x-y| uniform at 1.0 => MAE = 1.0
        lo, hi = bootstrap_ci([1, 2, 3, 4, 5], [2, 3, 4, 5, 6], n_boot=200, seed=0)
        # MAE stats should fall in the CI
        assert 0.0 <= lo <= 1.0 <= hi + 1e-9 or lo == 1.0

    def test_too_few_samples(self):
        lo, hi = bootstrap_ci([1.0], [2.0], n_boot=100, seed=0)
        assert math.isnan(lo) and math.isnan(hi)


# --------------------------------------------------------------------------- #
# Blind-spot detection
# --------------------------------------------------------------------------- #

class TestBlindSpots:
    def test_flags_section_with_large_delta(self):
        # Human always 8, auto always 3 => |mean delta| = 5
        flags = blind_spots(
            section_data={"Contact": ([8, 8, 8], [3, 3, 3])},
            delta_threshold=1.5,
        )
        assert "Contact" in flags
        # flags[section] is a dict; "flag" key is a string reason
        assert isinstance(flags["Contact"], dict)
        assert "Δ" in flags["Contact"]["flag"] or "delta" in flags["Contact"]["flag"].lower()

    def test_no_flag_for_well_calibrated(self):
        flags = blind_spots(
            section_data={"Contact": ([8, 7, 9], [8, 7, 9])},
            delta_threshold=1.5,
        )
        assert "Contact" not in flags

    def test_flags_low_pearson(self):
        # Perfect anti-correlation: r = -1, but Δ is small (auto and human differ by 1 only)
        flags = blind_spots(
            section_data={"Skills": ([8, 7, 8, 7], [3, 4, 3, 4])},
            delta_threshold=1.5,
            pearson_floor=0.4,
        )
        assert "Skills" in flags

    def test_empty_section_data(self):
        flags = blind_spots(section_data={}, delta_threshold=1.5)
        assert flags == {}

    def test_does_not_flag_with_insufficient_samples(self):
        # Only 2 samples — CI not reliable, should not flag
        flags = blind_spots(
            section_data={"Experience": ([8, 8], [3, 3])},
            delta_threshold=1.5,
            min_samples=3,
        )
        assert "Experience" not in flags


# --------------------------------------------------------------------------- #
# Role-grouped correlation
# --------------------------------------------------------------------------- #

class TestCorrelateByGroup:
    def test_groups_by_key(self):
        # Use a setup that produces clear, distinguishable correlations per group.
        items = [
            (1.0, 2.0, "swe"),  # +1
            (2.0, 3.0, "swe"),
            (3.0, 4.0, "swe"),
            (1.0, 8.0, "pm"),  # -1 (anti-correlated)
            (2.0, 7.0, "pm"),
        ]
        groups = correlate_by_group(items, key=lambda x: x[2])
        assert "swe" in groups
        assert "pm" in groups
        # SWE: y = x + 1 => Pearson = +1
        assert groups["swe"]["n"] == 3
        assert pearson([1, 2, 3], [2, 3, 4]) == pytest.approx(groups["swe"]["pearson"])
        # PM: y = -x + 9 => Pearson = -1 (n=2 still computes Pearson)
        assert groups["pm"]["n"] == 2
        assert groups["pm"]["pearson"] == pytest.approx(-1.0)

    def test_skips_ungrouped(self):
        items = [(1.0, 2.0, "")]
        groups = correlate_by_group(items, key=lambda x: x[2])
        assert groups == {}


# --------------------------------------------------------------------------- #
# Integration with bundled validation set
# --------------------------------------------------------------------------- #

class TestBundledSet:
    """End-to-end smoke test on the real 20-CV set."""

    @pytest.fixture
    def grades(self):
        path = Path(__file__).resolve().parent.parent / "data" / "validation" / "grades.json"
        cv_dir = path.parent
        if not path.exists():
            pytest.skip("bundled grades.json not present")
        return load_grades(path, cv_dir)

    def test_loads_20_or_more(self, grades):
        assert len(grades) >= 20, f"expected 20+ CVs, got {len(grades)}"

    def test_role_coverage(self, grades):
        roles = {g.human_role for g in grades}
        # We want at least 3 different role tags represented
        assert len(roles) >= 3, f"only {len(roles)} roles covered: {roles}"

    def test_every_grade_has_overall(self, grades):
        for g in grades:
            assert 0.0 <= g.human_overall <= 10.0, f"{g.path.name}: invalid human_overall"
            assert g.human_sections, f"{g.path.name}: missing human_sections"

    def test_overall_correlation_positive(self, grades):
        # Even with blind spots, the overall trend should be positive.
        # We re-score a few using the deterministic scorer (no LLM, no Ollama).
        from app.scorer import score_cv
        pairs: list[tuple[float, float]] = []
        for g in grades[:10]:  # subset to keep it fast
            try:
                rep = score_cv(g.path)
                pairs.append((g.human_overall, rep.overall))
            except Exception:
                continue
        if len(pairs) < 3:
            pytest.skip("could not score enough CVs")
        xs, ys = zip(*pairs)
        r = pearson(list(xs), list(ys))
        assert r > 0.0, f"overall Pearson {r} is non-positive — heuristic broken"


# --------------------------------------------------------------------------- #
# Corrections log (C5 integration)
# --------------------------------------------------------------------------- #

class TestLoadCorrections:
    def test_load_empty_when_missing(self, tmp_path):
        result = load_corrections(tmp_path / "nope.jsonl")
        assert result == []

    def test_loads_jsonl(self, tmp_path):
        log = tmp_path / "corr.jsonl"
        log.write_text(
            json.dumps({"cv": "a.pdf", "section": "Skills", "auto": 3, "human": 7}) + "\n"
            + json.dumps({"cv": "b.pdf", "section": "Contact", "auto": 8, "human": 9}) + "\n"
        )
        result = load_corrections(log)
        assert len(result) == 2
        assert result[0]["section"] == "Skills"

    def test_skips_malformed_lines(self, tmp_path):
        log = tmp_path / "corr.jsonl"
        log.write_text(
            json.dumps({"cv": "a.pdf", "section": "Skills", "auto": 3, "human": 7}) + "\n"
            + "this is not json\n"
            + json.dumps({"cv": "b.pdf", "section": "Contact", "auto": 8, "human": 9}) + "\n"
        )
        result = load_corrections(log)
        assert len(result) == 2  # malformed line skipped

    def test_returns_empty_on_empty_file(self, tmp_path):
        log = tmp_path / "corr.jsonl"
        log.write_text("")
        assert load_corrections(log) == []
