/** SHA-256 sorted-pair Merkle tree — spec §7. Mirrors protocol/merkle.py:
 * raw 32-byte leaves, ordered-pair concat, odd leaf promoted (not duplicated),
 * direction-free proofs. */
export declare function sha256Hex(data: Uint8Array): string;
export declare function digestBytes(hex: string): Uint8Array;
export declare function merkleRoot(leaves: Uint8Array[]): string;
/** Direction-free sibling path from leaf index to root (spec §8). */
export declare function merkleProof(leaves: Uint8Array[], index: number): string[];
export declare function verifyMerkleProof(root: string, leaf: Uint8Array, siblings: string[]): boolean;
