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
import random
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

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
# Bootstrap confidence intervals (B2)
# --------------------------------------------------------------------------- #

def bootstrap_ci(
    xs: list[float],
    ys: list[float],
    n_boot: int = 1000,
    seed: int = 42,
    alpha: float = 0.05,
) -> tuple[float, float]:
    """Return (lower, upper) of a percentile bootstrap CI for the MAE.

    Why MAE and not Pearson?
    ------------------------
    Pearson CI on small samples is unstable and not the main question we
    need answered ("how confident are we in our point estimate of the
    error?"). The mean absolute error is the thing we actually report
    to users, so its CI is the most actionable.

    Returns (NaN, NaN) when the input is too small to bootstrap (n < 2).
    """
    n = len(xs)
    if n < 2:
        return float("nan"), float("nan")
    if len(ys) != n:
        raise ValueError(f"xs/ys length mismatch: {n} vs {len(ys)}")

    rng = random.Random(seed)
    samples: list[float] = []
    indices = list(range(n))
    for _ in range(n_boot):
        # Resample with replacement
        boot_idx = [rng.choice(indices) for _ in range(n)]
        bx = [xs[i] for i in boot_idx]
        by = [ys[i] for i in boot_idx]
        try:
            err = mae(bx, by)
        except ZeroDivisionError:
            continue
        if not math.isnan(err):
            samples.append(err)

    if not samples:
        return float("nan"), float("nan")

    samples.sort()
    lower_idx = max(0, int(len(samples) * (alpha / 2)))
    upper_idx = min(len(samples) - 1, int(len(samples) * (1 - alpha / 2)))
    return samples[lower_idx], samples[upper_idx]


# --------------------------------------------------------------------------- #
# Blind-spot detection (B2)
# --------------------------------------------------------------------------- #

def blind_spots(
    section_data: dict[str, tuple[list[float], list[float]]],
    delta_threshold: float = 1.5,
    pearson_floor: float = 0.4,
    min_samples: int = 3,
) -> dict[str, dict[str, Any]]:
    """Flag sections where the heuristic is miscalibrated.

    Parameters
    ----------
    section_data
        Mapping of section name -> (human_scores, auto_scores).
    delta_threshold
        Sections whose mean |delta| exceeds this are flagged for bias.
    pearson_floor
        Sections whose Pearson falls below this are flagged for ranking
        quality (the order of CVs by score is wrong).
    min_samples
        Skip sections with fewer than this many samples (statistical
        significance is meaningless below n=3).

    Returns
    -------
    dict[section_name, {"delta": float, "pearson": float, "flag": str}]
    """
    flags: dict[str, dict[str, Any]] = {}
    for section, (h_vals, a_vals) in section_data.items():
        n = len(h_vals)
        if n < min_samples:
            continue
        mean_delta = sum(ah - hh for ah, hh in zip(a_vals, h_vals)) / n
        r = pearson(h_vals, a_vals)
        reasons: list[str] = []
        if abs(mean_delta) > delta_threshold:
            reasons.append(f"|Δ|={abs(mean_delta):.2f}>{delta_threshold}")
        if not math.isnan(r) and r < pearson_floor:
            reasons.append(f"Pearson={r:.2f}<{pearson_floor}")
        if reasons:
            flags[section] = {
                "delta": mean_delta,
                "pearson": r,
                "flag": "; ".join(reasons),
                "n": n,
            }
    return flags


# --------------------------------------------------------------------------- #
# Role-grouped correlation (B2)
# --------------------------------------------------------------------------- #

def correlate_by_group(
    items: Iterable[tuple[float, float, str]],
    key: Callable[[tuple[float, float, str]], str],
) -> dict[str, dict[str, Any]]:
    """Group triples (human, auto, label) by label and compute correlation.

    Returns a dict of ``{label: {"n", "pearson", "spearman", "mae"}}`` for
    every label with at least one item. Pearson is NaN for n<2.
    """
    groups: dict[str, list[tuple[float, float]]] = {}
    for it in items:
        label = key(it) or ""
        if not label:
            continue
        groups.setdefault(label, []).append((it[0], it[1]))

    out: dict[str, dict[str, Any]] = {}
    for label, pairs in groups.items():
        if not pairs:
            continue
        n = len(pairs)
        h = [p[0] for p in pairs]
        a = [p[1] for p in pairs]
        out[label] = {
            "n": n,
            "pearson": pearson(h, a) if n >= 2 else float("nan"),
            "spearman": spearman(h, a) if n >= 2 else float("nan"),
            "mae": mae(h, a),
        }
    return out


# --------------------------------------------------------------------------- #
# Corrections log (C5 integration)
# --------------------------------------------------------------------------- #

