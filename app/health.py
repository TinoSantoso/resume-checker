"""Ollama health check (C2 backlog).

Reports whether the local Ollama server is reachable and whether the
models required by ``app.feedback`` and ``app.rag`` are pulled.

Used by the Streamlit sidebar to give the recruiter a clear status
indicator instead of letting the app crash silently when Ollama is
down. Also powers the optional "Pull model" button that talks to
Ollama's ``POST /api/pull`` endpoint.

Design notes:
- urllib only — no extra dependency on ``requests`` or ``httpx``
- Cached via ``functools.lru_cache`` so the Streamlit sidebar doesn't
  re-hit Ollama on every rerun (the cache can be cleared from the UI)
- Status codes (HEALTH_OK / HEALTH_OFFLINE / HEALTH_MODEL_MISSING) are
  short stable strings the UI can switch on
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from typing import List, Tuple
from urllib import error as urlerror
from urllib import request as urlrequest
from urllib.request import urlopen as _urlopen  # exposed for test monkeypatching


# --------------------------------------------------------------------------- #
# Status codes — used by the UI to render different colors/icons.
# --------------------------------------------------------------------------- #

HEALTH_OK = "ok"
HEALTH_OFFLINE = "offline"
HEALTH_MODEL_MISSING = "model_missing"


# --------------------------------------------------------------------------- #
# Required models — keep in sync with app/feedback.py and app/rag.py.
# --------------------------------------------------------------------------- #

REQUIRED_MODELS: Tuple[str, ...] = ("qwen2.5:3b", "nomic-embed-text")


def required_models() -> List[str]:
    """Public accessor so tests/UI can introspect without mutation."""
    return list(REQUIRED_MODELS)


# --------------------------------------------------------------------------- #
# Dataclass
# --------------------------------------------------------------------------- #

@dataclass
class OllamaStatus:
    """Snapshot of Ollama server health.

    Attributes:
        reachable: True if the ``/api/tags`` endpoint responded.
        available_models: every model reported by Ollama.
        missing_models: subset of ``required_models()`` NOT in
            ``available_models`` (empty when ``reachable`` is False).
        error: human-readable error string when not reachable.
    """

    reachable: bool = False
    available_models: List[str] = field(default_factory=list)
    missing_models: List[str] = field(default_factory=list)
    error: str = ""


# --------------------------------------------------------------------------- #
# Health check (cached)
# --------------------------------------------------------------------------- #

def _check_ollama_health_impl(
    base_url: str = "http://localhost:11434",
    timeout: float = 3.0,
) -> OllamaStatus:
    """Implementation — wrapped by the cached ``check_ollama_health``.

    Hits ``GET <base_url>/api/tags`` (Ollama's standard model listing
    endpoint). Any network/HTTP error -> ``reachable=False``.
    """
    url = f"{base_url.rstrip('/')}/api/tags"
    try:
        resp = _urlopen(url, timeout=timeout)
        payload = json.loads(resp.read().decode("utf-8"))
    except urlerror.HTTPError as e:
        return OllamaStatus(
            reachable=False,
            error=f"HTTP {e.code} {e.reason}",
        )
    except urlerror.URLError as e:
        return OllamaStatus(
            reachable=False,
            error=str(e.reason) if hasattr(e, "reason") else str(e),
        )
    except (ConnectionRefusedError, TimeoutError, OSError) as e:
        return OllamaStatus(reachable=False, error=str(e))
    except Exception as e:  # pragma: no cover — defensive
        return OllamaStatus(reachable=False, error=f"{type(e).__name__}: {e}")

    available = [m["name"] for m in payload.get("models", []) if "name" in m]
    required = set(REQUIRED_MODELS)
    missing = sorted(m for m in required if m not in available)

    return OllamaStatus(
        reachable=True,
        available_models=available,
        missing_models=missing,
    )


@lru_cache(maxsize=4)
def check_ollama_health(
    base_url: str = "http://localhost:11434",
    timeout: float = 3.0,
) -> OllamaStatus:
    """Cached health check. Clear cache to force a re-probe:
    ``check_ollama_health.cache_clear()``.
    """
    return _check_ollama_health_impl(base_url=base_url, timeout=timeout)


def clear_health_cache() -> None:
    """Reset the lru_cache — call from a Streamlit 'Refresh' button."""
    check_ollama_health.cache_clear()


# --------------------------------------------------------------------------- #
# UI rendering
# --------------------------------------------------------------------------- #

def health_summary_text(status: OllamaStatus) -> Tuple[str, str]:
    """Return ``(message, code)`` for sidebar rendering.

    ``code`` is one of ``HEALTH_OK`` / ``HEALTH_OFFLINE`` / ``HEALTH_MODEL_MISSING``.
    """
    if not status.reachable:
        msg = (
            "🔴 Ollama offline. Start it with `ollama serve` and reload."
            + (f" ({status.error})" if status.error else "")
        )
        return msg, HEALTH_OFFLINE

    if status.missing_models:
        listed = ", ".join(status.missing_models)
        msg = (
            f"⚠ Ollama reachable but missing model(s): {listed}. "
            f"Run `ollama pull <model>` for each."
        )
        return msg, HEALTH_MODEL_MISSING

    n = len(status.available_models)
    msg = f"🟢 Ollama ready ({n} model{'s' if n != 1 else ''} loaded)."
    return msg, HEALTH_OK


# --------------------------------------------------------------------------- #
# Pull helper — used by the optional "Pull model" Streamlit button.
# NOT exercised by unit tests (real network call); safe to call with a
# confirmation prompt in the UI.
# --------------------------------------------------------------------------- #

def pull_model(model_name: str, base_url: str = "http://localhost:11434") -> bool:
    """Trigger ``ollama pull <model_name>`` via HTTP. Returns True on 200.

    Streams JSON progress lines from ``POST /api/pull``; logs each to
    stdout. The Streamlit button should call this in a thread/subprocess
    so the UI doesn't freeze during a large download.
    """
    url = f"{base_url.rstrip('/')}/api/pull"
    body = json.dumps({"name": model_name}).encode("utf-8")
    req = urlrequest.Request(
        url, data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        resp = urlrequest.urlopen(req, timeout=600)
        # Drain the streaming response so the connection closes cleanly.
        for raw in resp:
            line = raw.decode("utf-8", errors="replace").strip()
            if line:
                try:
                    obj = json.loads(line)
                    status = obj.get("status", "")
                    if status:
                        print(f"[ollama pull] {model_name}: {status}")
                except json.JSONDecodeError:
                    pass
        return True
    except (urlerror.URLError, OSError) as e:
        print(f"[ollama pull] failed: {e}")
        return False