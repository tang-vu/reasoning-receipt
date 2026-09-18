//! Conformance corpus runner — executes `conformance/vectors/*.json`.
//! Mirrors `protocol/conformance.py`; the same vector files drive every
//! SDK's conformance suite.

use crate::canon::canonical_string;
use crate::errors::{ReceiptError, E_NONCANONICAL};
use crate::receipt::{
    verify_proof_document, PortableReceipt, ReceiptEdge, ReceiptNode,
};
use crate::signatures::{sign, verify_signatures};
use crate::verify::verify_any;
use serde_json::{json, Map, Value};
use std::fs;
use std::path::Path;

const TAG: &str = "$rr";

/// Tagged inputs (`{"$rr": "…"}`) express values JSON literals can't.
/// serde_json::Value cannot hold non-finite floats, so nan/inf tags are
/// rejected here with `noncanonical_value` — the same code Python's
/// canonicalizer emits one stage later when it sees the real float.
fn untag(v: &Value) -> Result<Value, ReceiptError> {
    match v {
        Value::Object(o) if o.len() == 1 && o.contains_key(TAG) => match o[TAG].as_str() {
            Some("nan") | Some("+inf") | Some("-inf") => Err(ReceiptError::new(
                E_NONCANONICAL,
                "non-finite number is not portable",
            )),
            Some("-0") => Ok(json!(-0.0f64)),
            other => panic!("unknown tag {other:?}"),
        },
        Value::Object(o) => o
            .iter()
            .map(|(k, v)| untag(v).map(|u| (k.clone(), u)))
            .collect::<Result<Map<String, Value>, _>>()
            .map(Value::Object),
        Value::Array(a) => a
            .iter()
            .map(untag)
            .collect::<Result<Vec<Value>, _>>()
            .map(Value::Array),
        _ => Ok(v.clone()),
    }
}

fn build(spec: &Value) -> PortableReceipt {
    let nodes: Vec<ReceiptNode> = spec
        .get("nodes")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default()
        .iter()
        .map(|n| ReceiptNode {
            id: n["id"].as_str().unwrap_or_default().to_string(),
            kind: n["kind"].as_str().unwrap_or_default().to_string(),
            payload: untag(n.get("payload").unwrap_or(&Value::Null))
                .unwrap_or(Value::Null),
            meta: n.get("meta").cloned(),
        })
        .collect();
    let edges: Vec<ReceiptEdge> = spec
        .get("edges")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default()
        .iter()
        .map(|e| ReceiptEdge {
            src: e["from"].as_str().unwrap_or_default().to_string(),
            dst: e["to"].as_str().unwrap_or_default().to_string(),
            rel: e["rel"].as_str().unwrap_or_default().to_string(),
        })
        .collect();
    PortableReceipt {
        subject: spec["subject"].as_str().unwrap_or_default().to_string(),
        metadata: spec
            .get("metadata")
            .and_then(Value::as_object)
            .cloned()
            .unwrap_or_default(),
        nodes,
        edges,
        receipt_id: spec
            .get("receipt_id")
            .and_then(Value::as_str)
            .unwrap_or("rr-conformance")
            .to_string(),
        produced_at: spec
            .get("produced_at")
            .and_then(Value::as_str)
            .unwrap_or("2026-01-01T00:00:00Z")
            .to_string(),
        schema_version: crate::receipt::SCHEMA_VERSION.to_string(),
        signatures: Vec::new(),
    }
}

type RunResult = std::result::Result<(bool, String), ReceiptError>;

fn run_canon(vector: &Value) -> RunResult {
    let expect = &vector["expect"];
    match untag(&vector["input"]).and_then(|v| canonical_string(&v)) {
        Ok(produced) => {
            if expect.get("error").is_some() {
                return Ok((false, format!("expected error {}, encoded fine", expect["error"])));
            }
            Ok((produced == expect["canonical"].as_str().unwrap_or(""), "canonical bytes differ".into()))
        }
        Err(exc) => {
            if let Some(want) = expect.get("error").and_then(Value::as_str) {
                return Ok((want == exc.code, format!("error {} vs {want}", exc.code)));
            }
            Ok((false, format!("unexpected error {}: {}", exc.code, exc.message)))
        }
    }
}

