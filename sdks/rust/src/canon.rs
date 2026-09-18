//! RR-Canonical-JSON-1 (`rr-json-1`) — spec §7. Byte-for-byte parity with
//! `protocol/canon.py` is a hard requirement.

use crate::errors::{E_LIMIT, E_NONCANONICAL, ReceiptError, Result};
use serde_json::{Map, Number, Value};

pub const CANONICALIZATION_ID: &str = "rr-json-1";

const MAX_DEPTH: usize = 64;
const MAX_KEY_LENGTH: usize = 256;
const MAX_STRING_LENGTH: usize = 1 << 20; // 1 MiB
const PORTABLE_INT_ABS_MAX: u64 = (1u64 << 53) - 1; // ±(2^53-1)
const PORTABLE_ABS_BOUND: f64 = 9_007_199_254_740_992.0; // 2^53

fn check_string(value: &str, what: &str) -> Result<()> {
    if value.chars().count() > MAX_STRING_LENGTH {
        return Err(ReceiptError::new(
            E_LIMIT,
            format!("{what} exceeds {MAX_STRING_LENGTH} chars"),
        ));
    }
    // Rust strings are always valid UTF-8 — lone surrogates cannot exist.
    Ok(())
}

fn encode_string(value: &str, out: &mut String) -> Result<()> {
    check_string(value, "string")?;
    out.push('"');
    for ch in value.chars() {
        match ch {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\u{08}' => out.push_str("\\b"),
            '\u{0c}' => out.push_str("\\f"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            c if (c as u32) < 0x20 => out.push_str(&format!("\\u{:04x}", c as u32)),
            c => out.push(c),
        }
    }
    out.push('"');
    Ok(())
}

fn encode_f64(value: f64, out: &mut String) -> Result<()> {
    if !value.is_finite() {
        return Err(ReceiptError::new(
            E_NONCANONICAL,
            "non-finite number is not canonicalizable",
        ));
    }
    if value.abs() >= PORTABLE_ABS_BOUND {
        return Err(ReceiptError::new(
            E_NONCANONICAL,
            format!("number {value} outside portable range 2^53"),
        ));
    }
    if value == value.trunc() {
        // Integral: decimal digits; -0.0 → "0"
        out.push_str(&format!("{}", value as i64));
        return Ok(());
    }
    let mut fixed = format!("{value:.6}");
    if fixed.starts_with('-') && fixed[1..].parse::<f64>().unwrap_or(1.0) == 0.0 {
        fixed.remove(0);
    }
    if fixed.ends_with(".000000") {
        // Rounding collapsed the value to an integer — emit integer form
        // so canonical output reparses to the same canonical bytes.
        fixed.truncate(fixed.len() - ".000000".len());
    }
    out.push_str(&fixed);
    Ok(())
}

fn encode(value: &Value, out: &mut String, depth: usize) -> Result<()> {
    if depth > MAX_DEPTH {
        return Err(ReceiptError::new(E_LIMIT, format!("nesting exceeds {MAX_DEPTH}")));
    }
    match value {
        Value::Null => out.push_str("null"),
        Value::Bool(b) => out.push_str(if *b { "true" } else { "false" }),
        Value::Number(n) => encode_number(n, out)?,
        Value::String(s) => encode_string(s, out)?,
        Value::Array(items) => {
            out.push('[');
            for (i, item) in items.iter().enumerate() {
                if i > 0 {
                    out.push(',');
                }
                encode(item, out, depth + 1)?;
            }
            out.push(']');
        }
        Value::Object(map) => {
            let mut pairs: Vec<(&String, &Value)> = Vec::with_capacity(map.len());
            let mut seen = std::collections::HashSet::new();
            for (key, item) in map.iter() {
                if key.chars().count() > MAX_KEY_LENGTH {
                    return Err(ReceiptError::new(
                        E_LIMIT,
                        format!("object key exceeds {MAX_KEY_LENGTH} chars"),
                    ));
                }
                check_string(key, "object key")?;
                let encoded = key.as_bytes();
                if !seen.insert(encoded.to_vec()) {
                    return Err(ReceiptError::new(
                        E_NONCANONICAL,
                        format!("duplicate object key {key}"),
                    ));
                }
                pairs.push((key, item));
            }
            pairs.sort_by(|a, b| a.0.as_bytes().cmp(b.0.as_bytes()));
            out.push('{');
            for (i, (key, item)) in pairs.iter().enumerate() {
                if i > 0 {
                    out.push(',');
                }
                encode_string(key, out)?;
                out.push(':');
                encode(item, out, depth + 1)?;
            }
            out.push('}');
        }
    }
    Ok(())
}

fn encode_number(n: &Number, out: &mut String) -> Result<()> {
    if let Some(i) = n.as_i64() {
        if i.unsigned_abs() > PORTABLE_INT_ABS_MAX {
            return Err(ReceiptError::new(
                E_NONCANONICAL,
                format!("integer {i} outside portable range ±(2^53-1)"),
            ));
        }
        out.push_str(&i.to_string());
        return Ok(());
    }
    if let Some(u) = n.as_u64() {
        if u > PORTABLE_INT_ABS_MAX {
            return Err(ReceiptError::new(
                E_NONCANONICAL,
                format!("integer {u} outside portable range ±(2^53-1)"),
            ));
        }
        out.push_str(&u.to_string());
        return Ok(());
    }
    let f = n.as_f64().ok_or_else(|| {
        ReceiptError::new(E_NONCANONICAL, "non-JSON number")
    })?;
    encode_f64(f, out)
}

pub fn canonical_string(value: &Value) -> Result<String> {
    let mut out = String::new();
    encode(value, &mut out, 0)?;
    Ok(out)
}

pub fn canonical_bytes(value: &Value) -> Result<Vec<u8>> {
    Ok(canonical_string(value)?.into_bytes())
}

/// Parse any JSON value strictly (recursive descent — serde_json can't
/// surface duplicate keys or tolerate the surrogate cases the protocol
/// must reject explicitly). Lone-surrogate `\uXXXX` escapes are rejected
/// with `noncanonical_value` — Python reaches the same code one stage
/// later at encode time; the observable code is identical.
pub fn parse_json_value(text: &str) -> Result<Value> {
    let mut p = Parser { s: text.as_bytes(), pos: 0 };
    p.ws();
    let v = p.value(0)?;
    p.ws();
    if p.pos != p.s.len() {
        return Err(ReceiptError::new(E_NONCANONICAL, "invalid JSON: trailing data"));
    }
    Ok(v)
}

/// Parse JSON text strictly for envelope ingest — duplicate keys and
/// non-object roots rejected, matching `parse_json_object`.
pub fn parse_json_object(text: &str) -> Result<Map<String, Value>> {
    match parse_json_value(text)? {
        Value::Object(map) => Ok(map),
        _ => Err(ReceiptError::new(
            E_NONCANONICAL,
            "receipt document is not a JSON object",
        )),
    }
}

struct Parser<'a> {
    s: &'a [u8],
    pos: usize,
}

