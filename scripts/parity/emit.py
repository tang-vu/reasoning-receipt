"""Emit the cross-language parity receipt (spec: conformance/parity/).

Every SDK emitter must produce a byte-identical canonical envelope for
this fixed semantic input — deterministic IDs, timestamps and signing
key make the whole document (signatures included) reproducible.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from protocol.receipt import ReceiptBuilder  # noqa: E402
from protocol.signatures import sign  # noqa: E402

PRIVATE_KEY = "0x" + "0123456789abcdef" * 4
SIGNED_AT = "2026-05-20T00:00:00Z"


def build() -> dict:
    receipt = (
        ReceiptBuilder(
            "parity:cross-language",
            metadata={"harness": "rr-parity/1", "unicode": "héllo wörld — 数据 ✓"},
        )
        .add("intent", "intent", {"action": "deploy", "target": "testnet"}, meta={"source": "emit"})
        .add("policy", "policy", {"limit": 100, "rules": ["r1", "r2"]})
        .add("decision", "decision", {"approved": True, "score": 0.125})
        .add("outcome", "outcome", {"status": "success", "emoji": "🧾"})
        .link("decision", "policy", "evaluated_against")
        .link("decision", "intent", "produced")
        .link("outcome", "decision", "produced")
        .finalize(receipt_id="rr-parity-0001", produced_at=SIGNED_AT)
    )
    envelope = receipt.committed_envelope()
    receipt.signatures = [
        sign(envelope, PRIVATE_KEY, scope="receipt", key_id="parity-key", signed_at=SIGNED_AT),
        sign(envelope, PRIVATE_KEY, scope="node:decision", key_id="parity-key", signed_at=SIGNED_AT),
    ]
    return receipt.to_dict()


def main() -> None:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "conformance/parity/py.receipt.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(build(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main()
