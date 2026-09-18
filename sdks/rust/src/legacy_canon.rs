//! `legacy-json-6dp` — the frozen canonicalization used by `rr-trace/*` and
//! draft-era `reasoning-receipt/1` documents (spec §14). Mirrors
//! `protocol/legacy_canon.py` byte-for-byte, including CPython `repr` float
//! formatting.

use serde_json::Value;

pub const LEGACY_CANONICALIZATION_ID: &str = "legacy-json-6dp";

fn round6(x: f64) -> f64 {
    if !x.is_finite() {
        return x;
    }
    if x.abs() >= 1e21 {
        return x; // Python f"{x:.6f}" handles big values; every f64 there is integral
    }
    format!("{x:.6}").parse().unwrap_or(x)
}

/// CPython repr() of a float.
fn py_repr_float(x: f64) -> String {
    if x == 0.0 {
        return if x.is_sign_negative() { "-0.0".into() } else { "0.0".into() };
    }
    if x == x.trunc() && x.abs() < 1e16 {
        return format!("{}.0", x as i64);
    }
    let e = x.abs().log10().floor() as i32;
    if e < -4 || e >= 16 || (x == x.trunc() && x.abs() >= 1e16) {
        return exp_form(x);
    }
    // Shortest round-trip repr: Rust's {} on f64 gives the same digits.
    format!("{x}")
}

fn exp_form(x: f64) -> String {
    // Produce "d.ddde+XX" like CPython repr.
    let s = format!("{:e}", x.abs()); // e.g. "1.5e16", "1e-5", "1.234e20"
    let (mant, exp) = s.split_once('e').unwrap();
    let mut digits: String = mant.chars().filter(|c| *c != '.').collect();
    while digits.len() > 1 && digits.ends_with('0') {
        digits.pop();
    }
    let exp: i32 = exp.parse().unwrap();
    let mantissa = if digits.len() == 1 {
        digits
    } else {
        format!("{}.{}", &digits[..1], &digits[1..])
    };
    format!(
        "{}{}e{}{:02}",
        if x < 0.0 { "-" } else { "" },
        mantissa,
        if exp < 0 { "-" } else { "+" },
        exp.abs()
    )
}

fn norm(v: &Value) -> Value {
    match v {
        Value::Number(n) => {
            if let Some(f) = n.as_f64() {
                if !f.is_finite() {
                    return v.clone();
                }
                if n.is_f64() {
                    // Preserve floatness: integral floats stay floats after round6
                    let r = round6(f);
                    if r == r.trunc() && r.abs() < 1e16 {
                        return Value::from(r); // still f64 → repr "N.0"
                    }
                    Value::from(r)
                } else {
                    v.clone() // ints pass through unchanged
                }
            } else {
                v.clone()
            }
        }
        Value::Array(a) => Value::Array(a.iter().map(norm).collect()),
        Value::Object(m) => Value::Object(m.iter().map(|(k, v)| (k.clone(), norm(v))).collect()),
        _ => v.clone(),
    }
}

fn encode(v: &Value, out: &mut String) {
    match v {
        Value::Null => out.push_str("null"),
        Value::Bool(b) => out.push_str(if *b { "true" } else { "false" }),
        Value::Number(n) => {
            if let Some(f) = n.as_f64() {
                if n.is_f64() {
                    out.push_str(&py_repr_float(f));
                } else {
                    out.push_str(&n.to_string());
                }
            }
        }
        Value::String(s) => encode_str(s, out),
        Value::Array(a) => {
            out.push('[');
            for (i, x) in a.iter().enumerate() {
                if i > 0 {
                    out.push(',');
                }
                encode(x, out);
            }
            out.push(']');
        }
        Value::Object(m) => {
            // json.dumps(sort_keys=True): Python str ordering = code-point
            // order = UTF-8 byte order.
            let mut keys: Vec<&String> = m.keys().collect();
            keys.sort_by(|a, b| a.as_bytes().cmp(b.as_bytes()));
            out.push('{');
            for (i, k) in keys.iter().enumerate() {
                if i > 0 {
                    out.push(',');
                }
                encode_str(k, out);
                out.push(':');
                encode(&m[*k], out);
            }
            out.push('}');
        }
    }
}

/// json.dumps(ensure_ascii=True): escape non-ASCII as \uXXXX (+ surrogate pairs).
fn encode_str(s: &str, out: &mut String) {
    out.push('"');
    for c in s.chars() {
        match c {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\u{08}' => out.push_str("\\b"),
            '\t' => out.push_str("\\t"),
            '\n' => out.push_str("\\n"),
            '\u{0c}' => out.push_str("\\f"),
            '\r' => out.push_str("\\r"),
            c if (c as u32) < 0x20 => out.push_str(&format!("\\u{:04x}", c as u32)),
            c if (c as u32) > 0x7e => {
                let cp = c as u32;
                if cp > 0xffff {
                    let v = cp - 0x10000;
                    out.push_str(&format!(
                        "\\u{:04x}\\u{:04x}",
                        0xd800 + (v >> 10),
                        0xdc00 + (v & 0x3ff)
                    ));
                } else {
                    out.push_str(&format!("\\u{:04x}", cp));
                }
            }
            c => out.push(c),
        }
    }
    out.push('"');
}

pub fn legacy_canonical_bytes(doc: &Value) -> Vec<u8> {
    let mut out = String::new();
    encode(&norm(doc), &mut out);
    out.into_bytes()
}
