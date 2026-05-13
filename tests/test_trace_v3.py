"""rr-trace/3 tests — schema determinism + Merkle proof round-trip.

Covers Phase 1 success criteria:
- ReasoningTraceV3 round-trips through JSON deterministically
- merkle_root reproduces when called twice
- merkle_proof + verify_proof agree
- Mutating one node changes that node's hash AND the root
- Off-chain verify_node_inclusion mirrors what the Solidity contract will do
"""

from __future__ import annotations

import hashlib

import pytest

from agent import merkle
from agent.trace_v3 import (
    SCHEMA_VERSION,
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
    hash_node,
    verify_node_inclusion,
)


def _make_trace() -> ReasoningTraceV3:
    """Synthetic trace with enough nodes (~14) to exercise an odd-level Merkle tree."""
    bull = Stance(
        id="s_bull",
        role="bull",
        model="gemini-3.1-pro-preview",
        probability_estimate=0.71,
        confidence=0.8,
        key_factors=["CPI cooling", "Fed dovish pivot signal"],
        evidence=[
            Evidence(id="e_bull_1", url="https://example.com/cpi", title="CPI Mar", cited_for="CPI cooling"),
            Evidence(id="e_bull_2", url="https://example.com/fed", title="FOMC minutes", cited_for="Fed dovish"),
        ],
        weight_in_synthesis=0.45,
    )
    bear = Stance(
        id="s_bear",
        role="bear",
        model="gemini-3.1-pro-preview",
        probability_estimate=0.42,
        confidence=0.75,
        key_factors=["Sticky core services inflation"],
        evidence=[Evidence(id="e_bear_1", url="https://example.com/core", title="Core CPI", cited_for="sticky core")],
        weight_in_synthesis=0.35,
    )
    edge = Stance(
        id="s_edge",
        role="edge_case",
        model="gemini-3.1-pro-preview",
        probability_estimate=0.55,
        confidence=0.6,
        key_factors=["Geopolitical oil shock invalidates both"],
        evidence=[],
        weight_in_synthesis=0.20,
    )
    audit = CriticAudit(
        version="ara-rigor-v1",
        evidence_relevance=CriticDimension(score=0.85, notes="sources on-topic"),
        falsifiability=CriticDimension(score=0.9, notes="concrete falsifier present"),
        scope=CriticDimension(score=0.8, notes="scope matches market end date"),
        coherence=CriticDimension(score=0.78, notes="weights consistent with final"),
        exploration_integrity=CriticDimension(score=0.72, notes="searched 2+ source types"),
        methodology=CriticDimension(score=0.81, notes="sensitivity present + credible"),
        verdict="approved",
    )
    return ReasoningTraceV3(
        market_id="poly-42",
        market_source="polymarket",
        market_question="Will Fed cut rates by Jun 2026?",
        horizon_days=30,
        category="macro",
        claim=Claim(id="c0", text="P(yes)=0.62", probability=0.62, confidence=0.78),
        stances=[bull, bear, edge],
        supervisor_synthesis=SupervisorSynthesis(
            merge_method="weighted_bayesian",
            disagreement_pp=29.0,
            synthesis_reasoning="weighted toward bull on stronger evidence",
        ),
        falsifiable_claims=[
            FalsifiableClaim(
                id="fc1",
                text="If CPI > 3.2% on May 22, this prediction is wrong",
                checkable_by="2026-05-22",
                failure_implies="bull",
            )
        ],
        sensitivity=[SensitivityNode(id="sn1", factor="oil shock", delta_pp=-8.0, note="if Brent +$10")],
        counter_arguments=[CounterArgument(id="ca1", claim="recession halts cuts", weight=0.3, rebuttal="prob low")],
        critic_audit=audit,
        revision_history=[],
        model_routing={
            "researcher": "gemini-3.1-pro-preview",
            "critic": "gemini-3-flash-preview",
            "supervisor": "gemini-3.1-pro-preview",
        },
        produced_at="2026-05-14T01:00:00Z",
    )


# ---------------------------------------------------------------------------
# Schema + determinism
# ---------------------------------------------------------------------------


def test_schema_version() -> None:
    trace = _make_trace()
    assert trace.schema_version == "rr-trace/3"
    assert SCHEMA_VERSION == "rr-trace/3"


def test_node_dicts_includes_every_addressable_node() -> None:
    trace = _make_trace()
    nodes = trace.node_dicts()
    # claim + 3 stances + 3 evidence + 1 counter + 1 sensitivity + 1 falsifier + 6 critic dims = 16
    assert len(nodes) == 16
    for expected_id in ("c0", "s_bull", "s_bear", "s_edge", "e_bull_1", "ca1", "sn1", "fc1", "cd_falsifiability"):
        assert expected_id in nodes


def test_node_hashes_are_stable_and_hex_prefixed() -> None:
    trace = _make_trace()
    h1 = trace.node_hashes()
    h2 = trace.node_hashes()
    assert h1 == h2
    for hex_str in h1.values():
        assert hex_str.startswith("0x")
        assert len(hex_str) == 66  # 0x + 64 hex chars


