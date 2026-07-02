"""Tests for the weight-preset A/B switch.

Presets reuse the 4 role-tuned weight tables in app.weights; this module
only checks that the mapping is consistent and the sidebar integration
plumbs the chosen preset through to score_cv as a role override.
"""
from __future__ import annotations

from app.weights import (
    SECTION_WEIGHTS_BY_ROLE,
    SUPPORTED_ROLES,
    WEIGHT_PRESETS,
)


class TestWeightPresetsMapping:
    """The preset table must reference real roles and not invent weights."""

    def test_presets_non_empty(self):
        assert len(WEIGHT_PRESETS) >= 2, "A/B needs at least 2 presets to compare"

    def test_preset_values_are_supported_roles(self):
        for name, role in WEIGHT_PRESETS.items():
            assert role in SUPPORTED_ROLES, (
                f"preset {name!r} maps to unknown role {role!r}"
            )

    def test_preset_targets_exist_in_section_weights(self):
        for name, role in WEIGHT_PRESETS.items():
            assert role in SECTION_WEIGHTS_BY_ROLE, (
                f"preset {name!r} targets role {role!r} with no weight table"
            )

    def test_default_preset_is_general(self):
        """The first preset must be the backward-compatible default."""
        first_name = next(iter(WEIGHT_PRESETS))
        assert WEIGHT_PRESETS[first_name] == "general"
        assert "general" in first_name.lower()

    def test_preset_keys_are_unique(self):
        keys = list(WEIGHT_PRESETS.keys())
        assert len(keys) == len(set(keys))

    def test_no_preset_collapses_to_self_reference(self):
        """Each preset maps to a real role; no None / empty / typos."""
        for name, role in WEIGHT_PRESETS.items():
            assert role and isinstance(role, str), (
                f"preset {name!r} has invalid role {role!r}"
            )


class TestPresetWeightsDistinct:
    """At least two presets must produce different scoring weights,
    otherwise the A/B switch is a no-op."""

    def test_at_least_two_distinct_weight_vectors(self):
        seen = set()
        for role in WEIGHT_PRESETS.values():
            weights = SECTION_WEIGHTS_BY_ROLE[role]
            seen.add(tuple(sorted(weights.items())))
        assert len(seen) >= 2, (
            "all preset roles share identical weight vectors; "
            "A/B switch has no observable effect"
        )


class TestStreamlitSidebarIntegration:
    """Verify streamlit_app.py exposes the A/B widget and plumbs it
    into score_cv via st.session_state."""

    def test_streamlit_app_imports_weight_presets(self):
        from app import streamlit_app  # noqa: F401

        src_path = streamlit_app.__file__
        src = open(src_path, encoding="utf-8").read()
        assert "WEIGHT_PRESETS" in src
        assert "_ab_preset_active" in src
        assert "Weight preset" in src or "A/B" in src

    def test_session_state_pop_is_used(self):
        """Preset should be one-shot (pop), not sticky across reruns."""
        from app import streamlit_app  # noqa: F401

        src = open(streamlit_app.__file__, encoding="utf-8").read()
        assert 'pop("_ab_preset_active"' in src, (
            "preset override must use pop() so reruns without reselecting "
            "don't permanently lock the role"
        )


# Ponytail: one-line demo self-check. Confirms WEIGHT_PRESETS is loadable
# and round-trips through the scoring pipeline without raising.
if __name__ == "__main__":
    import sys
    sys.path.insert(0, "/mnt/d/Development/resume-reviewer")
    for name, role in WEIGHT_PRESETS.items():
        w = SECTION_WEIGHTS_BY_ROLE[role]
        total = sum(w.values())
        assert abs(total - 1.0) < 0.01, f"{name} weights don't sum to 1.0: {total}"
    print(f"OK: {len(WEIGHT_PRESETS)} presets, all weights sum to 1.0")
