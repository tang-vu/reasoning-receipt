use reasoning_receipt::{
    canonical_string, generate_keypair, sign, verify_any, verify_proof_document, ReceiptBuilder,
};
use serde_json::json;

fn demo_receipt() -> reasoning_receipt::PortableReceipt {
    let mut b = ReceiptBuilder::new("support:refund-approval", Default::default());
    b.add("intent", "intent", json!({"refund_usd": 49}), None)
        .add("policy", "policy", json!({"limit_usd": 100}), None)
        .add("decision", "decision", json!({"approved": true}), None)
        .link("decision", "policy", "evaluated_against")
        .link("decision", "intent", "produced");
    b.finalize(Some("rr-1".into()), Some("2026-01-01T00:00:00Z".into()))
        .unwrap()
}

#[test]
fn build_verify_roundtrip() {
    let doc = demo_receipt().to_dict().unwrap();
    let report = verify_any(&doc, None);
    assert!(report.valid, "{:?}", report.errors);
    assert_eq!(report.node_count, 3);
    assert_eq!(report.edge_count, 2);
}

#[test]
fn proof_verifies() {
    let receipt = demo_receipt();
    let proof = receipt.proof_for("policy").unwrap();
    assert!(verify_proof_document(&proof));
}

#[test]
fn payload_mutation_detected() {
    let mut doc = demo_receipt().to_dict().unwrap();
    doc["nodes"][0]["payload"]["refund_usd"] = json!(50);
    let report = verify_any(&doc, None);
    assert!(!report.valid);
}

#[test]
fn signature_roundtrip() {
    let (private_key, _public) = generate_keypair();
    let committed = demo_receipt().committed_envelope().unwrap();
    let sig = sign(&committed, &private_key, "receipt", None, Some("2026-01-01T00:00:00Z"), None).unwrap();
    let mut doc = demo_receipt().to_dict().unwrap();
    doc["signatures"] = json!([sig]);
    let report = verify_any(&doc, None);
    assert!(report.valid, "{:?}", report.errors);
}

#[test]
fn canon_key_order_stable() {
    assert_eq!(
        canonical_string(&json!({"b": 1, "a": 2})).unwrap(),
        canonical_string(&json!({"a": 2, "b": 1})).unwrap()
    );
}
