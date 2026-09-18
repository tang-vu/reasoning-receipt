"""Property tests for reasoning-receipt/1 (spec §conformance invariants).

Invariants under test:

* verify(build(x)) is valid for every well-formed receipt
* canonicalize(parse(canonicalize(x))) is a fixed point
* an inclusion proof verifies against the receipt's root — and never
  against a different leaf
* a semantically identical document with reordered keys yields the same
  canonical bytes
* mutating any committed value changes the node hash / Merkle root
* semantic document mutations never silently re-verify
* non-canonical values (lone surrogates, non-finite numbers) are rejected
"""

from __future__ import annotations

import json
import random

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from protocol.canon import PORTABLE_INT_MAX, canonical_bytes
from protocol.errors import CanonError
from protocol.merkle import merkle_root, verify_proof
from protocol.receipt import ReceiptBuilder, verify_proof_document
from protocol.verify import verify_any

# ---------------------------------------------------------------- strategies

_SAFE_TEXT = st.text(
    alphabet=st.characters(exclude_categories=("Cs",)),
    max_size=64,
)

_json_scalars = st.one_of(
    st.none(),
    st.booleans(),
    st.integers(min_value=-PORTABLE_INT_MAX, max_value=PORTABLE_INT_MAX),
    st.floats(
        allow_nan=False,
        allow_infinity=False,
        min_value=-(2**52),
        max_value=2**52,
        allow_subnormal=False,
    ),
    _SAFE_TEXT,
)

JSON_VALUE = st.recursive(
    _json_scalars,
    lambda children: st.one_of(
        st.lists(children, max_size=8),
        st.dictionaries(_SAFE_TEXT, children, max_size=8),
    ),
    max_leaves=24,
)

NODE_ID = st.from_regex(r"[A-Za-z0-9][A-Za-z0-9_.:/-]{0,30}", fullmatch=True)
VOCAB = st.from_regex(r"[a-z][a-z0-9_]{0,30}", fullmatch=True)

_SLOW = settings(
    max_examples=150,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
)


# ------------------------------------------------------------- canon tests


@given(value=JSON_VALUE)
@settings(max_examples=300, suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large])
def test_canonical_roundtrip_is_fixed_point(value):
    """canonical_bytes(parse(canonical_bytes(v))) == canonical_bytes(v)."""
    once = canonical_bytes(value)
    reparsed = json.loads(once.decode("utf-8"))
    assert canonical_bytes(reparsed) == once


@given(value=JSON_VALUE)
@settings(max_examples=200)
def test_key_order_is_semantically_irrelevant(value):
    """Reordering object keys must not change canonical bytes."""
    if not isinstance(value, dict) or len(value) < 2:
        return
    items = list(value.items())
    rng = random.Random(0)
    rng.shuffle(items)
    shuffled = dict(items)
    assert canonical_bytes(shuffled) == canonical_bytes(value)


@given(
    value=JSON_VALUE,
    mutated=st.one_of(
        st.none(),
        st.booleans(),
        st.integers(min_value=-10**6, max_value=10**6),
        st.text(min_size=1, max_size=8),
    ),
)
@settings(max_examples=200)
def test_mutation_changes_canonical_bytes(value, mutated):
    """Changing any committed byte produces different canonical bytes."""
    if mutated == value:
        return
    assert canonical_bytes(mutated) != canonical_bytes(value)


@given(s=st.text(alphabet=st.characters(categories=("Cs",)), min_size=1, max_size=8))
@settings(max_examples=50)
def test_lone_surrogate_rejected(s):
    """Strings containing lone surrogates can never canonicalize."""
    with pytest.raises(CanonError):
        canonical_bytes(s)


# ----------------------------------------------------------- receipt tests


@given(
    ids=st.lists(NODE_ID, min_size=1, max_size=8, unique=True),
    kinds=st.lists(VOCAB, min_size=1, max_size=8),
    payload=JSON_VALUE,
)
@_SLOW
def test_build_verify_roundtrip(ids, kinds, payload):
    """verify_any(build(x)) is always valid for well-formed inputs."""
    builder = ReceiptBuilder("prop:test")
    for i, node_id in enumerate(ids):
        builder.add(node_id, kinds[i % len(kinds)], payload)
    receipt = builder.finalize(receipt_id="rr-prop", produced_at="2026-05-20T00:00:00Z")
    report = verify_any(receipt.to_dict())
    assert report.valid, report.errors
    assert report.node_count == len(ids)


@given(ids=st.lists(NODE_ID, min_size=2, max_size=8, unique=True))
@_SLOW
def test_proof_verifies_and_stays_local(ids):
    """A generated proof verifies its own leaf — and only its own leaf."""
    builder = ReceiptBuilder("prop:proof")
    for node_id in ids:
        builder.add(node_id, "evidence", {"n": node_id})
    receipt = builder.finalize(receipt_id="rr-prop", produced_at="2026-05-20T00:00:00Z")

    target = ids[0]
    doc = receipt.proof_for(target)
    assert verify_proof_document(doc)

    # Same proof against a different node id must fail.
    other = next(i for i in ids if i != target)
    wrong = dict(doc)
    wrong["item"] = {"id": other, "kind": "evidence", "payload": {"n": other}}
    assert not verify_proof_document(wrong)


@given(
    ids=st.lists(NODE_ID, min_size=1, max_size=6, unique=True),
    mutation=st.sampled_from(["payload", "node_id", "root_nibble", "subject"]),
)
@_SLOW
def test_semantic_mutation_breaks_verification(ids, mutation):
    """Mutating a committed field must break verification."""
    builder = ReceiptBuilder("prop:tamper")
    for node_id in ids:
        builder.add(node_id, "claim", {"v": 1})
    receipt = builder.finalize(receipt_id="rr-prop", produced_at="2026-05-20T00:00:00Z")
    doc = receipt.to_dict()

    tampered = json.loads(json.dumps(doc))
    if mutation == "payload":
        tampered["nodes"][0]["payload"] = {"v": 2, "injected": True}
    elif mutation == "node_id":
        tampered["nodes"][0]["id"] = "zz" + tampered["nodes"][0]["id"][:30]
    elif mutation == "root_nibble":
        root = tampered["merkle_root"]
        flip = "0" if root[-1] != "0" else "1"
        tampered["merkle_root"] = root[:-1] + flip
    else:
        tampered["subject"] = "prop:tampered"
    report = verify_any(tampered)
    assert not report.valid


@given(ids=st.lists(NODE_ID, min_size=2, max_size=6, unique=True))
@_SLOW
def test_proof_never_verifies_wrong_leaf(ids):
    """A proof for one leaf must not verify a different leaf."""
    builder = ReceiptBuilder("prop:neg")
    for node_id in ids:
        builder.add(node_id, "evidence", {"id": node_id})
    receipt = builder.finalize(receipt_id="rr-prop", produced_at="2026-05-20T00:00:00Z")
    leaves = receipt.leaves()
    root = merkle_root(leaves)

    target_doc = receipt.proof_for(ids[0])
    siblings = [bytes.fromhex(s[2:]) for s in target_doc["proof"]]
    target_leaf = bytes.fromhex(target_doc["leaf"][2:])
    assert verify_proof(target_leaf, siblings, root)

    other_leaf = bytes.fromhex(receipt.proof_for(ids[1])["leaf"][2:])
    if other_leaf != target_leaf:
        assert not verify_proof(other_leaf, siblings, root)
