/** RR-Canonical-JSON-1 (`rr-json-1`) — spec §7. Byte-for-byte parity with
 * `protocol/canon.py` is a hard requirement.
 *
 * Contract: UTF-8, no BOM, zero whitespace; object keys sorted by UTF-8
 * byte order with duplicates rejected; minimal string escaping; numbers by
 * value (|v| < 2^53, integral → decimal digits, non-integral → fixed 6
 * fraction digits, no negative zero); lone surrogates rejected. */

import { CanonError, E_LIMIT, E_NONCANONICAL } from "./errors.js";

export const CANONICALIZATION_ID = "rr-json-1";

const MAX_DEPTH = 64;
const MAX_KEY_LENGTH = 256;
const MAX_STRING_LENGTH = 1 << 20; // 1 MiB
const PORTABLE_ABS_BOUND = 0x20000000000000; // 2^53

const ESCAPES: Record<number, string> = {
  0x22: '\\"',
  0x5c: "\\\\",
  0x08: "\\b",
  0x0c: "\\f",
  0x0a: "\\n",
  0x0d: "\\r",
  0x09: "\\t",
};

const encoder = new TextEncoder();

export type JsonValue =
  | null
  | boolean
  | number
  | string
  | JsonValue[]
  | { [k: string]: JsonValue };

function checkString(value: string, what: string): void {
  if (value.length > MAX_STRING_LENGTH) {
    throw new CanonError(`${what} exceeds ${MAX_STRING_LENGTH} chars`, E_LIMIT);
  }
  for (const ch of value) {
    const cp = ch.codePointAt(0)!;
    if (cp >= 0xd800 && cp <= 0xdfff) {
      throw new CanonError(
        `${what} contains an unpaired surrogate (U+${cp.toString(16).toUpperCase().padStart(4, "0")})`,
        E_NONCANONICAL,
      );
    }
  }
}

function encodeString(value: string, out: string[]): void {
  checkString(value, "string");
  out.push('"');
  for (const ch of value) {
    const cp = ch.codePointAt(0)!;
    const esc = ESCAPES[cp];
    if (esc !== undefined) {
      out.push(esc);
    } else if (cp < 0x20) {
      out.push("\\u" + cp.toString(16).padStart(4, "0"));
    } else {
      out.push(ch);
    }
  }
  out.push('"');
}

function encodeNumber(value: number, out: string[]): void {
  if (!Number.isFinite(value)) {
    throw new CanonError("non-finite number is not canonicalizable", E_NONCANONICAL);
  }
  if (Math.abs(value) >= PORTABLE_ABS_BOUND) {
    throw new CanonError(
      `number ${value} outside portable range 2^53`,
      E_NONCANONICAL,
    );
  }
  if (Number.isInteger(value)) {
    // |v| < 2^53 ⇒ String(v) yields exact decimal digits; String(-0) === "0".
    out.push(String(value));
    return;
  }
  let fixed = value.toFixed(6);
  if (fixed.startsWith("-") && Number(fixed) === 0) fixed = fixed.slice(1);
  if (fixed.endsWith(".000000")) {
    // Rounding collapsed the value to an integer — emit integer form so
    // canonical output reparses to the same canonical bytes.
    fixed = fixed.slice(0, -".000000".length);
  }
  out.push(fixed);
}

function encode(value: JsonValue, out: string[], depth: number): void {
  if (depth > MAX_DEPTH) {
    throw new CanonError(`nesting exceeds ${MAX_DEPTH}`, E_LIMIT);
  }
  if (value === null) {
    out.push("null");
  } else if (typeof value === "boolean") {
    out.push(value ? "true" : "false");
  } else if (typeof value === "number") {
    encodeNumber(value, out);
  } else if (typeof value === "string") {
    encodeString(value, out);
  } else if (Array.isArray(value)) {
    out.push("[");
    value.forEach((item, i) => {
      if (i) out.push(",");
      encode(item, out, depth + 1);
    });
    out.push("]");
  } else if (typeof value === "object") {
    const pairs: { bytes: Uint8Array; key: string; item: JsonValue }[] = [];
    const seen = new Set<string>();
    for (const key of Object.keys(value)) {
      if (key.length > MAX_KEY_LENGTH) {
        throw new CanonError(`object key exceeds ${MAX_KEY_LENGTH} chars`, E_LIMIT);
      }
      checkString(key, "object key");
      if (seen.has(key)) {
        throw new CanonError(`duplicate object key ${key}`, E_NONCANONICAL);
      }
      seen.add(key);
      pairs.push({ bytes: encoder.encode(key), key, item: value[key] });
    }
    pairs.sort((a, b) => {
      const m = Math.min(a.bytes.length, b.bytes.length);
      for (let i = 0; i < m; i++) {
        if (a.bytes[i] !== b.bytes[i]) return a.bytes[i] - b.bytes[i];
      }
      return a.bytes.length - b.bytes.length;
    });
    out.push("{");
    pairs.forEach(({ key, item }, i) => {
      if (i) out.push(",");
      encodeString(key, out);
      out.push(":");
      encode(item, out, depth + 1);
    });
    out.push("}");
  } else {
    throw new CanonError(
      `unsupported type ${typeof value} is not canonicalizable`,
      E_NONCANONICAL,
    );
  }
}

