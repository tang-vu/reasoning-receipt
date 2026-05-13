"""Critic stage — audits a draft trace produced by the Analyst.

Reads the Researcher's draft JSON and the original market question. Returns a
structured review:

  {
    "passed": <bool>,
    "categories": {
      "fabrication":          {"pass": <bool>, "notes": "..."},
      "strawmen":             {"pass": <bool>, "notes": "..."},
      "calibration":          {"pass": <bool>, "notes": "..."},
      "sensitivity":          {"pass": <bool>, "notes": "..."},
      "internal_consistency": {"pass": <bool>, "notes": "..."}
    },
    "revision_request": "<instruction for the researcher, or empty>"
  }

The critic uses a smaller / faster model than the Researcher (default Gemini
Flash). Quota / 429 / empty-response errors fall back through the same chain.

Mock mode: deterministic pass — only useful for tests + offline dev.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

from .analyst import (
    MarketCandidate,
    _build_client,
    _extract_first_json,
)
from .trace import ReasoningTrace

logger = logging.getLogger(__name__)

DEFAULT_CRITIC_MODEL = os.getenv("GEMINI_CRITIC_MODEL", "gemini-3-flash-preview")
_DEFAULT_CRITIC_FALLBACKS = "gemini-2.5-flash,gemini-2.5-flash-lite"
DEFAULT_CRITIC_FALLBACK_MODELS = [
    m.strip()
    for m in os.getenv("GEMINI_CRITIC_FALLBACK_MODELS", _DEFAULT_CRITIC_FALLBACKS).split(",")
    if m.strip()
]
CRITIC_PROMPT_FILE = Path(__file__).parent / "prompts" / "critic.md"

_CATEGORY_KEYS = ("fabrication", "strawmen", "calibration", "sensitivity", "internal_consistency")


def _load_critic_prompt() -> str:
    if CRITIC_PROMPT_FILE.exists():
        return CRITIC_PROMPT_FILE.read_text(encoding="utf-8")
    return "You audit prediction traces. Return JSON {passed, categories, revision_request}."


@dataclass(slots=True)
class CriticConfig:
    model: str = DEFAULT_CRITIC_MODEL
    fallback_models: list[str] = field(default_factory=lambda: list(DEFAULT_CRITIC_FALLBACK_MODELS))
    max_tokens: int = 4_096
    thinking_budget: int | None = 512  # critics don't need deep thinking; keep cheap + fast
    temperature: float = 0.1
    enable_web_search: bool = False  # critic checks the draft, doesn't research fresh


def _mock_review(draft: dict) -> dict:
    """Deterministic pass-through review for offline dev / tests."""
    return {
        "passed": True,
        "categories": {k: {"pass": True, "notes": "mock"} for k in _CATEGORY_KEYS},
        "revision_request": "",
    }


def _normalise_review(obj: dict) -> dict:
    """Coerce arbitrary LLM JSON into the canonical schema. Best-effort, never raises."""
    cats = obj.get("categories") or {}
    out_cats: dict[str, dict] = {}
    for key in _CATEGORY_KEYS:
        entry = cats.get(key) if isinstance(cats, dict) else None
        if isinstance(entry, dict):
            out_cats[key] = {
                "pass": bool(entry.get("pass", True)),
                "notes": str(entry.get("notes", ""))[:200],
            }
        else:
            out_cats[key] = {"pass": True, "notes": ""}
    passed = all(c["pass"] for c in out_cats.values())
    declared = obj.get("passed")
    if isinstance(declared, bool):
        passed = passed and declared
    return {
        "passed": passed,
        "categories": out_cats,
        "revision_request": str(obj.get("revision_request", ""))[:600],
    }


class Critic:
    """Audits a draft ReasoningTrace via Gemini Flash (or fallback)."""

    def __init__(
        self,
        *,
        config: CriticConfig | None = None,
        mock: bool | None = None,
    ) -> None:
        self.config = config or CriticConfig()
        env_mock = os.getenv("RR_MOCK_CRITIC", "").lower() in {"1", "true", "yes"}
        # Inherit RR_MOCK_ANALYST too — if analyst is mocked, critic should be as well.
        if not env_mock:
            env_mock = os.getenv("RR_MOCK_ANALYST", "").lower() in {"1", "true", "yes"}
        self.mock = env_mock if mock is None else mock

        self.backend: str | None = None
        self._client = None
        self._last_model_used: str | None = None
        if not self.mock:
            self._client, self.backend = _build_client()
            if self._client is None:
                self.mock = True

        self.prompt = _load_critic_prompt()

    def review(
        self,
        candidate: MarketCandidate,
        draft: ReasoningTrace | dict,
    ) -> dict:
        """Audit `draft` against `candidate`. Returns normalised review dict."""
        draft_dict = draft.to_dict() if isinstance(draft, ReasoningTrace) else draft

        if self.mock or self._client is None:
            return _mock_review(draft_dict)

        raw = self._call_model(candidate, draft_dict)
        try:
            obj = _extract_first_json(raw)
        except Exception as exc:
            logger.warning("critic: output unparseable (%s); treating as pass", exc)
            return _mock_review(draft_dict)
        return _normalise_review(obj)

    def _call_model(self, candidate: MarketCandidate, draft_dict: dict) -> str:
        from google.genai import types  # type: ignore

        # Trim draft to the fields the critic needs to score; keep payload small.
        slim_draft = {
            k: draft_dict.get(k)
            for k in (
                "claim",
                "probability",
                "confidence",
                "horizon_days",
                "sources",
                "counter_arguments",
                "sensitivity",
                "summary",
            )
        }
        user = (
            f"Market question: {candidate.question}\n"
            f"Resolves by: {candidate.end_date.isoformat() if candidate.end_date else 'unknown'}\n\n"
            f"Researcher's draft (JSON):\n{json.dumps(slim_draft, separators=(',', ':'))}\n\n"
            "Audit the draft per the five categories in the system instruction. Return ONLY the JSON."
        )

        thinking = None
        if self.config.thinking_budget is not None:
            try:
                thinking = types.ThinkingConfig(thinking_budget=self.config.thinking_budget)
            except Exception:
                thinking = None

        cfg = types.GenerateContentConfig(
            system_instruction=self.prompt,
            temperature=self.config.temperature,
            max_output_tokens=self.config.max_tokens,
            response_mime_type="application/json",
            thinking_config=thinking,
        )

        chain = [self.config.model, *self.config.fallback_models]
        last_exc: Exception | None = None
        for model in chain:
            try:
                resp = self._client.models.generate_content(model=model, contents=user, config=cfg)
                self._last_model_used = model
                if model != self.config.model:
                    logger.info("critic: fell back from %s -> %s", self.config.model, model)
                text = getattr(resp, "text", None)
                if text:
                    return text
                for cand in getattr(resp, "candidates", []) or []:
                    for part in getattr(cand.content, "parts", []) or []:
                        if getattr(part, "text", None):
                            return part.text
                raise RuntimeError(f"critic ({model}) returned no text")
            except Exception as exc:
                last_exc = exc
                msg = str(exc)
                retry_triggers = (
                    "429", "RESOURCE_EXHAUSTED", "404", "NOT_FOUND", "503",
                    "no text", "returned no text", "INVALID_ARGUMENT",
                )
                if any(s in msg for s in retry_triggers):
                    logger.warning("critic: %s failed (%s); trying fallback", model, msg[:200])
                    continue
                raise
        assert last_exc is not None
        raise last_exc
