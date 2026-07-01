"""Tests for app/feedback.py: concurrent per-section feedback generation.

These tests do NOT call a real LLM. They monkey-patch _generate_one_section
to simulate work, so the suite stays fast and doesn't require Ollama.
"""
from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Dict, List
from unittest.mock import patch

import pytest

from app.feedback import (
    LLM_MAX_WORKERS,
    _generate_one_section,
    generate_feedback,
)
from app.scorer import CVReport, SectionScore


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _make_report(section_names: List[str]) -> CVReport:
    """Build a minimal CVReport with the given section names, all scored 5."""
    sections: Dict[str, SectionScore] = {}
    for n in section_names:
        sections[n] = SectionScore(name=n, score=5.0, evidence=["stub"], issues=["stub"])
    return CVReport(sections=sections, overall=5.0, grade="D — Weak")


def _slow_fake_llm(per_section_delay: float = 0.2):
    """Build a function that simulates a slow LLM call.

    Returns a side_effect for _generate_one_section that sleeps
    per_section_delay then returns deterministic text. Accepts the
    optional system_prompt kwarg added in P1.4 and role kwarg added in v0.4.
    """
    def _fake(llm, name, section, system_prompt=None, role=None):
        time.sleep(per_section_delay)
        return name, f"feedback for {name}"
    return _fake


# --------------------------------------------------------------------------- #
# Concurrent execution — speedup
# --------------------------------------------------------------------------- #

class TestConcurrentExecution:
    def test_sequential_takes_longer_than_concurrent(self):
        # 6 sections, 0.2s each -> sequential = 1.2s, concurrent (3 workers) ~0.4s
        report = _make_report(["A", "B", "C", "D", "E", "F"])
        with patch("app.feedback._generate_one_section", side_effect=_slow_fake_llm(0.2)):
            t0 = time.monotonic()
            fb_seq = generate_feedback(report, max_workers=1)
            t_seq = time.monotonic() - t0

            t0 = time.monotonic()
            fb_par = generate_feedback(report, max_workers=3)
            t_par = time.monotonic() - t0

        # All 6 sections should have feedback
        assert len(fb_seq) == 6
        assert len(fb_par) == 6
        # Both runs return the same set of sections
        assert set(fb_seq.keys()) == set(fb_par.keys())
        # Concurrent should be at least 2x faster (conservative: 2x of sequential time)
        assert t_par < t_seq / 2.0, (
            f"concurrent ({t_par:.2f}s) not faster than sequential ({t_seq:.2f}s)"
        )

    def test_all_sections_covered_in_concurrent_run(self):
        report = _make_report(["A", "B", "C", "D", "E", "F"])
        with patch("app.feedback._generate_one_section", side_effect=_slow_fake_llm(0.05)):
            fb = generate_feedback(report, max_workers=3)
        assert set(fb.keys()) == {"A", "B", "C", "D", "E", "F"}
        for v in fb.values():
            assert v.startswith("feedback for ")


# --------------------------------------------------------------------------- #
# Bounded concurrency
# --------------------------------------------------------------------------- #

class TestBoundedConcurrency:
    def test_max_workers_is_respected(self):
        # Track max in-flight threads during execution.
        in_flight = 0
        lock = threading.Lock()
        peak = 0

        def _track(llm, name, section, system_prompt=None, role=None):
            nonlocal in_flight, peak
            with lock:
                in_flight += 1
                peak = max(peak, in_flight)
            try:
                time.sleep(0.05)
                return name, f"feedback for {name}"
            finally:
                with lock:
                    in_flight -= 1

        report = _make_report(["A", "B", "C", "D", "E", "F", "G", "H"])
        with patch("app.feedback._generate_one_section", side_effect=_track):
            generate_feedback(report, max_workers=3)

        # Peak should not exceed max_workers. Allow 1 slack for timing
        # edge cases (a thread finishing exactly when another starts).
        assert peak <= 3, f"peak in-flight threads was {peak}, expected <= 3"
        # And we should have actually used parallelism.
        assert peak >= 2, f"peak in-flight threads was {peak}, expected >= 2"


