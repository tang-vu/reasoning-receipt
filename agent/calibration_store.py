"""Per-category calibration store — what the Supervisor reads as `calibration_prior`.

Pulls resolved receipts from the last N days, splits them by category
(politics / macro / crypto / sports / tech / other), computes per-category
Brier + signed over/under bias. Returns a small struct + a human-readable
text block that the supervisor prompt inlines.

Cached in-process for 30 min so each `analyse()` call doesn't hammer the DB.

Sample size threshold (`MIN_SAMPLE`): below 5 resolved markets in a category,
we omit that category from the prior — it's noise, not signal.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from storage.db import Receipt as ReceiptRow
from storage.db import Session

CATEGORIES = ("politics", "macro", "crypto", "sports", "tech", "other")
MIN_SAMPLE = 5
DEFAULT_WINDOW_DAYS = 30
CACHE_TTL_S = 30 * 60  # 30 minutes


@dataclass(slots=True)
class CategoryStats:
    category: str
    n: int                       # resolved receipts in category, in window
    brier: float                 # mean(predicted - actual)^2 — lower is better
    over_under_bias: float       # mean(predicted - actual). Positive = overconfident YES.


def _fetch_resolved(window_days: int) -> list[tuple]:
    """Pull (category, probability, resolved_outcome) for receipts resolved in window."""
    cutoff = datetime.now(UTC) - timedelta(days=window_days)
    with Session() as session:
        return list(
            session.execute(
                select(
                    ReceiptRow.category,
                    ReceiptRow.probability,
                    ReceiptRow.resolved_outcome,
                ).where(
                    ReceiptRow.resolved_outcome.is_not(None),
                    ReceiptRow.resolved_at.is_not(None),
                    ReceiptRow.resolved_at >= cutoff,
                )
            )
        )


def _category_stats(rows: list[tuple], category: str) -> CategoryStats:
    matching = [r for r in rows if (r.category or "other") == category]
    n = len(matching)
    if n == 0:
        return CategoryStats(category=category, n=0, brier=0.0, over_under_bias=0.0)
    brier = sum((float(r.probability) - float(r.resolved_outcome)) ** 2 for r in matching) / n
    bias = sum(float(r.probability) - float(r.resolved_outcome) for r in matching) / n
    return CategoryStats(category=category, n=n, brier=brier, over_under_bias=bias)


class CalibrationStore:
    """Per-category Brier + bias, cached, with human-readable prior text."""

    def __init__(self, *, window_days: int = DEFAULT_WINDOW_DAYS, ttl_s: float = CACHE_TTL_S) -> None:
        self.window_days = window_days
        self.ttl_s = ttl_s
        self._cache: dict[str, CategoryStats] | None = None
        self._cached_at: float = 0.0

    def _refresh_if_stale(self) -> None:
        if self._cache is not None and (time.time() - self._cached_at) < self.ttl_s:
            return
        rows = _fetch_resolved(self.window_days)
        self._cache = {cat: _category_stats(rows, cat) for cat in CATEGORIES}
        self._cached_at = time.time()

    def stats_for(self, category: str) -> CategoryStats:
        self._refresh_if_stale()
        assert self._cache is not None
        return self._cache.get(category, CategoryStats(category=category, n=0, brier=0.0, over_under_bias=0.0))

    def all_stats(self) -> dict[str, CategoryStats]:
        self._refresh_if_stale()
        assert self._cache is not None
        return dict(self._cache)

    def prior_text(self, *, category: str | None = None) -> str:
        """Render the prior block the supervisor prompt inlines.

        If `category` is given, returns just that one's line (if signal exists).
        Otherwise returns one line per category that meets MIN_SAMPLE — the
        supervisor sees the full landscape and can apply the most relevant one
        based on the market's own category field.

        Returns empty string when no category has enough data — no prior, no harm.
        """
        self._refresh_if_stale()
        assert self._cache is not None
        lines: list[str] = []
        candidates = [self._cache[category]] if category else self._cache.values()
        for s in candidates:
            if s.n < MIN_SAMPLE:
                continue
            bias_phrase = self._describe_bias(s.over_under_bias)
            lines.append(
                f"  - {s.category}: Brier {s.brier:.3f} over {s.n} resolved markets in last "
                f"{self.window_days}d, {bias_phrase}"
            )
        if not lines:
            return ""
        return (
            "Past-performance prior from resolved markets (use to temper extreme probabilities):\n"
            + "\n".join(lines)
        )

    @staticmethod
    def _describe_bias(bias: float) -> str:
        """Plain English summary of a signed over/under-confidence bias."""
        abs_bias = abs(bias)
        if abs_bias < 0.03:
            return "well calibrated (mean predicted ≈ mean actual)"
        direction = "overconfident YES" if bias > 0 else "overconfident NO"
        magnitude = "mildly" if abs_bias < 0.07 else "significantly"
        return f"{magnitude} {direction} (mean predicted − actual = {bias:+.2f})"
