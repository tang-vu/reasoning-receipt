"""calibration — score the analyst on resolved receipts.

Computes three things from receipts where `resolved_outcome` has been filled in
by `agent.resolver`:

  1. Brier score — `mean((predicted_p - actual)**2)`. Lower is better. A perfect
     forecaster scores 0; a "50% on everything" forecaster scores ~0.25.
  2. Reliability buckets — group predictions into 10 buckets of probability
     [0-10%, 10-20%, ..., 90-100%]; for each bucket return mean_predicted vs
     mean_actual. A well-calibrated forecaster has mean_predicted ≈ mean_actual
     in every bucket.
  3. Confidence-tier accuracy — for high-conf vs low-conf predictions, what's
     the Brier? A useful agent has lower Brier when its confidence is higher.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select

from storage.db import Receipt as ReceiptRow
from storage.db import Session


@dataclass(slots=True)
class CalibrationBucket:
    label: str            # e.g. "0.30-0.40"
    bucket_min: float
    bucket_max: float
    n: int
    mean_predicted: float  # average predicted probability in this bucket
    mean_actual: float     # fraction of receipts in this bucket where outcome == 1


@dataclass(slots=True)
class CalibrationReport:
    total_resolved: int
    brier_score: float
    brier_high_conf: float | None  # Brier on receipts with confidence >= 0.7
    brier_low_conf: float | None   # Brier on receipts with confidence < 0.7
    buckets: list[CalibrationBucket]
    distinct_resolved_markets: int


_DEFAULT_BUCKETS = 10


def compute(num_buckets: int = _DEFAULT_BUCKETS) -> CalibrationReport:
    with Session() as session:
        rows = list(
            session.execute(
                select(
                    ReceiptRow.probability,
                    ReceiptRow.confidence,
                    ReceiptRow.resolved_outcome,
                    ReceiptRow.market_id,
                ).where(ReceiptRow.resolved_outcome.is_not(None))
            )
        )

    total = len(rows)
    if total == 0:
        return CalibrationReport(
            total_resolved=0,
            brier_score=0.0,
            brier_high_conf=None,
            brier_low_conf=None,
            buckets=[],
            distinct_resolved_markets=0,
        )

    # Overall Brier.
    brier = sum((float(r.probability) - float(r.resolved_outcome)) ** 2 for r in rows) / total

    # Confidence-tier Brier.
    high = [r for r in rows if float(r.confidence) >= 0.7]
    low = [r for r in rows if float(r.confidence) < 0.7]
    brier_high = (
        sum((float(r.probability) - float(r.resolved_outcome)) ** 2 for r in high) / len(high)
        if high
        else None
    )
    brier_low = (
        sum((float(r.probability) - float(r.resolved_outcome)) ** 2 for r in low) / len(low)
        if low
        else None
    )

    # Reliability buckets.
    buckets: list[CalibrationBucket] = []
    width = 1.0 / num_buckets
    for i in range(num_buckets):
        lo = i * width
        hi = lo + width
        bucket_rows = [
            r for r in rows
            if lo <= float(r.probability) < hi
            or (i == num_buckets - 1 and float(r.probability) == 1.0)
        ]
        if not bucket_rows:
            continue
        mean_pred = sum(float(r.probability) for r in bucket_rows) / len(bucket_rows)
        mean_actual = sum(float(r.resolved_outcome) for r in bucket_rows) / len(bucket_rows)
        buckets.append(
            CalibrationBucket(
                label=f"{lo:.2f}-{hi:.2f}",
                bucket_min=lo,
                bucket_max=hi,
                n=len(bucket_rows),
                mean_predicted=mean_pred,
                mean_actual=mean_actual,
            )
        )

    distinct_markets = len({r.market_id for r in rows})

    return CalibrationReport(
        total_resolved=total,
        brier_score=brier,
        brier_high_conf=brier_high,
        brier_low_conf=brier_low,
        buckets=buckets,
        distinct_resolved_markets=distinct_markets,
    )
