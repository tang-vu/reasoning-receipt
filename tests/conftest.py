"""Shared pytest fixtures.

Forces every external integration into mock mode so the suite runs with no
network, no creds, and no on-disk database file outside the test directory.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

_MOCK_ENV = {
    "RR_MOCK_CHAIN": "1",
    "RR_MOCK_IRYS": "1",
    "RR_MOCK_ANALYST": "1",
    "RR_MOCK_SCANNER": "1",
    "RR_MOCK_X402": "1",
    "RR_MOCK_TRADER": "1",
    "RR_MOCK_CIRCLE": "1",
    "RR_LOCAL_FACILITATOR": "0",
    "ANTHROPIC_API_KEY": "",
    "CORS_ORIGINS": "*",
}


@pytest.fixture(autouse=True)
def _force_mock_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Force every subsystem into mock mode + isolate the DB per test."""
    for k, v in _MOCK_ENV.items():
        monkeypatch.setenv(k, v)
    db_path = tmp_path / "rr-test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    # Force a fresh engine for each test
    import storage.db as db_module

    db_module._engine = None
    db_module._Session = None
    yield
    os.environ.pop("DATABASE_URL", None)
