"""Validation harness — measure correlation between auto-score and human grade.

Goal: prove the heuristic scorer actually tracks what a human reviewer would
say. Until we have 20+ manually graded CVs, the heuristic is a guess.

What this script does
---------------------
1. Loads a JSON file mapping CV path -> human grades (overall + per-section).
2. Runs the deterministic scorer on each CV.
3. Computes Pearson + Spearman correlation, MAE, and per-section deltas.
4. Prints a report. Exits non-zero if correlation < 0.5 OR MAE > 2.5.

The graded set is intentionally separate from unit-test fixtures:
- data/validation/grades.json  — the human labels
- data/validation/*.pdf|*.docx  — the CV files

Schema for grades.json
----------------------
{
  "<cv_filename>": {
    "human_overall": 7.5,          // 0-10, single number
    "human_sections": {            // optional, per-section 0-10
      "Contact": 9.0,
      "Summary": 8.0,
      "Experience": 7.0,
      "Skills": 8.0,
      "Education": 9.0
    },
    "notes": "Strong SWE with good metrics. Summary a bit long."
  },
  ...
}

Usage
-----
    .venv/bin/python scripts/validate_against_human.py \\
        --grades data/validation/grades.json \\
        --cv-dir data/validation

If the script can't find a CV for a grade, it warns and skips.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Make `from app.scorer import ...` work whether the script is run from
# the project root or from scripts/ directly.
_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.scorer import score_cv  # noqa: E402


# --------------------------------------------------------------------------- #
# Statistics helpers (pure stdlib, no scipy/numpy dependency)
# --------------------------------------------------------------------------- #

def pearson(xs: list[float], ys: list[float]) -> float:
    """Pearson correlation coefficient. Returns NaN if variance is 0."""
    n = len(xs)
    if n < 2:
        return float("nan")
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    dy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if dx == 0 or dy == 0:
        return float("nan")
    return num / (dx * dy)


def spearman(xs: list[float], ys: list[float]) -> float:
    """Spearman rank correlation. Pearson on the rank-transformed values."""
    def rankify(vs: list[float]) -> list[float]:
        # Average-rank ties: assign each unique value its mean rank.
        sorted_pairs = sorted(enumerate(vs), key=lambda p: p[1])
        ranks = [0.0] * len(vs)
        i = 0
        while i < len(sorted_pairs):
            j = i
            while j + 1 < len(sorted_pairs) and sorted_pairs[j + 1][1] == sorted_pairs[i][1]:
                j += 1
            # Indices i..j all have the same value; their rank is mean of 1-based positions.
            avg_rank = (i + 1 + j + 1) / 2
            for k in range(i, j + 1):
                orig_idx, _ = sorted_pairs[k]
                ranks[orig_idx] = avg_rank
            i = j + 1
        return ranks
    return pearson(rankify(xs), rankify(ys))


def mae(xs: list[float], ys: list[float]) -> float:
    """Mean absolute error."""
    if not xs:
        return float("nan")
    return sum(abs(x - y) for x, y in zip(xs, ys)) / len(xs)


# --------------------------------------------------------------------------- #
# Data loading
# --------------------------------------------------------------------------- #

@dataclass
class HumanGrade:
    path: Path
    human_overall: float
    human_sections: dict[str, float]
    notes: str
    human_role: str = "general"  # Role tag for role-aware validation.

    @classmethod
    def from_json(cls, cv_dir: Path, payload: dict[str, Any]) -> "HumanGrade | None":
        # The key in grades.json is the filename (with or without extension).
        # Resolve to the actual path under cv_dir, trying common extensions.
        filename = payload.get("__file__", "")
        if not filename:
            return None
        path = cv_dir / filename
        if not path.exists():
            # Try appending common CV extensions
            for ext in (".pdf", ".docx", ".txt"):
                candidate = cv_dir / (filename + ext)
                if candidate.exists():
                    path = candidate
                    break
            else:
                print(f"  WARN: CV file not found for {filename!r} in {cv_dir}", file=sys.stderr)
                return None
        return cls(
            path=path,
            human_overall=float(payload["human_overall"]),
            human_sections={k: float(v) for k, v in payload.get("human_sections", {}).items()},
            notes=str(payload.get("notes", "")),
            human_role=str(payload.get("human_role", "general")),
        )


def load_grades(grades_path: Path, cv_dir: Path) -> list[HumanGrade]:
    """Parse grades.json into a list of HumanGrade records.

    The file is a flat object: ``{ "<filename>": { ...grade data... } }``.
    """
    if not grades_path.exists():
        print(f"  WARN: grades file not found: {grades_path}", file=sys.stderr)
        return []
    raw = json.loads(grades_path.read_text())
    out: list[HumanGrade] = []
    for filename, payload in raw.items():
        if not isinstance(payload, dict):
            continue
        # Inject the filename so HumanGrade.from_json can resolve the path
        payload.setdefault("__file__", filename)
        g = HumanGrade.from_json(cv_dir, payload)
        if g is not None:
            out.append(g)
    return out


# --------------------------------------------------------------------------- #
# Scoring + comparison
# --------------------------------------------------------------------------- #

def score_one(grade: HumanGrade, use_role_rubrics: bool = False) -> dict[str, Any] | None:
    """Run score_cv on one CV. Returns None on error.

    When ``use_role_rubrics`` is True, the CV is scored with the role
    specified by ``grade.human_role`` instead of auto-detection. This
    isolates role-specific rubric performance: it tells us how well each
    role's rubric tracks human judgment, independent of detector accuracy.
    """
    try:
        if use_role_rubrics:
            rep = score_cv(grade.path, role=grade.human_role)
        else:
            rep = score_cv(grade.path)
    except Exception as e:
        print(f"  ERROR scoring {grade.path.name}: {e}", file=sys.stderr)
        return None
    return {
        "auto_overall": rep.overall,
        "auto_sections": {n: s.score for n, s in rep.sections.items()},
        "detected_role": rep.role,
        "human_role": grade.human_role,
    }


def print_report(grades: list[HumanGrade], scored: list[tuple[HumanGrade, dict]], use_role_rubrics: bool = False) -> None:
    """Pretty-print the comparison + correlations."""
    print()
    print("=" * 78)
    mode = "ROLE-AWARE" if use_role_rubrics else "GENERAL"
    print(f"CV REVIEWER VALIDATION REPORT [{mode}]")
    print("=" * 78)
    print(f"Samples: {len(grades)} graded CVs\n")

    # Per-sample detail
    if use_role_rubrics:
        # Show detected role + human role alignment.
        print(f"{'CV':<30} {'role':>5} {'human':>6} {'auto':>6} {'Δ':>5}  notes")
        print("-" * 78)
        for g, s in scored:
            delta = s["auto_overall"] - g.human_overall
            sign = "+" if delta >= 0 else ""
            short_name = g.path.name[:28]
            role_tag = f"{s['detected_role']}/{g.human_role}"
            short_notes = g.notes[:25] if g.notes else ""
            print(f"{short_name:<30} {role_tag:>5} {g.human_overall:>6.1f} {s['auto_overall']:>6.1f} {sign}{delta:>4.1f}  {short_notes}")

        # Role detection accuracy line.
        correct = sum(1 for g, s in scored if s["detected_role"] == s["human_role"])
        print(f"\nRole detector accuracy: {correct}/{len(scored)}")
    else:
        print(f"{'CV':<40} {'human':>7} {'auto':>7} {'Δ':>6}   notes")
        print("-" * 78)
        for g, s in scored:
            delta = s["auto_overall"] - g.human_overall
            sign = "+" if delta >= 0 else ""
            short_name = g.path.name[:38]
            short_notes = g.notes[:25] if g.notes else ""
            print(f"{short_name:<40} {g.human_overall:>7.1f} {s['auto_overall']:>7.1f} {sign}{delta:>5.1f}   {short_notes}")

    # Overall correlation
    humans = [g.human_overall for g, _ in scored]
    autos = [s["auto_overall"] for _, s in scored]
    p = pearson(humans, autos)
    sp = spearman(humans, autos)
    err = mae(humans, autos)

    print()
    print("Overall-score correlation:")
    print(f"  Pearson:  {p:+.3f}    (1.0 = perfect, 0.0 = no relationship)")
    print(f"  Spearman: {sp:+.3f}    (rank-based, robust to outliers)")
    print(f"  MAE:      {err:.2f} points  (mean absolute error)")

    # Per-section correlation (only for sections with >= 3 human grades)
    print()
    print("Per-section correlation (Pearson):")
    section_names: set[str] = set()
    for g, _ in scored:
        section_names.update(g.human_sections.keys())

    for sec in sorted(section_names):
        h_vals: list[float] = []
        a_vals: list[float] = []
        for g, s in scored:
            if sec in g.human_sections and sec in s["auto_sections"]:
                h_vals.append(g.human_sections[sec])
                a_vals.append(s["auto_sections"][sec])
        if len(h_vals) < 3:
            print(f"  {sec:<20} (n={len(h_vals)}, need 3+ for correlation)")
            continue
        sec_p = pearson(h_vals, a_vals)
        sec_err = mae(h_vals, a_vals)
        flag = "  ⚠️" if sec_p < 0.5 else ""
        print(f"  {sec:<20} n={len(h_vals):>3}  Pearson={sec_p:+.3f}  MAE={sec_err:.2f}{flag}")

    # Verdict
    print()
    print("=" * 78)
    if len(scored) < 5:
        print(f"VERDICT: ⚠️  Only {len(scored)} samples — need >= 5 for reliable correlation.")
    elif math.isnan(p):
        print("VERDICT: ⚠️  Cannot compute correlation (all human or all auto scores identical).")
    elif p < 0.5:
        print(f"VERDICT: ❌  Pearson {p:+.3f} below 0.5 threshold. Heuristic needs recalibration.")
    elif err > 2.5:
        print(f"VERDICT: ⚠️  Correlation OK ({p:+.3f}) but MAE {err:.2f} above 2.5 — scores drift.")
    else:
        print(f"VERDICT: ✅  Heuristic tracks human judgment (Pearson {p:+.3f}, MAE {err:.2f}).")
    print("=" * 78)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument(
        "--grades",
        type=Path,
        default=Path("data/validation/grades.json"),
        help="Path to grades.json (default: data/validation/grades.json)",
    )
    parser.add_argument(
        "--cv-dir",
        type=Path,
        default=Path("data/validation"),
        help="Directory containing the CV files (default: data/validation)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero if correlation is below threshold (CI mode).",
    )
    parser.add_argument(
        "--use-role-rubrics",
        action="store_true",
        help=(
            "Score each CV with the role specified in grades.json "
            "(human_role field) instead of auto-detection. Measures how well "
            "each role's rubric tracks human judgment, isolating rubric "
            "quality from detector accuracy."
        ),
    )
    args = parser.parse_args()

    grades = load_grades(args.grades, args.cv_dir)
    if not grades:
        print(f"No grades loaded from {args.grades}", file=sys.stderr)
        print("Create the file with the schema documented at the top of this script.", file=sys.stderr)
        return 1

    scored: list[tuple[HumanGrade, dict]] = []
    for g in grades:
        s = score_one(g, use_role_rubrics=args.use_role_rubrics)
        if s is not None:
            scored.append((g, s))

    if not scored:
        print("No CVs scored successfully.", file=sys.stderr)
        return 1

    print_report(grades, scored, use_role_rubrics=args.use_role_rubrics)

    # CI / strict mode
    if args.strict and scored:
        humans = [g.human_overall for g, _ in scored]
        autos = [s["auto_overall"] for _, s in scored]
        p = pearson(humans, autos)
        if math.isnan(p) or p < 0.5 or mae(humans, autos) > 2.5:
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
