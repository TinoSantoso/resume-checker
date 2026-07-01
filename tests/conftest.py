"""Pytest configuration: ensure project root is importable.

We don't ship a pyproject.toml yet, so `app` isn't installed editable.
This conftest puts the project root on sys.path for every test.
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
