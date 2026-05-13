"""Shared Gemini-call wrapper with fallback chain.

Used by `agent.ensemble` (Phase 2) and will be used by `agent.critic_v2`
(Phase 3). Centralises the retry logic so quota + 404 + empty-response
handling lives in one place. Existing `agent.analyst` and `agent.critic`
keep their own loops for rr-trace/2 compat — KISS, no big-bang refactor.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable

logger = logging.getLogger(__name__)

# Errors that should trigger a fallback model rather than re-raising.
_RETRY_TRIGGERS = (
    "429",
    "RESOURCE_EXHAUSTED",
    "404",
    "NOT_FOUND",
    "503",
    "no text",
    "returned no text",
    "INVALID_ARGUMENT",
)


def call_with_fallback(
    client,  # google.genai client
    *,
    models: Iterable[str],
    system_prompt: str,
    user: str,
    temperature: float,
    max_output_tokens: int,
    thinking_budget: int | None = None,
    enable_web_search: bool = False,
    log_label: str = "gemini",
) -> tuple[str, str]:
    """Call Gemini with a model fallback chain.

    Returns `(response_text, model_actually_used)`. Raises the last exception
    only if every model in the chain failed with a non-retryable error or with
    a retry-trigger that exhausted the chain.
    """
    from google.genai import types  # type: ignore

    tools: list = []
    if enable_web_search:
        tools.append(types.Tool(google_search=types.GoogleSearch()))

    thinking = None
    if thinking_budget is not None:
        try:
            thinking = types.ThinkingConfig(thinking_budget=thinking_budget)
        except Exception:  # noqa: BLE001
            thinking = None

    cfg = types.GenerateContentConfig(
        system_instruction=system_prompt,
        temperature=temperature,
        max_output_tokens=max_output_tokens,
        response_mime_type="application/json" if not tools else None,
        tools=tools or None,
        thinking_config=thinking,
    )

    last_exc: Exception | None = None
    chain = list(models)
    primary = chain[0] if chain else "unknown"
    for model in chain:
        try:
            resp = client.models.generate_content(model=model, contents=user, config=cfg)
            text = getattr(resp, "text", None)
            if text:
                if model != primary:
                    logger.info("%s: fell back %s -> %s", log_label, primary, model)
                return text, model
            for cand in getattr(resp, "candidates", []) or []:
                for part in getattr(cand.content, "parts", []) or []:
                    if getattr(part, "text", None):
                        if model != primary:
                            logger.info("%s: fell back %s -> %s", log_label, primary, model)
                        return part.text, model
            raise RuntimeError(f"{log_label} ({model}) returned no text")
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            msg = str(exc)
            if any(s in msg for s in _RETRY_TRIGGERS):
                logger.warning("%s: %s failed (%s); trying next model", log_label, model, msg[:150])
                continue
            raise
    assert last_exc is not None
    raise last_exc
