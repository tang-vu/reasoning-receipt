"""Load the same deployment configuration in serverless and local runtimes."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from fastapi import HTTPException


def load_deployment_config(prefix: str) -> dict[str, Any]:
    """Prefer inline JSON for serverless; retain the existing local-file option.

    An invalid inline configuration must fail closed, never fall back to a
    different file or expose its contents in an HTTP response.
    """
    inline = os.getenv(f"{prefix}_CONFIG_JSON", "").strip()
    path = os.getenv(f"{prefix}_CONFIG", "").strip()
    if not inline and not path:
        return {"enabled": False}
    try:
        config = json.loads(inline if inline else Path(path).read_text(encoding="utf-8"))
        if not isinstance(config, dict):
            raise ValueError("configuration must be an object")
    except (OSError, ValueError) as exc:
        raise HTTPException(503, "Deployment configuration is unavailable or invalid") from exc
    return config
