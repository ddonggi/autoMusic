#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from automusic.config import load_config, load_dotenv
from automusic.image import generate_image
from automusic.music import generate_lyria_track
from automusic.pipeline import dry_run_daily
from automusic.prompts import build_image_prompt
from automusic.state import load_json, save_json


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate daily music and image assets.")
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--root", default=Path("."), type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    load_dotenv()
    config = load_config(args.config)
    tracks_root = args.root / "workspace" / "tracks"
    if args.dry_run:
        track_dir = dry_run_daily(config, tracks_root)
    else:
        track_dir = asyncio.run(generate_lyria_track(config, tracks_root))
        track_path = track_dir / "track.json"
        track = load_json(track_path)
        image_prompt = build_image_prompt(track["music_prompt"], track)
        generate_image(image_prompt, track_dir / "image.png")
        track["image_prompt"] = image_prompt
        track["image_path"] = "image.png"
        track["status"] = "imaged"
        save_json(track_path, track)
    print(track_dir)


if __name__ == "__main__":
    main()
