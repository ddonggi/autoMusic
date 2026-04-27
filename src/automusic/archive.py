from __future__ import annotations

import shutil
from pathlib import Path

from .state import load_json, save_json


def archive_success(batch_path: Path, tracks_root: Path, success_root: Path) -> Path:
    batch_json_path = batch_path / "batch.json"
    batch = load_json(batch_json_path)
    if not batch.get("youtube_video_id"):
        raise RuntimeError("Cannot archive a batch before youtube_video_id is recorded")

    success_tracks = success_root / "tracks"
    success_batches = success_root / "batches"
    success_tracks.mkdir(parents=True, exist_ok=True)
    success_batches.mkdir(parents=True, exist_ok=True)

    for track_id in batch["track_ids"]:
        source = tracks_root / track_id
        destination = success_tracks / track_id
        track = load_json(source / "track.json")
        track["status"] = "archived"
        save_json(source / "track.json", track)
        shutil.move(str(source), str(destination))

    batch["status"] = "archived"
    save_json(batch_json_path, batch)
    destination_batch = success_batches / batch["batch_id"]
    shutil.move(str(batch_path), str(destination_batch))
    return destination_batch
