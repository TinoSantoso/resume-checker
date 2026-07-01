"""Tests for Ollama health check (C2 backlog).

Verifies that the health module correctly reports server reachability
and which models are loaded, and surfaces a clear status string for the
Streamlit sidebar UI.

The HTTP calls are mocked via ``urllib.request.urlopen`` so the tests
do NOT need a running Ollama server.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from app.health import (
    OllamaStatus,
    check_ollama_health,
    health_summary_text,
    required_models,
    HEALTH_OK,
    HEALTH_OFFLINE,
    HEALTH_MODEL_MISSING,
)


# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

class TestConstants:
    def test_required_models_includes_llm_and_embedder(self):
        models = required_models()
        assert "qwen2.5:3b" in models
        assert "nomic-embed-text" in models

    def test_health_status_codes_are_distinct(self):
        codes = {HEALTH_OK, HEALTH_OFFLINE, HEALTH_MODEL_MISSING}
        assert len(codes) == 3


# --------------------------------------------------------------------------- #
# OllamaStatus dataclass
# --------------------------------------------------------------------------- #

class TestOllamaStatus:
    def test_default_construction(self):
        s = OllamaStatus(reachable=True, available_models=["qwen2.5:3b"], missing_models=[])
        assert s.reachable is True
        assert s.available_models == ["qwen2.5:3b"]
        assert s.missing_models == []
        assert s.error == ""

    def test_repr_does_not_crash_on_missing_fields(self):
        s = OllamaStatus(reachable=False)
        assert "False" in repr(s)


# --------------------------------------------------------------------------- #
# check_ollama_health
# --------------------------------------------------------------------------- #

def _mock_urlopen(payload: dict | str | Exception, status: int = 200):
    """Build a MagicMock that mimics urllib.request.urlopen."""
    if isinstance(payload, Exception):
        def raise_err(*args, **kwargs):
            raise payload
        return MagicMock(side_effect=raise_err)

    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(payload).encode("utf-8")
    mock_resp.status = status
    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = MagicMock(return_value=False)
    return MagicMock(return_value=mock_resp)


def _clear_cache():
    """Reset lru_cache between tests so patched urlopen takes effect."""
    from app.health import check_ollama_health as fn
    fn.cache_clear()


class TestCheckOllamaHealth:
    def test_offline_when_connection_refused(self):
        _clear_cache()
        err = ConnectionRefusedError("connection refused")
        with patch("app.health._urlopen", _mock_urlopen(err)):
            status = check_ollama_health()
        assert status.reachable is False
        assert status.missing_models == []  # unknown when offline

    def test_offline_when_timeout(self):
        _clear_cache()
        with patch("app.health._urlopen", _mock_urlopen(TimeoutError("timed out"))):
            status = check_ollama_health()
        assert status.reachable is False
        assert "timeout" in status.error.lower() or "timed out" in status.error.lower()

    def test_online_all_models_present(self):
        _clear_cache()
        payload = {"models": [{"name": "qwen2.5:3b"}, {"name": "nomic-embed-text"}]}
        with patch("app.health._urlopen", _mock_urlopen(payload)):
            status = check_ollama_health()
        assert status.reachable is True
        assert status.missing_models == []
        assert "qwen2.5:3b" in status.available_models
        assert "nomic-embed-text" in status.available_models

    def test_online_with_missing_required_model(self):
        _clear_cache()
        # Only one required model present
        payload = {"models": [{"name": "qwen2.5:3b"}]}
        with patch("app.health._urlopen", _mock_urlopen(payload)):
            status = check_ollama_health()
        assert status.reachable is True
        assert "nomic-embed-text" in status.missing_models
        assert status.missing_models == ["nomic-embed-text"]

    def test_online_no_models_at_all(self):
        _clear_cache()
        payload = {"models": []}
        with patch("app.health._urlopen", _mock_urlopen(payload)):
            status = check_ollama_health()
        assert status.reachable is True
        assert set(status.missing_models) == {"qwen2.5:3b", "nomic-embed-text"}

    def test_http_error_marked_offline(self):
        _clear_cache()
        from urllib.error import HTTPError
        err = HTTPError(url="http://x", code=500, msg="server error", hdrs={}, fp=None)
        with patch("app.health._urlopen", _mock_urlopen(err)):
            status = check_ollama_health()
        assert status.reachable is False
        assert "500" in status.error or "server error" in status.error.lower()

    def test_custom_base_url_respected(self):
        _clear_cache()
        payload = {"models": [{"name": "qwen2.5:3b"}, {"name": "nomic-embed-text"}]}
        with patch("app.health._urlopen", _mock_urlopen(payload)) as m:
            check_ollama_health(base_url="http://remote:9999")
        # Verify the URL passed contains the custom host
        called_url = m.call_args[0][0]
        assert "remote:9999" in called_url
        assert "/api/tags" in called_url

    def test_custom_timeout_does_not_hang(self):
        _clear_cache()
        # Just ensure the timeout arg is passed — we don't actually wait
        with patch("app.health._urlopen", _mock_urlopen({"models": []})) as m:
            check_ollama_health(timeout=7)
        assert m.call_args[1].get("timeout") == 7


# --------------------------------------------------------------------------- #
# health_summary_text — UI rendering
# --------------------------------------------------------------------------- #

class TestHealthSummaryText:
    def test_ok_when_all_present(self):
        status = OllamaStatus(
            reachable=True,
            available_models=["qwen2.5:3b", "nomic-embed-text"],
            missing_models=[],
        )
        text, code = health_summary_text(status)
        assert code == HEALTH_OK
        assert "ready" in text.lower() or "online" in text.lower()

    def test_offline_message_mentions_ollama(self):
        status = OllamaStatus(reachable=False, error="connection refused")
        text, code = health_summary_text(status)
        assert code == HEALTH_OFFLINE
        assert "ollama" in text.lower() or "offline" in text.lower()

    def test_model_missing_message_names_the_missing_model(self):
        status = OllamaStatus(
            reachable=True,
            available_models=["qwen2.5:3b"],
            missing_models=["nomic-embed-text"],
        )
        text, code = health_summary_text(status)
        assert code == HEALTH_MODEL_MISSING
        assert "nomic-embed-text" in text

    def test_multiple_missing_models_all_named(self):
        status = OllamaStatus(
            reachable=True,
            available_models=[],
            missing_models=["qwen2.5:3b", "nomic-embed-text"],
        )
        text, code = health_summary_text(status)
        assert code == HEALTH_MODEL_MISSING
        assert "qwen2.5:3b" in text
        assert "nomic-embed-text" in text