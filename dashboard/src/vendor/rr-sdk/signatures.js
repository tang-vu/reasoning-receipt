/** Optional Ed25519 signatures for `reasoning-receipt/1` (spec §8).
 * Mirrors `protocol/signatures.py`. Signatures live outside the committed
 * envelope: `receipt` scope signs the 32-byte receipt_hash, `node:<id>`
 * signs one node leaf. A valid signature proves key possession only. */
import { etc, sign as edSign, verify as edVerify, getPublicKey } from "@noble/ed25519";
import { sha512 } from "@noble/hashes/sha2.js";
import { E_BAD_SIGNATURE, SignatureError } from "./errors.js";
import { nodeLeaf, receiptHashOf, validTimestamp } from "./receipt.js";
import { bytesToHex, hexToBytes } from "./hex.js";
export const ALG_ED25519 = "ed25519";
const SIG_DOMAIN_RECEIPT = concat(te("RR1:sig:receipt"), new Uint8Array([0]));
const SIG_DOMAIN_NODE = concat(te("RR1:sig:node"), new Uint8Array([0]));
const SIG_FIELDS = new Set(["alg", "scope", "public_key", "sig", "signed_at", "key_id", "meta"]);
const SIG_REQUIRED = ["alg", "scope", "public_key", "sig"];
function te(s) {
    return new TextEncoder().encode(s);
}
function concat(a, b) {
    const out = new Uint8Array(a.length + b.length);
    out.set(a, 0);
    out.set(b, a.length);
    return out;
}
// @noble/ed25519 v2 requires an explicit sync SHA-512 implementation.
etc.sha512Sync = (...msgs) => sha512(msgs.reduce((a, m) => concat(a, m), new Uint8Array()));
function decodeKey(hexValue, length, what) {
    if (typeof hexValue !== "string") {
        throw new SignatureError(`${what} is not a string`, E_BAD_SIGNATURE);
    }
    const raw = hexValue.startsWith("0x") ? hexValue.slice(2) : hexValue;
    if (!/^[0-9a-fA-F]*$/.test(raw)) {
        throw new SignatureError(`${what} is not hex`, E_BAD_SIGNATURE);
    }
    const decoded = hexToBytes(raw);
    if (decoded.length !== length) {
        throw new SignatureError(`${what} must be ${length} bytes`, E_BAD_SIGNATURE);
    }
    return decoded;
}
function utcNowIso() {
    return new Date().toISOString().replace(/\.\d{3}Z$/, "Z");
}
export function generateKeypair() {
    const seed = crypto.getRandomValues(new Uint8Array(32));
    return {
        private_key: "0x" + bytesToHex(seed),
        public_key: "0x" + bytesToHex(getPublicKey(seed)),
    };
}
export function sign(committedEnvelope, privateKeyHex, opts = {}) {
    const scope = opts.scope ?? "receipt";
    const seed = decodeKey(privateKeyHex, 32, "private_key");
    const publicKey = getPublicKey(seed);
    let preimage;
    if (scope === "receipt") {
        const target = hexToBytes(receiptHashOf(committedEnvelope));
        preimage = concat(SIG_DOMAIN_RECEIPT, Uint8Array.from(target));
    }
    else if (scope.startsWith("node:")) {
        const nodeId = scope.slice(5);
        const leaves = {};
        const nodes = (committedEnvelope.nodes ?? []);
        for (const nd of nodes)
            leaves[nd.id] = nodeLeaf(nd);
        if (!(nodeId in leaves)) {
            throw new SignatureError(`node ${nodeId} not in envelope`, E_BAD_SIGNATURE);
        }
        preimage = concat(SIG_DOMAIN_NODE, leaves[nodeId]);
    }
    else {
        throw new SignatureError(`unknown signature scope ${scope}`, E_BAD_SIGNATURE);
    }
    const signedAt = opts.signed_at ?? utcNowIso();
    if (opts.signed_at !== undefined && !validTimestamp(signedAt)) {
        throw new SignatureError(`invalid signed_at ${signedAt}`, E_BAD_SIGNATURE);
    }
    const sigBytes = edSign(preimage, seed);
    const sig = {
        alg: ALG_ED25519,
        scope,
        public_key: "0x" + bytesToHex(publicKey),
        sig: "0x" + bytesToHex(sigBytes),
        signed_at: signedAt,
    };
    if (opts.key_id !== undefined)
        sig.key_id = opts.key_id;
    if (opts.meta !== undefined)
        sig.meta = opts.meta;
    return sig;
}
export function verifySignatures(committedEnvelope, signatures) {
    const results = [];
    for (const [index, raw] of signatures.entries()) {
        const result = { index, valid: false };
        try {
            if (raw === null || typeof raw !== "object" || Array.isArray(raw)) {
                throw new SignatureError("signature is not an object");
            }
            const sig = raw;
            const missing = SIG_REQUIRED.filter((k) => !(k in sig));
            if (missing.length) {
                throw new SignatureError(`signature missing ${JSON.stringify(missing.sort())}`);
            }
            const extra = Object.keys(sig).filter((k) => !SIG_FIELDS.has(k));
            if (extra.length) {
                throw new SignatureError(`signature has unknown fields ${JSON.stringify(extra.sort())}`);
            }
            result.scope = sig.scope;
            result.public_key = sig.public_key;
            if (sig.alg !== ALG_ED25519) {
                throw new SignatureError(`unsupported alg ${String(sig.alg)}`);
            }
            if ("signed_at" in sig && !validTimestamp(sig.signed_at)) {
                throw new SignatureError("invalid signed_at");
            }
            const publicKey = decodeKey(sig.public_key, 32, "public_key");
            const signature = decodeKey(sig.sig, 64, "sig");
            let preimage;
            if (sig.scope === "receipt") {
                const target = hexToBytes(receiptHashOf(committedEnvelope));
                preimage = concat(SIG_DOMAIN_RECEIPT, Uint8Array.from(target));
            }
            else if (sig.scope.startsWith("node:")) {
                const nodeId = sig.scope.slice(5);
                const leaves = {};
                const nodes = (committedEnvelope.nodes ?? []);
                for (const nd of nodes)
                    leaves[nd.id] = nodeLeaf(nd);
                if (!(nodeId in leaves)) {
                    throw new SignatureError(`node ${nodeId} not in envelope`);
                }
                preimage = concat(SIG_DOMAIN_NODE, leaves[nodeId]);
            }
            else {
                throw new SignatureError(`unknown scope ${String(sig.scope)}`);
            }
            result.valid = edVerify(signature, preimage, publicKey);
            if (!result.valid)
                result.reason = "signature verification failed";
        }
        catch (exc) {
            if (exc instanceof SignatureError) {
                result.reason = exc.message;
            }
            else {
                throw exc;
            }
        }
        results.push(result);
    }
    return results;
}
