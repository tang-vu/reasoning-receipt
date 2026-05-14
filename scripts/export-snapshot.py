"""export-snapshot.py — dump the receipts DB to a static JSON snapshot.

Writes a single `dashboard/public/snapshot.json` with:
  - All receipts (latest first), paginated by limit
  - Pre-computed stats (total, USDC settled, distinct markets/consumers)
  - Per-market aggregates (count, avg probability, last priced)
  - 24-bucket time series for the volume chart

Used to build the dashboard as a static site that runs on Cloudflare Pages,
GitHub Pages, or any static host — no backend required.

Usage:
    uv run python -m scripts.export-snapshot --out dashboard/public/snapshot.json --limit 1000
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from sqlalchemy import desc, func, select

from storage.db import Receipt as ReceiptRow
from storage.db import Session, init_db

logger = logging.getLogger("rr.snapshot")


def _row_to_dict(r: ReceiptRow) -> dict:
    return {
        "id": r.id,
        "market_id": r.market_id,
        "market_source": r.market_source,
        "market_question": r.market_question,
        "probability": r.probability,
        "confidence": r.confidence,
        "trace_hash": r.trace_hash,
        "trace_cid": r.trace_cid,
        "consumer_address": r.consumer_address,
        "arc_tx_hash": r.arc_tx_hash,
        "paid_micro_usdc": r.paid_micro_usdc,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        # rr-trace/3 — None for older rows.
        "schema_version": getattr(r, "schema_version", None),
        "disagreement_pp": getattr(r, "disagreement_pp", None),
        "merkle_root": getattr(r, "merkle_root", None),
        "category": getattr(r, "category", None),
    }


def _bucketize(rows: list[dict], bucket_count: int = 24) -> list[dict]:
    """24 evenly-spaced buckets across the visible window."""
    if not rows:
        return []
    ts = [datetime.fromisoformat(r["created_at"]).timestamp() for r in rows if r.get("created_at")]
    if not ts:
        return []
    t_min, t_max = min(ts), max(ts)
    span = max(1.0, t_max - t_min)
    width = span / bucket_count
    buckets = [
        {
            "label": datetime.fromtimestamp(t_min + i * width).isoformat()[11:16],
            "count": 0,
        }
        for i in range(bucket_count)
    ]
    for t in ts:
        idx = min(bucket_count - 1, int((t - t_min) / width))
        buckets[idx]["count"] += 1
    return buckets


def _per_market(rows: list[dict]) -> list[dict]:
    bucket: dict[str, dict] = defaultdict(
        lambda: {"market_id": "", "question": "", "count": 0, "avg_probability": 0.0, "last_at": ""}
    )
    for r in rows:
        e = bucket[r["market_id"]]
        if e["count"] == 0:
            e["market_id"] = r["market_id"]
            e["question"] = r["market_question"] or r["market_id"]
        e["count"] += 1
        e["avg_probability"] = (
            e["avg_probability"] * (e["count"] - 1) + r["probability"]
        ) / e["count"]
        if not e["last_at"] or (r["created_at"] and r["created_at"] > e["last_at"]):
            e["last_at"] = r["created_at"] or e["last_at"]
    return sorted(bucket.values(), key=lambda x: -x["count"])


def build_snapshot(limit: int = 1000) -> dict:
    with Session() as session:
        rows = [
            _row_to_dict(r)
            for r in session.execute(
                select(ReceiptRow).order_by(desc(ReceiptRow.created_at)).limit(limit)
            ).scalars()
        ]
        total = session.scalar(select(func.count(ReceiptRow.id))) or 0
        paid = session.scalar(select(func.coalesce(func.sum(ReceiptRow.paid_micro_usdc), 0))) or 0
        distinct_markets = (
            session.scalar(select(func.count(func.distinct(ReceiptRow.market_id)))) or 0
        )
        distinct_consumers = (
            session.scalar(select(func.count(func.distinct(ReceiptRow.consumer_address)))) or 0
        )
        latest = session.scalar(select(func.max(ReceiptRow.created_at)))

    # Calibration over resolved receipts (Brier score + reliability buckets).
    try:
        from agent.calibration import compute as compute_calibration

        cal = compute_calibration()
        calibration_block = {
            "total_resolved": cal.total_resolved,
            "distinct_resolved_markets": cal.distinct_resolved_markets,
            "brier_score": cal.brier_score,
            "brier_high_conf": cal.brier_high_conf,
            "brier_low_conf": cal.brier_low_conf,
            "buckets": [
                {
                    "label": b.label,
                    "bucket_min": b.bucket_min,
                    "bucket_max": b.bucket_max,
                    "n": b.n,
                    "mean_predicted": b.mean_predicted,
                    "mean_actual": b.mean_actual,
                }
                for b in cal.buckets
            ],
        }
    except Exception as exc:
        logger.warning("snapshot: calibration compute failed (%s)", exc)
        calibration_block = {
            "total_resolved": 0,
            "distinct_resolved_markets": 0,
            "brier_score": 0.0,
            "brier_high_conf": None,
            "brier_low_conf": None,
            "buckets": [],
        }

    return {
        "version": "rr-snapshot/1",
        "exported_at": datetime.now().astimezone().isoformat(),
        "stats": {
            "total_receipts": int(total),
            "total_paid_micro_usdc": int(paid),
            "distinct_markets": int(distinct_markets),
            "distinct_consumers": int(distinct_consumers),
            "latest_receipt_at": latest.isoformat() if latest else None,
        },
        "receipts": rows,
        "per_market": _per_market(rows),
        "volume_chart": _bucketize(rows),
        "calibration": calibration_block,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export receipts snapshot to JSON.")
    parser.add_argument("--out", default="dashboard/public/snapshot.json")
    parser.add_argument("--limit", type=int, default=1000)
    args = parser.parse_args(argv)

    logging.basicConfig(level="INFO", format="%(asctime)s %(levelname)-7s %(message)s")
    init_db()
    snapshot = build_snapshot(limit=args.limit)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
    logger.info(
        "snapshot: wrote %d receipts → %s (%.1f KB)",
        len(snapshot["receipts"]),
        out_path,
        out_path.stat().st_size / 1024,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
