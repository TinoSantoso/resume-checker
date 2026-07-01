"""Tests for app/corrections.py — C5 HITL correction storage.

The corrections log is an append-only JSONL file. Each row is one
recruiter correction. The module must be:

* Crash-proof — a malformed line in the log must never block the
  validation report or the Streamlit UI.
* Append-safe — concurrent writes do not corrupt the file (we use
  append mode + a final newline; OS-level append is atomic for
  small writes on POSIX).
* Schema-versioned — older rows are tolerated even if the schema
  evolves.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from app.corrections import (
    Correction,
    append_correction,
    corrections_summary,
    load_corrections,
    validate_correction_payload,
)


# --------------------------------------------------------------------------- #
# Payload validation
# --------------------------------------------------------------------------- #

class TestValidatePayload:
    def test_minimal_valid(self):
        ok, err = validate_correction_payload({
            "cv_filename": "x.pdf",
            "section": "Skills",
            "auto_score": 5.0,
            "human_score": 7.0,
        })
        assert ok is True
        assert err == ""

    def test_rejects_missing_cv_filename(self):
        ok, err = validate_correction_payload({
            "section": "Skills",
            "auto_score": 5.0,
            "human_score": 7.0,
        })
        assert ok is False
        assert "cv_filename" in err

    def test_rejects_missing_section(self):
        ok, err = validate_correction_payload({
            "cv_filename": "x.pdf",
            "auto_score": 5.0,
            "human_score": 7.0,
        })
        assert ok is False
        assert "section" in err

    def test_rejects_non_numeric_score(self):
        ok, err = validate_correction_payload({
            "cv_filename": "x.pdf",
            "section": "Skills",
            "auto_score": "high",
            "human_score": 7.0,
        })
        assert ok is False

    def test_rejects_out_of_range_score(self):
        ok, err = validate_correction_payload({
            "cv_filename": "x.pdf",
            "section": "Skills",
            "auto_score": 15.0,
            "human_score": 7.0,
        })
        assert ok is False
        assert "0..10" in err or "out" in err.lower()

    def test_accepts_zero_and_ten(self):
        for s in (0.0, 10.0):
            ok, _ = validate_correction_payload({
                "cv_filename": "x.pdf",
                "section": "Skills",
                "auto_score": s,
                "human_score": s,
            })
            assert ok is True

    def test_rejects_negative_score(self):
        ok, err = validate_correction_payload({
            "cv_filename": "x.pdf",
            "section": "Skills",
            "auto_score": -1.0,
            "human_score": 7.0,
        })
        assert ok is False

    def test_rejects_empty_section(self):
        ok, err = validate_correction_payload({
            "cv_filename": "x.pdf",
            "section": "",
            "auto_score": 5.0,
            "human_score": 7.0,
        })
        assert ok is False


# --------------------------------------------------------------------------- #
# Append
# --------------------------------------------------------------------------- #

class TestAppend:
    def test_creates_file_if_missing(self, tmp_path):
        log = tmp_path / "subdir" / "corr.jsonl"
        corr = Correction(
            cv_filename="a.pdf",
            section="Skills",
            auto_score=5.0,
            human_score=7.0,
        )
        append_correction(log, corr)
        assert log.exists()
        rows = log.read_text().strip().splitlines()
        assert len(rows) == 1

    def test_appends_multiple(self, tmp_path):
        log = tmp_path / "corr.jsonl"
        for i in range(5):
            corr = Correction(
                cv_filename=f"cv{i}.pdf",
                section="Skills",
                auto_score=5.0,
                human_score=7.0,
            )
            append_correction(log, corr)
        rows = log.read_text().strip().splitlines()
        assert len(rows) == 5

    def test_each_row_is_valid_json(self, tmp_path):
        log = tmp_path / "corr.jsonl"
        corr = Correction(
            cv_filename="x.pdf",
            section="Contact",
            auto_score=8.0,
            human_score=9.0,
            recruiter_id="tino",
        )
        append_correction(log, corr)
        row = json.loads(log.read_text().strip())
        assert row["cv_filename"] == "x.pdf"
        assert row["section"] == "Contact"
        assert row["auto_score"] == 8.0
        assert row["human_score"] == 9.0
        assert row["recruiter_id"] == "tino"
        assert "timestamp" in row  # auto-filled

    def test_timestamp_is_iso8601(self, tmp_path):
        log = tmp_path / "corr.jsonl"
        corr = Correction(
            cv_filename="x.pdf",
            section="Contact",
            auto_score=8.0,
            human_score=9.0,
        )
        before = time.time()
        append_correction(log, corr)
        after = time.time()
        row = json.loads(log.read_text().strip())
        # ISO 8601 with Z suffix
        assert row["timestamp"].endswith("Z"), f"got {row['timestamp']!r}"
        # Validate by re-parsing (Python 3.11 fromisoformat doesn't accept Z,
        # so replace with explicit +00:00)
        from datetime import datetime
        ts = datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00"))
        epoch = ts.timestamp()
        assert before - 1 <= epoch <= after + 1

    def test_evidence_fields_optional(self, tmp_path):
        log = tmp_path / "corr.jsonl"
        corr = Correction(
            cv_filename="x.pdf",
            section="Contact",
            auto_score=8.0,
            human_score=9.0,
            auto_evidence="matched email + phone",
            # human_evidence left empty -> should be omitted from row
        )
        append_correction(log, corr)
        row = json.loads(log.read_text().strip())
        assert row["auto_evidence"] == "matched email + phone"
        assert "human_evidence" not in row  # empty optional stripped
        assert "recruiter_id" not in row

    def test_all_optionals_present(self, tmp_path):
        log = tmp_path / "corr.jsonl"
        corr = Correction(
            cv_filename="x.pdf",
            section="Contact",
            auto_score=8.0,
            human_score=9.0,
            auto_evidence="a",
            human_evidence="b",
            recruiter_id="tino",
        )
        append_correction(log, corr)
        row = json.loads(log.read_text().strip())
        assert row["auto_evidence"] == "a"
        assert row["human_evidence"] == "b"
        assert row["recruiter_id"] == "tino"


# --------------------------------------------------------------------------- #
# Load + summary
# --------------------------------------------------------------------------- #

class TestLoadAndSummary:
    def test_load_empty_when_missing(self, tmp_path):
        assert load_corrections(tmp_path / "nope.jsonl") == []

    def test_round_trip(self, tmp_path):
        log = tmp_path / "corr.jsonl"
        for s, h in [(3.0, 7.0), (5.0, 5.0), (8.0, 9.0)]:
            append_correction(log, Correction(
                cv_filename="x.pdf", section="Skills",
                auto_score=s, human_score=h,
            ))
        loaded = load_corrections(log)
        assert len(loaded) == 3
        assert loaded[0].auto_score == 3.0
        assert loaded[2].human_score == 9.0

    def test_summary_counts_by_section(self, tmp_path):
        log = tmp_path / "corr.jsonl"
        for sec, s, h in [
            ("Skills", 3.0, 7.0),
            ("Skills", 4.0, 6.0),
            ("Contact", 8.0, 9.0),
        ]:
            append_correction(log, Correction(
                cv_filename="x.pdf", section=sec,
                auto_score=s, human_score=h,
            ))
        summary = corrections_summary(log)
        assert summary["total"] == 3
        assert "Skills" in summary["by_section"]
        assert summary["by_section"]["Skills"]["n"] == 2
        assert summary["by_section"]["Skills"]["mean_delta"] == pytest.approx(3.0)
        assert summary["by_section"]["Contact"]["n"] == 1
        assert summary["by_section"]["Contact"]["mean_delta"] == pytest.approx(1.0)

    def test_summary_empty_log(self, tmp_path):
        log = tmp_path / "corr.jsonl"
        summary = corrections_summary(log)
        assert summary["total"] == 0
        assert summary["by_section"] == {}

    def test_summary_handles_malformed_lines(self, tmp_path):
        log = tmp_path / "corr.jsonl"
        append_correction(log, Correction(
            cv_filename="x.pdf", section="Skills",
            auto_score=3.0, human_score=7.0,
        ))
        # Append garbage
        with log.open("a") as f:
            f.write("not valid json\n")
        append_correction(log, Correction(
            cv_filename="y.pdf", section="Contact",
            auto_score=5.0, human_score=8.0,
        ))
        summary = corrections_summary(log)
        # Malformed line is silently skipped
        assert summary["total"] == 2
