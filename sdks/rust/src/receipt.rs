//! `reasoning-receipt/1` — portable evidence-receipt envelope.
//! Mirrors `protocol/receipt.py` (spec §3–§6, §9–§12).

use crate::canon::{canonical_bytes, CANONICALIZATION_ID};
use crate::errors::*;
use crate::merkle;
use serde_json::{json, Map, Value};
use sha2::{Digest, Sha256};
use std::collections::{HashMap, HashSet};

pub const SCHEMA_VERSION: &str = "reasoning-receipt/1";
pub const CANONICALIZATION: &str = CANONICALIZATION_ID;

const MAX_NODES: usize = 1024;
const MAX_EDGES: usize = 4096;
const MAX_SUBJECT: usize = 500;
const MAX_RECEIPT_ID: usize = 128;
const ENVELOPE_MAX_BYTES: usize = 8 << 20;

const ENVELOPE_FIELDS: &[&str] = &[
    "schema_version", "receipt_id", "subject", "produced_at", "metadata",
    "nodes", "edges", "node_hashes", "edge_hashes", "merkle_root",
    "signatures", "receipt_hash",
];
const REQUIRED_FIELDS: &[&str] = &[
    "schema_version", "receipt_id", "subject", "produced_at",
    "nodes", "node_hashes", "edge_hashes", "merkle_root",
];
const NODE_FIELDS: &[&str] = &["id", "kind", "payload", "meta"];

const LEAF_DOMAIN_NODE: &[u8] = b"RR1:node\x00";
const LEAF_DOMAIN_EDGE: &[u8] = b"RR1:edge\x00";
const HASH_DOMAIN_RECEIPT: &[u8] = b"RR1:receipt\x00";

fn node_id_ok(s: &str) -> bool {
    let b = s.as_bytes();
    !b.is_empty()
        && b.len() <= 128
        && b[0].is_ascii_alphanumeric()
        && b.iter().all(|c| {
            c.is_ascii_alphanumeric() || matches!(*c, b'_' | b'.' | b':' | b'/' | b'-')
        })
}

fn vocab_ok(s: &str) -> bool {
    let b = s.as_bytes();
    !b.is_empty()
        && b.len() <= 64
        && b[0].is_ascii_lowercase()
        && b.iter().all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || *c == b'_')
}

fn has_controls(s: &str) -> bool {
    s.chars().any(|c| (c as u32) < 0x20 || c as u32 == 0x7f)
}

fn check_no_controls(s: &str, what: &str, code: &'static str) -> Result<()> {
    if has_controls(s) {
        return Err(ReceiptError::new(code, format!("{what} contains a control character")));
    }
    Ok(())
}

