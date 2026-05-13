"""Pure-function trace-assembly helpers for the ensemble pipeline.

Coerce raw dicts (stance JSON, supervisor JSON) into the strongly-typed
`ReasoningTraceV3` shape. No I/O, no network — fully unit-testable.

Separated from `agent.ensemble` so the orchestrator stays focused on
parallelism + model calls, not data plumbing.
"""

from __future__ import annotations

from .analyst import MarketCandidate
from .trace_v3 import (
    Claim,
    CounterArgument,
    CriticAudit,
    CriticDimension,
    Evidence,
    FalsifiableClaim,
    ReasoningTraceV3,
    SensitivityNode,
    Stance,
    SupervisorSynthesis,
)

_VALID_CATEGORIES = {"politics", "macro", "crypto", "sports", "tech", "other"}


def stance_from_dict(role: str, stance_model: str, obj: dict) -> Stance:
    """Build a Stance from a sub-researcher's raw JSON.

    `role` is the prompt role ("bull" | "bear" | "edge"); the trace stores the
    canonical role string ("bull" | "bear" | "edge_case").
    """
    canonical_role = "edge_case" if role == "edge" else role
    prob = _clip01(obj.get("probability_estimate", 0.5))
    conf = _clip01(obj.get("confidence", 0.5))
    evidence: list[Evidence] = []
    for i, ev in enumerate(obj.get("evidence", []) or []):
        if not isinstance(ev, dict):
            continue
        evidence.append(
            Evidence(
                id=f"e_{role}_{i + 1}",
                url=str(ev.get("url", ""))[:500],
                title=str(ev.get("title", ""))[:200],
                cited_for=str(ev.get("cited_for", ""))[:200],
            )
        )
    return Stance(
        id=f"s_{role}",
        role=canonical_role,
        model=f"{stance_model}@ensemble",
        probability_estimate=prob,
        confidence=conf,
        key_factors=[str(k)[:200] for k in (obj.get("key_factors", []) or [])][:6],
        evidence=evidence,
    )


def assemble_trace_v3(
    *,
    candidate: MarketCandidate,
    stances: list[Stance],
    synthesis: dict,
    stance_model: str,
    supervisor_model: str,
    consumer_address: str | None,
    calibration_prior: str | None,
) -> ReasoningTraceV3:
    """Combine three Stances + the supervisor's synthesis JSON into a v3 trace."""
    weights = synthesis.get("stance_weights") or {"bull": 0.34, "bear": 0.33, "edge": 0.33}
    for stance in stances:
        key = "edge" if stance.role == "edge_case" else stance.role
        stance.weight_in_synthesis = float(weights.get(key, 0.0))

    probs = [s.probability_estimate for s in stances]
    observed_disagreement_pp = round((max(probs) - min(probs)) * 100, 2)
    disagreement_pp = float(synthesis.get("disagreement_pp", observed_disagreement_pp))

    final_prob = _clip01(synthesis.get("final_probability", sum(probs) / max(len(probs), 1)))
    final_conf = _clip01(synthesis.get("final_confidence", 0.5))

    category = str(synthesis.get("category", "other")).lower()
    if category not in _VALID_CATEGORIES:
        category = "other"

    falsifiable = _coerce_falsifiable_claims(synthesis.get("falsifiable_claims"))
    sensitivity = _coerce_sensitivity(synthesis.get("sensitivity"))
    counter = _coerce_counter_args(synthesis.get("counter_arguments"))

    return ReasoningTraceV3(
        market_id=candidate.market_id,
        market_source=candidate.source,
        market_question=candidate.question,
        horizon_days=14,
        category=category,
        claim=Claim(
            id="c0",
            text=str(synthesis.get("claim", ""))[:300],
            probability=final_prob,
            confidence=final_conf,
        ),
        stances=stances,
        supervisor_synthesis=SupervisorSynthesis(
            merge_method="weighted_bayesian",
            disagreement_pp=disagreement_pp,
            synthesis_reasoning=str(synthesis.get("synthesis_reasoning", ""))[:1000],
            calibration_prior_used=calibration_prior,
        ),
        falsifiable_claims=falsifiable,
        sensitivity=sensitivity,
        counter_arguments=counter,
        critic_audit=_placeholder_audit(),
        revision_history=[],
        model_routing={
            "researcher": stance_model,
            "supervisor": supervisor_model,
            "critic": "pending-phase-3",
        },
        consumer_address=consumer_address,
    )


def _placeholder_audit() -> CriticAudit:
    """Open audit until Phase 3 wires the real critic_v2."""
    pending = CriticDimension(score=1.0, notes="critic_v2 pending (Phase 3)")
    return CriticAudit(
        version="ara-rigor-v1-placeholder",
        evidence_relevance=pending,
        falsifiability=pending,
        scope=pending,
        coherence=pending,
        exploration_integrity=pending,
        methodology=pending,
        verdict="approved",
    )


def _coerce_falsifiable_claims(raw) -> list[FalsifiableClaim]:
    """Always return ≥ 1 falsifiable claim — Phase 3 critic will downgrade trivial ones."""
    out = [
        FalsifiableClaim(
            id=f"fc{i + 1}",
            text=str(fc.get("text", ""))[:400],
            checkable_by=str(fc.get("checkable_by", "")),
            failure_implies=str(fc.get("failure_implies", ""))[:80],
        )
        for i, fc in enumerate(raw or [])
        if isinstance(fc, dict)
    ]
    if not out:
        out = [
            FalsifiableClaim(
                id="fc1",
                text="No specific falsifier produced — supervisor returned an empty list.",
                checkable_by="2026-12-31",
                failure_implies="all",
            )
        ]
    return out


def _coerce_sensitivity(raw) -> list[SensitivityNode]:
    return [
        SensitivityNode(
            id=f"sn{i + 1}",
            factor=str(sn.get("factor", ""))[:200],
            delta_pp=float(sn.get("delta_pp", 0.0)),
            note=(str(sn.get("note"))[:200] if sn.get("note") is not None else None),
        )
        for i, sn in enumerate(raw or [])
        if isinstance(sn, dict)
    ]


def _coerce_counter_args(raw) -> list[CounterArgument]:
    return [
        CounterArgument(
            id=f"ca{i + 1}",
            claim=str(ca.get("claim", ""))[:300],
            weight=float(ca.get("weight", 0.0)),
            rebuttal=(str(ca.get("rebuttal"))[:300] if ca.get("rebuttal") is not None else None),
        )
        for i, ca in enumerate(raw or [])
        if isinstance(ca, dict)
    ]


def _clip01(x) -> float:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return 0.5
    return max(0.0, min(1.0, v))
