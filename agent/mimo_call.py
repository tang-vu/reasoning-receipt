"""Xiaomi MiMo backend — a drop-in stand-in for the google-genai client.

Every LLM call site in the agent funnels through
`client.models.generate_content(model=, contents=, config=)` and reads
`.text` off the result (see analyst, ensemble via gemini_call, critic,
critic_v2). `MimoClient` mimics exactly that surface against MiMo's
OpenAI-compatible `/chat/completions`, so selecting MiMo is a one-line swap
in `_build_client` with no change to any call site.

MiMo flagship is `mimo-v2.5-pro`. The API is OpenAI-shaped: system + user
messages, `response_format={"type":"json_object"}` for the JSON traces.

Credentials: MIMO_API_KEY / MIMO_API_BASE from the environment (.env).

Caveats vs Vertex Gemini:
- No Google-Search grounding. `config.tools` is ignored; stances run on the
  model's own knowledge. Documented trade-off for staying on free credit.
- No embedding model in the MiMo catalogue, so `embed_content` raises and the
  memory module falls back to its deterministic mock vector.
"""

from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger(__name__)

DEFAULT_BASE = "https://api.xiaomimimo.com/v1"

# MiMo flagship + a faster sibling. We map by tier so callers that still pass
# Gemini model names (their env-derived defaults can bind at import time,
# before .env loads) still hit a valid MiMo model: anything "flash"/"haiku"-
# tier maps to the fast model, everything else to the pro flagship.
MIMO_PRO_MODEL = os.getenv("MIMO_PRO_MODEL", "mimo-v2.5-pro")
MIMO_FAST_MODEL = os.getenv("MIMO_FAST_MODEL", "mimo-v2.5")

# Token floor for grounded calls — reasoning_content + visible answer must both
# fit or `content` comes back empty (see generate_content).
WEB_SEARCH_MIN_TOKENS = int(os.getenv("MIMO_WEB_SEARCH_MIN_TOKENS", "8192"))


def _normalize_model(model: str) -> str:
    """Map any caller-supplied model id onto a valid MiMo model."""
    m = (model or "").lower()
    if m.startswith("mimo-"):
        return model  # already a MiMo id — pass through
    if "flash" in m or "haiku" in m or "lite" in m or "mini" in m:
        return MIMO_FAST_MODEL
    return MIMO_PRO_MODEL


class _Resp:
    """Minimal shape the call sites read: `.text` plus an empty `.candidates`."""

    def __init__(self, text: str) -> None:
        self.text = text
        self.candidates: list = []


class _Models:
    def __init__(self, parent: MimoClient) -> None:
        self._p = parent

    def generate_content(self, *, model: str, contents, config=None) -> _Resp:
        model = _normalize_model(model)
        system = getattr(config, "system_instruction", None)
        temperature = getattr(config, "temperature", None)
        max_tokens = getattr(config, "max_output_tokens", None)
        json_mode = getattr(config, "response_mime_type", None) == "application/json"

        messages: list[dict] = []
        if system:
            messages.append({"role": "system", "content": str(system)})
        messages.append({"role": "user", "content": contents if isinstance(contents, str) else str(contents)})

        # When the caller attached a grounding tool (gemini_call sets a
        # google_search Tool whenever enable_web_search=True, and leaves
        # response_mime_type unset in that case), turn on MiMo's web search so
        # stances cite live sources. force_search makes it grounded every call.
        # Kill switch: MIMO_WEB_SEARCH=0 disables it globally (web search is
        # token-heavy on a reasoning model — see WEB_SEARCH_MIN_TOKENS floor).
        web_search_enabled = os.getenv("MIMO_WEB_SEARCH", "1").strip().lower() not in {"0", "false", "no", "off"}
        web_search = web_search_enabled and bool(getattr(config, "tools", None))

        payload: dict = {"model": model, "messages": messages}
        if temperature is not None:
            payload["temperature"] = float(temperature)
        if max_tokens is not None:
            payload["max_tokens"] = int(max_tokens)
        if web_search:
            payload["tools"] = [{"type": "web_search", "force_search": True}]
            # MiMo is a reasoning model: with grounding it fills a long
            # `reasoning_content` before the answer, so a tight budget gets
            # consumed by thinking and leaves `content` empty (finish_reason
            # "length"). Floor the budget so the visible answer survives.
            payload["max_tokens"] = max(int(max_tokens or 0), WEB_SEARCH_MIN_TOKENS)
        elif json_mode:
            # json_object mode and web_search are mutually exclusive on MiMo;
            # only request strict JSON when not grounding.
            payload["response_format"] = {"type": "json_object"}

        try:
            resp = self._p._http.post(
                f"{self._p.base}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self._p.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
        except httpx.HTTPError as exc:  # network/timeout — surface as retryable
            raise RuntimeError(f"503 mimo network error: {exc}") from exc

        if resp.status_code >= 400:
            # Carry the status code in the message so gemini_call's retry-trigger
            # check ("429", "503", ...) can route a fallback model.
            raise RuntimeError(f"{resp.status_code} mimo error: {resp.text[:200]}")

        data = resp.json()
        text = (data.get("choices") or [{}])[0].get("message", {}).get("content") or ""
        if not text:
            raise RuntimeError(f"mimo ({model}) returned no text")
        return _Resp(text)

    def embed_content(self, *, model: str, contents):  # noqa: ANN001
        # MiMo has no embedding model; callers (memory) catch and use a mock.
        raise RuntimeError("mimo: no embedding model available")


class MimoClient:
    """google-genai-compatible facade backed by MiMo chat completions."""

    is_mimo = True

    def __init__(self, *, api_key: str, base: str | None = None) -> None:
        self.api_key = api_key
        self.base = (base or os.getenv("MIMO_API_BASE", DEFAULT_BASE)).rstrip("/")
        self._http = httpx.Client(timeout=90.0)
        self.models = _Models(self)


def build_mimo_client():
    """Return (MimoClient, "mimo") if a key is configured, else (None, None)."""
    api_key = os.getenv("MIMO_API_KEY")
    if not api_key:
        return None, None
    return MimoClient(api_key=api_key), "mimo"
