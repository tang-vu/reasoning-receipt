//! SHA-256 sorted-pair Merkle tree — spec §6. Mirrors `protocol/merkle.py`:
//! raw 32-byte leaves, ordered-pair concat, odd node promoted (never
//! duplicated), direction-free proofs.

use crate::errors::{E_BAD_HASH, Result, ReceiptError};
use sha2::{Digest, Sha256};

pub fn sha256_hex(data: &[u8]) -> String {
    format!("0x{}", hex_encode(&Sha256::digest(data)))
}

pub fn hex_encode(b: &[u8]) -> String {
    b.iter().map(|x| format!("{x:02x}")).collect()
}

pub fn hex_decode(s: &str) -> Result<Vec<u8>> {
    let raw = s.strip_prefix("0x").unwrap_or(s);
    if raw.len() % 2 != 0 || !raw.chars().all(|c| c.is_ascii_hexdigit()) {
        return Err(ReceiptError::new(E_BAD_HASH, format!("{s} is not hex")));
    }
    (0..raw.len())
        .step_by(2)
        .map(|i| {
            u8::from_str_radix(&raw[i..i + 2], 16)
                .map_err(|_| ReceiptError::new(E_BAD_HASH, format!("{s} is not hex")))
        })
        .collect()
}

fn parent(a: &[u8; 32], b: &[u8; 32]) -> [u8; 32] {
    let (lo, hi) = if a <= b { (a, b) } else { (b, a) };
    let mut h = Sha256::new();
    h.update(lo);
    h.update(hi);
    h.finalize().into()
}

pub fn merkle_root(leaves: &[[u8; 32]]) -> [u8; 32] {
    assert!(!leaves.is_empty(), "merkle root of empty set");
    let mut level: Vec<[u8; 32]> = leaves.to_vec();
    while level.len() > 1 {
        let mut next = Vec::with_capacity(level.len().div_ceil(2));
        for pair in level.chunks(2) {
            if pair.len() == 1 {
                next.push(pair[0]); // promote odd node
            } else {
                next.push(parent(&pair[0], &pair[1]));
            }
        }
        level = next;
    }
    level[0]
}

/// Direction-free sibling path (bottom-up). Promoted odd nodes contribute
/// no sibling — mirrors Python exactly.
pub fn merkle_proof(leaves: &[[u8; 32]], index: usize) -> Vec<[u8; 32]> {
    assert!(index < leaves.len(), "leaf index out of range");
    let mut siblings = Vec::new();
    let mut level: Vec<[u8; 32]> = leaves.to_vec();
    let mut idx = index;
    while level.len() > 1 {
        let sib = if idx % 2 == 0 { idx + 1 } else { idx - 1 };
        if sib < level.len() {
            siblings.push(level[sib]);
        }
        let mut next = Vec::with_capacity(level.len().div_ceil(2));
        for pair in level.chunks(2) {
            if pair.len() == 1 {
                next.push(pair[0]);
            } else {
                next.push(parent(&pair[0], &pair[1]));
            }
        }
        idx /= 2;
        level = next;
    }
    siblings
}

pub fn verify_proof(leaf: &[u8; 32], siblings: &[[u8; 32]], root: &[u8; 32]) -> bool {
    let mut node = *leaf;
    for sib in siblings {
        node = parent(&node, sib);
    }
    node == *root
}