def test_to_dict_round_trip_deterministic() -> None:
    """Two consecutive .to_dict() calls must produce identical payloads."""
    trace = _make_trace()
    assert trace.to_dict() == trace.to_dict()


def test_full_blob_hash_changes_when_any_node_changes() -> None:
    trace = _make_trace()
    h_before = trace.full_blob_hash()
    trace.claim.probability = 0.63  # one-pp shift
    h_after = trace.full_blob_hash()
    assert h_before != h_after


# ---------------------------------------------------------------------------
# Merkle root + proofs
# ---------------------------------------------------------------------------


def test_merkle_root_stable() -> None:
    trace = _make_trace()
    r1 = trace.merkle_root_hex()
    r2 = trace.merkle_root_hex()
    assert r1 == r2
    assert r1.startswith("0x")
    assert len(r1) == 66


def test_merkle_proof_verifies_for_every_node() -> None:
    trace = _make_trace()
    root = trace.merkle_root_hex()
    for nid, node in trace.node_dicts().items():
        proof = trace.merkle_proof_for(nid)
        assert verify_node_inclusion(node, proof, root), f"proof failed for {nid}"


def test_mutating_one_node_changes_root_and_invalidates_old_leaf() -> None:
    """Security property: an attacker holding an old (node, proof) pair cannot
    pass it off against a new Merkle root after the tree has been mutated.
    The proof structure itself is leaf-agnostic — what matters is that the
    *original* leaf doesn't fold to the new root, even if its sibling path is
    structurally unchanged."""
    trace = _make_trace()
    root_before = trace.merkle_root_hex()
    old_bull_node = trace.node_dicts()["s_bull"]
    proof_for_bull = trace.merkle_proof_for("s_bull")

    # The old (node, proof) pair verifies against the old root.
    assert verify_node_inclusion(old_bull_node, proof_for_bull, root_before)

    # Mutate the bull stance — the root must move.
    trace.stances[0].probability_estimate = 0.72
    root_after = trace.merkle_root_hex()
    assert root_before != root_after

    # The OLD leaf with the OLD proof MUST NOT verify against the NEW root.
    # This is the meaningful tamper-detection property.
    assert not verify_node_inclusion(old_bull_node, proof_for_bull, root_after)

    # A fresh proof on the mutated tree still verifies the new bull node.
    new_bull_node = trace.node_dicts()["s_bull"]
    fresh_proof = trace.merkle_proof_for("s_bull")
    assert verify_node_inclusion(new_bull_node, fresh_proof, root_after)


def test_tampered_node_rejected() -> None:
    """Cannot fabricate a leaf and pass it off with a real proof."""
    trace = _make_trace()
    root = trace.merkle_root_hex()
    real_node = trace.node_dicts()["e_bull_1"]
    proof = trace.merkle_proof_for("e_bull_1")

    # Real node verifies.
    assert verify_node_inclusion(real_node, proof, root)

    # Tampered node (same id, different content) does NOT verify with the same proof.
    fake = {**real_node, "url": "https://attacker.example/fake"}
    assert not verify_node_inclusion(fake, proof, root)


def test_hash_node_matches_canonical_bytes() -> None:
    trace = _make_trace()
    node = trace.node_dicts()["c0"]
    assert hash_node(node) == trace.node_hashes()["c0"]


# ---------------------------------------------------------------------------
# Merkle helper unit tests (independent of trace structure)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("n_leaves", [1, 2, 3, 4, 7, 8, 15, 16, 17])
def test_merkle_root_and_proof_for_arbitrary_n(n_leaves: int) -> None:
    """Every leaf in an n-leaf tree must verify against the root."""
    leaves = [hashlib.sha256(f"leaf-{i}".encode()).digest() for i in range(n_leaves)]
    root = merkle.merkle_root(leaves)
    assert len(root) == 32
    for idx, leaf in enumerate(leaves):
        proof = merkle.merkle_proof(leaves, idx)
        assert merkle.verify_proof(leaf, proof, root), f"n={n_leaves} idx={idx}"


def test_merkle_single_leaf_is_its_own_root() -> None:
    leaf = hashlib.sha256(b"only").digest()
    assert merkle.merkle_root([leaf]) == leaf
    assert merkle.verify_proof(leaf, [], leaf)


def test_merkle_proof_rejects_wrong_sibling() -> None:
    leaves = [hashlib.sha256(f"l{i}".encode()).digest() for i in range(4)]
    root = merkle.merkle_root(leaves)
    proof = merkle.merkle_proof(leaves, 0)
    # Flip one byte in the proof.
    bad = bytes([proof[0][0] ^ 0xFF]) + proof[0][1:]
    assert not merkle.verify_proof(leaves[0], [bad] + proof[1:], root)


def test_merkle_rejects_malformed_leaf() -> None:
    with pytest.raises(ValueError):
        merkle.merkle_root([b"too-short"])
