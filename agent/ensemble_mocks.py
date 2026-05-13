"""Deterministic mocks for the Bull / Bear / Edge / Supervisor pipeline.

Used by `agent.ensemble` when:
- `RR_MOCK_ANALYST=1` (offline dev / unit tests)
- Vertex client cannot be constructed (no GOOGLE_CLOUD_PROJECT + no GOOGLE_API_KEY)
- A stance call fails and we don't want to block the whole tick on one quota hit
"""

from __future__ import annotations

import hashlib

from .analyst import MarketCandidate
from .trace_v3 import Stance


def mock_stance(role: str, candidate: MarketCandidate) -> dict:
    """Role-tuned deterministic stance keyed on (market_id, role).

    Bull biases toward 0.60-0.85, Bear toward 0.15-0.40, Edge toward 0.40-0.60.
    Yields non-zero disagreement_pp in tests by construction.
    """
    digest = hashlib.sha256(f"{candidate.market_id}:{role}".encode()).digest()
    if role == "bull":
        prob = 0.6 + (digest[0] / 255.0) * 0.25
    elif role == "bear":
        prob = 0.15 + (digest[0] / 255.0) * 0.25
    else:
        prob = 0.4 + (digest[0] / 255.0) * 0.2
    return {
        "probability_estimate": round(prob, 6),
        "confidence": 0.55 + (digest[1] / 255.0) * 0.3,
        "key_factors": [f"mock {role} factor #1", f"mock {role} factor #2"],
        "evidence": [
            {
                "url": f"https://example.com/{role}/article",
                "title": f"Mock {role} source",
                "cited_for": f"{role}-leaning baseline for {candidate.market_id}",
            }
        ],
    }


def mock_supervisor(candidate: MarketCandidate, stances: list[Stance]) -> dict:
    """Deterministic supervisor — weighted equal between bull/bear, edge haircut."""
    probs = [s.probability_estimate for s in stances]
    weights = {"bull": 0.4, "bear": 0.4, "edge": 0.2}
    final = sum(
        weights["edge" if s.role == "edge_case" else s.role] * s.probability_estimate for s in stances
    )
    return {
        "final_probability": round(final, 6),
        "final_confidence": 0.7,
        "claim": f"P(yes)={final:.4f} for {candidate.market_id}",
        "category": "other",
        "disagreement_pp": round((max(probs) - min(probs)) * 100, 2),
        "synthesis_reasoning": "Mock supervisor — weighted toward bull/bear with light edge haircut.",
        "stance_weights": weights,
        "falsifiable_claims": [
            {
                "text": (
                    f"If the observable for '{candidate.question[:60]}' moves > 20pp by resolution, "
                    "both stances were wrong."
                ),
                "checkable_by": candidate.end_date.isoformat() if candidate.end_date else "2026-12-31",
                "failure_implies": "bull,bear",
            }
        ],
        "sensitivity": [{"factor": "mock sensitivity", "delta_pp": 5.0, "note": "synthetic"}],
        "counter_arguments": [{"claim": "mock counter", "weight": 0.25, "rebuttal": "synthetic rebuttal"}],
    }