export function canonicalBytes(value: JsonValue): Uint8Array {
  const out: string[] = [];
  encode(value, out, 0);
  return encoder.encode(out.join(""));
}

export function canonicalString(value: JsonValue): string {
  const out: string[] = [];
  encode(value, out, 0);
  return out.join("");
}

/* ---------- strict JSON parsing for envelope ingest ---------- */

function noDupesReviver() {
  // JSON.parse can't surface duplicate keys; we walk the raw text with a
  // minimal recursive-descent parser below instead.
  return undefined;
}
void noDupesReviver;

class Parser {
  private i = 0;
  constructor(private s: string) {}

  parseObject(): Record<string, JsonValue> {
    this.ws();
    const v = this.value(0);
    this.ws();
    if (this.i !== this.s.length) {
      throw new CanonError("invalid JSON: trailing data", E_NONCANONICAL);
    }
    if (v === null || typeof v !== "object" || Array.isArray(v)) {
      throw new CanonError("receipt document is not a JSON object", E_NONCANONICAL);
    }
    return v as Record<string, JsonValue>;
  }

  private ws(): void {
    while (this.i < this.s.length) {
      const c = this.s.charCodeAt(this.i);
      if (c === 0x20 || c === 0x09 || c === 0x0a || c === 0x0d) this.i++;
      else break;
    }
  }

  private peek(): number {
    return this.i < this.s.length ? this.s.charCodeAt(this.i) : -1;
  }

  private value(depth: number): JsonValue {
    if (depth > MAX_DEPTH) throw new CanonError("nesting exceeds limit", E_LIMIT);
    const c = this.peek();
    if (c === 0x22) return this.string();
    if (c === 0x7b) return this.object(depth);
    if (c === 0x5b) return this.array(depth);
    if (c === 0x74) return this.literal("true", true);
    if (c === 0x66) return this.literal("false", false);
    if (c === 0x6e) return this.literal("null", null);
    if (c === 0x2d || (c >= 0x30 && c <= 0x39)) return this.number();
    // NaN / Infinity literals are non-JSON — reject like Python's parse_constant.
    throw new CanonError("invalid JSON", E_NONCANONICAL);
  }

  private literal(word: string, v: JsonValue): JsonValue {
    if (this.s.slice(this.i, this.i + word.length) !== word) {
      throw new CanonError("invalid JSON", E_NONCANONICAL);
    }
    this.i += word.length;
    return v;
  }

