#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from automusic.archive import archive_success
from automusic.batch import build_batch
from automusic.config import load_config, load_dotenv
from automusic.pipeline import dry_run_batch_upload
from automusic.render import render_batch
from automusic.secrets import load_required_env
from automusic.state import load_json, save_json
from automusic.youtube import update_batch_after_upload


def main() -> None:
    parser = argparse.ArgumentParser(description="Build, render, upload, and archive a full batch.")
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--root", default=Path("."), type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    load_dotenv()
    if args.dry_run:
        archived = dry_run_batch_upload(args.root)
        print(archived)
        return

    config = load_config(args.config)
    root = args.root
    tracks_root = root / "workspace" / "tracks"
    batch_path = build_batch(tracks_root, root / "workspace" / "batches", batch_count=10)
    render_batch(batch_path, tracks_root)
    load_required_env(["YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET", "YOUTUBE_REFRESH_TOKEN"])
    from automusic.youtube_live import upload_video

    video_id = upload_video(batch_path, config)
    update_batch_after_upload(batch_path / "batch.json", video_id)

    batch = load_json(batch_path / "batch.json")
    for track_id in batch["track_ids"]:
        track_path = tracks_root / track_id / "track.json"
        track = load_json(track_path)
        track["status"] = "uploaded"
        save_json(track_path, track)

    archived = archive_success(batch_path, tracks_root, root / "success")
    print(archived)


if __name__ == "__main__":
    main()
