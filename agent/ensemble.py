"""Multi-agent ensemble — Bull / Bear / Edge → Supervisor → rr-trace/3.

Three independent role-tuned Gemini calls run in parallel (Bull argues YES,
Bear argues NO, Edge surfaces tail risks the other two miss). A Supervisor
reads all three drafts and synthesises the final probability + claim +
falsifiable claims + sensitivity + counter-arguments. Output is a
`ReasoningTraceV3` with a placeholder CriticAudit — Phase 3's `critic_v2`
replaces it before the trace ships on-chain.

Why parallel + supervisor: isolated context per stance prevents groupthink.
Each sub-researcher sees only the market prompt — not the others' drafts.
The Supervisor sees the three finished drafts, but not the chains of thought
that produced them.

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
from .critic_v2 import CriticV2
from .ensemble_assembly import assemble_trace_v3, stance_from_dict
from .ensemble_mocks import mock_stance, mock_supervisor
from .gemini_call import call_with_fallback
from .trace_v3 import ReasoningTraceV3, RevisionRound, Stance

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).parent / "prompts"
_STANCE_ROLES = ("bull", "bear", "edge")
_ROLE_ORDER = {"bull": 0, "bear": 1, "edge_case": 2}


_DEFAULT_STANCE_MODEL = os.getenv("RR_ENSEMBLE_STANCE_MODEL", "gemini-3-flash-preview")
_DEFAULT_SUPERVISOR_MODEL = os.getenv("RR_ENSEMBLE_SUPERVISOR_MODEL", DEFAULT_REASONING_MODEL)


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "") or default)
    except (TypeError, ValueError):
        return default


@dataclass(slots=True)
class EnsembleConfig:
    # Stances are advocacy generators (Bull / Bear / Edge) — they produce
    # bounded, structured JSON, so Flash is sufficient and ~50× cheaper than
    # Pro on output. Supervisor stays on Pro because that's where the actual
    # weighted-Bayesian synthesis happens. Both override via env.
    stance_model: str = field(default_factory=lambda: _DEFAULT_STANCE_MODEL)
    supervisor_model: str = field(default_factory=lambda: _DEFAULT_SUPERVISOR_MODEL)
    fallback_models: list[str] = field(default_factory=lambda: list(DEFAULT_FALLBACK_MODELS))
    stance_temperature: float = 0.8  # partisan advocates — let them disagree
    supervisor_temperature: float = 0.2
    # Stance JSON is < 2k tokens in practice; capping at 4k prevents thinking-
    # mode runaway. Supervisor still gets 8k for the synthesis step.
    stance_max_tokens: int = field(default_factory=lambda: _env_int("RR_ENSEMBLE_STANCE_MAX_TOKENS", 4_096))
    supervisor_max_tokens: int = field(default_factory=lambda: _env_int("RR_ENSEMBLE_SUPERVISOR_MAX_TOKENS", 8_192))
    # Stances don't need deep thinking — they just emit a partisan JSON.
    # Supervisor merges three drafts and benefits from some thinking budget.
    stance_thinking_budget: int = field(default_factory=lambda: _env_int("RR_ENSEMBLE_STANCE_THINKING", 256))
    supervisor_thinking_budget: int = field(default_factory=lambda: _env_int("RR_ENSEMBLE_SUPERVISOR_THINKING", 1_024))
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
    candidate: MarketCandidate,
    stances: list[Stance],
    calibration_prior: str | None,
    critic_feedback: str | None = None,
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
    revision_block = (
        f"\nCRITIC FEEDBACK FROM PREVIOUS DRAFT — address this in the revision:\n{critic_feedback}\n"
        if critic_feedback
        else ""
    )
    return (
        f"Market source: {candidate.source}\n"
        f"Market id: {candidate.market_id}\n"
        f"Question: {candidate.question}\n"
        f"Resolves by: {candidate.end_date.isoformat() if candidate.end_date else 'unknown'}\n"
        f"{prior_block}{revision_block}\n"
        f"Three stance drafts (JSON):\n{json.dumps(slim, separators=(',', ':'))}\n\n"
        "Synthesise per the system instruction. Return ONLY the JSON."
    )


class Ensemble:
    """Run Bull/Bear/Edge in parallel → supervisor → ReasoningTraceV3."""

    def __init__(
        self,
        *,
        config: EnsembleConfig | None = None,
        mock: bool | None = None,
        critic: CriticV2 | None = None,
    ) -> None:
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
        # Critic shares mock-mode with the rest of the ensemble — if there's no
        # Gemini client, both the stances AND the critic run on mocks. That
        # keeps test runs deterministic and offline.
        self._critic = critic or CriticV2(mock=self.mock)

    def analyse(
        self,
        candidate: MarketCandidate,
        *,
        consumer_address: str | None = None,
        calibration_prior: str | None = None,
    ) -> ReasoningTraceV3:
        """Full pipeline: stances → supervisor → critic → maybe revise → final trace."""
        stances = self._run_stances_parallel(candidate)
        synthesis = self._run_supervisor(candidate, stances, calibration_prior, critic_feedback=None)
        trace = self._build_trace(candidate, stances, synthesis, consumer_address, calibration_prior)

        audit, feedback = self._critic.review(candidate, trace, revision_round=0)
        revision_history: list[RevisionRound] = []

        if audit.verdict == "needs_revision":
            logger.info(
                "ensemble: critic flagged %s — re-running supervisor with feedback",
                candidate.market_id,
            )
            revision_history.append(
                RevisionRound(
                    round=1,
                    trigger=feedback[:300] if feedback else "critic verdict needs_revision",
                    deltas=["supervisor re-run with critic feedback inlined"],
                )
            )
            synthesis = self._run_supervisor(candidate, stances, calibration_prior, critic_feedback=feedback)
            trace = self._build_trace(candidate, stances, synthesis, consumer_address, calibration_prior)
            audit, _ = self._critic.review(candidate, trace, revision_round=1)

        trace.critic_audit = audit
        trace.revision_history = revision_history
        return trace

    def _build_trace(
        self,
        candidate: MarketCandidate,
        stances: list[Stance],
        synthesis: dict,
        consumer_address: str | None,
        calibration_prior: str | None,
    ) -> ReasoningTraceV3:
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
            max_output_tokens=self.config.stance_max_tokens,
            thinking_budget=self.config.stance_thinking_budget,
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
        self,
        candidate: MarketCandidate,
        stances: list[Stance],
        calibration_prior: str | None,
        critic_feedback: str | None = None,
    ) -> dict:
        if self.mock or self._client is None:
            return mock_supervisor(candidate, stances)
        raw, _ = call_with_fallback(
            self._client,
            models=[self.config.supervisor_model, *self.config.fallback_models],
            system_prompt=self._supervisor_prompt,
            user=_user_msg_for_supervisor(candidate, stances, calibration_prior, critic_feedback),
            temperature=self.config.supervisor_temperature,
            max_output_tokens=self.config.supervisor_max_tokens,
            thinking_budget=self.config.supervisor_thinking_budget,
            enable_web_search=False,
            log_label="ensemble.supervisor",
        )
        try:
            return _extract_first_json(raw)
        except Exception as exc:  # noqa: BLE001
            logger.warning("ensemble: supervisor unparseable (%s); using mock", exc)
            return mock_supervisor(candidate, stances)
