"""`rr` — the ReasoningReceipt command line. Fully offline.

    rr canon FILE          canonical bytes for a JSON document
    rr hash FILE           receipt_hash (or content hash for legacy schemas)
    rr verify FILE         full structural + commitment verification
    rr inspect FILE        human-readable receipt summary
    rr proof FILE --node ID | --edge N
                           inclusion proof for one committed item
    rr verify-proof FILE   verify a proof document standalone
    rr sign FILE --key 0x… [--scope receipt|node:ID] [--key-id NAME]
    rr conformance [--dir] run the language-independent vector corpus
    rr schemas             list schema versions this build understands

Everything works on plain files — no server, chain, or storage provider.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import click

from .bundle import verify_bundle
from .canon import canonical_bytes, parse_json_object
from .legacy import legacy_trace_hash
from .receipt import (
    SCHEMA_VERSION,
    dumps,
    restore_receipt,
    verify_proof_document,
)
from .signatures import generate_keypair, sign, signature_backend
from .verify import supported_schemas, verify_any


def _read_document(path: str) -> dict[str, Any]:
    raw = Path(path).read_bytes() if path != "-" else sys.stdin.buffer.read()
    return parse_json_object(raw)


def _emit_json(data: Any) -> None:
    click.echo(json.dumps(data, indent=2, ensure_ascii=False))


@click.group()
@click.version_option(message="reasoning-receipt %(version)s")
def cli() -> None:
    """ReasoningReceipt — portable, byte-verifiable receipts for AI decisions."""


@cli.command()
@click.argument("path")
def canon(path: str) -> None:
    """Print the RR-Canonical-JSON-1 bytes of FILE (raw, to stdout)."""
    doc = _read_document(path)
    sys.stdout.buffer.write(canonical_bytes(doc))
    sys.stdout.buffer.write(b"\n")


@cli.command()
@click.argument("path")
def hash_cmd(path: str) -> None:
    """Print the commitment hash of FILE (receipt_hash or legacy blob hash)."""
    doc = _read_document(path)
    schema = doc.get("schema_version")
    if schema == SCHEMA_VERSION:
        receipt = restore_receipt(doc)
        click.echo(receipt.receipt_hash())
    elif isinstance(schema, str) and schema.startswith("rr-trace/"):
        click.echo(legacy_trace_hash(doc))
    else:
        raise click.ClickException(f"unsupported schema_version {schema!r}")


@cli.command()
@click.argument("path")
@click.option("--expected-hash", default=None, help="Anchored hash to compare (legacy blob schemas).")
@click.option("--json", "as_json", is_flag=True, help="Machine-readable report.")
def verify(path: str, expected_hash: str | None, as_json: bool) -> None:
    """Verify FILE: shape, graph, hashes, Merkle root, signatures. Exit 1 on failure."""
    doc = _read_document(path)
    report = verify_any(doc, expected_hash=expected_hash)
    if as_json:
        _emit_json(report.to_dict())
    else:
        verdict = "VALID" if report.valid else "INVALID"
        click.echo(f"verdict           : {verdict}")
        click.echo(f"schema_version    : {report.schema_version}")
        click.echo(f"variant           : {report.variant}")
        click.echo(f"canonicalization  : {report.canonicalization}")
        click.echo(f"nodes / edges     : {report.node_count} / {report.edge_count}")
        if report.merkle_root:
            click.echo(f"merkle_root       : {report.merkle_root}")
        if report.receipt_hash:
            click.echo(f"content hash      : {report.receipt_hash}")
        for name, ok in report.checks.items():
            click.echo(f"  check {name:<14}: {'ok' if ok else 'FAIL'}")
        for i, sig in enumerate(report.signatures):
            state = "valid" if sig.get("valid") else f"INVALID ({sig.get('reason', '?')})"
            click.echo(f"  signature[{i}]    : {sig.get('scope', '?')} — {state}")
        for error in report.errors:
            click.echo(f"  error           : {error}")
    sys.exit(0 if report.valid else 1)


@cli.command()
@click.argument("path")
@click.option("--json", "as_json", is_flag=True)
def inspect(path: str, as_json: bool) -> None:
    """Show a receipt's structure — nodes, edges, hashes, signatures."""
    doc = _read_document(path)
    report = verify_any(doc)
    if as_json:
        _emit_json({"document": doc, "verification": report.to_dict()})
        return
    click.echo(f"schema_version : {doc.get('schema_version')}")
    click.echo(f"receipt_id     : {doc.get('receipt_id')}")
    click.echo(f"subject        : {doc.get('subject')}")
    click.echo(f"produced_at    : {doc.get('produced_at')}")
    click.echo(f"merkle_root    : {doc.get('merkle_root')}")
    click.echo(f"receipt_hash   : {doc.get('receipt_hash')}")
    nodes = doc.get("nodes") or []
    click.echo(f"nodes          : {len(nodes)}")
    for node in nodes:
        short = json.dumps(node.get("payload"), ensure_ascii=False)
        click.echo(f"  - {node.get('id')}  [{node.get('kind')}]  {short[:90]}")
    edges = doc.get("edges") or []
    click.echo(f"edges          : {len(edges)}")
    for edge in edges:
        click.echo(f"  - {edge.get('from')} -{edge.get('rel')}-> {edge.get('to')}")
    sigs = doc.get("signatures") or []
    click.echo(f"signatures     : {len(sigs)}")
    for sig in sigs:
        click.echo(f"  - {sig.get('scope')}  {sig.get('alg')}  {sig.get('public_key', '')[:20]}…")
    click.echo(f"verification   : {'VALID' if report.valid else 'INVALID'} ({report.variant})")


