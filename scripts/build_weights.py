"""Build app/weights.py from kb/rubrics/*.json (one rubric per role).

Single source of truth: the rubric files define per-rule weights and the
section each rule belongs to (the ``category`` field). This script
aggregates per-role section weights and writes a Python module that
``scorer.py`` imports.

Why per-role?
-------------
Different roles weight sections differently:
- General: balanced weights
- SWE: Experience and Skills are highest (build + ship signal)
- Data: Experience and Skills are highest (data artifacts matter)
- PM: Experience highest (impact bullets dominate), Skills weighted lower
  (PM soft skills are OK per the PM rubric)

This script regenerates ALL roles in one pass and emits a single module
that exports a ``SECTION_WEIGHTS_BY_ROLE`` dict plus a default
``SECTION_WEIGHTS`` (the 'general' weights, for backward compatibility).

Usage:
    python3 scripts/build_weights.py
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

# Make app/ importable so we can use the registry.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from app.rubric_registry import RUBRIC_DIR, RUBRIC_ROLES, load_rubric


def derive_section_weights(rules: list[dict]) -> dict[str, float]:
    """Sum per-rule weights grouped by category, normalize to sum=1.0.

    A rule's section = its ``category`` field (which is set by the rubric
    author — no separate RULE_TO_SECTION mapping needed).
    """
    by_section: dict[str, float] = defaultdict(float)
    for rule in rules:
        section = rule["category"]
        by_section[section] += float(rule.get("weight", 0))

    total = sum(by_section.values())
    if total <= 0:
        raise ValueError(f"rubric weights sum to {total}, must be > 0")

    # Normalize and round to 4 decimal places.
    return {sec: round(w / total, 4) for sec, w in by_section.items()}


def render_module(
    weights_by_role: dict[str, dict[str, float]],
    rubric_dir: Path,
) -> str:
    """Render app/weights.py source code as a string."""
    lines: list[str] = []
    lines.append('"""Auto-generated from kb/rubrics/*.json — DO NOT EDIT BY HAND.')
    lines.append("")
    lines.append("Regenerate with: python3 scripts/build_weights.py")
    lines.append("")
    lines.append("Per-section weights are derived by summing per-rule weights")
    lines.append("within each role's rubric, then normalizing so they sum to 1.0.")
    lines.append("")
    lines.append("Each role uses different weights — see SECTION_WEIGHTS_BY_ROLE.")
    lines.append("SECTION_WEIGHTS below is the 'general' default (kept for v0.x")
    lines.append("backward compatibility).")
    lines.append('"""')
    lines.append("from __future__ import annotations")
    lines.append("")
    lines.append("from typing import Dict")
    lines.append("from pathlib import Path")
    lines.append("")
    # Emit path resolved relative to the *generated module's* location
    # (app/weights.py -> project root -> kb/rubrics). This makes the
    # module portable: it works on dev laptops, CI runners, and Docker
    # containers regardless of CWD, because the path is anchored to the
    # module file itself, not the caller's working directory.
    rel_dir = (rubric_dir.resolve().relative_to(_PROJECT_ROOT.resolve())
               if rubric_dir.is_absolute()
               else rubric_dir)
    lines.append(
        f"RUBRIC_DIR: Path = Path(__file__).resolve().parent.parent / "
        f"{rel_dir.as_posix()!r}"
    )
    lines.append(f"SUPPORTED_ROLES: tuple[str, ...] = {list(weights_by_role.keys())!r}")
    lines.append("")

    # Emit the per-role dict.
    lines.append("# Per-role, per-section normalized weights (sum to 1.0 within each role).")
    lines.append("SECTION_WEIGHTS_BY_ROLE: Dict[str, Dict[str, float]] = {")
    for role, weights in weights_by_role.items():
        lines.append(f"    {role!r}: {{")
        for sec, w in weights.items():
            lines.append(f"        {sec!r}: {w},")
        lines.append("    },")
    lines.append("}")
    lines.append("")

    # Default: 'general' weights, kept for v0.x backward compatibility.
    general = weights_by_role.get("general", {})
    lines.append("# Default weights = 'general' role (backward compatible with v0.x).")
    lines.append("SECTION_WEIGHTS: Dict[str, float] = SECTION_WEIGHTS_BY_ROLE['general']")
    lines.append("")
    lines.append("__all__ = [")
    lines.append("    'RUBRIC_DIR',")
    lines.append("    'SUPPORTED_ROLES',")
    lines.append("    'SECTION_WEIGHTS',")
    lines.append("    'SECTION_WEIGHTS_BY_ROLE',")
    lines.append("]")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    out_path = _PROJECT_ROOT / "app" / "weights.py"

    print(f"Reading rubrics from {RUBRIC_DIR}")
    weights_by_role: dict[str, dict[str, float]] = {}
    for role in RUBRIC_ROLES:
        rules = load_rubric(role)
        weights = derive_section_weights(rules)
        weights_by_role[role] = weights

        print(f"\n[{role}] {len(rules)} rules")
        for sec, w in sorted(weights.items(), key=lambda kv: -kv[1]):
            print(f"  {sec:<20} {w:.4f}")
        print(f"  {'TOTAL':<20} {sum(weights.values()):.4f}")

    out_path.write_text(render_module(weights_by_role, RUBRIC_DIR), encoding="utf-8")
    print(f"\nWrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())