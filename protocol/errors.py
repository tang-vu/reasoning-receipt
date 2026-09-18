"""Protocol error types with stable machine-readable codes.

Every rejection a verifier can produce carries a `.code` from the catalog
below. Conformance vectors assert on these codes, so they are part of the
protocol contract — rename cautiously.
"""

from __future__ import annotations


class ReceiptError(ValueError):
    """Base class. `.code` is the stable machine-readable reason."""

    code = "receipt_error"

    def __init__(self, message: str | None = None, *, code: str | None = None) -> None:
        super().__init__(message or self.code)
        if code is not None:
            self.code = code


class CanonError(ReceiptError):
    """Input is outside the canonical-JSON domain (§7.1)."""

    code = "noncanonical_value"


class ShapeError(ReceiptError):
    """Envelope/node/edge structure violates the schema."""

    code = "invalid_shape"


class GraphError(ReceiptError):
    """Node-id / edge / DAG violations."""

    code = "invalid_graph"


class SchemaError(ReceiptError):
    """Unsupported or missing schema_version."""

    code = "unsupported_schema"


class SignatureError(ReceiptError):
    """Malformed signature object (a *failed* signature is not an error)."""

    code = "invalid_signature"


# --- Stable error codes used across implementations (negative vectors) ---

E_MISSING_FIELD = "missing_field"
E_UNKNOWN_FIELD = "unknown_field"
E_BAD_TYPE = "bad_type"
E_BAD_SCHEMA = "unsupported_schema"
E_BAD_NODE_ID = "invalid_node_id"
E_BAD_KIND = "invalid_kind"
E_BAD_REL = "invalid_rel"
E_BAD_TIMESTAMP = "invalid_timestamp"
E_EMPTY_SUBJECT = "empty_subject"
E_EMPTY_RECEIPT_ID = "empty_receipt_id"
E_EMPTY_NODES = "empty_nodes"
E_DUP_NODE_ID = "duplicate_node_id"
E_DUP_EDGE = "duplicate_edge"
E_DANGLING_EDGE = "dangling_edge"
E_SELF_LOOP = "self_loop"
E_CYCLE = "cycle"
E_HASH_MISMATCH = "hash_mismatch"
E_ROOT_MISMATCH = "root_mismatch"
E_BAD_HASH = "malformed_hash"
E_NONCANONICAL = "noncanonical_value"
E_LIMIT = "limit_exceeded"
E_BAD_SIGNATURE = "invalid_signature"
E_BAD_PROOF = "invalid_proof"
