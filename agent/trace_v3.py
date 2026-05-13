"""rr-trace/3 — reasoning DAG with per-node hashes + Merkle root.

Where rr-trace/2 commits a single SHA-256 of the whole canonical JSON, rr-trace/3
adds a Merkle root over the hashes of every node in the trace's reasoning
graph. Each node (a stance, a piece of evidence, a counter-argument, a
sensitivity factor, a falsifiable claim, a critic dimension) is independently
addressable: anyone can prove that a single evidence URL was part of the
on-chain commit without downloading the full trace.

This module is pure data + bytes; the orchestration (Bull/Bear/Edge → Supervisor
→ Critic) lives in `agent.ensemble`.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

from storage.irys import canonical_bytes, sha256_hex

from . import merkle

SCHEMA_VERSION = "rr-trace/3"


def _utcnow_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(slots=True)
class Evidence:
    id: str
    url: str
    title: str
    cited_for: str
    accessed_at: str = field(default_factory=_utcnow_iso)


@dataclass(slots=True)
class CounterArgument:
    id: str
    claim: str
    weight: float
    rebuttal: str | None = None


@dataclass(slots=True)
class SensitivityNode:
    id: str
    factor: str
    delta_pp: float
    note: str | None = None


@dataclass(slots=True)
class Stance:
    """One of the Bull / Bear / Edge sub-researchers' draft."""

    id: str
    role: str  # "bull" | "bear" | "edge_case"
    model: str
    probability_estimate: float
    confidence: float
    key_factors: list[str]
    evidence: list[Evidence] = field(default_factory=list)
    weight_in_synthesis: float = 0.0  # filled by supervisor


@dataclass(slots=True)
class FalsifiableClaim:
    id: str
    text: str
    checkable_by: str  # ISO date
    failure_implies: str  # which stance(s) wrong if observed


@dataclass(slots=True)
class CriticDimension:
    score: float  # ∈ [0, 1]
    notes: str


@dataclass(slots=True)
class CriticAudit:
    """Six-dimensional rigor audit. Filled by `agent.critic_v2` (Phase 3).

    Dimensions: evidence relevance, falsifiability, scope, coherence,
    exploration integrity, methodology. Each scored in [0, 1] with notes.
    Verdict: approved (all ≥ 0.6) / needs_revision (any < 0.4 once) /
    rejected (still failing after one revision pass).
    """

    version: str  # "rr-critic-v1"
    evidence_relevance: CriticDimension
    falsifiability: CriticDimension
    scope: CriticDimension
    coherence: CriticDimension
    exploration_integrity: CriticDimension
    methodology: CriticDimension
    verdict: str  # "approved" | "needs_revision" | "rejected"


@dataclass(slots=True)
class RevisionRound:
    round: int
    trigger: str
    deltas: list[str] = field(default_factory=list)


@dataclass(slots=True)
class SupervisorSynthesis:
    merge_method: str  # "weighted_bayesian"
    disagreement_pp: float  # max(prob) - min(prob) across stances, in pp
    synthesis_reasoning: str
    calibration_prior_used: str | None = None  # Phase 5 will fill this


@dataclass(slots=True)
class Claim:
    id: str  # always "c0"
    text: str
    probability: float
    confidence: float


