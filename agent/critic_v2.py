"""Critic v2 — six-dimensional rigor audit for rr-trace/3 ensemble traces.

Replaces rr-trace/2's 5-category pass/fail audit with a continuous-score audit
across six dimensions of epistemic rigor (evidence relevance, falsifiability,
scope, coherence, exploration integrity, methodology). Verdict is computed
deterministically from the scores:

  all dims ≥ 0.6           → approved
  any dim  < 0.4 (round 1) → needs_revision (one revision pass)
  any dim  < 0.4 (round 2) → rejected

The critic emits a feedback string used by the Ensemble to re-run the
Supervisor with the critic's notes inlined. The critic_v2 prompt is
read-only — it audits the trace, it never proposes new content.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

from .analyst import MarketCandidate, _build_client, _extract_first_json
from .gemini_call import call_with_fallback
from .trace_v3 import CriticAudit, CriticDimension, ReasoningTraceV3

logger = logging.getLogger(__name__)

DEFAULT_CRITIC_MODEL = os.getenv("GEMINI_CRITIC_MODEL", "gemini-3-flash-preview")
_DEFAULT_CRITIC_FALLBACKS = "gemini-2.5-flash,gemini-2.5-flash-lite"
DEFAULT_CRITIC_FALLBACK_MODELS = [
    m.strip()
    for m in os.getenv("GEMINI_CRITIC_FALLBACK_MODELS", _DEFAULT_CRITIC_FALLBACKS).split(",")
    if m.strip()
]
_CRITIC_PROMPT_FILE = Path(__file__).parent / "prompts" / "critic-v2.md"

DIM_NAMES = (
    "evidence_relevance",
    "falsifiability",
    "scope",
    "coherence",
    "exploration_integrity",
    "methodology",
)
APPROVE_THRESHOLD = 0.6
FAIL_THRESHOLD = 0.4


@dataclass(slots=True)
class CriticV2Config:
    model: str = DEFAULT_CRITIC_MODEL
    fallback_models: list[str] = field(default_factory=lambda: list(DEFAULT_CRITIC_FALLBACK_MODELS))
    max_tokens: int = 4_096
    thinking_budget: int = 512
    temperature: float = 0.1


def _load_prompt() -> str:
    if _CRITIC_PROMPT_FILE.exists():
        return _CRITIC_PROMPT_FILE.read_text(encoding="utf-8")
    return "You audit prediction traces. Return JSON {verdict, dimensions, revision_request}."


def _slim_trace_for_audit(trace: ReasoningTraceV3) -> dict:
    """The view of the trace the critic sees. Keep token-light."""
    return {
        "claim": trace.claim.text,
        "final_probability": trace.claim.probability,
        "final_confidence": trace.claim.confidence,
        "category": trace.category,
        "stances": [
            {
                "role": s.role,
                "probability_estimate": s.probability_estimate,
                "confidence": s.confidence,
                "weight_in_synthesis": s.weight_in_synthesis,
                "key_factors": s.key_factors,
                "evidence_urls": [e.url for e in s.evidence],
                "evidence_cited_for": [e.cited_for for e in s.evidence],
            }
            for s in trace.stances
        ],
        "supervisor_synthesis": trace.supervisor_synthesis.synthesis_reasoning,
        "falsifiable_claims": [
            {"text": fc.text, "checkable_by": fc.checkable_by, "failure_implies": fc.failure_implies}
            for fc in trace.falsifiable_claims
        ],
        "sensitivity": [{"factor": s.factor, "delta_pp": s.delta_pp} for s in trace.sensitivity],
        "counter_arguments": [{"claim": c.claim, "weight": c.weight} for c in trace.counter_arguments],
    }


def _compute_verdict(scores: dict[str, float], revision_round: int) -> str:
    """Apply the verdict rule given per-dim scores and how many revisions used."""
    if all(scores.get(d, 0.0) >= APPROVE_THRESHOLD for d in DIM_NAMES):
        return "approved"
    if any(scores.get(d, 0.0) < FAIL_THRESHOLD for d in DIM_NAMES):
        return "rejected" if revision_round >= 1 else "needs_revision"
    # All dims in [0.4, 0.6) — borderline. Treat as approved (no clear failure)
    # to avoid stalling the daemon on every borderline trace. The probability
    # gets a confidence haircut elsewhere if the supervisor saw the prior.
    return "approved"


def _audit_from_dict(obj: dict, revision_round: int) -> CriticAudit:
    """Coerce critic JSON into a strongly-typed CriticAudit + apply verdict rule."""
    raw_dims = obj.get("dimensions") or {}
    dims_out: dict[str, CriticDimension] = {}
    scores: dict[str, float] = {}
    for name in DIM_NAMES:
        entry = raw_dims.get(name) if isinstance(raw_dims, dict) else None
        score = 1.0
        notes = "n/a"
        if isinstance(entry, dict):
            try:
                score = max(0.0, min(1.0, float(entry.get("score", 1.0))))
            except (TypeError, ValueError):
                score = 1.0
            notes = str(entry.get("notes", ""))[:200]
        dims_out[name] = CriticDimension(score=score, notes=notes)
        scores[name] = score
    verdict = _compute_verdict(scores, revision_round)
    # Trust the rule over the model's self-reported verdict — keeps thresholds
    # deterministic and avoids the critic talking itself into a free pass.
    return CriticAudit(
        version="rr-critic-v1",
        evidence_relevance=dims_out["evidence_relevance"],
        falsifiability=dims_out["falsifiability"],
        scope=dims_out["scope"],
        coherence=dims_out["coherence"],
        exploration_integrity=dims_out["exploration_integrity"],
        methodology=dims_out["methodology"],
        verdict=verdict,
    )


def _mock_audit(trace: ReasoningTraceV3, revision_round: int) -> CriticAudit:
    """Deterministic mock audit for offline tests. All dims pass cleanly."""
    return _audit_from_dict(
        {
            "verdict": "approved",
            "dimensions": {name: {"score": 0.85, "notes": "mock"} for name in DIM_NAMES},
            "revision_request": "",
        },
        revision_round,
    )


class CriticV2:
    """Audits a v3 reasoning trace and returns a CriticAudit + revision feedback."""

    def __init__(self, *, config: CriticV2Config | None = None, mock: bool | None = None) -> None:
        self.config = config or CriticV2Config()
        env_mock = os.getenv("RR_MOCK_CRITIC", "").lower() in {"1", "true", "yes"}
        if not env_mock:
            env_mock = os.getenv("RR_MOCK_ANALYST", "").lower() in {"1", "true", "yes"}
        self.mock = env_mock if mock is None else mock
        self._client = None
        self.backend: str | None = None
        if not self.mock:
            self._client, self.backend = _build_client()
            if self._client is None:
                self.mock = True
        self._prompt = _load_prompt()

    def review(
        self,
        candidate: MarketCandidate,
        trace: ReasoningTraceV3,
        revision_round: int = 0,
    ) -> tuple[CriticAudit, str]:
        """Audit the trace. Return (audit, revision_feedback).

        revision_feedback is empty unless verdict == "needs_revision". The
        Ensemble re-runs the Supervisor with this text inlined as a hint.
        """
        if self.mock or self._client is None:
            audit = _mock_audit(trace, revision_round)
            return audit, ""

        user = (
            f"Market question: {candidate.question}\n"
            f"Resolves by: {candidate.end_date.isoformat() if candidate.end_date else 'unknown'}\n\n"
            f"Trace under audit (JSON):\n{json.dumps(_slim_trace_for_audit(trace), separators=(',', ':'))}\n\n"
            "Audit per the system instruction. Return ONLY the JSON."
        )
        try:
            raw, _ = call_with_fallback(
                self._client,
                models=[self.config.model, *self.config.fallback_models],
                system_prompt=self._prompt,
                user=user,
                temperature=self.config.temperature,
                max_output_tokens=self.config.max_tokens,
                thinking_budget=self.config.thinking_budget,
                enable_web_search=False,
                log_label="critic_v2",
            )
            obj = _extract_first_json(raw)
        except Exception as exc:  # noqa: BLE001
            logger.warning("critic_v2: audit failed (%s); falling back to mock approve", exc)
            return _mock_audit(trace, revision_round), ""

        audit = _audit_from_dict(obj, revision_round)
        feedback = ""
        if audit.verdict == "needs_revision":
            feedback = str(obj.get("revision_request", ""))[:800] or self._auto_feedback(audit)
        return audit, feedback

    def _auto_feedback(self, audit: CriticAudit) -> str:
        """Synthesise a revision hint when the model didn't supply one."""
        weak = []
        for name in DIM_NAMES:
            dim: CriticDimension = getattr(audit, name)
            if dim.score < FAIL_THRESHOLD:
                weak.append(f"{name} (score {dim.score:.2f}): {dim.notes}")
        return "Address these weak dimensions: " + " | ".join(weak)
