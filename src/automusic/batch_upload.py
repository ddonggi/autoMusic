from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from .archive import archive_success
from .batch import build_batch, find_pending_batch
from .notify import (
    Notification,
    build_batch_failure_notification,
    build_batch_success_notification,
    send_notification_safely,
)
from .render import render_batch
from .secrets import load_required_env
from .state import load_json, save_json
from .youtube import update_batch_after_upload

YOUTUBE_ENV_NAMES = ["YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET", "YOUTUBE_REFRESH_TOKEN"]

Notifier = Callable[[Notification], Any]


def run_batch_upload(
    root: Path,
    config: dict[str, Any],
    *,
    batch_count: int = 10,
    render_func=render_batch,
    require_youtube_env=load_required_env,
    upload_func: Callable[[Path, dict[str, Any]], str],
    archive_func=archive_success,
    notifier: Notifier = send_notification_safely,
) -> Path:
    tracks_root = root / "workspace" / "tracks"
    batches_root = root / "workspace" / "batches"
    batch_path: Path | None = None
    stage = "select_batch"

    try:
        batch_path = find_pending_batch(batches_root)
        if batch_path is None:
            batch_path = build_batch(tracks_root, batches_root, batch_count=batch_count)

        batch = load_json(batch_path / "batch.json")
        video_path = batch_path / str(batch.get("video_path") or "video.mp4")
        if not batch.get("youtube_video_id") and (
            batch.get("status") == "assembled" or not video_path.exists()
        ):
            stage = "render"
            render_func(batch_path, tracks_root)
            batch = load_json(batch_path / "batch.json")

        if not batch.get("youtube_video_id"):
            stage = "youtube_credentials"
            require_youtube_env(YOUTUBE_ENV_NAMES)
            stage = "upload"
            video_id = upload_func(batch_path, config)
            update_batch_after_upload(batch_path / "batch.json", video_id)
            batch = load_json(batch_path / "batch.json")
            _mark_tracks_uploaded(batch, tracks_root)

        stage = "archive"
        batch = load_json(batch_path / "batch.json")
        archived_path = archive_func(batch_path, tracks_root, root / "success")
        _notify_safely(notifier, build_batch_success_notification(batch, archived_path))
        return archived_path
    except Exception as exc:
        if batch_path is not None:
            _notify_safely(
                notifier,
                build_batch_failure_notification(_batch_id(batch_path), stage, exc),
            )
        raise


def _mark_tracks_uploaded(batch: dict[str, Any], tracks_root: Path) -> None:
    for track_id in batch["track_ids"]:
        track_path = tracks_root / track_id / "track.json"
        track = load_json(track_path)
        track["status"] = "uploaded"
        save_json(track_path, track)


def _batch_id(batch_path: Path) -> str:
    try:
        return str(load_json(batch_path / "batch.json").get("batch_id") or batch_path.name)
    except Exception:
        return batch_path.name


def _notify_safely(notifier: Notifier, notification: Notification) -> None:
    try:
        notifier(notification)
    except Exception:
        pass
