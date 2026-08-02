#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from automusic.automation import run_automation
from automusic.categories import resolve_music_config_path
from automusic.config import load_config, load_dotenv


def main() -> None:
    default_project_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Run daily generation and batch upload when ready.")
    parser.add_argument("--project-root", default=default_project_root, type=Path)
    parser.add_argument("--root", default=None, type=Path)
    parser.add_argument("--music-config", default=None, type=Path)
    parser.add_argument("--category-config", default=None, type=Path)
    parser.add_argument("--upload-config", default=None, type=Path)
    parser.add_argument("--batch-count", default=None, type=int)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    project_root = args.project_root.resolve()
    root = (args.root or project_root).resolve()
    category_config = args.category_config or project_root / "configs" / "category.conf"
    music_config = resolve_music_config_path(project_root, category_config, args.music_config)
    upload_config = args.upload_config or project_root / "configs" / "upload.yaml"

    load_dotenv(project_root / ".env")
    music_options = load_config(music_config)
    batch_count = args.batch_count or int(music_options.get("batch_count", 10))
    result = run_automation(
        project_root=project_root,
        root=root,
        music_config=music_config,
        upload_config=upload_config,
        batch_count=batch_count,
        dry_run=args.dry_run,
    )
    print(f"daily_command={' '.join(result['daily_command'])}")
    if result["batch_ran"]:
        print(f"batch_command={' '.join(result['batch_command'])}")
    else:
        print("batch_command=skipped")


if __name__ == "__main__":
    main()
