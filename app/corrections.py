"""HITL correction storage (C5).

Stores recruiter overrides of auto-scored sections in an append-only
JSONL log. The log is a deliberately separate file from
``data/validation/grades.json`` so that:

* The grades file is the curated, version-controlled ground truth.
* The corrections log can be wiped, exported, or merged without
  affecting grades.
* Each correction is individually auditable (timestamped).

Schema for one row::

    {
        "timestamp": "2026-07-01T13:45:00.123Z",  # auto-filled (ISO 8601 UTC)
        "cv_filename": "tino_actual.pdf",
        "section": "Experience",
        "auto_score": 4.5,
        "human_score": 7.0,
        "auto_evidence": "...",  # optional
        "human_evidence": "...",  # optional
        "recruiter_id": "tino"    # optional
    }

The module is deliberately stdlib-only and crash-proof — a malformed
row in the log must never block the validation report or the UI.
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
ALLOWED_SECTIONS = {
    "Contact", "Summary", "Experience", "Skills", "Education",
    "Certifications", "Projects", "Links", "Other",
}


@dataclass
class Correction:
    """A single recruiter override of one section score."""
    cv_filename: str
    section: str
    auto_score: float
    human_score: float
    auto_evidence: str = ""
    human_evidence: str = ""
    recruiter_id: str = ""
    timestamp: str = ""  # auto-filled on append

    def to_row(self) -> dict[str, Any]:
        # Always include the core fields; include optional fields only
        # if they were explicitly set (non-empty). This keeps the log
        # compact without losing any intentional data.
        d = asdict(self)
        keep_optional = {"auto_evidence", "human_evidence", "recruiter_id"}
        return {k: v for k, v in d.items() if k not in keep_optional or v}


def validate_correction_payload(payload: dict[str, Any]) -> tuple[bool, str]:
    """Validate a dict from the UI before it's appended.

    Returns (ok, error_message). Empty error message means OK.
    """
    if not payload.get("cv_filename"):
        return False, "cv_filename is required"
    if not payload.get("section"):
        return False, "section is required"
    for key in ("auto_score", "human_score"):
        v = payload.get(key)
        if not isinstance(v, (int, float)):
            return False, f"{key} must be numeric"
        if not (0.0 <= float(v) <= 10.0):
            return False, f"{key} must be in 0..10 (got {v})"
    return True, ""


def _make_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + \
        f"{int(time.time() * 1000) % 1000:03d}Z"


def append_correction(path: Path, correction: Correction) -> None:
    """Append one correction to the JSONL log.

    Creates parent directories if needed. The row is auto-timestamped
    and a final newline is always written so each row is on its own
    line. Append-mode writes are atomic for small payloads on POSIX
    (the OS guarantees write atomicity below PIPE_BUF; on Linux this
    is 4096 bytes — well above our row size).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    if not correction.timestamp:
        correction.timestamp = _make_timestamp()
    row = correction.to_row()
    row["schema_version"] = SCHEMA_VERSION

    line = json.dumps(row, ensure_ascii=False, separators=(",", ":"))
    with path.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def load_corrections(path: Path) -> list[Correction]:
    """Read the JSONL log and return all valid rows as Correction records.

    Malformed lines are silently skipped — never crash the validation
    report or UI on a single bad row. The log is allowed to be missing.
    """
    if not path.exists():
        return []
    out: list[Correction] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(row, dict):
            continue
        ok, _ = validate_correction_payload(row)
        if not ok:
            continue
        out.append(Correction(
            cv_filename=str(row.get("cv_filename", "")),
            section=str(row.get("section", "")),
            auto_score=float(row.get("auto_score", 0.0)),
            human_score=float(row.get("human_score", 0.0)),
            auto_evidence=str(row.get("auto_evidence", "")),
            human_evidence=str(row.get("human_evidence", "")),
            recruiter_id=str(row.get("recruiter_id", "")),
            timestamp=str(row.get("timestamp", "")),
        ))
    return out


def corrections_summary(path: Path) -> dict[str, Any]:
    """Aggregate correction log into per-section stats.

    Returns::

        {
            "total": N,
            "by_section": {
                "Skills": {"n": 5, "mean_delta": +2.3, "min_delta": ..., "max_delta": ...},
                ...
            }
        }

    The ``mean_delta`` is human_score − auto_score. A positive value
    means the recruiter scored the section *higher* than the auto-scorer
    (i.e. the auto-scorer was too harsh).
    """
    corrections = load_corrections(path)
    by_section: dict[str, list[float]] = {}
    for c in corrections:
        delta = c.human_score - c.auto_score
        by_section.setdefault(c.section, []).append(delta)

    out_by_section: dict[str, dict[str, Any]] = {}
    for sec, deltas in by_section.items():
        out_by_section[sec] = {
            "n": len(deltas),
            "mean_delta": sum(deltas) / len(deltas),
            "min_delta": min(deltas),
            "max_delta": max(deltas),
        }

    return {
        "total": len(corrections),
        "by_section": out_by_section,
    }
