"""Rubric registry — load role-specific ATS rubrics.

Single source of truth for rubric files. Used by:
- ``scorer.py`` to look up per-rule weights and rationales
- ``rag.py`` to embed each rule into the vector store (with role metadata)
- ``build_weights.py`` to regenerate ``app/weights.py``

Public surface
--------------
- ``load_rubric(role)`` — return list of rule dicts for a given role
- ``load_all_rubrics()`` — return dict {role: rules}
- ``RUBRIC_ROLES`` — tuple of supported role names
- ``RUBRIC_DIR`` — path to the rubric directory (single source of truth)

Adding a new role
-----------------
1. Drop a JSON file into ``kb/rubrics/<role>.json`` with the same schema
   as ``general.json`` (id, category, rule, weight, rationale).
2. Add ``<role>`` to ``RUBRIC_ROLES``.
3. Add signal keywords to ``app/role_detector.py`` (SWE_SIGNALS,
   DATA_SIGNALS, PM_SIGNALS, or a new role set if expanding).
4. Run ``python3 scripts/build_weights.py`` to regenerate ``app/weights.py``.
5. Add tests in ``tests/test_rubric_registry.py``.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Dict, List


# --------------------------------------------------------------------------- #
# Paths and supported roles
# --------------------------------------------------------------------------- #

# Project root: this file is at app/rubric_registry.py, so root is one
# level up + /kb/rubrics. We resolve relative to __file__ so the registry
# works regardless of the caller's CWD.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
RUBRIC_DIR: Path = _PROJECT_ROOT / "kb" / "rubrics"

# Backward-compat shim: the legacy ``kb/ats_rubric.json`` (the v0.x single
# rubric) is now ``kb/rubrics/general.json``. Keep the old constant
# exported so anything still importing it gets the new path.
SOURCE_RUBRIC_GENERAL: Path = RUBRIC_DIR / "general.json"

# Supported role identifiers. Must match filenames in ``RUBRIC_DIR``.
RUBRIC_ROLES: tuple[str, ...] = ("general", "swe", "data", "pm")


# --------------------------------------------------------------------------- #
# Loaders
# --------------------------------------------------------------------------- #


@lru_cache(maxsize=None)
def _load_rubric_cached(role: str) -> tuple[dict, ...]:
    """Cached raw load: returns a tuple of rule dicts (hashable for lru_cache).

    We cache the tuple form because dicts aren't hashable. The public
    ``load_rubric`` wraps this and returns a list (mutable) for callers.
    """
    if role not in RUBRIC_ROLES:
        raise ValueError(
            f"unknown role '{role}'. Supported: {list(RUBRIC_ROLES)}"
        )
    path = RUBRIC_DIR / f"{role}.json"
    if not path.exists():
        raise FileNotFoundError(
            f"rubric file missing for role '{role}': expected at {path}"
        )
    with path.open(encoding="utf-8") as f:
        rules = json.load(f)
    # Validate shape — every rule must have id, category, rule, weight, rationale.
    for r in rules:
        for required in ("id", "category", "rule", "weight", "rationale"):
            if required not in r:
                raise ValueError(
                    f"rubric {path.name} rule {r.get('id', '?')} missing field '{required}'"
                )
    return tuple(rules)


def load_rubric(role: str) -> List[dict]:
    """Load the rubric for the given role.

    Args:
        role: One of ``RUBRIC_ROLES`` (case-sensitive).

    Returns:
        List of rule dicts, each with keys ``id``, ``category``, ``rule``,
        ``weight``, ``rationale``. The list is a fresh copy each call
        (mutating it doesn't poison the cache).

    Raises:
        ValueError: Unknown role.
        FileNotFoundError: Rubric file is missing on disk.
    """
    return [dict(r) for r in _load_rubric_cached(role)]


def load_all_rubrics() -> Dict[str, List[dict]]:
    """Load every supported rubric at once.

    Useful for the RAG builder, which embeds every rule from every rubric
    in a single pass (with role metadata on each document).

    Returns:
        Dict mapping role name -> list of rule dicts.
    """
    return {role: load_rubric(role) for role in RUBRIC_ROLES}


__all__ = [
    "RUBRIC_DIR",
    "RUBRIC_ROLES",
    "SOURCE_RUBRIC_GENERAL",
    "load_rubric",
    "load_all_rubrics",
]


if __name__ == "__main__":
    # Quick sanity check: print rubric summary for each role.
    for role in RUBRIC_ROLES:
        rules = load_rubric(role)
        total_w = sum(r["weight"] for r in rules)
        print(f"\n[{role}] {len(rules)} rules, total weight={total_w:.1f}")
        for r in rules:
            print(f"  {r['id']:4s} ({r['category']:18s}) w={r['weight']:.1f}  {r['rule'][:60]}…")