#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from automusic.config import load_config, load_dotenv
from automusic.music import generate_lyria_track
from automusic.pipeline import dry_run_music


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate one Lyria music track.")
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--tracks-root", default=Path("workspace/tracks"), type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    load_dotenv()
    config = load_config(args.config)
    if args.dry_run:
        track_dir = dry_run_music(config, args.tracks_root)
    else:
        track_dir = asyncio.run(generate_lyria_track(config, args.tracks_root))
    print(track_dir)


if __name__ == "__main__":
    main()