fn run_receipt(vector: &Value) -> RunResult {
    let expect = &vector["expect"];
    let receipt = build(&vector["input"]);
    let envelope = match receipt.committed_envelope() {
        Ok(e) => e,
        Err(exc) => {
            if let Some(want) = expect.get("error").and_then(Value::as_str) {
                return Ok((want == exc.code, format!("error {} vs {want}", exc.code)));
            }
            return Ok((false, format!("unexpected error {}: {}", exc.code, exc.message)));
        }
    };
    if expect.get("error").is_some() {
        return Ok((false, format!("expected error {}, built fine", expect["error"])));
    }
    let mut mismatches = Vec::new();
    if envelope["node_hashes"] != expect["node_hashes"] {
        mismatches.push("node_hashes");
    }
    if envelope["edge_hashes"] != expect["edge_hashes"] {
        mismatches.push("edge_hashes");
    }
    if envelope["merkle_root"] != expect["merkle_root"] {
        mismatches.push("merkle_root");
    }
    if let Some(want) = expect.get("receipt_hash") {
        if receipt.receipt_hash().ok().as_deref() != want.as_str() {
            mismatches.push("receipt_hash");
        }
    }
    if let Some(want) = expect.get("canonical_envelope").and_then(Value::as_str) {
        if canonical_string(&envelope).unwrap_or_default() != want {
            mismatches.push("canonical_envelope");
        }
    }
    Ok((mismatches.is_empty(), format!("fields differ: {}", mismatches.join(", "))))
}

fn run_document(vector: &Value) -> RunResult {
    let expect = &vector["expect"];
    let document = match untag(&vector["input"]) {
        Ok(d) => d,
        Err(exc) => {
            let want = expect["valid"].as_bool().unwrap_or(false);
            return Ok((!want, format!("untag error {}", exc.code)));
        }
    };
    let report = verify_any(&document, None);
    if report.valid != expect["valid"].as_bool().unwrap_or(false) {
        return Ok((
            false,
            format!("valid={} expected {} ({:?})", report.valid, expect["valid"], report.errors),
        ));
    }
    if let Some(codes) = expect.get("errors").and_then(Value::as_array) {
        for code in codes {
            let code = code.as_str().unwrap_or("");
            if !report.errors.iter().any(|e| e.contains(code)) {
                return Ok((
                    false,
                    format!("missing expected error code {code} in {:?}", report.errors),
                ));
            }
        }
    }
    Ok((true, String::new()))
}

fn run_proof(vector: &Value) -> RunResult {
    let expect = &vector["expect"];
    if let Some(doc) = vector.get("proof_document") {
        let ok = untag(doc).map(|d| verify_proof_document(&d)).unwrap_or(false);
        return Ok((ok == expect["verify"].as_bool().unwrap_or(false), format!("verify={ok} expected {}", expect["verify"])));
    }
    let receipt = build(&vector["input"]);
    let proof_doc = if let Some(node) = expect.get("node") {
        match receipt.proof_for(node.as_str().unwrap_or("")) {
            Ok(p) => p,
            Err(_) => {
                return if expect.get("error").is_some() {
                    Ok((true, String::new()))
                } else {
                    Ok((false, "node not found, no error expected".into()))
                }
            }
        }
    } else {
        match receipt.proof_for_edge(expect["edge_index"].as_u64().unwrap_or(0) as usize) {
            Ok(p) => p,
            Err(e) => return Ok((false, format!("edge proof error: {e}"))),
        }
    };
    if proof_doc["leaf"] != expect["leaf"] {
        return Ok((false, "leaf differs".into()));
    }
    if proof_doc["proof"] != expect["proof"] {
        return Ok((false, "proof siblings differ".into()));
    }
    if proof_doc["merkle_root"] != expect["merkle_root"] {
        return Ok((false, "root differs".into()));
    }
    Ok((verify_proof_document(&proof_doc), "generated proof does not verify".into()))
}

fn run_signature(vector: &Value) -> RunResult {
    let expect = &vector["expect"];
    let committed = build(&vector["input"]).committed_envelope()?;
    let spec = &vector["sign"];
    let sig_obj = sign(
        &committed,
        spec["private_key"].as_str().unwrap_or(""),
        spec.get("scope").and_then(Value::as_str).unwrap_or("receipt"),
        spec.get("key_id").and_then(Value::as_str),
        spec.get("signed_at").and_then(Value::as_str),
        None,
    )?;
    if let Some(want) = expect.get("public_key") {
        if sig_obj["public_key"] != *want {
            return Ok((false, "public_key differs".into()));
        }
    }
    if let Some(want) = expect.get("sig") {
        if sig_obj["sig"] != *want {
            return Ok((false, "signature bytes differ".into()));
        }
    }
    let target = match vector.get("verify_against") {
        Some(v) => build(v).committed_envelope()?,
        None => committed,
    };
    let results = verify_signatures(&target, vec![sig_obj])?;
    let ok = results[0]["valid"].as_bool().unwrap_or(false);
    Ok((ok == expect.get("valid").and_then(Value::as_bool).unwrap_or(true), format!("verify={ok}")))
}

