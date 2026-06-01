"""Calibration compute tests — focus on the Brier-over-time series.

The bucket / overall-Brier maths is exercised indirectly elsewhere; these cases
pin the time-series behaviour added for the dashboard chart: resolution-order
sorting, rolling-window vs cumulative Brier, the coin-flip sanity value, and the
downsample cap that keeps the snapshot light.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from agent.calibration import _DEFAULT_BRIER_WINDOW, _MAX_BRIER_POINTS, compute
from storage.db import Receipt, Session, init_db


def _seed(rid: int, *, prob: float, outcome: float, resolved_offset_days: int) -> None:
    """Insert one resolved receipt with a deterministic resolved_at."""
    with Session() as session:
        session.add(
            Receipt(
                id=rid,
                market_id=f"poly-{rid}",
                market_question=f"market {rid}?",
                market_source="polymarket",
                probability=prob,
                confidence=0.7,
                trace_hash=f"0x{'c' * 64}",
                trace_cid="bafy-cal",
                publisher_address="0xpub",
                paid_micro_usdc=0,
                schema_version="rr-trace/3",
                resolved_at=datetime(2026, 6, 1, tzinfo=UTC) + timedelta(days=resolved_offset_days),
                resolved_outcome=outcome,
            )
        )


def test_brier_over_time_empty_when_no_resolved() -> None:
    init_db()
    report = compute()
    assert report.total_resolved == 0
    assert report.brier_over_time == []


def test_brier_over_time_orders_by_resolution_and_indexes() -> None:
    init_db()
    # Insert out of resolution order; series must come back resolution-ordered.
    _seed(1, prob=0.9, outcome=1.0, resolved_offset_days=3)
    _seed(2, prob=0.1, outcome=0.0, resolved_offset_days=1)
    _seed(3, prob=0.5, outcome=1.0, resolved_offset_days=2)
    series = compute().brier_over_time
    assert [p.index for p in series] == [1, 2, 3]
    # Earliest resolved is receipt 2 (offset 1) → its timestamp leads.
    assert series[0].t.startswith("2026-06-02")
    assert series[1].t.startswith("2026-06-03")
    assert series[2].t.startswith("2026-06-04")


def test_brier_cumulative_matches_running_mean() -> None:
    init_db()
    # Perfect calls → squared error 0 each → cumulative stays 0.
    _seed(1, prob=1.0, outcome=1.0, resolved_offset_days=1)
    _seed(2, prob=0.0, outcome=0.0, resolved_offset_days=2)
    # A miss: predicted 1.0, resolved 0.0 → sq error 1.0.
    _seed(3, prob=1.0, outcome=0.0, resolved_offset_days=3)
    series = compute().brier_over_time
    assert series[0].brier_cumulative == 0.0
    assert series[1].brier_cumulative == 0.0
    # cumulative after 3 = (0 + 0 + 1) / 3
    assert abs(series[2].brier_cumulative - (1.0 / 3.0)) < 1e-9
    # rolling window covers all 3 here (< window), so rolling == cumulative at end.
    assert abs(series[2].brier_rolling - series[2].brier_cumulative) < 1e-9


def test_brier_rolling_window_caps_at_window_size() -> None:
    init_db()
    # More receipts than the window → final rolling point covers exactly `window`.
    n = _DEFAULT_BRIER_WINDOW + 20
    for i in range(1, n + 1):
        _seed(i, prob=0.5, outcome=1.0, resolved_offset_days=i)
    series = compute().brier_over_time
    assert series[-1].n == _DEFAULT_BRIER_WINDOW
    # 0.5 vs 1.0 → squared error 0.25 every time, so rolling Brier == 0.25.
    assert abs(series[-1].brier_rolling - 0.25) < 1e-9


def test_brier_over_time_downsamples_above_cap() -> None:
    init_db()
    n = _MAX_BRIER_POINTS + 50
    for i in range(1, n + 1):
        _seed(i, prob=0.6, outcome=1.0, resolved_offset_days=i)
    series = compute().brier_over_time
    assert len(series) == _MAX_BRIER_POINTS
    # Last point is always preserved exactly so the latest score is honest.
    assert series[-1].index == n
