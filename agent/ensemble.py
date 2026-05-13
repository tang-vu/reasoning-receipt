"""Multi-agent ensemble — Bull / Bear / Edge → Supervisor → rr-trace/3.

Three independent role-tuned Gemini calls run in parallel (Bull argues YES,
Bear argues NO, Edge surfaces tail risks the other two miss). A Supervisor
reads all three drafts and synthesises the final probability + claim +
falsifiable claims + sensitivity + counter-arguments. Output is a
`ReasoningTraceV3` with a placeholder CriticAudit — Phase 3's `critic_v2`
replaces it before the trace ships on-chain.

Why parallel + supervisor: deer-flow / agentscope-style. Isolated context per
stance prevents groupthink. Supervisor sees only the drafts, not each
stance's chain of thought.

Cost: 4 Gemini calls per market (3 stances + supervisor). At 50 receipts/h
that's ~200 Pro calls/h — stays in the Vertex global free tier. The fallback
chain (Pro Preview → Flash Preview → 2.5 Flash) handles 429s.
"""

from __future__ import annotations

import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from .analyst import (
    DEFAULT_FALLBACK_MODELS,
    DEFAULT_REASONING_MODEL,
    MarketCandidate,
    _build_client,
    _extract_first_json,
)
from .ensemble_assembly import assemble_trace_v3, stance_from_dict
from .ensemble_mocks import mock_stance, mock_supervisor
from .gemini_call import call_with_fallback
from .trace_v3 import ReasoningTraceV3, Stance

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).parent / "prompts"
_STANCE_ROLES = ("bull", "bear", "edge")
_ROLE_ORDER = {"bull": 0, "bear": 1, "edge_case": 2}


@dataclass(slots=True)
class EnsembleConfig:
    stance_model: str = DEFAULT_REASONING_MODEL
    supervisor_model: str = DEFAULT_REASONING_MODEL
    fallback_models: list[str] = field(default_factory=lambda: list(DEFAULT_FALLBACK_MODELS))
    stance_temperature: float = 0.8  # partisan advocates — let them disagree
    supervisor_temperature: float = 0.2
    max_tokens: int = 12_288
    thinking_budget: int = 1_024
    enable_web_search: bool = True
    stance_timeout_s: float = 120.0


def _load_prompt(name: str) -> str:
    path = _PROMPTS_DIR / f"{name}.md"
    return path.read_text(encoding="utf-8") if path.exists() else f"# {name}\nProduce the requested JSON only."


def _user_msg_for_stance(candidate: MarketCandidate) -> str:
    return (
        f"Market source: {candidate.source}\n"
        f"Market id: {candidate.market_id}\n"
        f"Question: {candidate.question}\n"
        f"Resolves by: {candidate.end_date.isoformat() if candidate.end_date else 'unknown'}\n"
        f"On-platform liquidity: ${candidate.liquidity_usd:,.0f}\n\n"
        "Produce the JSON described in the system instruction. JSON only — no prose, no fences."
    )


def _user_msg_for_supervisor(
    candidate: MarketCandidate, stances: list[Stance], calibration_prior: str | None
) -> str:
    slim = [
        {
            "role": s.role,
            "probability_estimate": s.probability_estimate,
            "confidence": s.confidence,
            "key_factors": s.key_factors,
            "evidence": [{"url": e.url, "title": e.title, "cited_for": e.cited_for} for e in s.evidence],
        }
        for s in stances
    ]
    prior_block = f"\nCALIBRATION PRIOR: {calibration_prior}\n" if calibration_prior else ""
    return (
        f"Market source: {candidate.source}\n"
        f"Market id: {candidate.market_id}\n"
        f"Question: {candidate.question}\n"
        f"Resolves by: {candidate.end_date.isoformat() if candidate.end_date else 'unknown'}\n"
        f"{prior_block}\n"
        f"Three stance drafts (JSON):\n{json.dumps(slim, separators=(',', ':'))}\n\n"
        "Synthesise per the system instruction. Return ONLY the JSON."
    )


