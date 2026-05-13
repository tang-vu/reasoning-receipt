"""Canonical reasoning-trace assembly + upload pipeline.

A trace is the *full* artifact behind a price: the question, the claim, the
sources cited (with URLs), the counter-arguments weighed, sensitivity analysis,
and the final probability + confidence. The agent canonicalizes it,
SHA-256s it, uploads to Irys, and returns the on-chain-ready tuple.

This module is pure plumbing — the actual reasoning is `agent.analyst`.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

from storage.irys import IrysClient, TraceUpload, canonical_bytes, sha256_hex


def _utcnow_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(slots=True)
class Source:
    url: str
    title: str
    cited_for: str
    accessed_at: str = field(default_factory=_utcnow_iso)


@dataclass(slots=True)
class CounterArgument:
    claim: str
    weight: float
    rebuttal: str | None = None


@dataclass(slots=True)
class SensitivityNode:
    factor: str
    delta_pp: float
    note: str | None = None


@dataclass(slots=True)
class ReasoningTrace:
    """The on-chain-committed reasoning artifact. Hash this, upload this."""

    schema_version: str
    market_id: str
    market_source: str
    market_question: str
    claim: str
    probability: float
    confidence: float
    horizon_days: int
    sources: list[Source]
    counter_arguments: list[CounterArgument]
    sensitivity: list[SensitivityNode]
    summary: str
    model: str
    produced_at: str
    consumer_address: str | None = None
    agent_version: str = "0.1.0"
    # Optional fields added with schema "rr-trace/2". When None they are NOT
    # emitted in to_dict(), so the canonical bytes (and therefore the SHA-256)
    # of any pre-existing rr-trace/1 trace stay unchanged.
    critic_review: dict[str, Any] | None = None
    revision_count: int | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "schema_version": self.schema_version,
            "market_id": self.market_id,
            "market_source": self.market_source,
            "market_question": self.market_question,
            "claim": self.claim,
            "probability": self.probability,
            "confidence": self.confidence,
            "horizon_days": self.horizon_days,
            "sources": [asdict(s) for s in self.sources],
            "counter_arguments": [asdict(c) for c in self.counter_arguments],
            "sensitivity": [asdict(s) for s in self.sensitivity],
            "summary": self.summary,
            "model": self.model,
            "produced_at": self.produced_at,
            "consumer_address": self.consumer_address,
            "agent_version": self.agent_version,
        }
        if self.critic_review is not None:
            out["critic_review"] = self.critic_review
        if self.revision_count is not None:
            out["revision_count"] = self.revision_count
        return out


@dataclass(slots=True)
class SealedTrace:
    """Output of `TraceSealer.seal` — exactly what `ChainClient.publish` needs."""

    trace: ReasoningTrace
    upload: TraceUpload

    @property
    def hash_hex(self) -> str:
        return self.upload.hash_hex

    @property
    def cid(self) -> str:
        return self.upload.cid


class TraceSealer:
    """Canonicalize → hash → upload. Stateless apart from the injected uploader."""

    SCHEMA_VERSION = "rr-trace/1"

    def __init__(self, uploader: IrysClient | None = None) -> None:
        self.uploader = uploader or IrysClient()

    def canonical_payload(self, trace: ReasoningTrace) -> dict[str, Any]:
        """The dict that gets serialized and hashed."""
        payload = trace.to_dict()
        payload["schema_version"] = self.SCHEMA_VERSION
        return payload

    def hash_only(self, trace: ReasoningTrace) -> str:
        """Hash the trace without uploading. Useful for tests."""
        return sha256_hex(canonical_bytes(self.canonical_payload(trace)))

    def seal(self, trace: ReasoningTrace) -> SealedTrace:
        """Canonical-hash + upload. Returns the on-chain tuple."""
        upload = self.uploader.upload(self.canonical_payload(trace))
        return SealedTrace(trace=trace, upload=upload)
