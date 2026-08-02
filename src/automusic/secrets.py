from __future__ import annotations

import os


def load_required_env(names: list[str]) -> dict[str, str]:
    values: dict[str, str] = {}
    missing: list[str] = []
    for name in names:
        value = os.environ.get(name)
        if value:
            values[name] = value
        else:
            missing.append(name)
    if missing:
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")
    return values