class Ensemble:
    """Run Bull/Bear/Edge in parallel → supervisor → ReasoningTraceV3."""

    def __init__(self, *, config: EnsembleConfig | None = None, mock: bool | None = None) -> None:
        self.config = config or EnsembleConfig()
        env_mock = os.getenv("RR_MOCK_ANALYST", "").lower() in {"1", "true", "yes"}
        self.mock = env_mock if mock is None else mock
        self._client = None
        self.backend: str | None = None
        if not self.mock:
            self._client, self.backend = _build_client()
            if self._client is None:
                self.mock = True
        self._stance_prompts = {role: _load_prompt(role) for role in _STANCE_ROLES}
        self._supervisor_prompt = _load_prompt("supervisor")

    def analyse(
        self,
        candidate: MarketCandidate,
        *,
        consumer_address: str | None = None,
        calibration_prior: str | None = None,
    ) -> ReasoningTraceV3:
        stances = self._run_stances_parallel(candidate)
        synthesis = self._run_supervisor(candidate, stances, calibration_prior)
        return assemble_trace_v3(
            candidate=candidate,
            stances=stances,
            synthesis=synthesis,
            stance_model=self.config.stance_model,
            supervisor_model=self.config.supervisor_model,
            consumer_address=consumer_address,
            calibration_prior=calibration_prior,
        )

    def _run_stances_parallel(self, candidate: MarketCandidate) -> list[Stance]:
        with ThreadPoolExecutor(max_workers=3, thread_name_prefix="ensemble-stance") as pool:
            futures = {pool.submit(self._run_one_stance, role, candidate): role for role in _STANCE_ROLES}
            stances: list[Stance] = []
            for future in futures:
                role = futures[future]
                try:
                    stances.append(future.result(timeout=self.config.stance_timeout_s))
                except Exception as exc:  # noqa: BLE001
                    logger.warning("ensemble: stance %s failed (%s); using mock", role, exc)
                    stances.append(stance_from_dict(role, self.config.stance_model, mock_stance(role, candidate)))
        stances.sort(key=lambda s: _ROLE_ORDER.get(s.role, 99))
        return stances

    def _run_one_stance(self, role: str, candidate: MarketCandidate) -> Stance:
        if self.mock or self._client is None:
            return stance_from_dict(role, self.config.stance_model, mock_stance(role, candidate))
        raw, _ = call_with_fallback(
            self._client,
            models=[self.config.stance_model, *self.config.fallback_models],
            system_prompt=self._stance_prompts[role],
            user=_user_msg_for_stance(candidate),
            temperature=self.config.stance_temperature,
            max_output_tokens=self.config.max_tokens,
            thinking_budget=self.config.thinking_budget,
            enable_web_search=self.config.enable_web_search,
            log_label=f"ensemble.{role}",
        )
        try:
            obj = _extract_first_json(raw)
        except Exception as exc:  # noqa: BLE001
            logger.warning("ensemble: %s stance unparseable (%s); using mock", role, exc)
            obj = mock_stance(role, candidate)
        return stance_from_dict(role, self.config.stance_model, obj)

    def _run_supervisor(
        self, candidate: MarketCandidate, stances: list[Stance], calibration_prior: str | None
    ) -> dict:
        if self.mock or self._client is None:
            return mock_supervisor(candidate, stances)
        raw, _ = call_with_fallback(
            self._client,
            models=[self.config.supervisor_model, *self.config.fallback_models],
            system_prompt=self._supervisor_prompt,
            user=_user_msg_for_supervisor(candidate, stances, calibration_prior),
            temperature=self.config.supervisor_temperature,
            max_output_tokens=self.config.max_tokens,
            thinking_budget=self.config.thinking_budget,
            enable_web_search=False,
            log_label="ensemble.supervisor",
        )
        try:
            return _extract_first_json(raw)
        except Exception as exc:  # noqa: BLE001
            logger.warning("ensemble: supervisor unparseable (%s); using mock", exc)
            return mock_supervisor(candidate, stances)
