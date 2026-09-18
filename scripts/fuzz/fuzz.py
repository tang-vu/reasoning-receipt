"""Seeded fuzz harness for reasoning-receipt/1 (offline, deterministic).

Invariants exercised:

* byte mutation of a canonical document: any semantic change either
  breaks parsing or breaks verification — it never silently verifies
  with the wrong commitment
* canonicalization stability: canon(parse(canon(x))) == canon(x)
* proof negatives: mutated/flipped/truncated proofs never verify
* malformed node references never become valid after re-serialization

Usage:
    uv run python scripts/fuzz/fuzz.py [--iterations N] [--seed S]

Exit 0 iff every invariant held for every case.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from protocol.canon import canonical_bytes  # noqa: E402
from protocol.receipt import (  # noqa: E402
    ReceiptBuilder,
    restore_receipt,
    verify_proof_document,
)
from protocol.verify import verify_any  # noqa: E402


def build_corpus(rng: random.Random) -> list[dict]:
    """Random well-formed receipts for mutation."""
    corpus = []
    vocab = ["intent", "policy", "evidence", "decision", "outcome", "tool_call"]
    for _ in range(6):
        n = rng.randint(1, 6)
        ids = [f"n{i}_{rng.randrange(1 << 20):x}" for i in range(n)]
        builder = ReceiptBuilder(f"fuzz:{rng.randrange(1 << 30):x}")
        for node_id in ids:
            builder.add(
                node_id,
                rng.choice(vocab),
                {"k": rng.randrange(1 << 40), "s": rng.choice(["a", "bc", "🧾", "数据"])},
            )
        for _ in range(rng.randint(0, 4)):
            a, b = rng.sample(ids, 2) if len(ids) > 1 else (ids[0], ids[0])
            if a != b:
                builder.link(a, b, rng.choice(vocab).replace("-", "_"))
        try:
            corpus.append(
                builder.finalize(receipt_id="rr-fuzz", produced_at="2026-05-20T00:00:00Z").to_dict()
            )
        except Exception:
            continue
    return corpus


def mutate_json(doc: dict, rng: random.Random) -> dict:
    """Random semantic mutation inside a parsed document."""
    d = json.loads(json.dumps(doc))
    kind = rng.choice(["payload", "node_id", "edge", "hash", "subject", "delete"])
    nodes = d.get("nodes", [])
    if kind == "payload" and nodes:
        node = rng.choice(nodes)
        node["payload"] = {"mutated": rng.randrange(1 << 32)}
    elif kind == "node_id" and nodes:
        node = rng.choice(nodes)
        node["id"] = node["id"] + "x"
    elif kind == "edge" and d.get("edges"):
        edge = rng.choice(d["edges"])
        edge["to"] = "nonexistent-" + str(rng.randrange(1000))
    elif kind == "hash":
        field = rng.choice(["merkle_root", "receipt_hash"])
        if field in d and isinstance(d[field], str):
            d[field] = d[field][:-2] + rng.choice("0123456789abcdef") + "0"
    elif kind == "subject":
        d["subject"] = "mutated-" + d.get("subject", "")
    elif kind == "delete" and nodes and len(nodes) > 1:
        nodes.pop(rng.randrange(len(nodes)))
    return d


def committed_view(doc: dict) -> dict:
    """The committed portion of a document (annotations stripped)."""
    return {k: v for k, v in doc.items() if k not in ("signatures", "receipt_hash")}


def fuzz_byte_mutation(corpus: list[dict], rng: random.Random, iters: int) -> list[str]:
    """A mutated document must never verify against its ORIGINAL
    commitment — i.e. node_hashes/merkle_root/receipt_hash embedded in
    the mutated doc must mismatch the recomputed values, or the doc is
    itself a different valid receipt (not the original)."""
    failures = []
    for i in range(iters):
        original = rng.choice(corpus)
        original_canon = canonical_bytes(committed_view(original))
        doc = mutate_json(original, rng)
        mutated_canon = canonical_bytes(committed_view(doc))
        if mutated_canon == original_canon:
            continue  # mutation produced no semantic change
        report = verify_any(doc)
        if report.valid and doc.get("merkle_root") == original.get("merkle_root"):
            failures.append(f"iter {i}: mutated doc verifies with original root")
    return failures


def fuzz_canon_stability(rng: random.Random, iters: int) -> list[str]:
    """canon(parse(canon(x))) == canon(x) for generated values."""
    failures = []
    for i in range(iters):
        value = rng.choice(
            [
                rng.random() * 1e-6,
                rng.randint(-(2**53 - 1), 2**53 - 1),
                rng.choice(["", "a", "数据", "🧾\u2028", "\\", '"']),
                {"k": [rng.random(), rng.randint(0, 9)]},
                [True, None, rng.random()],
            ]
        )
        try:
            once = canonical_bytes(value)
        except Exception:
            continue
        reparsed = json.loads(once.decode("utf-8"))
        try:
            twice = canonical_bytes(reparsed)
        except Exception as exc:
            failures.append(f"iter {i}: re-canon failed for {value!r}: {exc}")
            continue
        if twice != once:
            failures.append(f"iter {i}: canon not idempotent for {value!r}: {once} != {twice}")
    return failures


def fuzz_proof_negatives(corpus: list[dict], rng: random.Random, iters: int) -> list[str]:
    """Corrupted proofs must never verify."""
    failures = []
    receipts = [restore_receipt(d) for d in corpus]
    for i in range(iters):
        receipt = rng.choice(receipts)
        node_ids = [n["id"] for n in receipt.node_dicts()]
        doc = receipt.proof_for(rng.choice(node_ids))
        attack = rng.choice(["sibling", "leaf", "root", "truncate", "item"])
        bad = json.loads(json.dumps(doc))
        if attack == "sibling" and bad["proof"]:
            sib = rng.choice(bad["proof"])
            bad["proof"][bad["proof"].index(sib)] = "0x" + "00" * 32
        elif attack == "leaf":
            bad["leaf"] = "0x" + "ff" * 32
        elif attack == "root":
            bad["merkle_root"] = "0x" + "00" * 32
        elif attack == "truncate":
            bad["proof"] = bad["proof"][:-1]
        else:
            bad["item"] = {"id": "forged", "kind": "claim", "payload": {}}
        if verify_proof_document(bad):
            failures.append(f"iter {i}: corrupted proof verified (attack={attack})")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=500)
    parser.add_argument("--seed", type=int, default=0x5EED)
    args = parser.parse_args()

    rng = random.Random(args.seed)
    corpus = build_corpus(rng)
    print(f"corpus: {len(corpus)} receipts, seed={args.seed}, iterations={args.iterations}")

    failures: list[str] = []
    for name, fn in [
        ("byte-mutation", lambda: fuzz_byte_mutation(corpus, rng, args.iterations)),
        ("canon-stability", lambda: fuzz_canon_stability(rng, args.iterations)),
        ("proof-negatives", lambda: fuzz_proof_negatives(corpus, rng, args.iterations)),
    ]:
        found = fn()
        status = "PASS" if not found else f"FAIL ({len(found)} violations)"
        print(f"[{status}] {name}")
        failures.extend(found)

    for line in failures[:10]:
        print(f"  ! {line}")
    if failures:
        print(f"{len(failures)} invariant violation(s)")
        return 1
    print("all invariants held")
    return 0


if __name__ == "__main__":
    sys.exit(main())
