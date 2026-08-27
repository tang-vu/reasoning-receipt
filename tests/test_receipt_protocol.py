from __future__ import annotations

from copy import deepcopy

import pytest

from protocol.receipt import PortableReceipt, ReceiptNode, verify_receipt, verify_receipt_proof


def _receipt() -> PortableReceipt:
    return PortableReceipt(
        receipt_id="rr-demo-1",
        produced_at="2026-08-27T00:00:00Z",
        subject="agent-action:transfer",
        metadata={"agent": "demo", "chain": "testnet"},
        nodes=[
            ReceiptNode("intent", "intent", {"action": "transfer", "amount": 5.0}),
            ReceiptNode("policy", "policy", {"max_amount": 10.0, "allowed": True}),
            ReceiptNode("outcome", "outcome", {"status": "success", "tx": "0xabc"}),
        ],
    )


def test_portable_receipt_is_order_independent() -> None:
    original = _receipt()
    reversed_receipt = PortableReceipt(
        receipt_id=original.receipt_id,
        produced_at=original.produced_at,
        subject=original.subject,
        metadata=original.metadata,
        nodes=list(reversed(original.nodes)),
    )
    assert original.node_hashes() == reversed_receipt.node_hashes()
    assert original.merkle_root_hex() == reversed_receipt.merkle_root_hex()


def test_receipt_and_each_node_proof_verify() -> None:
    receipt = _receipt()
    serialized = receipt.to_dict()
    assert verify_receipt(serialized)
    for node in receipt.nodes:
        assert verify_receipt_proof(receipt.proof_for(node.id))


def test_tampered_node_fails_standalone_proof() -> None:
    proof = _receipt().proof_for("policy").to_dict()
    proof["node"]["payload"]["max_amount"] = 1000.0
    assert not verify_receipt_proof(proof)


def test_tampered_envelope_fails_verification() -> None:
    serialized = _receipt().to_dict()
    tampered = deepcopy(serialized)
    tampered["nodes"][0]["payload"]["amount"] = 500.0
    assert not verify_receipt(tampered)


def test_duplicate_ids_and_empty_receipts_are_rejected() -> None:
    with pytest.raises(ValueError, match="at least one"):
        PortableReceipt(subject="x", nodes=[]).to_dict()
    with pytest.raises(ValueError, match="unique"):
        PortableReceipt(
            subject="x",
            nodes=[ReceiptNode("a", "fact", {}), ReceiptNode("a", "fact", {})],
        ).to_dict()