pub fn valid_timestamp(value: &str) -> bool {
    // ^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$ + real calendar date
    let b = value.as_bytes();
    if b.len() != 20 || b[4] != b'-' || b[7] != b'-' || b[10] != b'T'
        || b[13] != b':' || b[16] != b':' || b[19] != b'Z'
    {
        return false;
    }
    let digits = |i: usize, j: usize| -> Option<u32> {
        value[i..j].parse().ok()
    };
    let (Some(y), Some(mo), Some(d), Some(h), Some(mi), Some(s)) = (
        digits(0, 4), digits(5, 7), digits(8, 10),
        digits(11, 13), digits(14, 16), digits(17, 19),
    ) else {
        return false;
    };
    if !(1..=12).contains(&mo) || d < 1 || h > 23 || mi > 59 || s > 59 {
        return false;
    }
    let leap = y % 4 == 0 && (y % 100 != 0 || y % 400 == 0);
    let dim = [31, if leap { 29 } else { 28 }, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
    d <= dim[(mo - 1) as usize]
}

pub fn bytes32_hex(value: &Value, what: &str) -> Result<[u8; 32]> {
    let s = value
        .as_str()
        .ok_or_else(|| ReceiptError::new(E_BAD_HASH, format!("{what} is not a string")))?;
    let raw = merkle::hex_decode(s).map_err(|_| {
        ReceiptError::new(E_BAD_HASH, format!("{what} is not hex"))
    })?;
    if raw.len() != 32 {
        return Err(ReceiptError::new(
            E_BAD_HASH,
            format!("{what} is {} bytes, expected 32", raw.len()),
        ));
    }
    let mut out = [0u8; 32];
    out.copy_from_slice(&raw);
    Ok(out)
}

// ------------------------------------------------------------------ leaves

pub fn node_leaf(node_dict: &Value) -> [u8; 32] {
    let mut h = Sha256::new();
    h.update(LEAF_DOMAIN_NODE);
    h.update(canonical_bytes(node_dict).expect("node canonicalization"));
    h.finalize().into()
}

pub fn edge_leaf(edge_dict: &Value) -> [u8; 32] {
    let mut h = Sha256::new();
    h.update(LEAF_DOMAIN_EDGE);
    h.update(canonical_bytes(edge_dict).expect("edge canonicalization"));
    h.finalize().into()
}

pub fn merkle_root_of(leaves: &[[u8; 32]]) -> [u8; 32] {
    let mut sorted = leaves.to_vec();
    sorted.sort();
    merkle::merkle_root(&sorted)
}

pub fn receipt_hash_of(committed_envelope: &Value) -> String {
    let mut h = Sha256::new();
    h.update(HASH_DOMAIN_RECEIPT);
    h.update(canonical_bytes(committed_envelope).expect("envelope canonicalization"));
    format!("0x{}", merkle::hex_encode(&h.finalize()))
}

// ------------------------------------------------------------------- model

#[derive(Debug, Clone)]
pub struct ReceiptNode {
    pub id: String,
    pub kind: String,
    pub payload: Value,
    pub meta: Option<Value>,
}

impl ReceiptNode {
    pub fn validate(&self) -> Result<()> {
        if !node_id_ok(&self.id) {
            return Err(ReceiptError::new(E_BAD_NODE_ID, format!("invalid node id {}", self.id)));
        }
        if !vocab_ok(&self.kind) {
            return Err(ReceiptError::new(E_BAD_KIND, format!("invalid node kind {}", self.kind)));
        }
        if let Some(m) = &self.meta {
            if !m.is_object() {
                return Err(ReceiptError::new(E_BAD_TYPE, "node meta must be an object"));
            }
        }
        canonical_bytes(&self.to_dict())?;
        Ok(())
    }

    pub fn to_dict(&self) -> Value {
        let mut o = Map::new();
        o.insert("id".into(), json!(self.id));
        o.insert("kind".into(), json!(self.kind));
        o.insert("payload".into(), self.payload.clone());
        if let Some(m) = &self.meta {
            o.insert("meta".into(), m.clone());
        }
        Value::Object(o)
    }
}

#[derive(Debug, Clone)]
pub struct ReceiptEdge {
    pub src: String,
    pub dst: String,
    pub rel: String,
}

impl ReceiptEdge {
    pub fn validate(&self) -> Result<()> {
        if !node_id_ok(&self.src) {
            return Err(ReceiptError::new(E_BAD_NODE_ID, format!("invalid edge source {}", self.src)));
        }
        if !node_id_ok(&self.dst) {
            return Err(ReceiptError::new(E_BAD_NODE_ID, format!("invalid edge target {}", self.dst)));
        }
        if !vocab_ok(&self.rel) {
            return Err(ReceiptError::new(E_BAD_REL, format!("invalid edge rel {}", self.rel)));
        }
        if self.src == self.dst {
            return Err(ReceiptError::new(E_SELF_LOOP, format!("self-loop on {}", self.src)));
        }
        Ok(())
    }

    pub fn to_dict(&self) -> Value {
        json!({"from": self.src, "to": self.dst, "rel": self.rel})
    }
}

#[derive(Debug, Clone)]
pub struct PortableReceipt {
    pub subject: String,
    pub nodes: Vec<ReceiptNode>,
    pub edges: Vec<ReceiptEdge>,
    pub metadata: Map<String, Value>,
    pub receipt_id: String,
    pub produced_at: String,
    pub schema_version: String,
    pub signatures: Vec<Value>,
}

impl PortableReceipt {
    fn ordered_nodes(&self) -> Result<Vec<ReceiptNode>> {
        if self.subject.trim().is_empty() {
            return Err(ReceiptError::new(E_EMPTY_SUBJECT, "receipt subject must not be empty"));
        }
        if self.subject.chars().count() > MAX_SUBJECT {
            return Err(ReceiptError::new(E_LIMIT, "subject too long"));
        }
        check_no_controls(&self.subject, "subject", E_EMPTY_SUBJECT)?;
        if self.nodes.is_empty() {
            return Err(ReceiptError::new(E_EMPTY_NODES, "receipt must contain at least one node"));
        }
        if self.nodes.len() > MAX_NODES {
            return Err(ReceiptError::new(E_LIMIT, "too many nodes"));
        }
        let mut ids = HashSet::new();
        for node in &self.nodes {
            node.validate()?;
            if !ids.insert(node.id.clone()) {
                return Err(ReceiptError::new(
                    E_DUP_NODE_ID,
                    format!("duplicate node id {}", node.id),
                ));
            }
        }
        let mut ordered = self.nodes.clone();
        ordered.sort_by(|a, b| a.id.cmp(&b.id));
        Ok(ordered)
    }

    fn ordered_edges(&self) -> Result<Vec<ReceiptEdge>> {
        if self.edges.len() > MAX_EDGES {
            return Err(ReceiptError::new(E_LIMIT, "too many edges"));
        }
        let node_ids: HashSet<&str> = self.nodes.iter().map(|n| n.id.as_str()).collect();
        let mut triples = HashSet::new();
        for edge in &self.edges {
            edge.validate()?;
            let triple = (edge.src.clone(), edge.dst.clone(), edge.rel.clone());
            if !triples.insert(triple.clone()) {
                return Err(ReceiptError::new(E_DUP_EDGE, format!("duplicate edge {triple:?}")));
            }
            for endpoint in [&edge.src, &edge.dst] {
                if !node_ids.contains(endpoint.as_str()) {
                    return Err(ReceiptError::new(
                        E_DANGLING_EDGE,
                        format!("edge references unknown node {endpoint}"),
                    ));
                }
            }
        }
        let mut ordered = self.edges.clone();
        ordered.sort_by(|a, b| {
            (&a.src, &a.dst, &a.rel).cmp(&(&b.src, &b.dst, &b.rel))
        });
        assert_acyclic(&ordered)?;
        Ok(ordered)
    }

    pub fn node_dicts(&self) -> Result<Vec<Value>> {
        Ok(self.ordered_nodes()?.iter().map(|n| n.to_dict()).collect())
    }

    pub fn edge_dicts(&self) -> Result<Vec<Value>> {
        Ok(self.ordered_edges()?.iter().map(|e| e.to_dict()).collect())
    }

    pub fn leaves(&self) -> Result<Vec<[u8; 32]>> {
        let mut set: Vec<[u8; 32]> = self.node_dicts()?.iter().map(node_leaf).collect();
        set.extend(self.edge_dicts()?.iter().map(edge_leaf));
        set.sort();
        Ok(set)
    }

    pub fn node_hashes(&self) -> Result<Map<String, Value>> {
        let mut out = Map::new();
        for nd in self.node_dicts()? {
            out.insert(
                nd["id"].as_str().unwrap().to_string(),
                json!(format!("0x{}", merkle::hex_encode(&node_leaf(&nd)))),
            );
        }
        Ok(out)
    }

    pub fn edge_hashes(&self) -> Result<Vec<Value>> {
        Ok(self
            .edge_dicts()?
            .iter()
            .map(|ed| json!(format!("0x{}", merkle::hex_encode(&edge_leaf(ed)))))
            .collect())
    }

    pub fn merkle_root_hex(&self) -> Result<String> {
        Ok(format!("0x{}", merkle::hex_encode(&merkle_root_of(&self.leaves()?))))
    }

    pub fn committed_envelope(&self) -> Result<Value> {
        if !valid_timestamp(&self.produced_at) {
            return Err(ReceiptError::new(
                E_BAD_TIMESTAMP,
                format!("invalid produced_at {}", self.produced_at),
            ));
        }
        if self.receipt_id.is_empty() || self.receipt_id.len() > MAX_RECEIPT_ID {
            return Err(ReceiptError::new(E_EMPTY_RECEIPT_ID, "invalid receipt_id"));
        }
        check_no_controls(&self.receipt_id, "receipt_id", E_EMPTY_RECEIPT_ID)?;
        Ok(json!({
            "schema_version": self.schema_version,
            "receipt_id": self.receipt_id,
            "subject": self.subject,
            "produced_at": self.produced_at,
            "metadata": self.metadata,
            "nodes": self.node_dicts()?,
            "edges": self.edge_dicts()?,
            "node_hashes": self.node_hashes()?,
            "edge_hashes": self.edge_hashes()?,
            "merkle_root": self.merkle_root_hex()?,
        }))
    }

    pub fn to_dict(&self) -> Result<Value> {
        let mut envelope = self.committed_envelope()?;
        if !self.signatures.is_empty() {
            envelope["signatures"] = json!(self.signatures);
        }
        envelope["receipt_hash"] = json!(self.receipt_hash()?);
        Ok(envelope)
    }

    pub fn receipt_hash(&self) -> Result<String> {
        Ok(receipt_hash_of(&self.committed_envelope()?))
    }

    pub fn proof_for(&self, node_id: &str) -> Result<Value> {
        let ordered = self.node_dicts()?;
        let idx = ordered
            .iter()
            .position(|n| n["id"].as_str() == Some(node_id))
            .ok_or_else(|| ReceiptError::new("node_not_found", format!("node {node_id} not in receipt")))?;
        let leaves = self.leaves()?;
        let leaf = node_leaf(&ordered[idx]);
        let index = leaves.iter().position(|l| *l == leaf).unwrap();
        Ok(json!({
            "schema_version": self.schema_version,
            "item_type": "node",
            "item": ordered[idx],
            "leaf": format!("0x{}", merkle::hex_encode(&leaf)),
            "merkle_root": format!("0x{}", merkle::hex_encode(&merkle_root_of(&leaves))),
            "proof": merkle::merkle_proof(&leaves, index)
                .iter()
                .map(|s| format!("0x{}", merkle::hex_encode(s)))
                .collect::<Vec<_>>(),
        }))
    }

    pub fn proof_for_edge(&self, index: usize) -> Result<Value> {
        let edge_dicts = self.edge_dicts()?;
        if index >= edge_dicts.len() {
            return Err(ReceiptError::new("edge_index", format!("edge index {index} out of range")));
        }
        let leaves = self.leaves()?;
        let leaf = edge_leaf(&edge_dicts[index]);
        let leaf_index = leaves.iter().position(|l| *l == leaf).unwrap();
        Ok(json!({
            "schema_version": self.schema_version,
            "item_type": "edge",
            "item": edge_dicts[index],
            "leaf": format!("0x{}", merkle::hex_encode(&leaf)),
            "merkle_root": format!("0x{}", merkle::hex_encode(&merkle_root_of(&leaves))),
            "proof": merkle::merkle_proof(&leaves, leaf_index)
                .iter()
                .map(|s| format!("0x{}", merkle::hex_encode(s)))
                .collect::<Vec<_>>(),
        }))
    }
}

fn assert_acyclic(edges: &[ReceiptEdge]) -> Result<()> {
    let mut adjacency: HashMap<&str, Vec<&str>> = HashMap::new();
    for e in edges {
        adjacency.entry(&e.src).or_default().push(&e.dst);
    }
    // 0=white 1=gray 2=black, iterative DFS
    let mut color: HashMap<&str, u8> = HashMap::new();
    for &start in adjacency.keys() {
        if color.get(start).copied().unwrap_or(0) != 0 {
            continue;
        }
        color.insert(start, 1);
        let mut stack: Vec<(&str, std::vec::IntoIter<&str>)> =
            vec![(start, adjacency.get(start).cloned().unwrap_or_default().into_iter())];
        while !stack.is_empty() {
            let (node, it) = stack.last_mut().unwrap();
            match it.next() {
                Some(nxt) => {
                    let state = color.get(nxt).copied().unwrap_or(0);
                    if state == 1 {
                        return Err(ReceiptError::new(
                            E_CYCLE,
                            format!("cycle detected via edge {node} -> {nxt}"),
                        ));
                    }
                    if state == 0 {
                        color.insert(nxt, 1);
                        let children = adjacency.get(nxt).cloned().unwrap_or_default().into_iter();
                        stack.push((nxt, children));
                    }
                }
                None => {
                    color.insert(*node, 2);
                    stack.pop();
                }
            }
        }
    }
    Ok(())
}

// ----------------------------------------------------------------- builder

#[derive(Debug)]
pub struct ReceiptBuilder {
    subject: String,
    metadata: Map<String, Value>,
    nodes: Vec<ReceiptNode>,
    edges: Vec<ReceiptEdge>,
}

impl ReceiptBuilder {
    pub fn new(subject: impl Into<String>, metadata: Map<String, Value>) -> Self {
        Self {
            subject: subject.into(),
            metadata,
            nodes: Vec::new(),
            edges: Vec::new(),
        }
    }

    pub fn add(
        &mut self,
        id: impl Into<String>,
        kind: impl Into<String>,
        payload: Value,
        meta: Option<Map<String, Value>>,
    ) -> &mut Self {
        self.nodes.push(ReceiptNode {
            id: id.into(),
            kind: kind.into(),
            payload,
            meta: meta.map(Value::Object),
        });
        self
    }

    pub fn link(&mut self, src: impl Into<String>, dst: impl Into<String>, rel: impl Into<String>) -> &mut Self {
        self.edges.push(ReceiptEdge {
            src: src.into(),
            dst: dst.into(),
            rel: rel.into(),
        });
        self
    }

    pub fn finalize(&self, receipt_id: Option<String>, produced_at: Option<String>) -> Result<PortableReceipt> {
        let receipt = PortableReceipt {
            subject: self.subject.clone(),
            nodes: self.nodes.clone(),
            edges: self.edges.clone(),
            metadata: self.metadata.clone(),
            receipt_id: receipt_id.unwrap_or_else(|| "rr-auto".to_string()),
            produced_at: produced_at.unwrap_or_else(|| "1970-01-01T00:00:00Z".to_string()),
            schema_version: SCHEMA_VERSION.to_string(),
            signatures: Vec::new(),
        };
        receipt.to_dict()?; // force full validation
        Ok(receipt)
    }
}

// ----------------------------------------------------------------- reports

#[derive(Debug, Clone, Default)]
pub struct VerifyReport {
    pub valid: bool,
    pub schema_version: String,
    pub canonicalization: String,
    pub variant: String,
    pub checks: Map<String, Value>,
    pub errors: Vec<String>,
    pub signatures: Vec<Value>,
    pub receipt_hash: Option<String>,
    pub merkle_root: Option<String>,
    pub node_count: usize,
    pub edge_count: usize,
}

impl VerifyReport {
    pub fn to_value(&self) -> Value {
        json!({
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
        })
    }
}

pub(crate) fn base_report(schema: &str, canon: &str, variant: &str, checks: Map<String, Value>, errors: Vec<String>) -> VerifyReport {
    VerifyReport {
        valid: false,
        schema_version: schema.to_string(),
        canonicalization: canon.to_string(),
        variant: variant.to_string(),
        checks,
        errors,
        ..Default::default()
    }
}

pub(crate) fn checks(pairs: &[(&str, bool)]) -> Map<String, Value> {
    let mut m = Map::new();
    for (k, v) in pairs {
        m.insert(k.to_string(), json!(v));
    }
    m
}

// ----------------------------------------------------------------- restore

pub fn restore_receipt(document: &Value) -> Result<PortableReceipt> {
    let doc = document
        .as_object()
        .ok_or_else(|| ReceiptError::new(E_BAD_TYPE, "receipt document is not an object"))?;

    let unknown: Vec<&String> = doc.keys().filter(|k| !ENVELOPE_FIELDS.contains(&k.as_str())).collect();
    if !unknown.is_empty() {
        let mut u: Vec<String> = unknown.into_iter().cloned().collect();
        u.sort();
        return Err(ReceiptError::new(E_UNKNOWN_FIELD, format!("unknown top-level fields {u:?}")));
    }
    for required in REQUIRED_FIELDS {
        if !doc.contains_key(*required) {
            return Err(ReceiptError::new(E_MISSING_FIELD, format!("missing field {required}")));
        }
    }
    if doc.get("schema_version").and_then(Value::as_str) != Some(SCHEMA_VERSION) {
        return Err(ReceiptError::schema(format!(
            "unsupported schema_version {:?}",
            doc.get("schema_version")
        )));
    }

    let receipt_id = doc["receipt_id"]
        .as_str()
        .filter(|s| !s.is_empty() && s.len() <= MAX_RECEIPT_ID)
        .ok_or_else(|| ReceiptError::new(E_EMPTY_RECEIPT_ID, "invalid receipt_id"))?;
    check_no_controls(receipt_id, "receipt_id", E_EMPTY_RECEIPT_ID)?;

    let produced_at = doc["produced_at"].as_str().unwrap_or("");
    if !valid_timestamp(produced_at) {
        return Err(ReceiptError::new(
            E_BAD_TIMESTAMP,
            format!("invalid produced_at {produced_at}"),
        ));
    }

    let metadata = doc.get("metadata").cloned().unwrap_or(json!({}));
    if !metadata.is_object() {
        return Err(ReceiptError::new(E_BAD_TYPE, "metadata must be an object"));
    }

    let raw_nodes = doc["nodes"]
        .as_array()
        .ok_or_else(|| ReceiptError::new(E_BAD_TYPE, "nodes must be an array"))?;
    let mut nodes = Vec::with_capacity(raw_nodes.len());
    for raw in raw_nodes {
        let n = raw
            .as_object()
            .ok_or_else(|| ReceiptError::new(E_BAD_TYPE, "node is not an object"))?;
        let extra: Vec<&String> = n.keys().filter(|k| !NODE_FIELDS.contains(&k.as_str())).collect();
        if !extra.is_empty() {
            return Err(ReceiptError::new(E_UNKNOWN_FIELD, format!("unknown node fields {extra:?}")));
        }
        for needed in ["id", "kind", "payload"] {
            if !n.contains_key(needed) {
                return Err(ReceiptError::new(E_MISSING_FIELD, format!("node missing {needed}")));
            }
        }
        nodes.push(ReceiptNode {
            id: n["id"].as_str().unwrap_or_default().to_string(),
            kind: n["kind"].as_str().unwrap_or_default().to_string(),
            payload: n["payload"].clone(),
            meta: n.get("meta").cloned(),
        });
    }

    let raw_edges = match doc.get("edges") {
        None => &Vec::new(),
        Some(v) => v
            .as_array()
            .ok_or_else(|| ReceiptError::new(E_BAD_TYPE, "edges must be an array"))?,
    };
    let mut edges = Vec::with_capacity(raw_edges.len());
    for raw in raw_edges {
        let e = raw
            .as_object()
            .ok_or_else(|| ReceiptError::new(E_BAD_TYPE, "edge is not an object"))?;
        let mut keys: Vec<&str> = e.keys().map(String::as_str).collect();
        keys.sort();
        if keys != ["from", "rel", "to"] {
            return Err(ReceiptError::new(
                E_UNKNOWN_FIELD,
                "edge must have exactly [\"from\", \"rel\", \"to\"]",
            ));
        }
        edges.push(ReceiptEdge {
            src: e["from"].as_str().unwrap_or_default().to_string(),
            dst: e["to"].as_str().unwrap_or_default().to_string(),
            rel: e["rel"].as_str().unwrap_or_default().to_string(),
        });
    }

    let node_hashes = doc["node_hashes"]
        .as_object()
        .ok_or_else(|| ReceiptError::new(E_BAD_TYPE, "node_hashes must be an object"))?;
    let edge_hashes = doc["edge_hashes"]
        .as_array()
        .ok_or_else(|| ReceiptError::new(E_BAD_TYPE, "edge_hashes must be an array"))?;
    for value in node_hashes.values().chain(edge_hashes.iter()) {
        bytes32_hex(value, "leaf hash")?;
    }
    bytes32_hex(&doc["merkle_root"], "merkle_root")?;

    let signatures = match doc.get("signatures") {
        None => Vec::new(),
        Some(v) => v
            .as_array()
            .ok_or_else(|| ReceiptError::new(E_BAD_TYPE, "signatures must be an array"))?
            .clone(),
    };

    let encoded = canonical_bytes(document)?;
    if encoded.len() > ENVELOPE_MAX_BYTES {
        return Err(ReceiptError::new(E_LIMIT, "envelope exceeds 8 MiB"));
    }

    Ok(PortableReceipt {
        receipt_id: receipt_id.to_string(),
        subject: doc["subject"].as_str().unwrap_or_default().to_string(),
        produced_at: produced_at.to_string(),
        metadata: metadata.as_object().unwrap().clone(),
        nodes,
        edges,
        signatures,
        schema_version: SCHEMA_VERSION.to_string(),
    })
}

// ------------------------------------------------------------------ verify

pub fn verify_receipt(document: &Value) -> VerifyReport {
    let mut check_map = Map::new();
    let mut errors: Vec<String> = Vec::new();

    let receipt = match restore_receipt(document) {
        Ok(r) => {
            check_map.insert("shape".into(), json!(true));
            r
        }
        Err(exc) => {
            check_map.insert("shape".into(), json!(false));
            errors.push(format!("{}: {}", exc.code, exc.message));
            return base_report(
                document
                    .get("schema_version")
                    .and_then(Value::as_str)
                    .unwrap_or("unknown"),
                CANONICALIZATION,
                "final",
                check_map,
                errors,
            );
        }
    };

    let expected = match receipt.committed_envelope() {
        Ok(e) => {
            check_map.insert("graph".into(), json!(true));
            e
        }
        Err(exc) => {
            check_map.insert("graph".into(), json!(false));
            errors.push(format!("{}: {}", exc.code, exc.message));
            return base_report(SCHEMA_VERSION, CANONICALIZATION, "final", check_map, errors);
        }
    };

    let hashes_ok = expected["node_hashes"] == document["node_hashes"]
        && expected["edge_hashes"] == document["edge_hashes"];
    check_map.insert("hashes".into(), json!(hashes_ok));
    if !hashes_ok {
        errors.push("hash_mismatch: node_hashes or edge_hashes do not match recomputed leaves".into());
    }
    let root_ok = expected["merkle_root"] == document["merkle_root"];
    check_map.insert("root".into(), json!(root_ok));
    if !root_ok {
        errors.push("root_mismatch: merkle_root does not match recomputed leaf set".into());
    }

    if document.get("receipt_hash").is_some() {
        let recomputed = receipt.receipt_hash().unwrap_or_default();
        let ok = document["receipt_hash"].as_str() == Some(recomputed.as_str());
        check_map.insert("receipt_hash".into(), json!(ok));
        if !ok {
            errors.push("hash_mismatch: receipt_hash annotation does not match".into());
        }
    }

    let mut sig_results: Vec<Value> = Vec::new();
    match crate::signatures::verify_signatures(
        &expected,
        document.get("signatures").and_then(Value::as_array).cloned().unwrap_or_default(),
    ) {
        Ok(results) => {
            let all_ok = results.iter().all(|r| r["valid"].as_bool() == Some(true));
            check_map.insert("signatures".into(), json!(all_ok));
            sig_results = results;
        }
        Err(exc) => {
            check_map.insert("signatures".into(), json!(false));
            errors.push(format!("{}: {}", exc.code, exc.message));
        }
    }

    let valid = check_map.values().all(|v| v.as_bool() == Some(true));
    let mut rep = base_report(SCHEMA_VERSION, CANONICALIZATION, "final", check_map, errors);
    rep.valid = valid;
    rep.signatures = sig_results;
    rep.receipt_hash = receipt.receipt_hash().ok();
    rep.merkle_root = document["merkle_root"].as_str().map(String::from);
    rep.node_count = receipt.nodes.len();
    rep.edge_count = receipt.edges.len();
    rep
}

// ------------------------------------------------------------------ proofs

pub fn verify_proof_document(proof_doc: &Value) -> bool {
    (|| -> Result<bool> {
        let item = proof_doc
            .get("item")
            .ok_or_else(|| ReceiptError::shape("missing item"))?;
        let item_type = proof_doc.get("item_type").and_then(Value::as_str);
        let expected_leaf = bytes32_hex(
            proof_doc.get("leaf").ok_or_else(|| ReceiptError::shape("missing leaf"))?,
            "leaf",
        )?;
        let actual_leaf = match item_type {
            Some("node") => {
                ReceiptNode {
                    id: item["id"].as_str().unwrap_or_default().to_string(),
                    kind: item["kind"].as_str().unwrap_or_default().to_string(),
                    payload: item["payload"].clone(),
                    meta: item.get("meta").cloned(),
                }
                .validate()?;
                node_leaf(item)
            }
            Some("edge") => {
                ReceiptEdge {
                    src: item["from"].as_str().unwrap_or_default().to_string(),
                    dst: item["to"].as_str().unwrap_or_default().to_string(),
                    rel: item["rel"].as_str().unwrap_or_default().to_string(),
                }
                .validate()?;
                edge_leaf(item)
            }
            _ => return Ok(false),
        };
        if actual_leaf != expected_leaf {
            return Ok(false);
        }
        let siblings: Vec<[u8; 32]> = proof_doc
            .get("proof")
            .and_then(Value::as_array)
            .ok_or_else(|| ReceiptError::shape("missing proof"))?
            .iter()
            .map(|p| bytes32_hex(p, "proof element"))
            .collect::<Result<Vec<_>>>()?;
        let root = bytes32_hex(
            proof_doc.get("merkle_root").ok_or_else(|| ReceiptError::shape("missing root"))?,
            "root",
        )?;
        Ok(merkle::verify_proof(&actual_leaf, &siblings, &root))
    })()
    .unwrap_or(false)
}
