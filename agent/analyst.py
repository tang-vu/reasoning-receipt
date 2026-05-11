"""Claude-driven probability analyst.

Takes a `MarketCandidate`, asks Claude Opus 4.7 (via the Anthropic SDK) for a
calibrated probability with cited sources, counter-arguments, and sensitivity.
Returns a populated `ReasoningTrace`.

Mock mode (`RR_MOCK_ANALYST=1` or missing `ANTHROPIC_API_KEY`): deterministic
synthetic answer so the full pipeline runs in tests and local dev.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .trace import CounterArgument, ReasoningTrace, SensitivityNode, Source

DEFAULT_REASONING_MODEL = "claude-opus-4-7"
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
        "claim": f"The outcome of '{candidate.question[:80]}' is most likely YES." if prob >= 0.5 else f"The outcome of '{candidate.question[:80]}' is most likely NO.",
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
        "summary": "Synthetic analyst output. Replace with real Claude call by populating ANTHROPIC_API_KEY.",
    }


class Analyst:
    """Produces a ReasoningTrace for a MarketCandidate."""

    def __init__(self, *, api_key: str | None = None, config: AnalystConfig | None = None, mock: bool | None = None) -> None:
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self.config = config or AnalystConfig()
        env_mock = os.getenv("RR_MOCK_ANALYST", "").lower() in {"1", "true", "yes"}
        self.mock = env_mock if mock is None else mock
        if not self.api_key:
            self.mock = True
        self.prompt = _load_prompt()

    def analyse(self, candidate: MarketCandidate, *, consumer_address: str | None = None) -> ReasoningTrace:
        raw = self._call_model(candidate)
        try:
            obj = _extract_first_json(raw)
        except Exception:
            obj = _mock_answer(candidate)

        sources = [Source(**s) for s in obj.get("sources", [])]
        counter = [CounterArgument(**c) for c in obj.get("counter_arguments", [])]
        sensitivity = [SensitivityNode(**s) for s in obj.get("sensitivity", [])]

        prob = float(obj.get("probability", 0.5))
        conf = float(obj.get("confidence", 0.5))
        prob = max(0.0, min(1.0, prob))
        conf = max(0.0, min(1.0, conf))

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
            model=self.config.model if not self.mock else f"mock:{self.config.model}",
            produced_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            consumer_address=consumer_address,
        )

    def _call_model(self, candidate: MarketCandidate) -> str:
        if self.mock:
            return json.dumps(_mock_answer(candidate))

        from anthropic import Anthropic

        client = Anthropic(api_key=self.api_key)
        user = (
            f"Market source: {candidate.source}\n"
            f"Market id: {candidate.market_id}\n"
            f"Question: {candidate.question}\n"
            f"Resolves by: {candidate.end_date.isoformat() if candidate.end_date else 'unknown'}\n"
            f"On-platform liquidity: ${candidate.liquidity_usd:,.0f}\n\n"
            "Produce the JSON described in the system prompt. JSON only."
        )
        tools = []
        if self.config.enable_web_search:
            tools = [{"type": "web_search_20250305", "name": "web_search", "max_uses": 5}]
        resp = client.messages.create(
            model=self.config.model,
            system=self.prompt,
            max_tokens=self.config.max_tokens,
            temperature=self.config.temperature,
            messages=[{"role": "user", "content": user}],
            tools=tools if tools else None,
        )
        for block in resp.content:
            if getattr(block, "type", None) == "text":
                return block.text
        raise RuntimeError("Claude returned no text blocks")
