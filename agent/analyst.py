"""Gemini-driven probability analyst.

Takes a `MarketCandidate`, asks Gemini (via Vertex AI or the public Gemini API)
for a calibrated probability with cited sources, counter-arguments, and
sensitivity. Returns a populated `ReasoningTrace`.

Mock mode (`RR_MOCK_ANALYST=1` or no Google credentials): deterministic
synthetic answer so the full pipeline runs in tests and local dev.

Credentials resolution order:
  1. `GOOGLE_CLOUD_PROJECT` set → Vertex AI client
     (also honours `GOOGLE_CLOUD_LOCATION`, default `us-central1`).
  2. `GOOGLE_API_KEY` set → public Gemini API client.
  3. Otherwise → mock mode.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from .trace import CounterArgument, ReasoningTrace, SensitivityNode, Source

logger = logging.getLogger(__name__)

DEFAULT_REASONING_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.1-pro-preview")
# Fallback chain — tried in order on quota/transient errors.
# Preview models are deployed only at `global` location; 2.5 stable is the last resort.
_DEFAULT_FALLBACKS = "gemini-3-flash-preview,gemini-2.5-flash"
DEFAULT_FALLBACK_MODELS = [
    m.strip() for m in os.getenv("GEMINI_FALLBACK_MODELS", _DEFAULT_FALLBACKS).split(",") if m.strip()
]
PROMPT_FILE = Path(__file__).parent / "prompts" / "analyst.md"


@dataclass(slots=True)
class MarketCandidate:
    market_id: str
    source: str
    question: str
    end_date: datetime | None
    liquidity_usd: float
    extra: dict | None = None


@dataclass(slots=True)
class AnalystConfig:
    model: str = DEFAULT_REASONING_MODEL
    fallback_models: list[str] = field(default_factory=lambda: list(DEFAULT_FALLBACK_MODELS))
    # Gemini 3.x defaults to "thinking" mode which consumes output budget. We give
    # ourselves room and explicitly cap thinking. 16k is a safe ceiling for a
    # trace JSON plus a moderate thinking budget.
    max_tokens: int = 16_384
    thinking_budget: int = 2_048
    temperature: float = 0.2
    enable_web_search: bool = True


def _load_prompt() -> str:
    if PROMPT_FILE.exists():
        return PROMPT_FILE.read_text(encoding="utf-8")
    return _DEFAULT_PROMPT


_DEFAULT_PROMPT = """You are ReasoningReceipt's analyst. Given a prediction market
question, produce a calibrated probability. Cite sources by URL. Return ONLY a
JSON object with the keys described in the task."""


def _balanced_object(text: str, start: int) -> str:
    """Return the first balanced {...} starting at `start`, string-aware.

    A naive brace counter miscounts when a `{` or `}` appears inside a string
    value, truncating the object early. This skips braces inside string
    literals (respecting backslash escapes), so values containing braces don't
    corrupt the extraction.
    """
    depth = 0
    in_str = False
    escaped = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    raise ValueError("unterminated JSON object")


def _repair_json(blob: str) -> str:
    """Best-effort cleanup of common LLM JSON slips: trailing commas + comments."""
    # Strip // line comments and /* */ block comments (outside strings is the
    # common case; LLMs rarely put these inside string values).
    blob = re.sub(r"/\*.*?\*/", "", blob, flags=re.DOTALL)
    blob = re.sub(r"(?m)//[^\n]*$", "", blob)
    # Drop trailing commas before a closing } or ].
    blob = re.sub(r",(\s*[}\]])", r"\1", blob)
    return blob


def _extract_first_json(text: str) -> dict:
    """Grab the first {...} block in `text`. Tolerant of code fences and prose.

    Falls back to a lenient repair (trailing commas, comments) when a model
    emits not-quite-valid JSON, so a single formatting slip doesn't force a
    whole re-generation downstream.
    """
    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fence:
        candidate = fence.group(1)
    else:
        brace = text.find("{")
        if brace == -1:
            raise ValueError("no JSON object in model output")
        candidate = _balanced_object(text, brace)
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        return json.loads(_repair_json(candidate))


def _mock_answer(candidate: MarketCandidate) -> dict:
    """Deterministic synthetic answer keyed on market_id — stable for replays."""
    digest = hashlib.sha256(candidate.market_id.encode()).digest()
    prob = (digest[0] / 255.0) * 0.6 + 0.2
    confidence = 0.55 + (digest[1] / 255.0) * 0.35
    return {
        "claim": (
            f"The outcome of '{candidate.question[:80]}' is most likely YES."
            if prob >= 0.5
            else f"The outcome of '{candidate.question[:80]}' is most likely NO."
        ),
        "probability": round(prob, 6),
        "confidence": round(confidence, 6),
        "horizon_days": 14,
        "sources": [
            {
                "url": "https://example.com/news/article",
                "title": "Synthetic news article for local dev",
                "cited_for": "baseline trend in the market topic",
            },
            {
                "url": "https://example.com/analysis/report",
                "title": "Synthetic analyst report",
                "cited_for": "quantitative anchor for the probability",
            },
        ],
        "counter_arguments": [
            {
                "claim": "The base rate over the past 5 years skews the other way.",
                "weight": 0.25,
                "rebuttal": "Regime shift in the underlying variable invalidates the base rate.",
            }
        ],
        "sensitivity": [
            {"factor": "Tail risk in news cycle", "delta_pp": 8.0, "note": "Single-event shock"},
            {"factor": "Liquidity drying up", "delta_pp": 3.0, "note": "Slippage on resolution"},
        ],
        "summary": (
            "Synthetic analyst output. Replace with real Gemini call by populating "
            "GOOGLE_CLOUD_PROJECT (Vertex AI) or GOOGLE_API_KEY (Gemini API)."
        ),
    }


def _build_client():
    """Return a (client, backend_name) pair or (None, None) for mock mode.

    Provider precedence: MiMo (when RR_LLM_PROVIDER=mimo, or it's the only
    credential present) → Vertex (GOOGLE_CLOUD_PROJECT) → public Gemini API
    (GOOGLE_API_KEY) → mock. MiMo speaks an OpenAI-compatible API behind a
    google-genai-shaped facade (see agent.mimo_call).
    """
    provider = os.getenv("RR_LLM_PROVIDER", "").strip().lower()
    if provider == "mimo" or (provider == "" and os.getenv("MIMO_API_KEY") and not os.getenv("GOOGLE_CLOUD_PROJECT")):
        from .mimo_call import build_mimo_client

        client, backend = build_mimo_client()
        if client is not None:
            return client, backend

    try:
        from google import genai  # type: ignore
    except ImportError:
        logger.warning("analyst: google-genai SDK not installed; falling back to mock")
        return None, None

    project = os.getenv("GOOGLE_CLOUD_PROJECT")
    api_key = os.getenv("GOOGLE_API_KEY")
    if project:
        # "global" is the multi-region endpoint and is the right default for Gemini
        # on Vertex unless a specific region is required for data residency.
        location = os.getenv("GOOGLE_CLOUD_LOCATION", "global")
        return genai.Client(vertexai=True, project=project, location=location), "vertex"
    if api_key:
        return genai.Client(api_key=api_key), "gemini-api"
    return None, None


class Analyst:
    """Produces a ReasoningTrace for a MarketCandidate via Gemini."""

    def __init__(
        self,
        *,
        config: AnalystConfig | None = None,
        mock: bool | None = None,
    ) -> None:
        self.config = config or AnalystConfig()
        env_mock = os.getenv("RR_MOCK_ANALYST", "").lower() in {"1", "true", "yes"}
        self.mock = env_mock if mock is None else mock

        self.backend: str | None = None
        self._client = None
        self._last_model_used: str | None = None
        if not self.mock:
            self._client, self.backend = _build_client()
            if self._client is None:
                self.mock = True

        self.prompt = _load_prompt()

    def analyse(
        self,
        candidate: MarketCandidate,
        *,
        consumer_address: str | None = None,
        revision_hint: str | None = None,
    ) -> ReasoningTrace:
        raw = self._call_model(candidate, revision_hint=revision_hint)
        try:
            obj = _extract_first_json(raw)
        except Exception as exc:
            logger.warning("analyst: model output unparseable (%s); falling back to mock answer", exc)
            obj = _mock_answer(candidate)

        sources = [Source(**s) for s in obj.get("sources", [])]
        counter = [CounterArgument(**c) for c in obj.get("counter_arguments", [])]
        sensitivity = [SensitivityNode(**s) for s in obj.get("sensitivity", [])]

        prob = float(obj.get("probability", 0.5))
        conf = float(obj.get("confidence", 0.5))
        prob = max(0.0, min(1.0, prob))
        conf = max(0.0, min(1.0, conf))

        if self.mock:
            model_label = f"mock:{self.config.model}"
        elif self.backend:
            actual = self._last_model_used or self.config.model
            model_label = f"{actual}@{self.backend}"
        else:
            model_label = self.config.model

        return ReasoningTrace(
            schema_version="rr-trace/1",
            market_id=candidate.market_id,
            market_source=candidate.source,
            market_question=candidate.question,
            claim=obj.get("claim", ""),
            probability=prob,
            confidence=conf,
            horizon_days=int(obj.get("horizon_days", 14)),
            sources=sources,
            counter_arguments=counter,
            sensitivity=sensitivity,
            summary=obj.get("summary", ""),
            model=model_label,
            produced_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            consumer_address=consumer_address,
        )

    def _call_model(self, candidate: MarketCandidate, revision_hint: str | None = None) -> str:
        if self.mock or self._client is None:
            return json.dumps(_mock_answer(candidate))

        from google.genai import types  # type: ignore

        user = (
            f"Market source: {candidate.source}\n"
            f"Market id: {candidate.market_id}\n"
            f"Question: {candidate.question}\n"
            f"Resolves by: {candidate.end_date.isoformat() if candidate.end_date else 'unknown'}\n"
            f"On-platform liquidity: ${candidate.liquidity_usd:,.0f}\n\n"
            "Produce the JSON described in the system instruction. JSON only — no prose, no fences."
        )
        if revision_hint:
            user += (
                "\n\nIMPORTANT: A critic flagged the previous draft. Revise per these notes "
                "and return a fresh JSON that addresses them:\n"
                f"{revision_hint}"
            )

        tools: list = []
        if self.config.enable_web_search:
            tools.append(types.Tool(google_search=types.GoogleSearch()))

        thinking = None
        if self.config.thinking_budget is not None:
            try:
                thinking = types.ThinkingConfig(thinking_budget=self.config.thinking_budget)
            except Exception:
                # Older SDK versions may not expose ThinkingConfig; skip silently.
                thinking = None

        config = types.GenerateContentConfig(
            system_instruction=self.prompt,
            temperature=self.config.temperature,
            max_output_tokens=self.config.max_tokens,
            response_mime_type="application/json" if not tools else None,
            tools=tools or None,
            thinking_config=thinking,
        )

        chain = [self.config.model, *self.config.fallback_models]
        last_exc: Exception | None = None
        for model in chain:
            try:
                resp = self._client.models.generate_content(
                    model=model,
                    contents=user,
                    config=config,
                )
                self._last_model_used = model
                if model != self.config.model:
                    logger.info("analyst: fell back from %s → %s", self.config.model, model)
                text = getattr(resp, "text", None)
                if text:
                    return text
                for cand in getattr(resp, "candidates", []) or []:
                    for part in getattr(cand.content, "parts", []) or []:
                        if getattr(part, "text", None):
                            return part.text
                raise RuntimeError(f"Gemini ({model}) returned no text")
            except Exception as exc:
                last_exc = exc
                msg = str(exc)
                # Retry on quota / availability / empty-response errors; otherwise re-raise.
                retry_triggers = (
                    "429", "RESOURCE_EXHAUSTED", "404", "NOT_FOUND", "503",
                    "no text", "returned no text", "INVALID_ARGUMENT",
                )
                if any(s in msg for s in retry_triggers):
                    logger.warning("analyst: %s failed (%s); trying fallback", model, msg[:200])
                    continue
                raise
        assert last_exc is not None
        raise last_exc

    def analyse_with_critic(
        self,
        candidate: MarketCandidate,
        *,
        consumer_address: str | None = None,
        critic: object | None = None,
        max_revisions: int = 1,
    ) -> ReasoningTrace:
        """Researcher + Critic pipeline.

        1. Draft a trace via the Researcher (`self.analyse`).
        2. Hand the draft to the Critic for a structured review.
        3. If the Critic flags issues AND we have a revision budget left, re-run
           the Researcher with the critic's `revision_request` inlined as a hint.
        4. Return the final trace with `critic_review` + `revision_count` filled
           in and `schema_version` bumped to `rr-trace/2`.

        On any Critic failure (network down, parse error, mock), the draft is
        returned unmodified with `revision_count=0` and a permissive review —
        the loop never blocks on the critic.
        """
        # Late import: critic depends on analyst (this module) at import time.
        if critic is None:
            from .critic import Critic  # noqa: PLC0415

            critic = Critic()

        trace = self.analyse(candidate, consumer_address=consumer_address)

        try:
            review = critic.review(candidate, trace)
        except Exception as exc:  # noqa: BLE001
            logger.warning("critic: review raised (%s); keeping draft", exc)
            trace.schema_version = "rr-trace/2"
            trace.critic_review = {
                "passed": True,
                "categories": {},
                "revision_request": "",
                "error": str(exc)[:200],
            }
            trace.revision_count = 0
            return trace

        revisions = 0
        while not review.get("passed", True) and revisions < max_revisions:
            hint = review.get("revision_request", "") or "Address the failures the critic flagged."
            logger.info(
                "critic: revision %d/%d requested (%s)",
                revisions + 1,
                max_revisions,
                hint[:120],
            )
            revisions += 1
            try:
                trace = self.analyse(
                    candidate,
                    consumer_address=consumer_address,
                    revision_hint=hint,
                )
                review = critic.review(candidate, trace)
            except Exception as exc:  # noqa: BLE001
                logger.warning("critic: revision %d raised (%s); accepting last draft", revisions, exc)
                break

        trace.schema_version = "rr-trace/2"
        trace.critic_review = review
        trace.revision_count = revisions
        return trace
