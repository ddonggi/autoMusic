#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from automusic.config import load_config, load_dotenv
from automusic.image import generate_image
from automusic.pipeline import dry_run_image
from automusic.prompts import build_image_prompt_with_metadata
from automusic.state import load_json, save_json


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate one background image for a track.")
    parser.add_argument("track_dir", type=Path)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    load_dotenv()
    config = load_config(args.config) if args.config else {}
    track_json = args.track_dir / "track.json"
    track = load_json(track_json)
    output_path = args.track_dir / "image.png"
    if args.dry_run:
        output_path = dry_run_image(args.track_dir, config)
    else:
        image_result = build_image_prompt_with_metadata(track["music_prompt"], track, config)
        prompt = str(image_result["prompt"])
        generate_image(prompt, output_path)
        track["image_prompt"] = prompt
        track["image_variant"] = image_result["image_variant"]
        track["image_path"] = "image.png"
        track["status"] = "imaged"
        save_json(track_json, track)
    print(output_path)


if __name__ == "__main__":
    main()
