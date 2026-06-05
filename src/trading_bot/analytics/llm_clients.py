"""Provider-agnostic LLM client factory for the nightly learner.

The narrator (learning_narrator.py) speaks one small interface — a ``client`` with
``client.messages.create(model=, max_tokens=, system=, messages=[...])`` returning an
object whose ``.content[0].text`` is the reply (the Anthropic Messages shape). This
module returns either the real Anthropic client or a thin **Gemini adapter** wearing
the same interface, so the narrator never has to know which provider is behind it.

Everything is fail-safe: a missing SDK or missing key returns ``None`` and the learner
falls back to deterministic templates — the nightly run never crashes on the LLM.
"""
from __future__ import annotations

import os
from types import SimpleNamespace
from typing import Any, Mapping

_GEMINI_KEYS = ("GEMINI_API_KEY", "GOOGLE_API_KEY")
_ANTHROPIC_KEYS = ("ANTHROPIC_API_KEY",)


def resolve_provider(configured: str | None, *, env: Mapping[str, str] | None = None) -> str:
    """Decide the LLM provider. Explicit config wins; ``auto`` picks by which key is set
    (Gemini first, since that's this operator's stack), else ``none`` (templates)."""
    env = env if env is not None else os.environ
    choice = (configured or "auto").strip().lower()
    if choice in {"gemini", "anthropic", "none"}:
        return choice
    if any(env.get(k) for k in _GEMINI_KEYS):
        return "gemini"
    if any(env.get(k) for k in _ANTHROPIC_KEYS):
        return "anthropic"
    return "none"


def make_llm_client(provider: str, *, env: Mapping[str, str] | None = None) -> Any | None:
    """Build a Messages-shaped client for the provider, or None if unavailable.
    Never raises — a missing SDK/key degrades to template narration."""
    env = env if env is not None else os.environ
    try:
        if provider == "anthropic":
            import anthropic  # noqa: PLC0415
            return anthropic.Anthropic()  # reads ANTHROPIC_API_KEY
        if provider == "gemini":
            api_key = next((env.get(k) for k in _GEMINI_KEYS if env.get(k)), None)
            if not api_key:
                return None
            return _GeminiClient(api_key)
    except Exception:
        return None
    return None


class _GeminiClient:
    """Adapter: exposes ``.messages.create(...)`` over the google-genai SDK so the
    Anthropic-shaped narrator works unchanged with Gemini (Flash/Pro) keys."""

    def __init__(self, api_key: str) -> None:
        from google import genai  # noqa: PLC0415  (pip install google-genai)
        self._genai = genai
        self._client = genai.Client(api_key=api_key)
        self.messages = self._Messages(self._client, genai)

    class _Messages:
        def __init__(self, client: Any, genai: Any) -> None:
            self._client = client
            self._genai = genai

        def create(self, *, model: str, max_tokens: int, system: str,
                   messages: list[dict[str, Any]]) -> Any:
            from google.genai import types  # noqa: PLC0415
            user = "\n\n".join(
                str(m.get("content", "")) for m in messages if m.get("role") == "user"
            )
            resp = self._client.models.generate_content(
                model=model,
                contents=user,
                config=types.GenerateContentConfig(
                    system_instruction=system,
                    max_output_tokens=max_tokens,
                    response_mime_type="application/json",
                ),
            )
            # Normalize to the Anthropic Messages shape the narrator expects.
            return SimpleNamespace(content=[SimpleNamespace(text=resp.text or "")])


def model_for(provider: str, lcfg: Mapping[str, Any]) -> str:
    """Pick the model id for the resolved provider from the learning config."""
    if provider == "gemini":
        return str(lcfg.get("gemini_model") or "gemini-2.0-flash")
    return str(lcfg.get("anthropic_model") or lcfg.get("model") or "claude-sonnet-4-6")
