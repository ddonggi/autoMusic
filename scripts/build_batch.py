#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from automusic.batch import build_batch


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a 10-track upload batch.")
    parser.add_argument("--tracks-root", default=Path("workspace/tracks"), type=Path)
    parser.add_argument("--batches-root", default=Path("workspace/batches"), type=Path)
    parser.add_argument("--batch-count", default=10, type=int)
    args = parser.parse_args()

    batch_path = build_batch(args.tracks_root, args.batches_root, batch_count=args.batch_count)
    print(batch_path)


if __name__ == "__main__":
    main()