pub struct VectorResult {
    pub name: String,
    pub ok: bool,
    pub detail: String,
}

pub fn run_vector(vector: &Value, name: &str) -> VectorResult {
    let kind = vector["kind"].as_str().unwrap_or("");
    let result: RunResult = match kind {
        "canon" => run_canon(vector),
        "receipt" => run_receipt(vector),
        "document" => run_document(vector),
        "proof" => run_proof(vector),
        "signature" => run_signature(vector),
        _ => return VectorResult { name: name.into(), ok: false, detail: format!("unknown kind {kind}") },
    };
    match result {
        Ok((ok, detail)) => VectorResult { name: name.into(), ok, detail },
        Err(exc) => {
            let want = vector["expect"]["error"].as_str();
            let ok = want == Some(exc.code);
            VectorResult {
                name: name.into(),
                ok,
                detail: format!("error {}{}", exc.code, if ok { "".into() } else { format!(" (wanted {})", want.unwrap_or("?")) }),
            }
        }
    }
}

pub struct CorpusReport {
    pub vectors: Vec<VectorResult>,
    pub total: usize,
    pub passed: usize,
    pub ok: bool,
}

/// Replace every `\uXXXX` surrogate-range escape with `\ufffd` so
/// serde_json can parse a vector's `expect` block after the strict
/// parser has already classified the file. Never applied to input bytes.
fn sanitize_surrogate_escapes(text: &str) -> String {
    let bytes = text.as_bytes();
    let mut out = String::with_capacity(text.len());
    let mut i = 0;
    while i < bytes.len() {
        if bytes[i] == b'\\'
            && i + 6 <= bytes.len()
            && bytes[i + 1] == b'u'
            && matches!(bytes[i + 2], b'd' | b'D')
        {
            if let Ok(cp) = u32::from_str_radix(&text[i + 2..i + 6], 16) {
                if (0xd800..=0xdfff).contains(&cp) {
                    out.push_str("\\ufffd");
                    i += 6;
                    continue;
                }
            }
        }
        let ch_len = utf8_char_len(bytes[i]);
        out.push_str(&text[i..i + ch_len]);
        i += ch_len;
    }
    out
}

fn utf8_char_len(first: u8) -> usize {
    match first {
        0x00..=0x7f => 1,
        0xc0..=0xdf => 2,
        0xe0..=0xef => 3,
        _ => 4,
    }
}

pub fn run_corpus(vector_dir: &Path) -> CorpusReport {
    let mut files: Vec<_> = fs::read_dir(vector_dir)
        .expect("vector dir")
        .filter_map(|e| e.ok())
        .map(|e| e.path())
        .filter(|p| p.extension().is_some_and(|x| x == "json"))
        .collect();
    files.sort();
    let vectors: Vec<VectorResult> = files
        .iter()
        .map(|p| {
            let text = fs::read_to_string(p).expect("read vector");
            let name = p.file_stem().unwrap().to_str().unwrap().to_string();
            // The strict parser can itself reject a vector file (e.g. the
            // lone-surrogate input). When it does, the vector's expected
            // error code is the contract — same observable result as
            // Python rejecting one stage later at encode time.
            match crate::canon::parse_json_value(&text) {
                Ok(vector) => {
                    let name = vector
                        .get("name")
                        .and_then(Value::as_str)
                        .unwrap_or(&name)
                        .to_string();
                    run_vector(&vector, &name)
                }
                Err(exc) => {
                    // Recover the expect block from a surrogate-sanitized
                    // copy (the strict parser already produced its code).
                    let sanitized = sanitize_surrogate_escapes(&text);
                    let vector: Value = serde_json::from_str(&sanitized).unwrap_or(json!({}));
                    let want = vector["expect"]["error"].as_str();
                    let ok = want == Some(exc.code);
                    VectorResult {
                        name,
                        ok,
                        detail: format!(
                            "error {}{}",
                            exc.code,
                            if ok { String::new() } else { format!(" (wanted {})", want.unwrap_or("?")) }
                        ),
                    }
                }
            }
        })
        .collect();
    let passed = vectors.iter().filter(|v| v.ok).count();
    CorpusReport {
        total: vectors.len(),
        passed,
        ok: passed == vectors.len() && !vectors.is_empty(),
        vectors,
    }
}
