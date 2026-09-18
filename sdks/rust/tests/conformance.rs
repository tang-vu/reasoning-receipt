//! Runs every vector in the shared language-independent corpus.

use reasoning_receipt::conformance::run_corpus;
use std::path::PathBuf;

#[test]
fn conformance_corpus() {
    let dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("..")
        .join("conformance")
        .join("vectors");
    let report = run_corpus(&dir);
    for v in &report.vectors {
        assert!(v.ok, "{}: {}", v.name, v.detail);
    }
    assert!(report.ok, "{}/{} vectors passed", report.passed, report.total);
}