def load_corrections(path: Path) -> list[dict[str, Any]]:
    """Read the JSONL corrections log produced by the HITL UI.

    The log is append-only and tolerant of malformed lines (they are
    silently skipped — never crash the validation report over a single
    bad row).
    """
    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            # Skip malformed lines — never crash a validation run on
            # one corrupt row.
            continue
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


def print_report(
    grades: list[HumanGrade],
    scored: list[tuple[HumanGrade, dict]],
    use_role_rubrics: bool = False,
    corrections: list[dict[str, Any]] | None = None,
) -> None:
    """Pretty-print the comparison + correlations.

    B2 extensions: bootstrap CI on overall MAE, blind-spot detection
    per section, role-grouped breakdown, and (if a corrections log
    was loaded) a summary of HITL corrections applied.
    """
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
    err_lo, err_hi = bootstrap_ci(humans, autos, n_boot=1000, seed=42)

    print()
    print("Overall-score correlation:")
    print(f"  Pearson:  {p:+.3f}    (1.0 = perfect, 0.0 = no relationship)")
    print(f"  Spearman: {sp:+.3f}    (rank-based, robust to outliers)")
    if math.isnan(err_lo):
        print(f"  MAE:      {err:.2f} points  (CI: n/a, too few samples)")
    else:
        print(f"  MAE:      {err:.2f} points  95% CI [{err_lo:.2f}, {err_hi:.2f}]")

    # Per-section correlation (only for sections with >= 3 human grades)
    print()
    print("Per-section correlation (Pearson):")
    section_names: set[str] = set()
    for g, _ in scored:
        section_names.update(g.human_sections.keys())

    section_data: dict[str, tuple[list[float], list[float]]] = {}
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
        section_data[sec] = (h_vals, a_vals)
        sec_p = pearson(h_vals, a_vals)
        sec_err = mae(h_vals, a_vals)
        sec_lo, sec_hi = bootstrap_ci(h_vals, a_vals, n_boot=1000, seed=42)
        ci_str = (
            f"CI [{sec_lo:.2f},{sec_hi:.2f}]"
            if not math.isnan(sec_lo)
            else "CI n/a"
        )
        flag = "  ⚠️" if sec_p < 0.5 else ""
        print(f"  {sec:<20} n={len(h_vals):>3}  Pearson={sec_p:+.3f}  MAE={sec_err:.2f} {ci_str}{flag}")

    # Blind-spot detection
    print()
    print("Blind-spot detection (sections needing recalibration):")
    flags = blind_spots(section_data, delta_threshold=1.5, pearson_floor=0.4)
    if not flags:
        print("  (none — heuristic is well-calibrated across all sections)")
    else:
        for sec, info in sorted(flags.items()):
            delta = info["delta"]
            sign = "+" if delta >= 0 else ""
            print(
                f"  {sec:<20} Δ={sign}{delta:.2f}  Pearson={info['pearson']:+.3f}  "
                f"({info['flag']})"
            )

    # Role-grouped breakdown
    print()
    print("Role-grouped correlation:")
    role_items = [(g.human_overall, s["auto_overall"], g.human_role) for g, s in scored]
    role_groups = correlate_by_group(role_items, key=lambda x: x[2])
    if not role_groups:
        print("  (no role tags in grades)")
    else:
        print(f"  {'role':<12} {'n':>3}  {'Pearson':>8}  {'MAE':>6}")
        for role, info in sorted(role_groups.items()):
            r_str = f"{info['pearson']:+.3f}" if not math.isnan(info["pearson"]) else "  n/a "
            print(f"  {role:<12} {info['n']:>3}  {r_str:>8}  {info['mae']:>6.2f}")

    # Corrections log summary
    if corrections:
        print()
        print(f"Corrections log (HITL): {len(corrections)} entries")
        # By section
        by_section: dict[str, list[float]] = {}
        for c in corrections:
            sec = c.get("section", "Unknown")
            delta = float(c.get("human", 0)) - float(c.get("auto", 0))
            by_section.setdefault(sec, []).append(delta)
        for sec, deltas in sorted(by_section.items()):
            mean_d = sum(deltas) / len(deltas)
            print(f"  {sec:<20} n={len(deltas):>3}  mean Δ={mean_d:+.2f}")

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
    parser.add_argument(
        "--corrections",
        type=Path,
        default=None,
        help=(
            "Optional path to a JSONL corrections log produced by the "
            "HITL UI (C5). When provided, the report includes a summary "
            "of corrections applied."
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

    # Load corrections log if provided (C5 integration).
    corrections: list[dict[str, Any]] = []
    if args.corrections is not None:
        corrections = load_corrections(args.corrections)

    print_report(grades, scored, use_role_rubrics=args.use_role_rubrics, corrections=corrections)

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