# --------------------------------------------------------------------------- #
# Progress callback
# --------------------------------------------------------------------------- #

class TestProgressCallback:
    def test_callback_invoked_per_section(self):
        report = _make_report(["A", "B", "C"])
        calls: List[tuple] = []

        def cb(name, completed, total):
            calls.append((name, completed, total))

        with patch("app.feedback._generate_one_section", side_effect=_slow_fake_llm(0.01)):
            generate_feedback(report, max_workers=2, progress_cb=cb)

        assert len(calls) == 3
        # Every call should report total=3
        for name, completed, total in calls:
            assert total == 3
            assert 1 <= completed <= 3
            assert name in {"A", "B", "C"}
        # completed should reach 3 by the end
        assert max(c[1] for c in calls) == 3

    def test_no_callback_is_ok(self):
        report = _make_report(["A", "B"])
        with patch("app.feedback._generate_one_section", side_effect=_slow_fake_llm(0.01)):
            fb = generate_feedback(report, max_workers=2, progress_cb=None)
        assert len(fb) == 2


# --------------------------------------------------------------------------- #
# Error handling
# --------------------------------------------------------------------------- #

class TestErrorHandling:
    def test_per_section_error_does_not_block_others(self):
        def _sometimes_error(llm, name, section, system_prompt=None, role=None):
            if name == "B":
                raise RuntimeError("simulated LLM failure")
            return name, f"feedback for {name}"

        report = _make_report(["A", "B", "C", "D"])
        with patch("app.feedback._generate_one_section", side_effect=_sometimes_error):
            fb = generate_feedback(report, max_workers=2)
        # All 4 sections should still have an entry
        assert len(fb) == 4
        # B should have the error placeholder
        assert "LLM error" in fb["B"]
        # Others should be normal feedback
        for good in ["A", "C", "D"]:
            assert "LLM error" not in fb[good]

    def test_outer_future_exception_caught(self):
        # If _generate_one_section itself raises (not the inner LLM call),
        # the executor future.result() raises — we should still capture
        # something for that section.
        def _always_raises(llm, name, section, system_prompt=None, role=None):
            raise ValueError("kaboom")

        report = _make_report(["A", "B"])
        with patch("app.feedback._generate_one_section", side_effect=_always_raises):
            fb = generate_feedback(report, max_workers=2)
        assert len(fb) == 2
        for v in fb.values():
            assert "LLM error" in v


# --------------------------------------------------------------------------- #
# Edge cases
# --------------------------------------------------------------------------- #

class TestEdgeCases:
    def test_empty_report_returns_empty_dict(self):
        report = _make_report([])
        fb = generate_feedback(report)
        assert fb == {}

    def test_max_workers_zero_falls_back_to_sequential(self):
        # max_workers <= 1 should hit the fast sequential path
        report = _make_report(["A", "B", "C"])
        with patch("app.feedback._generate_one_section", side_effect=_slow_fake_llm(0.01)):
            fb = generate_feedback(report, max_workers=0)
        assert set(fb.keys()) == {"A", "B", "C"}

    def test_default_max_workers_is_configured(self):
        # Sanity: the constant is exposed and reasonable.
        assert LLM_MAX_WORKERS >= 1
        assert LLM_MAX_WORKERS <= 8  # don't allow unbounded by default


# --------------------------------------------------------------------------- #
# Integration — end-to-end on a real PDF (no LLM call)
# --------------------------------------------------------------------------- #

class TestIntegrationWithRealPdf:
    def test_real_pdf_produces_all_section_keys(self):
        # We patch _generate_one_section so this stays fast + offline.
        pdf = Path(__file__).resolve().parent.parent / "data" / "sample_strong.pdf"
        if not pdf.exists():
            pytest.skip("sample_strong.pdf not present")
        from app.scorer import score_cv
        report = score_cv(str(pdf))

        with patch("app.feedback._generate_one_section", side_effect=_slow_fake_llm(0.01)):
            fb = generate_feedback(report, max_workers=2)
        # All sections from the real report should have feedback
        assert set(fb.keys()) == set(report.sections.keys())
        assert len(fb) > 0
