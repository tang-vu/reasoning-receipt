import { describe, expect, it } from "vitest";
import {
  ReceiptBuilder,
  generateKeypair,
  sign,
  verifyAny,
  verifyProofDocument,
  canonicalString,
} from "../src/index.js";

function demoReceipt() {
  return new ReceiptBuilder("support:refund-approval", { workflow: "cs" })
    .add("intent", "intent", { refund_usd: 49 })
    .add("policy", "policy", { limit_usd: 100 })
    .add("decision", "decision", { approved: true })
    .link("decision", "policy", "evaluated_against")
    .link("decision", "intent", "produced")
    .finalize({ receipt_id: "rr-1", produced_at: "2026-01-01T00:00:00Z" });
}

describe("ReceiptBuilder", () => {
  it("build → verify round-trip", () => {
    const doc = demoReceipt().toDict();
    const report = verifyAny(doc);
    expect(report.valid).toBe(true);
    expect(report.schema_version).toBe("reasoning-receipt/1");
    expect(report.variant).toBe("final");
    expect(report.node_count).toBe(3);
    expect(report.edge_count).toBe(2);
  });

  it("node-order insensitivity: same content, same root", () => {
    const a = demoReceipt().toDict();
    const b = new ReceiptBuilder("support:refund-approval", { workflow: "cs" })
      .add("decision", "decision", { approved: true })
      .add("intent", "intent", { refund_usd: 49 })
      .add("policy", "policy", { limit_usd: 100 })
      .link("decision", "intent", "produced")
      .link("decision", "policy", "evaluated_against")
      .finalize({ receipt_id: "rr-1", produced_at: "2026-01-01T00:00:00Z" })
      .toDict();
    expect(b.merkle_root).toBe(a.merkle_root);
    expect(b.receipt_hash).toBe(a.receipt_hash);
  });

  it("payload mutation changes the commitment", () => {
    const doc = demoReceipt().toDict() as Record<string, unknown>;
    (doc.nodes as { payload: Record<string, unknown> }[])[0].payload.refund_usd = 50;
    const report = verifyAny(doc);
    expect(report.valid).toBe(false);
    expect(report.checks.hashes).toBe(false);
  });

  it("proof for a node verifies standalone", () => {
    const receipt = demoReceipt();
    const proof = receipt.proofFor("policy");
    expect(verifyProofDocument(proof)).toBe(true);
    const tampered = { ...proof, leaf: proof.proof[0] ?? proof.leaf };
    if (tampered.leaf !== proof.leaf) {
      expect(verifyProofDocument(tampered)).toBe(false);
    }
  });

  it("ed25519 sign/verify round-trip, deterministic", () => {
    const { private_key } = generateKeypair();
    const committed = demoReceipt().committedEnvelope();
    const sig = sign(committed, private_key, { scope: "receipt", signed_at: "2026-01-01T00:00:00Z" });
    const doc = demoReceipt().toDict();
    doc.signatures = [sig as never];
    const report = verifyAny(doc);
    expect(report.checks.signatures).toBe(true);
    expect(report.signatures[0].valid).toBe(true);
  });
});

describe("canonicalization", () => {
  it("is stable across object key order", () => {
    expect(canonicalString({ b: 1, a: 2 })).toBe(canonicalString({ a: 2, b: 1 }));
  });
});