@cli.command()
@click.argument("path")
@click.option("--node", "node_id", default=None, help="Node id to prove.")
@click.option("--edge", "edge_index", type=int, default=None, help="Edge index (canonical order) to prove.")
def proof(path: str, node_id: str | None, edge_index: int | None) -> None:
    """Emit an inclusion proof document for one node or edge."""
    doc = _read_document(path)
    receipt = restore_receipt(doc)
    if node_id is not None:
        _emit_json(receipt.proof_for(node_id))
    elif edge_index is not None:
        _emit_json(receipt.proof_for_edge(edge_index))
    else:
        raise click.ClickException("pass --node ID or --edge N")


@cli.command(name="verify-proof")
@click.argument("path")
@click.option("--json", "as_json", is_flag=True)
def verify_proof_cmd(path: str, as_json: bool) -> None:
    """Verify a standalone inclusion proof document."""
    doc = _read_document(path)
    ok = verify_proof_document(doc)
    if as_json:
        _emit_json({"valid": ok})
    else:
        click.echo(f"verdict : {'VALID' if ok else 'INVALID'}")
    sys.exit(0 if ok else 1)


@cli.command()
@click.argument("path")
@click.option("--key", "private_key", required=True, help="0x-hex 32-byte Ed25519 seed.")
@click.option("--scope", default="receipt", help="'receipt' or 'node:<id>'.")
@click.option("--key-id", default=None)
@click.option("--out", "out_path", default=None, help="Write signed receipt here (default: stdout).")
def sign_cmd(path: str, private_key: str, scope: str, key_id: str | None, out_path: str | None) -> None:
    """Sign FILE's committed envelope with Ed25519; emit the signed receipt."""
    doc = _read_document(path)
    receipt = restore_receipt(doc)
    committed = receipt.committed_envelope()
    committed.setdefault("receipt_id", doc["receipt_id"])
    signatures = list(doc.get("signatures") or [])
    signatures.append(sign(committed, private_key, scope=scope, key_id=key_id))
    receipt.signatures = signatures
    output = dumps(receipt.to_dict())
    if out_path:
        Path(out_path).write_text(output + "\n", encoding="utf-8")
        click.echo(f"wrote {out_path}", err=True)
    else:
        click.echo(output)


@cli.command(name="keygen")
def keygen() -> None:
    """Generate an Ed25519 keypair (private seed + public key, hex)."""
    private, public = generate_keypair()
    click.echo(f"private_key : {private}")
    click.echo(f"public_key  : {public}")
    click.echo("store the private key in a secret manager — it signs receipts")


@cli.command()
@click.option("--dir", "vector_dir", default=None, help="Vector directory (default: conformance/vectors).")
@click.option("--json", "as_json", is_flag=True)
def conformance(vector_dir: str | None, as_json: bool) -> None:
    """Run the language-independent conformance corpus."""
    from .conformance import run_corpus

    base = Path(vector_dir) if vector_dir else Path(__file__).resolve().parent.parent / "conformance" / "vectors"
    results = run_corpus(base)
    if as_json:
        _emit_json(results)
    else:
        for entry in results["vectors"]:
            mark = "ok" if entry["ok"] else "FAIL"
            click.echo(f"  [{mark}] {entry['name']}" + (f" — {entry.get('detail','')}" if not entry["ok"] else ""))
        click.echo(
            f"conformance: {results['passed']}/{results['total']} vectors "
            f"({'PASS' if results['ok'] else 'FAIL'})"
        )
    sys.exit(0 if results["ok"] else 1)


@cli.command()
@click.option("--json", "as_json", is_flag=True)
def schemas(as_json: bool) -> None:
    """List schema versions this build verifies."""
    data = supported_schemas()
    if as_json:
        _emit_json({"schemas": data, "signature_backend": signature_backend()})
    else:
        for entry in data:
            click.echo(
                f"{entry['schema_version']:<24} {entry['status']:<8} "
                f"{entry['canonicalization']:<18} {', '.join(entry['features'])}"
            )


@cli.command(name="verify-bundle")
@click.argument("path")
def verify_bundle_cmd(path: str) -> None:
    """Verify a .rrbundle container (manifest hashes, paths, sizes)."""
    bundle = _read_document(path)
    report = verify_bundle(bundle)
    click.echo(f"bundle_version  : {bundle.get('bundle_version')}")
    click.echo(f"files           : {report.file_count} ({report.total_bytes} bytes)")
    for name, ok in report.checked.items():
        click.echo(f"  [{'ok' if ok else 'FAIL'}] {name}")
    click.echo(f"verdict         : {'VALID' if report.valid else 'INVALID'}")
    sys.exit(0 if report.valid else 1)


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