impl<'a> Parser<'a> {
    fn ws(&mut self) {
        while self.pos < self.s.len() && matches!(self.s[self.pos], b' ' | b'\t' | b'\n' | b'\r') {
            self.pos += 1;
        }
    }

    fn peek(&self) -> Option<u8> {
        self.s.get(self.pos).copied()
    }

    fn err(&self, msg: &str) -> ReceiptError {
        ReceiptError::new(E_NONCANONICAL, format!("invalid JSON: {msg}"))
    }

    fn value(&mut self, depth: usize) -> Result<Value> {
        if depth > MAX_DEPTH {
            return Err(ReceiptError::new(E_LIMIT, format!("nesting exceeds {MAX_DEPTH}")));
        }
        match self.peek() {
            Some(b'"') => Ok(Value::String(self.string()?)),
            Some(b'{') => self.object(depth),
            Some(b'[') => self.array(depth),
            Some(b't') => self.literal(b"true", Value::Bool(true)),
            Some(b'f') => self.literal(b"false", Value::Bool(false)),
            Some(b'n') => self.literal(b"null", Value::Null),
            Some(b'-') | Some(b'0'..=b'9') => self.number(),
            _ => Err(self.err("unexpected token")),
        }
    }

    fn literal(&mut self, word: &[u8], v: Value) -> Result<Value> {
        if self.s.len() >= self.pos + word.len() && &self.s[self.pos..self.pos + word.len()] == word {
            self.pos += word.len();
            Ok(v)
        } else {
            Err(self.err("bad literal"))
        }
    }

    fn string(&mut self) -> Result<String> {
        self.pos += 1; // opening quote
        let mut out = String::new();
        loop {
            let c = self.peek().ok_or_else(|| self.err("unterminated string"))?;
            match c {
                b'"' => {
                    self.pos += 1;
                    return Ok(out);
                }
                b'\\' => {
                    self.pos += 1;
                    let e = self.peek().ok_or_else(|| self.err("bad escape"))?;
                    self.pos += 1;
                    match e {
                        b'"' => out.push('"'),
                        b'\\' => out.push('\\'),
                        b'/' => out.push('/'),
                        b'b' => out.push('\u{08}'),
                        b'f' => out.push('\u{0c}'),
                        b'n' => out.push('\n'),
                        b'r' => out.push('\r'),
                        b't' => out.push('\t'),
                        b'u' => {
                            let cp = self.hex4()?;
                            if (0xd800..=0xdbff).contains(&cp) {
                                // High surrogate must pair with \uDC00-\uDFFF.
                                if self.peek() == Some(b'\\')
                                    && self.s.get(self.pos + 1) == Some(&b'u')
                                {
                                    self.pos += 2;
                                    let lo = self.hex4()?;
                                    if (0xdc00..=0xdfff).contains(&lo) {
                                        let combined =
                                            0x10000 + ((cp - 0xd800) << 10) + (lo - 0xdc00);
                                        out.push(
                                            char::from_u32(combined)
                                                .ok_or_else(|| self.err("bad surrogate pair"))?,
                                        );
                                        continue;
                                    }
                                    return Err(ReceiptError::new(
                                        E_NONCANONICAL,
                                        "unpaired surrogate escape",
                                    ));
                                }
                                return Err(ReceiptError::new(
                                    E_NONCANONICAL,
                                    "unpaired surrogate escape",
                                ));
                            }
                            if (0xdc00..=0xdfff).contains(&cp) {
                                return Err(ReceiptError::new(
                                    E_NONCANONICAL,
                                    "unpaired surrogate escape",
                                ));
                            }
                            out.push(char::from_u32(cp).ok_or_else(|| self.err("bad \\u escape"))?);
                        }
                        _ => return Err(self.err("bad escape")),
                    }
                }
                0x00..=0x1f => return Err(self.err("raw control character")),
                _ => {
                    // Copy one UTF-8 encoded char verbatim (input is &str —
                    // already valid UTF-8).
                    let len = utf8_len(c);
                    let chunk = std::str::from_utf8(&self.s[self.pos..self.pos + len])
                        .map_err(|_| self.err("bad utf-8"))?;
                    out.push_str(chunk);
                    self.pos += len;
                }
            }
        }
    }

