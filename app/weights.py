"""Auto-generated from kb/rubrics/*.json — DO NOT EDIT BY HAND.

Regenerate with: python3 scripts/build_weights.py

Per-section weights are derived by summing per-rule weights
within each role's rubric, then normalizing so they sum to 1.0.

Each role uses different weights — see SECTION_WEIGHTS_BY_ROLE.
SECTION_WEIGHTS below is the 'general' default (kept for v0.x
backward compatibility).
"""
from __future__ import annotations

from typing import Dict
from pathlib import Path

RUBRIC_DIR: Path = Path(__file__).resolve().parent.parent / 'kb/rubrics'
SUPPORTED_ROLES: tuple[str, ...] = ['general', 'swe', 'data', 'pm']

# Per-role, per-section normalized weights (sum to 1.0 within each role).
SECTION_WEIGHTS_BY_ROLE: Dict[str, Dict[str, float]] = {
    'general': {
        'Contact': 0.1349,
        'Summary': 0.119,
        'Experience': 0.4365,
        'Skills': 0.1746,
        'Education': 0.0556,
        'Length_Formatting': 0.0794,
    },
    'swe': {
        'Contact': 0.0795,
        'Summary': 0.1325,
        'Experience': 0.4106,
        'Skills': 0.1987,
        'Projects': 0.0662,
        'Education': 0.0464,
        'Length_Formatting': 0.0662,
    },
    'data': {
        'Contact': 0.0654,
        'Summary': 0.098,
        'Experience': 0.4118,
        'Skills': 0.2157,
        'Projects': 0.0654,
        'Education': 0.0784,
        'Length_Formatting': 0.0654,
    },
    'pm': {
        'Contact': 0.0625,
        'Summary': 0.1125,
        'Experience': 0.5125,
        'Skills': 0.1125,
        'Education': 0.0625,
        'Projects': 0.075,
        'Length_Formatting': 0.0625,
    },
}

# Default weights = 'general' role (backward compatible with v0.x).
SECTION_WEIGHTS: Dict[str, float] = SECTION_WEIGHTS_BY_ROLE['general']

# Ponytail: named weight presets for the Streamlit A/B sidebar.
# Reuses the 4 role variants already in SECTION_WEIGHTS_BY_ROLE — no new
# weights invented. Add an entry here to surface a new experiment in the UI.
WEIGHT_PRESETS: Dict[str, str] = {
    "v1 · current (general)": "general",
    "v1 · swe-tuned": "swe",
    "v1 · data-tuned": "data",
    "v1 · pm-tuned": "pm",
}

__all__ = [
    'RUBRIC_DIR',
    'SUPPORTED_ROLES',
    'SECTION_WEIGHTS',
    'SECTION_WEIGHTS_BY_ROLE',
    'WEIGHT_PRESETS',
]
