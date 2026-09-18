//! Cross-language parity check (Rust side). Mirrors
//! scripts/parity/check.py — verifies every emitted receipt and asserts
//! the canonical document bytes are identical across languages.

use reasoning_receipt::canon::{canonical_bytes, parse_json_value};
use reasoning_receipt::verify::verify_any;
use std::fs;
use std::path::PathBuf;
use std::process::ExitCode;

fn main() -> ExitCode {
    let dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("..")
        .join("conformance")
        .join("parity");
    let mut files: Vec<_> = fs::read_dir(&dir)
        .expect("parity dir")
        .filter_map(|e| e.ok())
        .map(|e| e.path())
        .filter(|p| p.file_name().is_some_and(|n| n.to_string_lossy().ends_with(".receipt.json")))
        .collect();
    files.sort();
    if files.is_empty() {
        eprintln!("no parity receipts emitted yet");
        return ExitCode::from(2);
    }

    let mut ok = true;
    let mut canonical: Vec<Vec<u8>> = Vec::new();
    for path in &files {
        let name = path.file_name().unwrap().to_string_lossy().to_string();
        let text = fs::read_to_string(path).expect("read receipt");
        let doc = parse_json_value(&text).expect("parse receipt");
        let report = verify_any(&doc, None);
        let sigs: Vec<bool> = report
            .signatures
            .iter()
            .map(|s| s["valid"].as_bool().unwrap_or(false))
            .collect();
        let mut line = format!(
            "{name}: valid={} sigs={sigs:?} root={:?}",
            report.valid, report.merkle_root
        );
        if !report.valid || !sigs.iter().all(|b| *b) {
            ok = false;
            line += &format!("  ERRORS={:?}", report.errors);
        }
        println!("{line}");
        canonical.push(canonical_bytes(&doc).expect("canonicalize"));
    }

    let unique: std::collections::HashSet<_> = canonical.iter().collect();
    if unique.len() > 1 {
        ok = false;
        eprintln!("canonical bytes differ across languages: {} variants", unique.len());
    } else {
        println!("canonical bytes identical across {} emitters", files.len());
    }
    if ok {
        ExitCode::SUCCESS
    } else {
        ExitCode::FAILURE
    }
}
