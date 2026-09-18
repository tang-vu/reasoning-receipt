"""Cross-language parity check (Python side).

Loads every emitted parity receipt, verifies it with the local verifier,
and asserts the canonical document bytes are identical across languages.
Exit 0 iff all present files verify and all canonical bytes match.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from protocol.canon import canonical_bytes  # noqa: E402
from protocol.verify import verify_any  # noqa: E402

PARITY_DIR = Path(__file__).resolve().parents[2] / "conformance" / "parity"


def main() -> int:
    files = sorted(PARITY_DIR.glob("*.receipt.json"))
    if not files:
        print("no parity receipts emitted yet", file=sys.stderr)
        return 2
    canonical: dict[str, bytes] = {}
    ok = True
    for path in files:
        doc = json.loads(path.read_text(encoding="utf-8"))
        report = verify_any(doc)
        sig_states = [s.get("valid") for s in report.signatures] if report.signatures else []
        line = f"{path.name}: valid={report.valid} sigs={sig_states} root={report.merkle_root}"
        if not report.valid or not all(sig_states):
            ok = False
            line += f"  ERRORS={report.errors}"
        print(line)
        canonical[path.name] = canonical_bytes(doc)
    unique = set(canonical.values())
    if len(unique) > 1:
        ok = False
        print(f"canonical bytes differ across languages: {len(unique)} variants")
    else:
        print(f"canonical bytes identical across {len(files)} emitters")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
