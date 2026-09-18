/** SHA-256 sorted-pair Merkle tree — spec §7. Mirrors protocol/merkle.py:
 * raw 32-byte leaves, ordered-pair concat, odd leaf promoted (not duplicated),
 * direction-free proofs. */

import { sha256 } from "@noble/hashes/sha2.js";
import { ReceiptError } from "./errors.js";

export function sha256Hex(data: Uint8Array): string {
  return "0x" + Buffer.from(sha256(data)).toString("hex");
}

export function hexToBytes(hex: string): Uint8Array {
  if (!/^0x[0-9a-f]{64}$/.test(hex)) throw new ReceiptError("invalid_hash", hex);
  return Uint8Array.from(Buffer.from(hex.slice(2), "hex"));
}

function cmpBytes(a: Uint8Array, b: Uint8Array): number {
  const m = Math.min(a.length, b.length);
  for (let i = 0; i < m; i++) {
    if (a[i] !== b[i]) return a[i] - b[i];
  }
  return a.length - b.length;
}

export function merkleRoot(leaves: Uint8Array[]): string {
  if (leaves.length === 0) throw new ReceiptError("malformed_document", "no leaves");
  let level = [...leaves];
  while (level.length > 1) {
    const next: Uint8Array[] = [];
    for (let i = 0; i < level.length; i += 2) {
      if (i + 1 === level.length) {
        next.push(level[i]); // promote odd leaf
      } else {
        const [a, b] = [level[i], level[i + 1]].sort(cmpBytes);
        next.push(sha256(concat(a, b)));
      }
    }
    level = next;
  }
  return "0x" + Buffer.from(level[0]).toString("hex");
}

function concat(a: Uint8Array, b: Uint8Array): Uint8Array {
  const out = new Uint8Array(a.length + b.length);
  out.set(a, 0);
  out.set(b, a.length);
  return out;
}

/** Direction-free sibling path from leaf index to root (spec §8). */
export function merkleProof(leaves: Uint8Array[], index: number): string[] {
  if (index < 0 || index >= leaves.length) {
    throw new ReceiptError("malformed_proof", "leaf index out of range");
  }
  const siblings: string[] = [];
  let level = [...leaves];
  let idx = index;
  while (level.length > 1) {
    const next: Uint8Array[] = [];
    const sib = idx % 2 === 0 ? idx + 1 : idx - 1;
    for (let i = 0; i < level.length; i += 2) {
      if (i + 1 === level.length) {
        next.push(level[i]);
      } else {
        const [a, b] = [level[i], level[i + 1]].sort(cmpBytes);
        next.push(sha256(concat(a, b)));
      }
    }
    if (sib < level.length) {
      siblings.push("0x" + Buffer.from(level[sib]).toString("hex"));
    }
    idx = Math.floor(idx / 2);
    level = next;
  }
  return siblings;
}

export function verifyMerkleProof(root: string, leaf: Uint8Array, siblings: string[]): boolean {
  let node = leaf;
  for (const sib of siblings) {
    const s = hexToBytes(sib);
    const [a, b] = [node, s].sort(cmpBytes);
    node = sha256(concat(a, b));
  }
  return "0x" + Buffer.from(node).toString("hex") === root;
}
