"""Phase 5 — per-category calibration store tests.

Covers: stats math, sample-size threshold gating, bias direction phrasing,
empty-state graceful handling, and the cache TTL behaviour.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest

from agent.calibration_store import (
    CATEGORIES,
    MIN_SAMPLE,
    CalibrationStore,
    CategoryStats,
    _category_stats,
)


class _Row:
    """Light stand-in for a SQLAlchemy result row."""

    def __init__(self, category: str | None, probability: float, resolved_outcome: float) -> None:
        self.category = category
        self.probability = probability
        self.resolved_outcome = resolved_outcome


# ---------------------------------------------------------------------------
# stats math
# ---------------------------------------------------------------------------


def test_category_stats_empty_category_returns_zero() -> None:
    stats = _category_stats([], "macro")
    assert stats.n == 0
    assert stats.brier == 0.0
    assert stats.over_under_bias == 0.0


def test_category_stats_perfect_predictor_brier_zero() -> None:
    rows = [
        _Row("macro", 0.0, 0.0),
        _Row("macro", 1.0, 1.0),
        _Row("macro", 0.5, 0.5),
    ]
    stats = _category_stats(rows, "macro")
    assert stats.n == 3
    assert stats.brier == pytest.approx(0.0)
    assert stats.over_under_bias == pytest.approx(0.0)


def test_category_stats_over_under_bias_sign() -> None:
    """Predicted higher than actual → positive bias (overconfident YES)."""
    rows = [_Row("crypto", 0.8, 0.0), _Row("crypto", 0.7, 0.0)]
    stats = _category_stats(rows, "crypto")
    assert stats.over_under_bias > 0
    # And brier = mean of (0.8 - 0)^2 = 0.64, (0.7 - 0)^2 = 0.49 → 0.565
    assert stats.brier == pytest.approx(0.565, abs=0.001)


def test_category_stats_filters_by_category() -> None:
    rows = [_Row("macro", 0.5, 0.0), _Row("crypto", 0.5, 1.0)]
    macro = _category_stats(rows, "macro")
    crypto = _category_stats(rows, "crypto")
    assert macro.n == 1 and crypto.n == 1
    assert macro.over_under_bias == pytest.approx(0.5)
    assert crypto.over_under_bias == pytest.approx(-0.5)


def test_category_stats_treats_null_category_as_other() -> None:
    rows = [_Row(None, 0.5, 0.0)]
    stats = _category_stats(rows, "other")
    assert stats.n == 1


# ---------------------------------------------------------------------------
# Prior text rendering
# ---------------------------------------------------------------------------


def _stub_store(rows: list[_Row]) -> CalibrationStore:
    """Build a CalibrationStore whose DB fetcher returns `rows`."""
    store = CalibrationStore()
    with patch("agent.calibration_store._fetch_resolved", return_value=rows):
        # Prime cache once.
        store._refresh_if_stale()
    return store


def test_prior_text_empty_when_no_category_meets_min_sample() -> None:
    rows = [_Row("macro", 0.6, 0.0) for _ in range(MIN_SAMPLE - 1)]
    store = _stub_store(rows)
    assert store.prior_text() == ""


def test_prior_text_includes_only_categories_with_signal() -> None:
    rows = (
        [_Row("macro", 0.6, 0.0) for _ in range(MIN_SAMPLE + 2)]
        + [_Row("crypto", 0.5, 0.5)]  # below threshold
    )
    store = _stub_store(rows)
    text = store.prior_text()
    assert "macro" in text
    assert "crypto" not in text
    assert text.startswith("Past-performance prior")


def test_prior_text_describes_overconfident_yes() -> None:
    rows = [_Row("politics", 0.85, 0.0) for _ in range(MIN_SAMPLE + 1)]
    store = _stub_store(rows)
    text = store.prior_text()
    assert "overconfident YES" in text


def test_prior_text_describes_overconfident_no() -> None:
    rows = [_Row("sports", 0.1, 1.0) for _ in range(MIN_SAMPLE + 1)]
    store = _stub_store(rows)
    text = store.prior_text()
    assert "overconfident NO" in text


def test_prior_text_describes_well_calibrated() -> None:
    rows = [
        _Row("tech", 0.5, 0.5),
        _Row("tech", 0.4, 0.4),
        _Row("tech", 0.6, 0.6),
        _Row("tech", 0.7, 0.7),
        _Row("tech", 0.3, 0.3),
    ]
    store = _stub_store(rows)
    text = store.prior_text()
    assert "well calibrated" in text


# ---------------------------------------------------------------------------
# Cache + stats_for / all_stats
# ---------------------------------------------------------------------------


def test_stats_for_returns_zero_when_no_signal() -> None:
    rows = [_Row("macro", 0.5, 0.0)]
    store = _stub_store(rows)
    crypto = store.stats_for("crypto")
    assert isinstance(crypto, CategoryStats)
    assert crypto.n == 0


def test_all_stats_returns_every_category() -> None:
    store = _stub_store([])
    all_stats = store.all_stats()
    assert set(all_stats.keys()) == set(CATEGORIES)


def test_cache_avoids_refetching_within_ttl() -> None:
    call_count = {"n": 0}

    def fake_fetch(_window_days: int) -> list:
        call_count["n"] += 1
        return []

    store = CalibrationStore(ttl_s=60.0)
    with patch("agent.calibration_store._fetch_resolved", side_effect=fake_fetch):
        store.all_stats()
        store.all_stats()
        store.all_stats()
    assert call_count["n"] == 1  # only first call hit the DB


def test_cache_refreshes_after_ttl_expires() -> None:
    call_count = {"n": 0}

    def fake_fetch(_window_days: int) -> list:
        call_count["n"] += 1
        return []

    store = CalibrationStore(ttl_s=0.01)  # 10 ms TTL
    with patch("agent.calibration_store._fetch_resolved", side_effect=fake_fetch):
        store.all_stats()
        time.sleep(0.05)
        store.all_stats()
    assert call_count["n"] == 2


# ---------------------------------------------------------------------------
# Bias-direction edge cases
# ---------------------------------------------------------------------------


def test_describe_bias_small_calls_well_calibrated() -> None:
    assert "well calibrated" in CalibrationStore._describe_bias(0.0)
    assert "well calibrated" in CalibrationStore._describe_bias(0.025)
    assert "well calibrated" in CalibrationStore._describe_bias(-0.029)


def test_describe_bias_mild_vs_significant() -> None:
    mild = CalibrationStore._describe_bias(0.05)
    big = CalibrationStore._describe_bias(0.15)
    assert "mildly" in mild
    assert "significantly" in big


# ---------------------------------------------------------------------------
# Smoke check: the full Ensemble path accepts a prior string
# ---------------------------------------------------------------------------


def test_ensemble_accepts_prior_text_from_store() -> None:
    """End-to-end: store generates a prior, ensemble.analyse swallows it."""
    from agent.analyst import MarketCandidate
    from agent.ensemble import Ensemble

    rows = [_Row("macro", 0.7, 0.0) for _ in range(MIN_SAMPLE + 1)]
    store = _stub_store(rows)
    prior = store.prior_text()
    assert prior  # smoke

    candidate = MarketCandidate(
        market_id="poly-prior-1",
        source="polymarket",
        question="Will the Fed cut rates by June 2026?",
        end_date=datetime(2026, 6, 30, tzinfo=UTC) + timedelta(days=0),
        liquidity_usd=125_000.0,
    )
    trace = Ensemble(mock=True).analyse(candidate, calibration_prior=prior)
    assert trace.supervisor_synthesis.calibration_prior_used == prior
