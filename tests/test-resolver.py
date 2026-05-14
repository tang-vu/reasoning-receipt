"""Resolver outcome-parsing tests — Polymarket and Kalshi."""

from __future__ import annotations

from agent.resolver import _parse_kalshi_outcome, _parse_outcome


def test_polymarket_closed_yes() -> None:
    m = {"closed": True, "outcomePrices": ["0.99", "0.01"]}
    assert _parse_outcome(m) == 1.0


def test_polymarket_closed_no() -> None:
    m = {"closed": True, "outcomePrices": ["0.02", "0.98"]}
    assert _parse_outcome(m) == 0.0


def test_polymarket_ambiguous_close_skipped() -> None:
    m = {"closed": True, "outcomePrices": ["0.55", "0.45"]}
    assert _parse_outcome(m) is None


def test_polymarket_not_closed_yet() -> None:
    assert _parse_outcome({"closed": False, "outcomePrices": ["0.99", "0.01"]}) is None


def test_polymarket_outcome_prices_as_json_string() -> None:
    # Gamma sometimes returns prices as a JSON-encoded string instead of a list.
    m = {"closed": True, "outcomePrices": '["0.97","0.03"]'}
    assert _parse_outcome(m) == 1.0


def test_kalshi_finalized_yes() -> None:
    assert _parse_kalshi_outcome({"status": "finalized", "result": "yes"}) == 1.0


def test_kalshi_settled_no() -> None:
    assert _parse_kalshi_outcome({"status": "settled", "result": "no"}) == 0.0


def test_kalshi_determined_is_terminal() -> None:
    assert _parse_kalshi_outcome({"status": "determined", "result": "yes"}) == 1.0


def test_kalshi_active_not_resolved() -> None:
    assert _parse_kalshi_outcome({"status": "active", "result": "yes"}) is None


def test_kalshi_finalized_without_result_skipped() -> None:
    assert _parse_kalshi_outcome({"status": "finalized", "result": ""}) is None


def test_kalshi_finalized_garbage_result_skipped() -> None:
    # Anything outside the binary yes/no contract is unsafe to back-fill blindly.
    assert _parse_kalshi_outcome({"status": "finalized", "result": "void"}) is None
