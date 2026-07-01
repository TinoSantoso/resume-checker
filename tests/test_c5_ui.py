"""Tests for the C5 Streamlit UI helpers + validation script integration.

The Streamlit form itself is hard to unit-test (it owns session state
and side-effects through st.*), but the *helpers* it calls —
``_build_correction`` and ``_persist_correction`` — are pure functions
or thin I/O wrappers. We test those plus the end-to-end
``validate_against_human.py`` flag that auto-loads the corrections log.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from app.corrections import Correction, append_correction, load_corrections
from app.streamlit_app import (
    CORRECTIONS_LOG_PATH,
    _build_correction,
    _persist_correction,
)


# --------------------------------------------------------------------------- #
# _build_correction — pure function
# --------------------------------------------------------------------------- #

class TestBuildCorrection:
    def test_minimal(self):
        c = _build_correction(
            cv_filename="a.pdf",
            section="Skills",
            auto_score=5.0,
            human_score=7.0,
        )
        assert c.cv_filename == "a.pdf"
        assert c.section == "Skills"
        assert c.auto_score == 5.0
        assert c.human_score == 7.0
        assert c.auto_evidence == ""
        assert c.human_evidence == ""
        assert c.recruiter_id == ""

    def test_with_evidence(self):
        c = _build_correction(
            cv_filename="a.pdf",
            section="Experience",
            auto_score=3.5,
            human_score=7.0,
            auto_evidence="Detected: 3 jobs",
            human_evidence="Actually 5 jobs, including freelance",
            recruiter_id="tino",
        )
        assert c.auto_evidence == "Detected: 3 jobs"
        assert c.human_evidence == "Actually 5 jobs, including freelance"
        assert c.recruiter_id == "tino"

    def test_coerces_numeric_scores(self):
        # Slider can return numpy scalars / Decimal — function must coerce
        c = _build_correction(
            cv_filename="a.pdf",
            section="X",
            auto_score="5",  # string from form
            human_score=7.0,
        )
        assert c.auto_score == 5.0
        assert isinstance(c.auto_score, float)


# --------------------------------------------------------------------------- #
# _persist_correction — validation + I/O
# --------------------------------------------------------------------------- #

class TestPersistCorrection:
    def test_writes_to_log(self, tmp_path, monkeypatch):
        log = tmp_path / "corr.jsonl"
        monkeypatch.setattr(
            "app.streamlit_app.CORRECTIONS_LOG_PATH", log,
        )
        c = Correction(
            cv_filename="x.pdf",
            section="Skills",
            auto_score=5.0,
            human_score=7.0,
        )
        err = _persist_correction(c, path=log)
        assert err == ""
        assert log.exists()
        rows = [json.loads(line) for line in log.read_text().splitlines() if line]
        assert len(rows) == 1
        assert rows[0]["cv_filename"] == "x.pdf"

    def test_rejects_invalid_payload(self, tmp_path):
        log = tmp_path / "corr.jsonl"
        c = Correction(
            cv_filename="",  # invalid: empty
            section="Skills",
            auto_score=5.0,
            human_score=7.0,
        )
        err = _persist_correction(c, path=log)
        assert err != ""
        assert "cv_filename" in err
        assert not log.exists()  # nothing written

    def test_rejects_out_of_range(self, tmp_path):
        log = tmp_path / "corr.jsonl"
        c = Correction(
            cv_filename="x.pdf",
            section="Skills",
            auto_score=15.0,  # invalid
            human_score=7.0,
        )
        err = _persist_correction(c, path=log)
        assert err != ""

    def test_appends_multiple(self, tmp_path):
        log = tmp_path / "corr.jsonl"
        for sec in ["Skills", "Contact", "Experience"]:
            c = Correction(
                cv_filename="x.pdf", section=sec,
                auto_score=5.0, human_score=7.0,
            )
            assert _persist_correction(c, path=log) == ""
        rows = log.read_text().strip().splitlines()
        assert len(rows) == 3
        sections = [json.loads(r)["section"] for r in rows]
        assert sections == ["Skills", "Contact", "Experience"]


# --------------------------------------------------------------------------- #
# End-to-end: validate_against_human.py with --corrections flag
# --------------------------------------------------------------------------- #

class TestValidationWithCorrections:
    """Smoke test that the --corrections flag works end-to-end."""

    def test_corrections_flag_accepted(self, tmp_path):
        # Generate a small log
        log = tmp_path / "corr.jsonl"
        for _ in range(3):
            append_correction(log, Correction(
                cv_filename="x.pdf", section="Skills",
                auto_score=5.0, human_score=7.0,
            ))

        # Run the validation script with --corrections flag
        repo = Path(__file__).resolve().parent.parent
        grades = repo / "data" / "validation" / "grades.json"
        cv_dir = repo / "data" / "validation"
        script = repo / "scripts" / "validate_against_human.py"

        if not grades.exists():
            pytest.skip("bundled grades.json not present")

        proc = subprocess.run(
            [sys.executable, str(script),
             "--grades", str(grades),
             "--cv-dir", str(cv_dir),
             "--corrections", str(log)],
            capture_output=True, text=True, timeout=120,
        )
        assert proc.returncode == 0, f"validation failed: {proc.stderr}"
        # The corrections log was loaded and printed
        assert "Corrections log (HITL): 3 entries" in proc.stdout
        # Per-section summary present
        assert "Skills" in proc.stdout
        assert "mean Δ=" in proc.stdout

    def test_missing_corrections_file_does_not_crash(self):
        repo = Path(__file__).resolve().parent.parent
        grades = repo / "data" / "validation" / "grades.json"
        cv_dir = repo / "data" / "validation"
        script = repo / "scripts" / "validate_against_human.py"
        if not grades.exists():
            pytest.skip("bundled grades.json not present")

        proc = subprocess.run(
            [sys.executable, str(script),
             "--grades", str(grades),
             "--cv-dir", str(cv_dir),
             "--corrections", "/tmp/nonexistent-corrections-xyz.jsonl"],
            capture_output=True, text=True, timeout=120,
        )
        assert proc.returncode == 0
        # No "Corrections log" line when log is missing
        assert "Corrections log" not in proc.stdout
