#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from automusic.config import load_config, load_dotenv
from automusic.secrets import load_required_env
from automusic.youtube import update_batch_after_upload


def main() -> None:
    parser = argparse.ArgumentParser(description="Upload rendered MP4 to YouTube.")
    parser.add_argument("batch_dir", type=Path)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    load_dotenv()
    config = load_config(args.config)
    if args.dry_run:
        video_id = "dry-run-video-id"
    else:
        load_required_env(
            ["YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET", "YOUTUBE_REFRESH_TOKEN"]
        )
        from automusic.youtube_live import upload_video

        video_id = upload_video(args.batch_dir, config)
    update_batch_after_upload(args.batch_dir / "batch.json", video_id)
    print(video_id)


if __name__ == "__main__":
    main()
