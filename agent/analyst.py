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
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .trace import CounterArgument, ReasoningTrace, SensitivityNode, Source

logger = logging.getLogger(__name__)

DEFAULT_REASONING_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.1-pro-preview")
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
    max_tokens: int = 4096
    temperature: float = 0.2
    enable_web_search: bool = True


def _load_prompt() -> str:
    if PROMPT_FILE.exists():
        return PROMPT_FILE.read_text(encoding="utf-8")
    return _DEFAULT_PROMPT


_DEFAULT_PROMPT = """You are ReasoningReceipt's analyst. Given a prediction market
question, produce a calibrated probability. Cite sources by URL. Return ONLY a
JSON object with the keys described in the task."""


def _extract_first_json(text: str) -> dict:
    """Grab the first {...} block in `text`. Tolerant of code fences and prose."""
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        return json.loads(fence.group(1))
    brace = text.find("{")
    if brace == -1:
        raise ValueError("no JSON object in model output")
    depth = 0
    for i, ch in enumerate(text[brace:], start=brace):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return json.loads(text[brace : i + 1])
    raise ValueError("unterminated JSON object")


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
    """Return a (client, backend_name) pair or (None, None) for mock mode."""
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
    ) -> ReasoningTrace:
        raw = self._call_model(candidate)
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

        model_label = self.config.model if not self.mock else f"mock:{self.config.model}"
        if not self.mock and self.backend:
            model_label = f"{self.config.model}@{self.backend}"

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

    def _call_model(self, candidate: MarketCandidate) -> str:
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

        tools: list = []
        if self.config.enable_web_search:
            tools.append(types.Tool(google_search=types.GoogleSearch()))

        config = types.GenerateContentConfig(
            system_instruction=self.prompt,
            temperature=self.config.temperature,
            max_output_tokens=self.config.max_tokens,
            response_mime_type="application/json" if not tools else None,
            tools=tools or None,
        )

        resp = self._client.models.generate_content(
            model=self.config.model,
            contents=user,
            config=config,
        )
        text = getattr(resp, "text", None)
        if not text:
            # Walk parts manually for the multi-part response shape.
            for cand in getattr(resp, "candidates", []) or []:
                for part in getattr(cand.content, "parts", []) or []:
                    if getattr(part, "text", None):
                        return part.text
            raise RuntimeError("Gemini returned no text")
        return text
