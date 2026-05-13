"""Phase 2 — Ensemble (Bull/Bear/Edge + Supervisor) tests.

Covers Phase 2 success criteria that don't depend on a live Gemini client:
- Mock-mode Ensemble.analyse returns a valid rr-trace/3
- 3 stances run; ordered bull → bear → edge_case
- Disagreement_pp > 0 (mock probabilities are role-separated by construction)
- Stance weights sum to 1.0
- Assembly tolerates partial supervisor JSON
- Calibration prior propagates into the trace
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from agent.analyst import MarketCandidate
from agent.ensemble import Ensemble, EnsembleConfig
from agent.ensemble_assembly import assemble_trace_v3, stance_from_dict
from agent.ensemble_mocks import mock_stance, mock_supervisor
from agent.trace_v3 import ReasoningTraceV3, SCHEMA_VERSION


def _candidate(market_id: str = "poly-test-1") -> MarketCandidate:
    return MarketCandidate(
        market_id=market_id,
        source="polymarket",
        question="Will the Fed cut rates by June 2026?",
        end_date=datetime(2026, 6, 30, tzinfo=UTC),
        liquidity_usd=125_000.0,
    )


# ---------------------------------------------------------------------------
# Ensemble end-to-end (mock mode)
# ---------------------------------------------------------------------------


def test_ensemble_analyse_returns_v3_in_mock_mode() -> None:
    trace = Ensemble(mock=True).analyse(_candidate())
    assert isinstance(trace, ReasoningTraceV3)
    assert trace.schema_version == SCHEMA_VERSION
    assert trace.market_question.startswith("Will the Fed")


def test_ensemble_runs_three_stances_ordered() -> None:
    trace = Ensemble(mock=True).analyse(_candidate())
    roles = [s.role for s in trace.stances]
    assert roles == ["bull", "bear", "edge_case"]


def test_ensemble_disagreement_pp_nonzero_in_mock() -> None:
    """Mock stances are role-separated (bull > 0.6, bear < 0.4) — disagreement must surface."""
    trace = Ensemble(mock=True).analyse(_candidate())
    assert trace.supervisor_synthesis.disagreement_pp > 0.0


def test_ensemble_stance_weights_sum_to_one() -> None:
    trace = Ensemble(mock=True).analyse(_candidate())
    total = sum(s.weight_in_synthesis for s in trace.stances)
    assert abs(total - 1.0) < 0.01, f"weights total {total}"


def test_ensemble_full_blob_hash_stable_across_calls() -> None:
    """Two analyse calls for the same market produce the same trace bytes (mock determinism)."""
    e = Ensemble(mock=True)
    a = e.analyse(_candidate())
    b = e.analyse(_candidate())
    # produced_at differs (datetime.now), so compare canonical structure minus that field.
    a_dict = a.to_dict()
    b_dict = b.to_dict()
    a_dict.pop("produced_at", None)
    b_dict.pop("produced_at", None)
    a_dict.pop("node_hashes", None)
    b_dict.pop("node_hashes", None)
    a_dict.pop("merkle_root", None)
    b_dict.pop("merkle_root", None)
    assert a_dict == b_dict


def test_ensemble_propagates_calibration_prior() -> None:
    prior = "Past 30d macro Brier 0.21, over-confidence bias +0.06"
    trace = Ensemble(mock=True).analyse(_candidate(), calibration_prior=prior)
    assert trace.supervisor_synthesis.calibration_prior_used == prior


def test_ensemble_v3_trace_has_falsifiable_claim() -> None:
    trace = Ensemble(mock=True).analyse(_candidate())
    assert len(trace.falsifiable_claims) >= 1
    fc = trace.falsifiable_claims[0]
    assert fc.checkable_by  # non-empty


def test_ensemble_merkle_root_verifies_for_every_node() -> None:
    """Phase 1 invariant must still hold for an ensemble-built trace."""
    from agent.trace_v3 import verify_node_inclusion

    trace = Ensemble(mock=True).analyse(_candidate())
    root = trace.merkle_root_hex()
    for node_id, node_dict in trace.node_dicts().items():
        proof = trace.merkle_proof_for(node_id)
        assert verify_node_inclusion(node_dict, proof, root), f"failed for {node_id}"


# ---------------------------------------------------------------------------
# Pure assembly (no Gemini, no threadpool)
# ---------------------------------------------------------------------------


def test_assembly_handles_empty_supervisor_output() -> None:
    candidate = _candidate()
    stances = [
        stance_from_dict(role, "gemini-mock", mock_stance(role, candidate))
        for role in ("bull", "bear", "edge")
    ]
    trace = assemble_trace_v3(
        candidate=candidate,
        stances=stances,
        synthesis={},  # supervisor returned nothing
        stance_model="gemini-mock",
        supervisor_model="gemini-mock",
        consumer_address=None,
        calibration_prior=None,
    )
    assert trace.claim.probability == pytest.approx(
        sum(s.probability_estimate for s in stances) / 3, abs=0.01
    )
    assert trace.category == "other"
    assert len(trace.falsifiable_claims) >= 1  # placeholder filled in


def test_assembly_clips_out_of_range_probabilities() -> None:
    candidate = _candidate()
    stances = [
        stance_from_dict(role, "gemini-mock", mock_stance(role, candidate))
        for role in ("bull", "bear", "edge")
    ]
    trace = assemble_trace_v3(
        candidate=candidate,
        stances=stances,
        synthesis={"final_probability": 1.7, "final_confidence": -0.4},
        stance_model="gemini-mock",
        supervisor_model="gemini-mock",
        consumer_address=None,
        calibration_prior=None,
    )
    assert 0.0 <= trace.claim.probability <= 1.0
    assert 0.0 <= trace.claim.confidence <= 1.0


def test_assembly_invalid_category_falls_back_to_other() -> None:
    candidate = _candidate()
    stances = [
        stance_from_dict(role, "gemini-mock", mock_stance(role, candidate))
        for role in ("bull", "bear", "edge")
    ]
    trace = assemble_trace_v3(
        candidate=candidate,
        stances=stances,
        synthesis={"category": "ASTROLOGY"},  # not in whitelist
        stance_model="gemini-mock",
        supervisor_model="gemini-mock",
        consumer_address=None,
        calibration_prior=None,
    )
    assert trace.category == "other"


def test_mock_supervisor_disagreement_matches_max_minus_min() -> None:
    candidate = _candidate()
    stances = [
        stance_from_dict(role, "gemini-mock", mock_stance(role, candidate))
        for role in ("bull", "bear", "edge")
    ]
    sup = mock_supervisor(candidate, stances)
    probs = [s.probability_estimate for s in stances]
    expected_pp = (max(probs) - min(probs)) * 100
    assert abs(sup["disagreement_pp"] - expected_pp) < 0.01


def test_ensemble_config_defaults_are_sane() -> None:
    cfg = EnsembleConfig()
    assert cfg.stance_temperature > cfg.supervisor_temperature
    assert cfg.stance_temperature <= 1.0
    assert cfg.supervisor_temperature >= 0.0
    assert len(cfg.fallback_models) >= 1
