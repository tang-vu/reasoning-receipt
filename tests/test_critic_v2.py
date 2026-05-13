"""Phase 3 — critic_v2 + revision-loop tests.

Covers the verdict logic, audit coercion, and the ensemble's single-pass
revision behaviour without hitting Vertex AI.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from agent.analyst import MarketCandidate
from agent.critic_v2 import (
    APPROVE_THRESHOLD,
    DIM_NAMES,
    FAIL_THRESHOLD,
    CriticV2,
    _audit_from_dict,
    _compute_verdict,
    _mock_audit,
)
from agent.ensemble import Ensemble
from agent.trace_v3 import CriticAudit, CriticDimension, ReasoningTraceV3


def _candidate() -> MarketCandidate:
    return MarketCandidate(
        market_id="poly-critic-1",
        source="polymarket",
        question="Will the Fed cut rates by June 2026?",
        end_date=datetime(2026, 6, 30, tzinfo=UTC),
        liquidity_usd=125_000.0,
    )


def _trace() -> ReasoningTraceV3:
    return Ensemble(mock=True).analyse(_candidate())


# ---------------------------------------------------------------------------
# Verdict logic — pure rules
# ---------------------------------------------------------------------------


def test_verdict_all_high_approves() -> None:
    scores = {d: 0.8 for d in DIM_NAMES}
    assert _compute_verdict(scores, revision_round=0) == "approved"


def test_verdict_any_below_fail_threshold_round_zero_needs_revision() -> None:
    scores = {d: 0.8 for d in DIM_NAMES}
    scores["falsifiability"] = FAIL_THRESHOLD - 0.05
    assert _compute_verdict(scores, revision_round=0) == "needs_revision"


def test_verdict_any_below_fail_threshold_round_one_rejected() -> None:
    scores = {d: 0.8 for d in DIM_NAMES}
    scores["falsifiability"] = FAIL_THRESHOLD - 0.05
    assert _compute_verdict(scores, revision_round=1) == "rejected"


def test_verdict_borderline_below_approve_but_above_fail_treated_approved() -> None:
    """All dims in [0.4, 0.6) — no clear failure, no clear pass — approve to keep daemon moving."""
    scores = {d: 0.5 for d in DIM_NAMES}
    assert _compute_verdict(scores, revision_round=0) == "approved"


def test_verdict_thresholds_are_inclusive_on_approve() -> None:
    scores = {d: APPROVE_THRESHOLD for d in DIM_NAMES}
    assert _compute_verdict(scores, revision_round=0) == "approved"


# ---------------------------------------------------------------------------
# Audit coercion
# ---------------------------------------------------------------------------


def test_audit_from_dict_handles_empty_payload() -> None:
    audit = _audit_from_dict({}, revision_round=0)
    assert audit.version == "rr-critic-v1"
    # Empty payload defaults to 1.0 across all dims, so verdict is approved.
    assert audit.verdict == "approved"


def test_audit_from_dict_clips_out_of_range_scores() -> None:
    audit = _audit_from_dict(
        {"dimensions": {d: {"score": 1.7 if d == "scope" else 0.7, "notes": "x"} for d in DIM_NAMES}},
        revision_round=0,
    )
    assert audit.scope.score == 1.0  # clipped from 1.7


def test_audit_from_dict_overrides_self_reported_verdict_using_rule() -> None:
    """The critic could lie ('verdict: approved') with bad scores — we recompute."""
    payload = {
        "verdict": "approved",  # model self-report
        "dimensions": {
            **{d: {"score": 0.9, "notes": "ok"} for d in DIM_NAMES if d != "falsifiability"},
            "falsifiability": {"score": 0.1, "notes": "no concrete falsifier"},
        },
    }
    audit = _audit_from_dict(payload, revision_round=0)
    assert audit.verdict == "needs_revision"  # rule wins over model self-report


def test_audit_from_dict_coerces_non_dict_dim_entry() -> None:
    audit = _audit_from_dict({"dimensions": {"scope": "not a dict"}}, revision_round=0)
    assert audit.scope.score == 1.0
    assert audit.scope.notes == "n/a"


# ---------------------------------------------------------------------------
# CriticV2 in mock mode
# ---------------------------------------------------------------------------


def test_mock_critic_returns_approved_audit_and_empty_feedback() -> None:
    audit, feedback = CriticV2(mock=True).review(_candidate(), _trace(), revision_round=0)
    assert audit.verdict == "approved"
    assert feedback == ""
    assert audit.version == "rr-critic-v1"


def test_mock_audit_all_dims_above_approve_threshold() -> None:
    audit = _mock_audit(_trace(), revision_round=0)
    for name in DIM_NAMES:
        dim: CriticDimension = getattr(audit, name)
        assert dim.score >= APPROVE_THRESHOLD


# ---------------------------------------------------------------------------
# Ensemble + critic revision loop
# ---------------------------------------------------------------------------


class _FlagFlipCritic:
    """Mock critic — first call says 'needs_revision', second says 'approved'.

    Lets us drive the revision branch deterministically without Gemini.
    """

    def __init__(self) -> None:
        self.call_count = 0
        self.calls: list[int] = []  # revision_round of each call

    def review(self, candidate, trace, revision_round=0):
        self.calls.append(revision_round)
        self.call_count += 1
        if revision_round == 0:
            # Bad falsifiability triggers needs_revision; other dims clean.
            payload = {
                "dimensions": {
                    **{d: {"score": 0.85, "notes": "ok"} for d in DIM_NAMES if d != "falsifiability"},
                    "falsifiability": {"score": 0.2, "notes": "no concrete falsifier"},
                },
                "revision_request": "Add a falsifiable claim with a concrete checkable_by date.",
            }
            audit = _audit_from_dict(payload, revision_round=0)
            return audit, "Add a falsifiable claim with a concrete checkable_by date."
        # Second round — all clean, verdict approved.
        audit = _mock_audit(trace, revision_round=1)
        return audit, ""


def test_ensemble_triggers_revision_when_critic_flags_then_approves() -> None:
    critic = _FlagFlipCritic()
    ensemble = Ensemble(mock=True, critic=critic)
    trace = ensemble.analyse(_candidate())

    assert critic.call_count == 2
    assert critic.calls == [0, 1]
    assert len(trace.revision_history) == 1
    assert trace.revision_history[0].round == 1
    assert "falsifiable" in trace.revision_history[0].trigger.lower()
    assert trace.critic_audit.verdict == "approved"


def test_ensemble_skips_revision_when_first_audit_passes() -> None:
    """Default mock critic always approves — no revision should happen."""
    ensemble = Ensemble(mock=True)
    trace = ensemble.analyse(_candidate())
    assert trace.critic_audit.verdict == "approved"
    assert trace.revision_history == []


def test_ensemble_records_critic_audit_on_returned_trace() -> None:
    trace = Ensemble(mock=True).analyse(_candidate())
    audit: CriticAudit = trace.critic_audit
    assert audit.version == "rr-critic-v1"
    for name in DIM_NAMES:
        dim: CriticDimension = getattr(audit, name)
        assert 0.0 <= dim.score <= 1.0


# ---------------------------------------------------------------------------
# Auto-feedback synthesis
# ---------------------------------------------------------------------------


def test_critic_auto_feedback_names_weak_dimensions() -> None:
    critic = CriticV2(mock=True)
    weak_audit = _audit_from_dict(
        {
            "dimensions": {
                **{d: {"score": 0.8, "notes": "ok"} for d in DIM_NAMES if d not in {"scope", "coherence"}},
                "scope": {"score": 0.2, "notes": "claim scope mismatched market window"},
                "coherence": {"score": 0.3, "notes": "supervisor weights inconsistent with final"},
            }
        },
        revision_round=0,
    )
    feedback = critic._auto_feedback(weak_audit)
    assert "scope" in feedback
    assert "coherence" in feedback
    assert "Address" in feedback


# ---------------------------------------------------------------------------
# Trace integrity post-revision
# ---------------------------------------------------------------------------


def test_trace_merkle_still_verifies_after_revision() -> None:
    """Phase 1 invariant must survive the revision loop."""
    from agent.trace_v3 import verify_node_inclusion

    critic = _FlagFlipCritic()
    trace = Ensemble(mock=True, critic=critic).analyse(_candidate())
    root = trace.merkle_root_hex()
    for node_id, node_dict in trace.node_dicts().items():
        proof = trace.merkle_proof_for(node_id)
        assert verify_node_inclusion(node_dict, proof, root), f"failed for {node_id}"


def test_revision_history_has_actionable_trigger() -> None:
    critic = _FlagFlipCritic()
    trace = Ensemble(mock=True, critic=critic).analyse(_candidate())
    assert len(trace.revision_history) == 1
    rh = trace.revision_history[0]
    assert rh.round == 1
    assert rh.trigger  # non-empty
    assert rh.deltas  # non-empty list


# ---------------------------------------------------------------------------
# Quick smoke for config + thresholds
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "weak_dim",
    ["evidence_relevance", "falsifiability", "scope", "coherence", "exploration_integrity", "methodology"],
)
def test_each_dimension_can_trigger_needs_revision(weak_dim: str) -> None:
    scores = {d: 0.8 for d in DIM_NAMES}
    scores[weak_dim] = 0.2
    assert _compute_verdict(scores, revision_round=0) == "needs_revision"