@dataclass(slots=True)
class ReasoningTraceV3:
    """The rr-trace/3 reasoning DAG. Each leaf gets its own hash; the Merkle
    root over all leaves is what lands on-chain in `ReceiptRegistryV2`.
    """

    market_id: str
    market_source: str
    market_question: str
    horizon_days: int
    category: str  # politics | macro | crypto | sports | tech | other
    claim: Claim
    stances: list[Stance]
    supervisor_synthesis: SupervisorSynthesis
    falsifiable_claims: list[FalsifiableClaim]
    sensitivity: list[SensitivityNode]
    counter_arguments: list[CounterArgument]
    critic_audit: CriticAudit
    revision_history: list[RevisionRound]
    model_routing: dict[str, str]  # researcher/critic/supervisor model names
    produced_at: str = field(default_factory=_utcnow_iso)
    consumer_address: str | None = None
    agent_version: str = "0.3.0"
    schema_version: str = SCHEMA_VERSION

    def node_dicts(self) -> dict[str, dict[str, Any]]:
        """Each addressable node, keyed by stable id, ready for hashing.

        Stable ids: c0 (claim), s_<role> (stances), e_<role>_<n> (evidence,
        flattened from stances), ca<n> (counter-arguments), sn<n>
        (sensitivity), fc<n> (falsifiable claims), cd_<dim> (critic dims).
        """
        out: dict[str, dict[str, Any]] = {self.claim.id: asdict(self.claim)}
        for stance in self.stances:
            sdict = asdict(stance)
            # Evidence under a stance is a sub-node too — flatten one level.
            evidence_list = sdict.pop("evidence", [])
            out[stance.id] = sdict
            for ev in evidence_list:
                out[ev["id"]] = ev
        for ca in self.counter_arguments:
            out[ca.id] = asdict(ca)
        for sn in self.sensitivity:
            out[sn.id] = asdict(sn)
        for fc in self.falsifiable_claims:
            out[fc.id] = asdict(fc)
        for dim_name in (
            "evidence_relevance",
            "falsifiability",
            "scope",
            "coherence",
            "exploration_integrity",
            "methodology",
        ):
            out[f"cd_{dim_name}"] = asdict(getattr(self.critic_audit, dim_name))
        return out

    def node_hashes(self) -> dict[str, str]:
        """SHA-256 of each node's canonical bytes, hex-prefixed."""
        return {nid: sha256_hex(canonical_bytes(nd)) for nid, nd in self.node_dicts().items()}

    def merkle_root_hex(self) -> str:
        """Merkle root over the per-node hashes, sorted lexicographically by id."""
        hashes = self.node_hashes()
        leaves = [bytes.fromhex(hashes[nid][2:]) for nid in sorted(hashes)]
        return "0x" + merkle.merkle_root(leaves).hex()

    def merkle_proof_for(self, node_id: str) -> list[str]:
        """Inclusion proof for one node, hex strings (bottom-up)."""
        hashes = self.node_hashes()
        ordered = sorted(hashes)
        if node_id not in hashes:
            raise KeyError(f"node {node_id!r} not in trace")
        idx = ordered.index(node_id)
        leaves = [bytes.fromhex(hashes[nid][2:]) for nid in ordered]
        return ["0x" + s.hex() for s in merkle.merkle_proof(leaves, idx)]

    def to_dict(self) -> dict[str, Any]:
        """Canonical-payload dict — gets serialised, hashed (full-blob SHA-256
        for V1 compat) AND uploaded to Irys. Includes derived `node_hashes` +
        `merkle_root` so a verifier can re-compute them from the same JSON.
        """
        payload: dict[str, Any] = {
            "schema_version": self.schema_version,
            "market_id": self.market_id,
            "market_source": self.market_source,
            "market_question": self.market_question,
            "horizon_days": self.horizon_days,
            "category": self.category,
            "claim": asdict(self.claim),
            "stances": [asdict(s) for s in self.stances],
            "supervisor_synthesis": asdict(self.supervisor_synthesis),
            "falsifiable_claims": [asdict(fc) for fc in self.falsifiable_claims],
            "sensitivity": [asdict(s) for s in self.sensitivity],
            "counter_arguments": [asdict(c) for c in self.counter_arguments],
            "critic_audit": asdict(self.critic_audit),
            "revision_history": [asdict(r) for r in self.revision_history],
            "model_routing": dict(self.model_routing),
            "produced_at": self.produced_at,
            "consumer_address": self.consumer_address,
            "agent_version": self.agent_version,
            "node_hashes": self.node_hashes(),
            "merkle_root": self.merkle_root_hex(),
        }
        return payload

    def full_blob_hash(self) -> str:
        """SHA-256 of the entire canonical-JSON blob — same algorithm as
        rr-trace/2's `traceHash`, kept for V1 contract compat."""
        return sha256_hex(canonical_bytes(self.to_dict()))


def hash_node(node_dict: dict[str, Any]) -> str:
    """Standalone helper — useful when verifying an isolated node without
    reconstructing a full ReasoningTraceV3."""
    return sha256_hex(canonical_bytes(node_dict))


def _bytes32(hex_str: str) -> bytes:
    """Strip the '0x' prefix and decode — for verifier code paths."""
    return bytes.fromhex(hex_str[2:] if hex_str.startswith("0x") else hex_str)


def verify_node_inclusion(node_dict: dict[str, Any], proof: list[str], root: str) -> bool:
    """Off-chain mirror of the on-chain `verifyInclusion`.

    Hash the node, fold the proof, compare to the on-chain root. Returns True
    iff the node was committed to the same Merkle root."""
    leaf = _bytes32(hash_node(node_dict))
    proof_bytes = [_bytes32(p) for p in proof]
    return merkle.verify_proof(leaf, proof_bytes, _bytes32(root))
