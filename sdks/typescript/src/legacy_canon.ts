/** `legacy-json-6dp` — the frozen canonicalization used by rr-trace/* and
 * draft-era reasoning-receipt/1 documents (spec §14). Mirrors
 * `protocol/legacy_canon.py` byte-for-byte, including Python `repr` float
 * formatting. */

import { ReceiptError } from "./errors.js";

export const LEGACY_CANONICALIZATION_ID = "legacy-json-6dp";

const encoder = new TextEncoder();

function round6(x: number): number {
  // Python: float(f"{x:.6f}") — format to 6dp then re-parse.
  // JS toFixed throws RangeError for |x| >= 1e21; every double in that
  // range is already integral so the value passes through unchanged.
  if (Math.abs(x) >= 1e21) return x;
  return Number(x.toFixed(6));
}

/** Python repr() of a float, emulated on JS numbers.
 * Rules: integral -> "N.0"; exponent form when exp10 < -4 or >= 16
 * (mantissa stripped of trailing zeros); otherwise decimal shortest repr
 * (which matches JS String(n) for the rounded values that occur here). */
function pyReprFloat(x: number): string {
  if (!Number.isFinite(x)) {
    throw new ReceiptError("malformed_number", "non-finite in legacy canon");
  }
  if (Object.is(x, -0)) return "-0.0";
  if (x === 0) return "0.0";
  if (Number.isInteger(x)) {
    const a = Math.abs(x);
    if (a >= 1e16) return expForm(x);
    return String(x) + ".0";
  }
  const a = Math.abs(x);
  const e = Math.floor(Math.log10(a));
  if (e < -4 || e >= 16) return expForm(x);
  return String(x);
}

function expForm(x: number): string {
  // Build "d.dddde+XX" like CPython repr for floats needing exponent form.
  const s = String(Math.abs(x));
  let digits: string;
  let exp: number;
  if (s.includes("e")) {
    // JS already in exponent form e.g. "1e+21", "1.5e-7"
    const m = /^(\d)(?:\.(\d+))?e([+-]\d+)$/.exec(s);
    if (!m) throw new ReceiptError("malformed_number");
    digits = (m[1] + (m[2] ?? "")).replace(/0+$/, "");
    exp = parseInt(m[3], 10);
  } else if (s.includes(".")) {
    // small values like "0.00001" -> exponent -5
    const m = /^0\.0*([1-9]\d*)$/.exec(s);
    if (m) {
      digits = m[1].replace(/0+$/, "");
      exp = -(s.indexOf(m[1]) - 1);
    } else {
      // e.g. "1.5" never reaches here (|x|>=1e16 is integer)
      digits = s.replace(".", "").replace(/0+$/, "");
      exp = s.indexOf(".") - 1;
    }
  } else {
    // large integer digits "10000000000000000"
    digits = s.replace(/0+$/, "");
    exp = s.length - 1;
  }
  const mant = digits.length === 1 ? digits : digits[0] + "." + digits.slice(1);
  const sign = x < 0 ? "-" : "";
  const expSign = exp < 0 ? "-" : "+";
  return `${sign}${mant}e${expSign}${String(Math.abs(exp)).padStart(2, "0")}`;
}

function norm(obj: unknown): unknown {
  if (typeof obj === "number") return round6(obj);
  if (Array.isArray(obj)) return obj.map(norm);
  if (obj !== null && typeof obj === "object") {
    const out: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(obj)) out[k] = norm(v);
    return out;
  }
  return obj;
}

function encode(v: unknown): string {
  if (v === null) return "null";
  if (typeof v === "boolean") return v ? "true" : "false";
  if (typeof v === "number") return pyReprFloat(v);
  if (typeof v === "string") {
    // json.dumps(ensure_ascii=True): escape non-ASCII as \uXXXX (+surrogates).
    let out = '"';
    for (let i = 0; i < v.length; i++) {
      const cp = v.charCodeAt(i);
      switch (cp) {
        case 0x22: out += '\\"'; break;
        case 0x5c: out += "\\\\"; break;
        case 0x08: out += "\\b"; break;
        case 0x09: out += "\\t"; break;
        case 0x0a: out += "\\n"; break;
        case 0x0c: out += "\\f"; break;
        case 0x0d: out += "\\r"; break;
        default:
          if (cp < 0x20 || cp > 0x7e) {
            out += "\\u" + cp.toString(16).padStart(4, "0");
          } else {
            out += v[i];
          }
      }
    }
    return out + '"';
  }
  if (Array.isArray(v)) return "[" + v.map(encode).join(",") + "]";
  if (typeof v === "object") {
    // json.dumps(sort_keys=True) sorts by code point; UTF-8 byte order is
    // equivalent to code-point order and differs from JS UTF-16 ordering
    // for astral keys.
    const keys = Object.keys(v as object)
      .map((k) => ({ k, b: encoder.encode(k) }))
      .sort((a, b) => {
        const m = Math.min(a.b.length, b.b.length);
        for (let i = 0; i < m; i++) {
          if (a.b[i] !== b.b[i]) return a.b[i] - b.b[i];
        }
        return a.b.length - b.b.length;
      })
      .map(({ k }) => k);
    const parts = keys.map(
      (k) => encode(k) + ":" + encode((v as Record<string, unknown>)[k]),
    );
    return "{" + parts.join(",") + "}";
  }
  throw new ReceiptError("malformed_document");
}

export function legacyCanonicalBytes(doc: Record<string, unknown>): Uint8Array {
  return encoder.encode(encode(norm(doc)));
}
