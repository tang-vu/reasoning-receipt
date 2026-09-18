/** Optional Ed25519 signatures for `reasoning-receipt/1` (spec §8).
 * Mirrors `protocol/signatures.py`. Signatures live outside the committed
 * envelope: `receipt` scope signs the 32-byte receipt_hash, `node:<id>`
 * signs one node leaf. A valid signature proves key possession only. */
import type { JsonValue } from "./canon.js";
export declare const ALG_ED25519 = "ed25519";
export declare function generateKeypair(): {
    private_key: string;
    public_key: string;
};
export interface SignatureObject {
    alg: string;
    scope: string;
    public_key: string;
    sig: string;
    signed_at: string;
    key_id?: string;
    meta?: Record<string, JsonValue>;
}
export declare function sign(committedEnvelope: Record<string, JsonValue>, privateKeyHex: string, opts?: {
    scope?: string;
    key_id?: string;
    signed_at?: string;
    meta?: Record<string, JsonValue>;
}): SignatureObject;
export interface SignatureResult {
    index: number;
    valid: boolean;
    scope?: string;
    public_key?: string;
    reason?: string;
}
export declare function verifySignatures(committedEnvelope: Record<string, JsonValue>, signatures: unknown[]): SignatureResult[];
