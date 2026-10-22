#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from automusic.automation import run_automation
from automusic.categories import resolve_music_config_path
from automusic.config import load_config, load_dotenv
from automusic.scheduler import SchedulerService


def main() -> None:
    default_project_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Run daily music generation; batch upload is disabled unless explicitly configured.")
    parser.add_argument("--project-root", default=default_project_root, type=Path)
    parser.add_argument("--root", default=None, type=Path)
    parser.add_argument("--music-config", default=None, type=Path)
    parser.add_argument("--category-config", default=None, type=Path)
    parser.add_argument("--upload-config", default=None, type=Path)
    parser.add_argument("--batch-count", default=None, type=int)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--manual", action="store_true",
                        help="Explicit manual run: bypass the persistent scheduler admission gate.")
    args = parser.parse_args()

    project_root = args.project_root.resolve()
    if not SchedulerService(project_root).admit_run(manual=args.manual):
        print("automation=skipped_scheduler_disabled_or_unknown")
        return
    root = (args.root or project_root).resolve()
    category_config = args.category_config or project_root / "configs" / "category.conf"
    music_config = resolve_music_config_path(project_root, category_config, args.music_config)
    upload_config = args.upload_config or project_root / "configs" / "upload.yaml"

    # Fail closed for a missing, unreadable, malformed, or non-boolean upload flag.
    try:
        upload_options = load_config(upload_config)
    except Exception:
        upload_options = {}
    # Manual compilation only: do not start image/render/upload from daily automation.
    # batch_upload_enabled = isinstance(upload_options, dict) and upload_options.get("batch_upload_enabled") is True
    batch_upload_enabled = False

    load_dotenv(project_root / ".env")
    music_options = load_config(music_config)
    batch_count = args.batch_count or int(music_options.get("batch_count", 10))
    result = run_automation(
        project_root=project_root,
        root=root,
        music_config=music_config,
        upload_config=upload_config,
        batch_count=batch_count,
        batch_upload_enabled=batch_upload_enabled,
        dry_run=args.dry_run,
    )
    print(f"daily_command={' '.join(result['daily_command'])}")
    if result["batch_ran"]:
        print(f"batch_command={' '.join(result['batch_command'])}")
    elif not batch_upload_enabled:
        print("batch_command=skipped_disabled")
    else:
        print("batch_command=skipped")


if __name__ == "__main__":
    main()
