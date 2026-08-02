#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from automusic.batch_upload import run_batch_upload
from automusic.config import load_config, load_dotenv
from automusic.pipeline import dry_run_batch_upload


def main() -> None:
    parser = argparse.ArgumentParser(description="Build, render, upload, and archive a full batch.")
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--music-config", default=None, type=Path)
    parser.add_argument("--batch-count", default=10, type=int)
    parser.add_argument("--root", default=Path("."), type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    load_dotenv()
    if args.dry_run:
        config = load_config(args.config)
        if args.music_config:
            music_config = load_config(args.music_config)
            for key in ("image_context", "image_variants"):
                if key in music_config:
                    config[key] = music_config[key]
        archived = dry_run_batch_upload(args.root, config, args.batch_count)
        print(archived)
        return

    config = load_config(args.config)
    if args.music_config:
        music_config = load_config(args.music_config)
        for key in ("image_context", "image_variants"):
            if key in music_config:
                config[key] = music_config[key]
    from automusic.youtube_live import upload_video

    archived = run_batch_upload(
        args.root,
        config,
        batch_count=args.batch_count,
        upload_func=upload_video,
    )
    print(archived)


if __name__ == "__main__":
    main()
