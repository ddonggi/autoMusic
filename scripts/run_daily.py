#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Awaitable, Callable

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from automusic.config import load_config, load_dotenv
from automusic.image import generate_image
from automusic.music import generate_lyria_track
from automusic.notify import (
    Notification,
    build_daily_failure_notification,
    build_daily_success_notification,
    send_notification_safely,
)
from automusic.pipeline import dry_run_daily
from automusic.prompts import build_image_prompt_with_metadata
from automusic.state import load_json, save_json

TrackGenerator = Callable[[dict, Path], Awaitable[Path]]
ImageGenerator = Callable[[str, Path], Path]
NotificationSender = Callable[[Notification], bool]


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate daily music and image assets.")
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--root", default=Path("."), type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    load_dotenv()
    config = load_config(args.config)
    track_dir = run_daily(config, args.root, dry_run=args.dry_run)
    print(track_dir)


def run_daily(
    config: dict,
    root: Path,
    *,
    dry_run: bool = False,
    track_generator: TrackGenerator = generate_lyria_track,
    image_generator: ImageGenerator = generate_image,
    notification_sender: NotificationSender = send_notification_safely,
) -> Path:
    tracks_root = root / "workspace" / "tracks"
    if dry_run:
        return dry_run_daily(config, tracks_root)

    try:
        track_dir = asyncio.run(track_generator(config, tracks_root))
    except Exception as exc:
        notification_sender(build_daily_failure_notification(stage="music_generation", error=exc))
        raise

    track_path = track_dir / "track.json"
    track = load_json(track_path)
    image_result = build_image_prompt_with_metadata(track["music_prompt"], track, config)
    image_prompt = str(image_result["prompt"])
    try:
        image_generator(image_prompt, track_dir / "image.png")
    except Exception as exc:
        notification_sender(
            build_daily_failure_notification(stage="image_generation", error=exc, track_dir=track_dir)
        )
        raise

    track["image_prompt"] = image_prompt
    track["image_variant"] = image_result["image_variant"]
    track["image_path"] = "image.png"
    track["status"] = "imaged"
    save_json(track_path, track)
    notification_sender(build_daily_success_notification(track_dir, track))
    return track_dir


if __name__ == "__main__":
    main()
