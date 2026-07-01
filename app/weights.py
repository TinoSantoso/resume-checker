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

RUBRIC_DIR: str = '/mnt/d/Development/resume-reviewer/kb/rubrics'
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
        'Contact': 0.0822,
        'Summary': 0.1027,
        'Experience': 0.4247,
        'Skills': 0.2055,
        'Projects': 0.0685,
        'Education': 0.0479,
        'Length_Formatting': 0.0685,
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
        'Contact': 0.0654,
        'Summary': 0.1176,
        'Experience': 0.5556,
        'Skills': 0.0523,
        'Education': 0.0654,
        'Projects': 0.0784,
        'Length_Formatting': 0.0654,
    },
}

# Default weights = 'general' role (backward compatible with v0.x).
SECTION_WEIGHTS: Dict[str, float] = SECTION_WEIGHTS_BY_ROLE['general']

__all__ = [
    'RUBRIC_DIR',
    'SUPPORTED_ROLES',
    'SECTION_WEIGHTS',
    'SECTION_WEIGHTS_BY_ROLE',
]
