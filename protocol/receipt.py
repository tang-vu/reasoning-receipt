"""`reasoning-receipt/1` — the portable evidence-receipt envelope.

Normative definition: `spec/REASONING-RECEIPT-1.md`. A receipt commits a
set of typed nodes and an optional edge DAG under one sorted-pair SHA-256
Merkle root. The module is pure data + bytes: no chain, model provider,
storage backend, clock authority, or network is required to build or
verify a receipt.

Terminology: "committed envelope" = the envelope minus `signatures` and the
`receipt_hash` annotation — the object `receipt_hash` is computed over.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from . import merkle
from .canon import canonical_bytes, parse_json_object
from .errors import (
    E_BAD_HASH,
    E_BAD_KIND,
    E_BAD_NODE_ID,
    E_BAD_REL,
    E_BAD_TIMESTAMP,
    E_BAD_TYPE,
    E_CYCLE,
    E_DANGLING_EDGE,
    E_DUP_EDGE,
    E_DUP_NODE_ID,
    E_EMPTY_NODES,
    E_EMPTY_RECEIPT_ID,
    E_EMPTY_SUBJECT,
    E_LIMIT,
    E_MISSING_FIELD,
    E_SELF_LOOP,
    E_UNKNOWN_FIELD,
    CanonError,
    GraphError,
    ReceiptError,
    ShapeError,
)

SCHEMA_VERSION = "reasoning-receipt/1"
CANONICALIZATION = "rr-json-1"

NODE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,127}$")
VOCAB_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

MAX_NODES = 1024
MAX_EDGES = 4096
MAX_SUBJECT = 500
MAX_RECEIPT_ID = 128
ENVELOPE_MAX_BYTES = 8 << 20  # 8 MiB

# Closed envelope. `signatures` + `receipt_hash` are uncommitted annotation
# fields — allowed at top level but excluded from the committed preimage.
ENVELOPE_FIELDS = {
    "schema_version",
    "receipt_id",
    "subject",
    "produced_at",
    "metadata",
    "nodes",
    "edges",
    "node_hashes",
    "edge_hashes",
    "merkle_root",
    "signatures",
    "receipt_hash",
}
UNCOMMITTED_FIELDS = {"signatures", "receipt_hash"}
REQUIRED_FIELDS = {
    "schema_version",
    "receipt_id",
    "subject",
    "produced_at",
    "nodes",
    "node_hashes",
    "edge_hashes",
    "merkle_root",
}
NODE_FIELDS = {"id", "kind", "payload", "meta"}
EDGE_FIELDS = {"from", "to", "rel"}

LEAF_DOMAIN_NODE = b"RR1:node\x00"
LEAF_DOMAIN_EDGE = b"RR1:edge\x00"
HASH_DOMAIN_RECEIPT = b"RR1:receipt\x00"


def _utcnow_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _check_no_controls(value: str, *, what: str, code: str) -> None:
    for ch in value:
        if ord(ch) < 0x20 or ord(ch) == 0x7F:
            raise ShapeError(f"{what} contains a control character", code=code)


def valid_timestamp(value: str) -> bool:
    if not isinstance(value, str) or not TIMESTAMP_RE.match(value):
        return False
    try:
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return False
    return True


def bytes32_hex(value: str, *, what: str = "hash") -> bytes:
    if not isinstance(value, str):
        raise ShapeError(f"{what} is not a string", code=E_BAD_HASH)
    raw = value[2:] if value.startswith("0x") else value
    try:
        decoded = bytes.fromhex(raw)
    except ValueError as exc:
        raise ShapeError(f"{what} is not hex", code=E_BAD_HASH) from exc
    if len(decoded) != 32:
        raise ShapeError(f"{what} is {len(decoded)} bytes, expected 32", code=E_BAD_HASH)
    return decoded


# ---------------------------------------------------------------- leaves


def node_leaf(node_dict: dict[str, Any]) -> bytes:
    """leaf = SHA-256("RR1:node" ‖ NUL ‖ canonical_bytes(node))."""
    return hashlib.sha256(LEAF_DOMAIN_NODE + canonical_bytes(node_dict)).digest()


def edge_leaf(edge_dict: dict[str, Any]) -> bytes:
    """leaf = SHA-256("RR1:edge" ‖ NUL ‖ canonical_bytes(edge))."""
    return hashlib.sha256(LEAF_DOMAIN_EDGE + canonical_bytes(edge_dict)).digest()


def merkle_root_of(leaves: list[bytes]) -> bytes:
    """Root over the leaf set sorted ascending by 32-byte value."""
    return merkle.merkle_root(sorted(leaves))


def receipt_hash_of(committed_envelope: dict[str, Any]) -> str:
    """"0x" ‖ sha256("RR1:receipt" ‖ NUL ‖ canonical_bytes(committed_envelope))."""
    return "0x" + hashlib.sha256(
        HASH_DOMAIN_RECEIPT + canonical_bytes(committed_envelope)
    ).hexdigest()


# ------------------------------------------------------------------ model


@dataclass(frozen=True, slots=True)
class ReceiptNode:
    """One independently provable fact in a decision/action trace."""

    id: str
    kind: str
    payload: Any
    meta: dict[str, Any] | None = None

    def validate(self) -> None:
        if not isinstance(self.id, str) or not NODE_ID_RE.match(self.id):
            raise GraphError(f"invalid node id {self.id!r}", code=E_BAD_NODE_ID)
        if not isinstance(self.kind, str) or not VOCAB_RE.match(self.kind):
            raise GraphError(f"invalid node kind {self.kind!r}", code=E_BAD_KIND)
        if self.meta is not None and not isinstance(self.meta, dict):
            raise ShapeError("node meta must be an object", code=E_BAD_TYPE)
        # Payload must be in the canonical domain — hashing is the check.
        canonical_bytes(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"id": self.id, "kind": self.kind, "payload": self.payload}
        if self.meta is not None:
            out["meta"] = self.meta
        return out


@dataclass(frozen=True, slots=True)
class ReceiptEdge:
    """A directed, typed relationship: src -rel→ dst."""

    src: str
    dst: str
    rel: str

    def validate(self) -> None:
        if not isinstance(self.src, str) or not NODE_ID_RE.match(self.src):
            raise GraphError(f"invalid edge source {self.src!r}", code=E_BAD_NODE_ID)
        if not isinstance(self.dst, str) or not NODE_ID_RE.match(self.dst):
            raise GraphError(f"invalid edge target {self.dst!r}", code=E_BAD_NODE_ID)
        if not isinstance(self.rel, str) or not VOCAB_RE.match(self.rel):
            raise GraphError(f"invalid edge rel {self.rel!r}", code=E_BAD_REL)
        if self.src == self.dst:
            raise GraphError(f"self-loop on {self.src!r}", code=E_SELF_LOOP)

    def to_dict(self) -> dict[str, Any]:
        return {"from": self.src, "to": self.dst, "rel": self.rel}


@dataclass(slots=True)
class PortableReceipt:
    """A domain-neutral commitment to the evidence behind a decision/action.

    The Merkle root is order-independent for both nodes and edges: leaves
    are always sorted by their 32-byte value before the tree is built.
    `signatures` are carried but never committed (see spec §8).
    """

    subject: str
    nodes: list[ReceiptNode]
    edges: list[ReceiptEdge] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    receipt_id: str = field(default_factory=lambda: str(uuid4()))
    produced_at: str = field(default_factory=_utcnow_iso)
    schema_version: str = SCHEMA_VERSION
    signatures: list[dict[str, Any]] = field(default_factory=list)

    # -- validation -----------------------------------------------------

    def _ordered_nodes(self) -> list[ReceiptNode]:
        if not isinstance(self.subject, str) or not self.subject.strip():
            raise ShapeError("receipt subject must not be empty", code=E_EMPTY_SUBJECT)
        if len(self.subject) > MAX_SUBJECT:
            raise ShapeError("subject too long", code=E_LIMIT)
        _check_no_controls(self.subject, what="subject", code=E_EMPTY_SUBJECT)
        if not self.nodes:
            raise ShapeError("receipt must contain at least one node", code=E_EMPTY_NODES)
        if len(self.nodes) > MAX_NODES:
            raise ShapeError("too many nodes", code=E_LIMIT)
        ids: set[str] = set()
        for node in self.nodes:
            node.validate()
            if node.id in ids:
                raise GraphError(f"duplicate node id {node.id!r}", code=E_DUP_NODE_ID)
            ids.add(node.id)
        return sorted(self.nodes, key=lambda node: node.id)

    def _ordered_edges(self) -> list[ReceiptEdge]:
        if len(self.edges) > MAX_EDGES:
            raise ShapeError("too many edges", code=E_LIMIT)
        node_ids = {node.id for node in self.nodes}
        triples: set[tuple[str, str, str]] = set()
        for edge in self.edges:
            edge.validate()
            triple = (edge.src, edge.dst, edge.rel)
            if triple in triples:
                raise GraphError(f"duplicate edge {triple!r}", code=E_DUP_EDGE)
            triples.add(triple)
            for endpoint in (edge.src, edge.dst):
                if endpoint not in node_ids:
                    raise GraphError(
                        f"edge references unknown node {endpoint!r}",
                        code=E_DANGLING_EDGE,
                    )
        ordered = sorted(self.edges, key=lambda e: (e.src, e.dst, e.rel))
        _assert_acyclic(ordered)
        return ordered

    # -- derived commitments ---------------------------------------------

    def node_dicts(self) -> list[dict[str, Any]]:
        return [node.to_dict() for node in self._ordered_nodes()]

    def edge_dicts(self) -> list[dict[str, Any]]:
        return [edge.to_dict() for edge in self._ordered_edges()]

    def leaves(self) -> list[bytes]:
        leaf_set = [node_leaf(nd) for nd in self.node_dicts()]
        leaf_set += [edge_leaf(ed) for ed in self.edge_dicts()]
        return sorted(leaf_set)

    def node_hashes(self) -> dict[str, str]:
        return {nd["id"]: "0x" + node_leaf(nd).hex() for nd in self.node_dicts()}

    def edge_hashes(self) -> list[str]:
        return ["0x" + edge_leaf(ed).hex() for ed in self.edge_dicts()]

    def merkle_root_hex(self) -> str:
        return "0x" + merkle_root_of(self.leaves()).hex()

    def committed_envelope(self) -> dict[str, Any]:
        """The object receipt_hash and receipt-scope signatures commit to."""
        if not valid_timestamp(self.produced_at):
            raise ShapeError(f"invalid produced_at {self.produced_at!r}", code=E_BAD_TIMESTAMP)
        if (
            not isinstance(self.receipt_id, str)
            or not 0 < len(self.receipt_id) <= MAX_RECEIPT_ID
        ):
            raise ShapeError("invalid receipt_id", code=E_EMPTY_RECEIPT_ID)
        _check_no_controls(self.receipt_id, what="receipt_id", code=E_EMPTY_RECEIPT_ID)
        return {
            "schema_version": self.schema_version,
            "receipt_id": self.receipt_id,
            "subject": self.subject,
            "produced_at": self.produced_at,
            "metadata": self.metadata,
            "nodes": self.node_dicts(),
            "edges": self.edge_dicts(),
            "node_hashes": self.node_hashes(),
            "edge_hashes": self.edge_hashes(),
            "merkle_root": self.merkle_root_hex(),
        }

    def to_dict(self) -> dict[str, Any]:
        envelope = self.committed_envelope()
        if self.signatures:
            envelope["signatures"] = list(self.signatures)
        envelope["receipt_hash"] = self.receipt_hash()
        return envelope

    def receipt_hash(self) -> str:
        return receipt_hash_of(self.committed_envelope())

    def canonical_bytes(self) -> bytes:
        return canonical_bytes(self.committed_envelope())

    # -- proofs -----------------------------------------------------------

    def proof_for(self, node_id: str) -> dict[str, Any]:
        """Inclusion proof document for one node (spec §12)."""
        ordered = self.node_dicts()
        ids = [nd["id"] for nd in ordered]
        if node_id not in ids:
            raise KeyError(f"node {node_id!r} not in receipt")
        leaves = self.leaves()
        leaf = node_leaf(ordered[ids.index(node_id)])
        index = leaves.index(leaf)
        return {
            "schema_version": self.schema_version,
            "item_type": "node",
            "item": ordered[ids.index(node_id)],
            "leaf": "0x" + leaf.hex(),
            "merkle_root": "0x" + merkle.merkle_root(leaves).hex(),
            "proof": ["0x" + sib.hex() for sib in merkle.merkle_proof(leaves, index)],
        }

    def proof_for_edge(self, index: int) -> dict[str, Any]:
        """Inclusion proof for the edge at `index` in canonical edge order."""
        edge_dicts = self.edge_dicts()
        if index < 0 or index >= len(edge_dicts):
            raise IndexError(f"edge index {index} out of range")
        leaves = self.leaves()
        leaf = edge_leaf(edge_dicts[index])
        leaf_index = leaves.index(leaf)
        return {
            "schema_version": self.schema_version,
            "item_type": "edge",
            "item": edge_dicts[index],
            "leaf": "0x" + leaf.hex(),
            "merkle_root": "0x" + merkle.merkle_root(leaves).hex(),
            "proof": ["0x" + sib.hex() for sib in merkle.merkle_proof(leaves, leaf_index)],
        }


def _assert_acyclic(edges: list[ReceiptEdge]) -> None:
    """DFS three-color cycle check. Raises GraphError(code=cycle)."""
    adjacency: dict[str, list[str]] = {}
    for edge in edges:
        adjacency.setdefault(edge.src, []).append(edge.dst)
    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = {}
    for start in adjacency:
        if color.get(start, WHITE) != WHITE:
            continue
        stack = [(start, iter(adjacency.get(start, [])))]
        color[start] = GRAY
        while stack:
            node, it = stack[-1]
            advanced = False
            for nxt in it:
                state = color.get(nxt, WHITE)
                if state == GRAY:
                    raise GraphError(
                        f"cycle detected via edge {node!r} -> {nxt!r}", code=E_CYCLE
                    )
                if state == WHITE:
                    color[nxt] = GRAY
                    stack.append((nxt, iter(adjacency.get(nxt, []))))
                    advanced = True
                    break
            if not advanced:
                color[node] = BLACK
                stack.pop()


# ---------------------------------------------------------------- builder


class ReceiptBuilder:
    """Ergonomic accumulator: add nodes, link edges, finalize.

    ```python
    receipt = (
        ReceiptBuilder("support:refund-approval", metadata={"workflow": "cs"})
        .add("intent", "intent", {"refund_usd": 49})
        .add("policy", "policy", {"limit_usd": 100})
        .add("decision", "decision", {"approved": True})
        .link("decision", "policy", "evaluated_against")
        .link("decision", "intent", "produced")
        .finalize(receipt_id="rr-1")
    )
    ```
    """

    def __init__(self, subject: str, *, metadata: dict[str, Any] | None = None) -> None:
        self.subject = subject
        self.metadata = metadata or {}
        self._nodes: list[ReceiptNode] = []
        self._edges: list[ReceiptEdge] = []

    def add(
        self,
        node_id: str,
        kind: str,
        payload: Any,
        meta: dict[str, Any] | None = None,
    ) -> ReceiptBuilder:
        self._nodes.append(ReceiptNode(id=node_id, kind=kind, payload=payload, meta=meta))
        return self

    def link(self, src: str, dst: str, rel: str) -> ReceiptBuilder:
        self._edges.append(ReceiptEdge(src=src, dst=dst, rel=rel))
        return self

    def finalize(
        self,
        *,
        receipt_id: str | None = None,
        produced_at: str | None = None,
    ) -> PortableReceipt:
        kwargs: dict[str, Any] = {}
        if receipt_id is not None:
            kwargs["receipt_id"] = receipt_id
        if produced_at is not None:
            kwargs["produced_at"] = produced_at
        receipt = PortableReceipt(
            subject=self.subject,
            metadata=self.metadata,
            nodes=self._nodes,
            edges=self._edges,
            **kwargs,
        )
        receipt.to_dict()  # forces full validation now
        return receipt


# ---------------------------------------------------------------- reports


@dataclass(slots=True)
class VerifyReport:
    """Structured verification outcome — spec §10.

    `valid` covers structural + commitment checks only; signature outcomes
    are reported per-signature so callers decide whether a signature is
    required for their context.
    """

    valid: bool
    schema_version: str
    canonicalization: str
    variant: str
    checks: dict[str, bool]
    errors: list[str]
    signatures: list[dict[str, Any]] = field(default_factory=list)
    receipt_hash: str | None = None
    merkle_root: str | None = None
    node_count: int = 0
    edge_count: int = 0

    def __bool__(self) -> bool:
        return self.valid

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "schema_version": self.schema_version,
            "canonicalization": self.canonicalization,
            "variant": self.variant,
            "checks": self.checks,
            "errors": self.errors,
            "signatures": self.signatures,
            "receipt_hash": self.receipt_hash,
            "merkle_root": self.merkle_root,
            "node_count": self.node_count,
            "edge_count": self.edge_count,
        }


# ---------------------------------------------------------------- restore


def _require(cond: bool, message: str, code: str) -> None:
    if not cond:
        raise ShapeError(message, code=code)


def restore_receipt(document: dict[str, Any]) -> PortableReceipt:
    """Validate envelope shape + graph, return a PortableReceipt.

    Raises ReceiptError subclass with a stable `.code` on any violation.
    Does NOT check derived commitments — that is verify_receipt's job.
    """
    if not isinstance(document, dict):
        raise ShapeError("receipt document is not an object", code=E_BAD_TYPE)

    unknown = set(document) - ENVELOPE_FIELDS
    if unknown:
        raise ShapeError(f"unknown top-level fields {sorted(unknown)}", code=E_UNKNOWN_FIELD)
    for required in sorted(REQUIRED_FIELDS):
        if required not in document:
            raise ShapeError(f"missing field {required!r}", code=E_MISSING_FIELD)

    if document.get("schema_version") != SCHEMA_VERSION:
        from .errors import E_BAD_SCHEMA, SchemaError

        raise SchemaError(
            f"unsupported schema_version {document.get('schema_version')!r}",
            code=E_BAD_SCHEMA,
        )

    receipt_id = document["receipt_id"]
    _require(
        isinstance(receipt_id, str) and 0 < len(receipt_id) <= MAX_RECEIPT_ID,
        "invalid receipt_id",
        E_EMPTY_RECEIPT_ID,
    )
    _check_no_controls(receipt_id, what="receipt_id", code=E_EMPTY_RECEIPT_ID)

    produced_at = document["produced_at"]
    if not valid_timestamp(produced_at):
        raise ShapeError(f"invalid produced_at {produced_at!r}", code=E_BAD_TIMESTAMP)

    metadata = document.get("metadata", {})
    _require(isinstance(metadata, dict), "metadata must be an object", E_BAD_TYPE)

    raw_nodes = document["nodes"]
    _require(isinstance(raw_nodes, list), "nodes must be an array", E_BAD_TYPE)
    nodes: list[ReceiptNode] = []
    for raw in raw_nodes:
        _require(isinstance(raw, dict), "node is not an object", E_BAD_TYPE)
        extra = set(raw) - NODE_FIELDS
        if extra:
            raise ShapeError(f"unknown node fields {sorted(extra)}", code=E_UNKNOWN_FIELD)
        for needed in ("id", "kind", "payload"):
            if needed not in raw:
                raise ShapeError(f"node missing {needed!r}", code=E_MISSING_FIELD)
        nodes.append(
            ReceiptNode(id=raw["id"], kind=raw["kind"], payload=raw["payload"], meta=raw.get("meta"))
        )

    raw_edges = document.get("edges", [])
    _require(isinstance(raw_edges, list), "edges must be an array", E_BAD_TYPE)
    edges: list[ReceiptEdge] = []
    for raw in raw_edges:
        _require(isinstance(raw, dict), "edge is not an object", E_BAD_TYPE)
        if set(raw) != EDGE_FIELDS:
            raise ShapeError(
                f"edge must have exactly {sorted(EDGE_FIELDS)}", code=E_UNKNOWN_FIELD
            )
        edges.append(ReceiptEdge(src=raw["from"], dst=raw["to"], rel=raw["rel"]))

    _require(
        isinstance(document["node_hashes"], dict), "node_hashes must be an object", E_BAD_TYPE
    )
    _require(
        isinstance(document["edge_hashes"], list), "edge_hashes must be an array", E_BAD_TYPE
    )
    for value in list(document["node_hashes"].values()) + list(document["edge_hashes"]):
        bytes32_hex(value, what="leaf hash")
    bytes32_hex(document["merkle_root"], what="merkle_root")

    signatures = document.get("signatures", [])
    _require(isinstance(signatures, list), "signatures must be an array", E_BAD_TYPE)

    try:
        canonical_bytes(document)
    except CanonError:
        raise
    if len(canonical_bytes(document)) > ENVELOPE_MAX_BYTES:
        raise ShapeError("envelope exceeds 8 MiB", code=E_LIMIT)

    return PortableReceipt(
        receipt_id=receipt_id,
        subject=document["subject"],
        produced_at=produced_at,
        metadata=metadata,
        nodes=nodes,
        edges=edges,
        signatures=signatures,
    )


def verify_receipt(document: dict[str, Any]) -> VerifyReport:
    """Full §10 verification: shape → graph → hashes → root.

    Returns a VerifyReport; truthy iff valid. Signature checks are reported
    separately inside the report.
    """
    checks: dict[str, bool] = {}
    errors: list[str] = []
    try:
        receipt = restore_receipt(document)
        checks["shape"] = True
    except ReceiptError as exc:
        checks["shape"] = False
        errors.append(f"{exc.code}: {exc}")
        return VerifyReport(
            valid=False,
            schema_version=str(document.get("schema_version", "unknown"))
            if isinstance(document, dict)
            else "unknown",
            canonicalization=CANONICALIZATION,
            variant="final",
            checks=checks,
            errors=errors,
        )

    try:
        expected = receipt.committed_envelope()
        checks["graph"] = True
    except ReceiptError as exc:
        checks["graph"] = False
        errors.append(f"{exc.code}: {exc}")
        return VerifyReport(
            valid=False,
            schema_version=SCHEMA_VERSION,
            canonicalization=CANONICALIZATION,
            variant="final",
            checks=checks,
            errors=errors,
        )
    checks["hashes"] = (
        expected["node_hashes"] == document["node_hashes"]
        and expected["edge_hashes"] == document["edge_hashes"]
    )
    if not checks["hashes"]:
        errors.append("hash_mismatch: node_hashes or edge_hashes do not match recomputed leaves")
    checks["root"] = expected["merkle_root"] == document["merkle_root"]
    if not checks["root"]:
        errors.append("root_mismatch: merkle_root does not match recomputed leaf set")

    if "receipt_hash" in document:
        recomputed = receipt.receipt_hash()
        checks["receipt_hash"] = recomputed == document["receipt_hash"]
        if not checks["receipt_hash"]:
            errors.append("hash_mismatch: receipt_hash annotation does not match")

    sig_results: list[dict[str, Any]] = []
    from .signatures import verify_signatures

    try:
        sig_results = verify_signatures(expected, document.get("signatures") or [])
        checks["signatures"] = all(r["valid"] for r in sig_results)
    except ReceiptError as exc:
        checks["signatures"] = False
        errors.append(f"{exc.code}: {exc}")

    valid = all(checks.values())
    return VerifyReport(
        valid=valid,
        schema_version=SCHEMA_VERSION,
        canonicalization=CANONICALIZATION,
        variant="final",
        checks=checks,
        errors=errors,
        signatures=sig_results,
        receipt_hash=receipt.receipt_hash(),
        merkle_root=document["merkle_root"],
        node_count=len(receipt.nodes),
        edge_count=len(receipt.edges),
    )


def verify_proof_document(proof_doc: dict[str, Any]) -> bool:
    """Verify a §12 inclusion proof without trusting the producer."""
    try:
        item = proof_doc["item"]
        item_type = proof_doc["item_type"]
        expected_leaf = bytes32_hex(proof_doc["leaf"], what="leaf")
        if item_type == "node":
            ReceiptNode(
                id=item["id"], kind=item["kind"], payload=item["payload"], meta=item.get("meta")
            ).validate()
            actual_leaf = node_leaf(item)
        elif item_type == "edge":
            ReceiptEdge(src=item["from"], dst=item["to"], rel=item["rel"]).validate()
            actual_leaf = edge_leaf(item)
        else:
            return False
        if actual_leaf != expected_leaf:
            return False
        siblings = [bytes32_hex(p, what="proof element") for p in proof_doc["proof"]]
        return merkle.verify_proof(
            actual_leaf, siblings, bytes32_hex(proof_doc["merkle_root"], what="root")
        )
    except (KeyError, TypeError, ReceiptError):
        return False


def verify_receipt_proof(proof: dict[str, Any]) -> bool:
    """Back-compat alias for verify_proof_document."""
    return verify_proof_document(proof)


def load_receipt(source: str | bytes | dict[str, Any]) -> dict[str, Any]:
    """Accept a file path, JSON text, or dict; return the parsed document."""
    if isinstance(source, dict):
        return source
    if isinstance(source, bytes):
        return parse_json_object(source)
    from pathlib import Path

    path = Path(source)
    if path.exists():
        return parse_json_object(path.read_bytes())
    return parse_json_object(source)


def dumps(document: dict[str, Any], *, pretty: bool = True) -> str:
    """Serialize a receipt for display/storage (key order preserved)."""
    return json.dumps(document, indent=2 if pretty else None, ensure_ascii=False)
