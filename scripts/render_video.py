#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from automusic.render import render_batch


def main() -> None:
    parser = argparse.ArgumentParser(description="Render a batch into MP4.")
    parser.add_argument("batch_dir", type=Path)
    parser.add_argument("--tracks-root", default=Path("workspace/tracks"), type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.dry_run:
        output_path = args.batch_dir / "video.mp4"
        output_path.write_bytes(b"dry-run video")
    else:
        output_path = render_batch(args.batch_dir, args.tracks_root)
    print(output_path)


if __name__ == "__main__":
    main()
