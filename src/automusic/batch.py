from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .state import load_json, save_json


def build_batch(
    tracks_root: Path,
    batches_root: Path,
    *,
    batch_count: int = 10,
    now: datetime | None = None,
) -> Path:
    eligible = _eligible_tracks(tracks_root)
    if len(eligible) < batch_count:
        raise RuntimeError(f"Need {batch_count} imaged tracks, found {len(eligible)}")
    selected = eligible[:batch_count]
    now = now or datetime.now(ZoneInfo("Asia/Seoul"))
    batch_id = f"{now:%Y%m%d-%H%M%S}-batch"
    batch_path = batches_root / batch_id
    batch_path.mkdir(parents=True, exist_ok=False)
    track_ids = [track["metadata"]["track_id"] for track in selected]
    save_json(
        batch_path / "batch.json",
        {
            "batch_id": batch_id,
            "status": "assembled",
            "track_ids": track_ids,
            "video_path": "video.mp4",
            "duration_seconds": None,
            "youtube_video_id": None,
            "archive_pending": False,
            "created_at": now.isoformat(),
        },
    )
    for track in selected:
        metadata = track["metadata"]
        metadata["status"] = "batched"
        metadata["batch_id"] = batch_id
        save_json(track["path"] / "track.json", metadata)
    return batch_path


def _eligible_tracks(tracks_root: Path) -> list[dict[str, Any]]:
    if not tracks_root.exists():
        return []
    tracks: list[dict[str, Any]] = []
    for track_json in tracks_root.glob("*/track.json"):
        metadata = load_json(track_json)
        if metadata.get("status") == "imaged" and not metadata.get("batch_id"):
            tracks.append({"path": track_json.parent, "metadata": metadata})
    return sorted(tracks, key=lambda item: item["metadata"].get("created_at", ""))
