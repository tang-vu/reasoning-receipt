/** RR-Canonical-JSON-1 (`rr-json-1`) — spec §7. Byte-for-byte parity with
 * `protocol/canon.py` is a hard requirement.
 *
 * Contract: UTF-8, no BOM, zero whitespace; object keys sorted by UTF-8
 * byte order with duplicates rejected; minimal string escaping; numbers by
 * value (|v| < 2^53, integral → decimal digits, non-integral → fixed 6
 * fraction digits, no negative zero); lone surrogates rejected. */
export declare const CANONICALIZATION_ID = "rr-json-1";
export type JsonValue = null | boolean | number | string | JsonValue[] | {
    [k: string]: JsonValue;
};
export declare function canonicalBytes(value: JsonValue): Uint8Array;
export declare function canonicalString(value: JsonValue): string;
/** Parse JSON text strictly for envelope ingest: duplicate keys and
 * non-object roots are rejected, matching `protocol.canon.parse_json_object`. */
export declare function parseJsonObject(text: string | Uint8Array): Record<string, JsonValue>;
