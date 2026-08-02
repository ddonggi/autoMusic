from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


TRACK_TRANSITIONS = {
    "new": {"generated"},
    "generated": {"imaged"},
    "imaged": {"batched"},
    "batched": {"uploaded"},
    "uploaded": {"archived"},
}


@dataclass(frozen=True)
class TrackMetadata:
    track_id: str
    status: str
    created_at: str
    audio_path: str | None = None
    image_path: str | None = None
    batch_id: str | None = None


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def save_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n")


def transition_track_status(track: dict[str, Any], next_status: str) -> None:
    current = str(track.get("status", "new"))
    allowed = TRACK_TRANSITIONS.get(current, set())
    if next_status not in allowed:
        raise ValueError(f"Invalid track status transition: {current} -> {next_status}")
    track["status"] = next_status
