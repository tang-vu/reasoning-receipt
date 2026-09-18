"""MCP adapter for reasoning-receipt/1 — stdio server exposing protocol tools.

Tools (all fully offline; no network, chain or clock authority is used):

  create_receipt   build + finalize a receipt from nodes/edges/spec
  verify_receipt   full structural + commitment verification report
  create_proof     inclusion proof for one node (or edge, canonical order)
  verify_proof     independent verification of a proof document
  inspect_receipt  summary view: schema, counts, hashes, checks

Run:
    uv run python -m protocol.mcp_server            # stdio transport
    uv run rr-mcp                                    # console script
"""

from __future__ import annotations

from typing import Any

from mcp.server.mcpserver import MCPServer

from .receipt import (
    ReceiptBuilder,
    restore_receipt,
    verify_proof_document,
)
from .verify import supported_schemas, verify_any

server = MCPServer(
    name="reasoning-receipt",
    version="0.1.0",
    description=(
        "Portable evidence receipts for AI decisions and actions — "
        "create, verify and prove reasoning-receipt/1 documents offline."
    ),
)


@server.tool(description="Build a reasoning-receipt/1 document. nodes: [{id, kind, payload, meta?}]; edges: [{from, to, rel}].")
def create_receipt(
    subject: str,
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]] | None = None,
    metadata: dict[str, Any] | None = None,
    receipt_id: str | None = None,
    produced_at: str | None = None,
) -> dict[str, Any]:
    builder = ReceiptBuilder(subject, metadata=metadata or {})
    for node in nodes:
        builder.add(
            node["id"],
            node["kind"],
            node.get("payload"),
            meta=node.get("meta"),
        )
    for edge in edges or []:
        builder.link(edge["from"], edge["to"], edge["rel"])
    kwargs: dict[str, Any] = {}
    if receipt_id is not None:
        kwargs["receipt_id"] = receipt_id
    if produced_at is not None:
        kwargs["produced_at"] = produced_at
    return builder.finalize(**kwargs).to_dict()


@server.tool(description="Verify a receipt or proof-envelope document offline. Returns the full report: checks, errors, per-signature outcomes.")
def verify_receipt(document: dict[str, Any], expected_hash: str | None = None) -> dict[str, Any]:
    report = verify_any(document, expected_hash=expected_hash)
    return report.to_dict()


@server.tool(description="Create an inclusion proof for one node id — or one edge index in canonical edge order — inside a receipt document.")
def create_proof(
    document: dict[str, Any],
    node_id: str | None = None,
    edge_index: int | None = None,
) -> dict[str, Any]:
    receipt = restore_receipt(document)
    if node_id is not None:
        return receipt.proof_for(node_id)
    if edge_index is not None:
        return receipt.proof_for_edge(edge_index)
    raise ValueError("create_proof requires node_id or edge_index")


@server.tool(description="Independently verify an inclusion proof document against its embedded root. Returns {verify: bool}.")
def verify_proof(proof_document: dict[str, Any]) -> dict[str, Any]:
    return {"verify": verify_proof_document(proof_document)}


@server.tool(description="Summarize a receipt document: schema, variant, node/edge counts, hashes, per-check outcomes.")
def inspect_receipt(document: dict[str, Any]) -> dict[str, Any]:
    report = verify_any(document)
    return {
        "schema_version": report.schema_version,
        "variant": report.variant,
        "canonicalization": report.canonicalization,
        "valid": report.valid,
        "node_count": report.node_count,
        "edge_count": report.edge_count,
        "merkle_root": report.merkle_root,
        "receipt_hash": report.receipt_hash,
        "checks": report.checks,
        "errors": report.errors,
        "signatures": report.signatures,
        "supported_schemas": supported_schemas(),
    }


def main() -> None:
    server.run("stdio")


if __name__ == "__main__":
    main()