    fn hex4(&mut self) -> Result<u32> {
        if self.pos + 4 > self.s.len() {
            return Err(self.err("bad \\u escape"));
        }
        let hex = std::str::from_utf8(&self.s[self.pos..self.pos + 4])
            .map_err(|_| self.err("bad \\u escape"))?;
        let cp = u32::from_str_radix(hex, 16).map_err(|_| self.err("bad \\u escape"))?;
        self.pos += 4;
        Ok(cp)
    }

    fn number(&mut self) -> Result<Value> {
        let start = self.pos;
        if self.peek() == Some(b'-') {
            self.pos += 1;
        }
        match self.peek() {
            Some(b'0') => self.pos += 1,
            Some(b'1'..=b'9') => {
                while matches!(self.peek(), Some(b'0'..=b'9')) {
                    self.pos += 1;
                }
            }
            _ => return Err(self.err("bad number")),
        }
        if self.peek() == Some(b'.') {
            self.pos += 1;
            if !matches!(self.peek(), Some(b'0'..=b'9')) {
                return Err(self.err("bad number"));
            }
            while matches!(self.peek(), Some(b'0'..=b'9')) {
                self.pos += 1;
            }
        }
        if matches!(self.peek(), Some(b'e') | Some(b'E')) {
            self.pos += 1;
            if matches!(self.peek(), Some(b'+') | Some(b'-')) {
                self.pos += 1;
            }
            if !matches!(self.peek(), Some(b'0'..=b'9')) {
                return Err(self.err("bad number"));
            }
            while matches!(self.peek(), Some(b'0'..=b'9')) {
                self.pos += 1;
            }
        }
        let text = std::str::from_utf8(&self.s[start..self.pos]).unwrap();
        serde_json::from_str(text).map_err(|_| self.err("bad number"))
    }

    fn array(&mut self, depth: usize) -> Result<Value> {
        self.pos += 1;
        let mut out = Vec::new();
        self.ws();
        if self.peek() == Some(b']') {
            self.pos += 1;
            return Ok(Value::Array(out));
        }
        loop {
            self.ws();
            out.push(self.value(depth + 1)?);
            self.ws();
            match self.peek() {
                Some(b',') => self.pos += 1,
                Some(b']') => {
                    self.pos += 1;
                    return Ok(Value::Array(out));
                }
                _ => return Err(self.err("expected ',' or ']'")),
            }
        }
    }

    fn object(&mut self, depth: usize) -> Result<Value> {
        self.pos += 1;
        let mut out = Map::new();
        self.ws();
        if self.peek() == Some(b'}') {
            self.pos += 1;
            return Ok(Value::Object(out));
        }
        loop {
            self.ws();
            if self.peek() != Some(b'"') {
                return Err(self.err("expected key"));
            }
            let key = self.string()?;
            if out.contains_key(&key) {
                return Err(ReceiptError::new(
                    E_NONCANONICAL,
                    format!("duplicate object key {key}"),
                ));
            }
            self.ws();
            if self.peek() != Some(b':') {
                return Err(self.err("expected ':'"));
            }
            self.pos += 1;
            self.ws();
            let v = self.value(depth + 1)?;
            out.insert(key, v);
            self.ws();
            match self.peek() {
                Some(b',') => self.pos += 1,
                Some(b'}') => {
                    self.pos += 1;
                    return Ok(Value::Object(out));
                }
                _ => return Err(self.err("expected ',' or '}'")),
            }
        }
    }
}

fn utf8_len(first: u8) -> usize {
    match first {
        0x00..=0x7f => 1,
        0xc0..=0xdf => 2,
        0xe0..=0xef => 3,
        _ => 4,
    }
}
