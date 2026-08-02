from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .config import load_config


_CATEGORY_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")


def load_music_category(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"Category config does not exist: {path}")
    for raw_line in path.read_text().splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        if "=" in line:
            key, value = line.split("=", 1)
        else:
            parts = line.split(None, 1)
            if len(parts) != 2:
                raise ValueError(f"Invalid category config line: {raw_line}")
            key, value = parts
        if key.strip() == "music_category":
            category = value.strip().strip('"').strip("'")
            if not _CATEGORY_PATTERN.fullmatch(category):
                raise ValueError(f"Invalid music category: {category}")
            return category
    raise ValueError(f"music_category is missing from {path}")


def resolve_music_config_path(
    project_root: Path,
    category_config: Path,
    explicit_music_config: Path | None = None,
) -> Path:
    if explicit_music_config is not None:
        return explicit_music_config.resolve()

    category = load_music_category(category_config)
    categories_root = project_root / "configs" / "categories"
    category_path = categories_root / f"{category}.yaml"
    if not category_path.exists():
        raise FileNotFoundError(
            f"No music config for category '{category}'. Create {categories_root / (category + '.yaml')}"
        )
    return category_path.resolve()


def load_category_config(path: Path) -> dict[str, Any]:
    return load_config(path)
