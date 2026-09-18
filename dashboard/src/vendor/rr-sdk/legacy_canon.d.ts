/** `legacy-json-6dp` — the frozen canonicalization used by rr-trace/* and
 * draft-era reasoning-receipt/1 documents (spec §14). Mirrors
 * `protocol/legacy_canon.py` byte-for-byte, including Python `repr` float
 * formatting. */
export declare const LEGACY_CANONICALIZATION_ID = "legacy-json-6dp";
export declare function legacyCanonicalBytes(doc: Record<string, unknown>): Uint8Array;