  private string(): string {
    this.i++;
    let out = "";
    while (true) {
      if (this.i >= this.s.length) throw new CanonError("invalid JSON: unterminated string", E_NONCANONICAL);
      const c = this.s.charCodeAt(this.i);
      if (c === 0x22) {
        this.i++;
        return out;
      }
      if (c < 0x20) throw new CanonError("invalid JSON: raw control char", E_NONCANONICAL);
      if (c === 0x5c) {
        this.i++;
        const e = this.s[this.i];
        switch (e) {
          case '"': case "\\": case "/": out += e; this.i++; break;
          case "b": out += "\b"; this.i++; break;
          case "f": out += "\f"; this.i++; break;
          case "n": out += "\n"; this.i++; break;
          case "r": out += "\r"; this.i++; break;
          case "t": out += "\t"; this.i++; break;
          case "u": {
            const hex = this.s.slice(this.i + 1, this.i + 5);
            if (!/^[0-9a-fA-F]{4}$/.test(hex)) {
              throw new CanonError("invalid JSON: bad \\u escape", E_NONCANONICAL);
            }
            let cp = parseInt(hex, 16);
            this.i += 5;
            if (cp >= 0xd800 && cp <= 0xdbff) {
              if (this.s[this.i] === "\\" && this.s[this.i + 1] === "u") {
                const hex2 = this.s.slice(this.i + 2, this.i + 6);
                if (/^[0-9a-fA-F]{4}$/.test(hex2)) {
                  const lo = parseInt(hex2, 16);
                  if (lo >= 0xdc00 && lo <= 0xdfff) {
                    cp = 0x10000 + ((cp - 0xd800) << 10) + (lo - 0xdc00);
                    this.i += 6;
                    out += String.fromCodePoint(cp);
                    break;
                  }
                }
              }
              // Lone surrogate escapes decode but fail canonicalization later
              out += String.fromCharCode(cp);
              break;
            }
            out += String.fromCharCode(cp);
            break;
          }
          default:
            throw new CanonError("invalid JSON: bad escape", E_NONCANONICAL);
        }
      } else {
        out += this.s[this.i];
        this.i++;
      }
    }
  }

  private number(): number {
    const start = this.i;
    if (this.peek() === 0x2d) this.i++;
    if (this.peek() === 0x30) {
      this.i++;
    } else if (this.peek() >= 0x31 && this.peek() <= 0x39) {
      while (this.peek() >= 0x30 && this.peek() <= 0x39) this.i++;
    } else {
      throw new CanonError("invalid JSON: bad number", E_NONCANONICAL);
    }
    if (this.peek() === 0x2e) {
      this.i++;
      if (!(this.peek() >= 0x30 && this.peek() <= 0x39)) {
        throw new CanonError("invalid JSON: bad number", E_NONCANONICAL);
      }
      while (this.peek() >= 0x30 && this.peek() <= 0x39) this.i++;
    }
    if (this.peek() === 0x65 || this.peek() === 0x45) {
      this.i++;
      if (this.peek() === 0x2b || this.peek() === 0x2d) this.i++;
      if (!(this.peek() >= 0x30 && this.peek() <= 0x39)) {
        throw new CanonError("invalid JSON: bad number", E_NONCANONICAL);
      }
      while (this.peek() >= 0x30 && this.peek() <= 0x39) this.i++;
    }
    return Number(this.s.slice(start, this.i));
  }

  private array(depth: number): JsonValue[] {
    this.i++;
    const out: JsonValue[] = [];
    this.ws();
    if (this.peek() === 0x5d) {
      this.i++;
      return out;
    }
    while (true) {
      this.ws();
      out.push(this.value(depth + 1));
      this.ws();
      const c = this.peek();
      if (c === 0x2c) {
        this.i++;
      } else if (c === 0x5d) {
        this.i++;
        return out;
      } else {
        throw new CanonError("invalid JSON", E_NONCANONICAL);
      }
    }
  }

  private object(depth: number): Record<string, JsonValue> {
    this.i++;
    const out: Record<string, JsonValue> = {};
    const seen = new Set<string>();
    this.ws();
    if (this.peek() === 0x7d) {
      this.i++;
      return out;
    }
    while (true) {
      this.ws();
      if (this.peek() !== 0x22) throw new CanonError("invalid JSON: expected key", E_NONCANONICAL);
      const k = this.string();
      if (seen.has(k)) {
        throw new CanonError(`duplicate object key ${k}`, E_NONCANONICAL);
      }
      seen.add(k);
      this.ws();
      if (this.peek() !== 0x3a) throw new CanonError("invalid JSON: expected ':'", E_NONCANONICAL);
      this.i++;
      this.ws();
      out[k] = this.value(depth + 1);
      this.ws();
      const c = this.peek();
      if (c === 0x2c) {
        this.i++;
      } else if (c === 0x7d) {
        this.i++;
        return out;
      } else {
        throw new CanonError("invalid JSON", E_NONCANONICAL);
      }
    }
  }
}

/** Parse JSON text strictly for envelope ingest: duplicate keys and
 * non-object roots are rejected, matching `protocol.canon.parse_json_object`. */
export function parseJsonObject(text: string | Uint8Array): Record<string, JsonValue> {
  const s = typeof text === "string" ? text : new TextDecoder().decode(text);
  return new Parser(s).parseObject();
}
