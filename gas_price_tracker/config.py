"""Local configuration loading for the desktop app."""

from __future__ import annotations

import os
from pathlib import Path


def load_eia_api_key(env_file: Path | None = None) -> str:
    """Return the EIA key, preferring the process environment over .env."""
    if "EIA_API_KEY" in os.environ:
        return os.environ["EIA_API_KEY"]

    if env_file is None:
        env_file = Path(__file__).resolve().parent.parent / ".env"

    try:
        lines = env_file.read_text(encoding="utf-8").splitlines()
    except OSError:
        return ""

    for line in lines:
        entry = line.strip()
        if not entry or entry.startswith("#") or "=" not in entry:
            continue
        name, value = entry.split("=", 1)
        if name.strip() != "EIA_API_KEY":
            continue

        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        return value

    return ""