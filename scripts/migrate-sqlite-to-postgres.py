"""One-shot, non-destructive SQLite to Postgres migration.

The target must be empty. This deliberately refuses merges so a typo cannot
silently duplicate or overwrite production data.
"""

from __future__ import annotations

import argparse
import os
from collections.abc import Sequence

from sqlalchemy import create_engine, func, select, text

from storage.db import Base, MemoryItem, Position, Receipt, ScanCandidate, normalize_database_url

MODELS = (Receipt, Position, ScanCandidate, MemoryItem)


def migrate(source_url: str, target_url: str, *, batch_size: int = 500) -> dict[str, int]:
    source_url = normalize_database_url(source_url)
    target_url = normalize_database_url(target_url)
    if not target_url.startswith("postgresql+"):
        raise ValueError("target must be Postgres")
    if source_url == target_url:
        raise ValueError("source and target databases must differ")

    source = create_engine(source_url, future=True)
    target = create_engine(target_url, future=True, pool_pre_ping=True)
    Base.metadata.create_all(target)
    copied: dict[str, int] = {}

    with source.connect() as src, target.begin() as dst:
        for model in MODELS:
            table = model.__table__
            target_count = dst.scalar(select(func.count()).select_from(table)) or 0
            if target_count:
                raise RuntimeError(f"target table {table.name!r} is not empty ({target_count} rows)")
            rows = [dict(row) for row in src.execute(select(table)).mappings()]
            for start in range(0, len(rows), batch_size):
                dst.execute(table.insert(), rows[start : start + batch_size])
            copied[table.name] = len(rows)

        for table_name in ("receipts", "positions", "scan_candidates"):
            dst.execute(
                text(
                    "SELECT setval(pg_get_serial_sequence(:table_name, 'id'), "
                    "COALESCE((SELECT MAX(id) FROM " + table_name + "), 1), true)"
                ),
                {"table_name": table_name},
            )
    return copied


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default="sqlite:///./data/reasoning_receipt.db")
    parser.add_argument("--target", default=os.getenv("TARGET_DATABASE_URL", ""))
    args = parser.parse_args(argv)
    if not args.target:
        raise SystemExit("set TARGET_DATABASE_URL or pass --target")
    copied = migrate(args.source, args.target)
    for table, count in copied.items():
        print(f"{table}: {count} rows copied")


if __name__ == "__main__":
    main()
