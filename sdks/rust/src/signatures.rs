//! Optional Ed25519 signatures for `reasoning-receipt/1` (spec §8).
//! Mirrors `protocol/signatures.py`: `receipt` scope signs the 32-byte
//! receipt_hash, `node:<id>` signs one node leaf. Signatures live outside
//! the committed envelope.

use crate::errors::{E_BAD_SIGNATURE, ReceiptError, Result};
use crate::merkle;
use crate::receipt::{node_leaf, receipt_hash_of, valid_timestamp};
use ed25519_dalek::{Signature, Signer, SigningKey, Verifier, VerifyingKey};
use serde_json::{json, Map, Value};

pub const ALG_ED25519: &str = "ed25519";

const SIG_DOMAIN_RECEIPT: &[u8] = b"RR1:sig:receipt\x00";
const SIG_DOMAIN_NODE: &[u8] = b"RR1:sig:node\x00";

const SIG_FIELDS: &[&str] = &["alg", "scope", "public_key", "sig", "signed_at", "key_id", "meta"];
const SIG_REQUIRED: &[&str] = &["alg", "scope", "public_key", "sig"];

fn decode_key(value: &Value, length: usize, what: &str) -> Result<Vec<u8>> {
    let s = value
        .as_str()
        .ok_or_else(|| ReceiptError::new(E_BAD_SIGNATURE, format!("{what} is not a string")))?;
    let raw = merkle::hex_decode(s)
        .map_err(|_| ReceiptError::new(E_BAD_SIGNATURE, format!("{what} is not hex")))?;
    if raw.len() != length {
        return Err(ReceiptError::new(
            E_BAD_SIGNATURE,
            format!("{what} must be {length} bytes"),
        ));
    }
    Ok(raw)
}

pub fn generate_keypair() -> (String, String) {
    let mut seed = [0u8; 32];
    use rand_core::{OsRng, RngCore};
    OsRng.fill_bytes(&mut seed);
    let key = SigningKey::from_bytes(&seed);
    (
        format!("0x{}", merkle::hex_encode(&seed)),
        format!("0x{}", merkle::hex_encode(&key.verifying_key().to_bytes())),
    )
}

fn preimage_for(scope: &str, envelope: &Value) -> Result<Vec<u8>> {
    if scope == "receipt" {
        let target = merkle::hex_decode(&receipt_hash_of(envelope))
            .map_err(|e| ReceiptError::new(E_BAD_SIGNATURE, e.message))?;
        let mut p = SIG_DOMAIN_RECEIPT.to_vec();
        p.extend_from_slice(&target);
        Ok(p)
    } else if let Some(node_id) = scope.strip_prefix("node:") {
        let nodes = envelope
            .get("nodes")
            .and_then(Value::as_array)
            .cloned()
            .unwrap_or_default();
        for nd in &nodes {
            if nd["id"].as_str() == Some(node_id) {
                let mut p = SIG_DOMAIN_NODE.to_vec();
                p.extend_from_slice(&node_leaf(nd));
                return Ok(p);
            }
        }
        Err(ReceiptError::new(
            E_BAD_SIGNATURE,
            format!("node {node_id} not in envelope"),
        ))
    } else {
        Err(ReceiptError::new(
            E_BAD_SIGNATURE,
            format!("unknown signature scope {scope}"),
        ))
    }
}

pub fn sign(
    committed_envelope: &Value,
    private_key_hex: &str,
    scope: &str,
    key_id: Option<&str>,
    signed_at: Option<&str>,
    meta: Option<Value>,
) -> Result<Value> {
    let seed = decode_key(&json!(private_key_hex), 32, "private_key")?;
    let mut seed32 = [0u8; 32];
    seed32.copy_from_slice(&seed);
    let signing_key = SigningKey::from_bytes(&seed32);

    let preimage = preimage_for(scope, committed_envelope)?;
    let signature = signing_key.sign(&preimage);

    let signed_at_val = match signed_at {
        None => chrono::Utc::now().format("%Y-%m-%dT%H:%M:%SZ").to_string(),
        Some(s) => {
            if !valid_timestamp(s) {
                return Err(ReceiptError::new(
                    E_BAD_SIGNATURE,
                    format!("invalid signed_at {s}"),
                ));
            }
            s.to_string()
        }
    };

    let mut sig = Map::new();
    sig.insert("alg".into(), json!(ALG_ED25519));
    sig.insert("scope".into(), json!(scope));
    sig.insert(
        "public_key".into(),
        json!(format!(
            "0x{}",
            merkle::hex_encode(&signing_key.verifying_key().to_bytes())
        )),
    );
    sig.insert("sig".into(), json!(format!("0x{}", merkle::hex_encode(&signature.to_bytes()))));
    sig.insert("signed_at".into(), json!(signed_at_val));
    if let Some(k) = key_id {
        sig.insert("key_id".into(), json!(k));
    }
    if let Some(m) = meta {
        sig.insert("meta".into(), m);
    }
    Ok(Value::Object(sig))
}

pub fn verify_signatures(committed_envelope: &Value, signatures: Vec<Value>) -> Result<Vec<Value>> {
    let mut results = Vec::with_capacity(signatures.len());
    for (index, sig) in signatures.iter().enumerate() {
        let mut result = Map::new();
        result.insert("index".into(), json!(index));
        result.insert("valid".into(), json!(false));
        let outcome: Result<()> = (|| {
            let obj = sig
                .as_object()
                .ok_or_else(|| ReceiptError::signature("signature is not an object"))?;
            let missing: Vec<&&str> = SIG_REQUIRED.iter().filter(|k| !obj.contains_key(**k)).collect();
            if !missing.is_empty() {
                return Err(ReceiptError::signature(format!("signature missing {missing:?}")));
            }
            let extra: Vec<&String> = obj.keys().filter(|k| !SIG_FIELDS.contains(&k.as_str())).collect();
            if !extra.is_empty() {
                return Err(ReceiptError::signature(format!("signature has unknown fields {extra:?}")));
            }
            result.insert("scope".into(), obj["scope"].clone());
            result.insert("public_key".into(), obj["public_key"].clone());
            if obj["alg"].as_str() != Some(ALG_ED25519) {
                return Err(ReceiptError::signature(format!(
                    "unsupported alg {:?}",
                    obj["alg"]
                )));
            }
            if let Some(sa) = obj.get("signed_at") {
                if !valid_timestamp(sa.as_str().unwrap_or("")) {
                    return Err(ReceiptError::signature("invalid signed_at"));
                }
            }
            let public = decode_key(&obj["public_key"], 32, "public_key")?;
            let sig_bytes = decode_key(&obj["sig"], 64, "sig")?;
            let mut pk32 = [0u8; 32];
            pk32.copy_from_slice(&public);
            let verifying_key = VerifyingKey::from_bytes(&pk32)
                .map_err(|_| ReceiptError::signature("bad public key"))?;
            let mut sig64 = [0u8; 64];
            sig64.copy_from_slice(&sig_bytes);
            let signature = Signature::from_bytes(&sig64);

            let scope = obj["scope"].as_str().unwrap_or("");
            let preimage = preimage_for(scope, committed_envelope)
                .map_err(|e| ReceiptError::signature(e.message))?;
            if verifying_key.verify(&preimage, &signature).is_err() {
                result.insert("reason".into(), json!("signature verification failed"));
                return Ok(());
            }
            result.insert("valid".into(), json!(true));
            Ok(())
        })();
        if let Err(exc) = outcome {
            result.insert("reason".into(), json!(exc.message));
        }
        results.push(Value::Object(result));
    }
    Ok(results)
}
