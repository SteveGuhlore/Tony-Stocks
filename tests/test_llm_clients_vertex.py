"""Tests for the Vertex AI mode of the Gemini LLM client adapter.

The bot's narrator speaks the Anthropic Messages shape over either the Gemini
Developer API (api_key) or Vertex AI (vertexai=True + project/location + ADC).
These tests inject a fake ``google.genai`` so no real SDK/creds are needed and
assert which construction path is selected for which environment.
"""
from __future__ import annotations

import sys
import types

import pytest

from trading_bot.analytics import llm_clients


@pytest.fixture
def fake_genai(monkeypatch):
    """Inject a fake ``google.genai`` whose Client records its kwargs."""
    calls: dict[str, object] = {}

    class _Client:
        def __init__(self, **kwargs):
            calls.clear()
            calls.update(kwargs)

        models = None

    genai_mod = types.SimpleNamespace(Client=_Client)
    google_pkg = types.ModuleType("google")
    google_pkg.genai = genai_mod  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "google", google_pkg)
    monkeypatch.setitem(sys.modules, "google.genai", genai_mod)
    return calls


def test_vertex_enabled_parsing():
    for v in ("true", "TRUE", "1", "yes", "on", " On "):
        assert llm_clients._vertex_enabled({"GOOGLE_GENAI_USE_VERTEXAI": v}) is True
    for v in ("", "false", "0", "no", "off", "maybe"):
        assert llm_clients._vertex_enabled({"GOOGLE_GENAI_USE_VERTEXAI": v}) is False
    assert llm_clients._vertex_enabled({}) is False


def test_make_client_vertex_mode(fake_genai):
    env = {
        "GOOGLE_GENAI_USE_VERTEXAI": "true",
        "GOOGLE_CLOUD_PROJECT": "p",
        "GOOGLE_CLOUD_LOCATION": "us-central1",
    }
    client = llm_clients.make_llm_client("gemini", env=env)
    assert client is not None
    assert fake_genai == {"vertexai": True, "project": "p", "location": "us-central1"}


def test_vertex_mode_defaults_location(fake_genai):
    env = {"GOOGLE_GENAI_USE_VERTEXAI": "true", "GOOGLE_CLOUD_PROJECT": "p"}
    client = llm_clients.make_llm_client("gemini", env=env)
    assert client is not None
    assert fake_genai == {"vertexai": True, "project": "p", "location": "us-central1"}


def test_vertex_mode_requires_project(fake_genai):
    env = {"GOOGLE_GENAI_USE_VERTEXAI": "true"}  # no project
    assert llm_clients.make_llm_client("gemini", env=env) is None


def test_api_key_mode_when_vertex_off(fake_genai):
    env = {"GEMINI_API_KEY": "k"}
    client = llm_clients.make_llm_client("gemini", env=env)
    assert client is not None
    assert fake_genai == {"api_key": "k"}


def test_gemini_none_when_no_creds(fake_genai):
    assert llm_clients.make_llm_client("gemini", env={}) is None
