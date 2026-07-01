"""Mobile-responsive layout helpers for the Streamlit CV Reviewer.

Two responsibilities:

1. ``inject_responsive_css()`` — load ``assets/styles.css`` and inject
   it into the running Streamlit app via ``st.markdown`` with
   ``unsafe_allow_html=True``. Should be called once at the very top of
   ``streamlit_app.main()`` (after ``st.set_page_config``).

2. ``card_container(title, content_html)`` — pure helper that builds an
   HTML card string. Useful when you want a card layout that survives
   arbitrary content length and renders identically inside Streamlit's
   ``st.markdown(..., unsafe_allow_html=True)``.

The helpers avoid touching Streamlit at import time so that
``import app.streamlit_layout`` works inside unit tests (where no
``ScriptRunContext`` exists).
"""
from __future__ import annotations

import html
from pathlib import Path
from typing import Optional

# Lazy Streamlit import — only needed when the helpers are called for real.
# Tests that import this module without a ScriptRunContext can still use
# the pure ``card_container`` helper (it doesn't touch Streamlit at all).
try:
    import streamlit as st  # type: ignore[import-untyped]
except ImportError:  # pragma: no cover — streamlit is a hard dep
    st = None  # type: ignore[assignment]


# --------------------------------------------------------------------------- #
# CSS file resolution.
# --------------------------------------------------------------------------- #

# Path to the stylesheet. Resolved relative to this module so it works
# regardless of the caller's cwd.
_CSS_PATH: Path = Path(__file__).resolve().parent.parent / "assets" / "styles.css"


# --------------------------------------------------------------------------- #
# inject_responsive_css()
# --------------------------------------------------------------------------- #

def inject_responsive_css() -> None:
    """Read ``assets/styles.css`` and inject it as a ``<style>`` block.

    Streamlit doesn't ship a ``st.css()`` primitive yet (1.58), so we
    embed the CSS inside ``st.markdown`` with ``unsafe_allow_html=True``.
    The CSS is read at call time (not at import time) so edits to the
    file are picked up on the next rerun — no restart required.

    Raises:
        FileNotFoundError: if ``assets/styles.css`` is missing.
        RuntimeError: if called outside a Streamlit script run.
    """
    if st is None:
        raise RuntimeError(
            "inject_responsive_css() called but streamlit is not installed"
        )
    if not _CSS_PATH.exists():
        raise FileNotFoundError(
            f"Responsive CSS missing at {_CSS_PATH}. "
            "Did the assets/ folder get deleted?"
        )
    css_body = _CSS_PATH.read_text(encoding="utf-8")
    # Wrap in a style tag. We deliberately do NOT escape the CSS body
    # because it contains characters that html.escape would mangle.
    st.markdown(
        f"<style>{css_body}</style>",
        unsafe_allow_html=True,
    )


# --------------------------------------------------------------------------- #
# card_container()
# --------------------------------------------------------------------------- #

# Default CSS class name; matches the selector in assets/styles.css.
_CARD_CLASS = "score-card"

# Optional second class for the row variant (section-row).
_ROW_CLASS = "section-row"


def card_container(
    title: str,
    content_html: str,
    *,
    variant: str = "card",
    extra_classes: Optional[str] = None,
) -> str:
    """Return an HTML card string.

    Args:
        title: Card heading. HTML-escaped automatically so a value like
            ``"Score < 5"`` doesn't break the surrounding markup.
        content_html: Body HTML. NOT escaped — caller controls the markup
            (use for trusted content like metric values, button rows, etc).
        variant: ``"card"`` (default) or ``"row"``. Selects the CSS class.
        extra_classes: Space-separated class names to append.

    Returns:
        A string of HTML suitable for passing into
        ``st.markdown(..., unsafe_allow_html=True)``.

    Example:
        >>> card_container("Overall", "<strong>9.5</strong> / 10")
        '<div class="score-card">...'
    """
    base_class = _ROW_CLASS if variant == "row" else _CARD_CLASS
    classes = base_class
    if extra_classes:
        classes = f"{classes} {extra_classes.strip()}"

    safe_title = html.escape(title, quote=True)
    return (
        f'<div class="{classes}">'
        f'<div class="{base_class}__title">{safe_title}</div>'
        f'<div class="{base_class}__value">{content_html}</div>'
        f"</div>"
    )


__all__ = ["inject_responsive_css", "card_container", "_CSS_PATH"]