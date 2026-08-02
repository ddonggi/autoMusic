from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

from .batch import find_pending_batch
from .state import load_json

Runner = Callable[[list[str], bool, Path], Any]


def count_ready_tracks(tracks_root: Path) -> int:
    if not tracks_root.exists():
        return 0
    ready = 0
    for track_json in tracks_root.glob("*/track.json"):
        track = load_json(track_json)
        if track.get("status") == "generated" and not track.get("batch_id"):
            ready += 1
    return ready


def should_run_batch(root: Path, batch_count: int) -> bool:
    if find_pending_batch(root / "workspace" / "batches") is not None:
        return True
    return count_ready_tracks(root / "workspace" / "tracks") >= batch_count


def run_automation(
    *,
    project_root: Path,
    root: Path,
    music_config: Path,
    upload_config: Path,
    batch_count: int = 10,
    dry_run: bool = False,
    python_path: Path | None = None,
    runner: Runner | None = None,
) -> dict[str, Any]:
    project_root = project_root.resolve()
    root = root.resolve()
    python_path = python_path or Path(sys.executable)
    runner = runner or _run_command

    daily_command = [
        str(python_path),
        str(project_root / "scripts" / "run_daily.py"),
        "--config",
        str(music_config),
        "--root",
        str(root),
    ]
    if dry_run:
        daily_command.append("--dry-run")
    runner(daily_command, True, project_root)

    batch_command: list[str] | None = None
    batch_ran = False
    if should_run_batch(root, batch_count):
        batch_command = [
            str(python_path),
            str(project_root / "scripts" / "run_batch_upload.py"),
            "--config",
            str(upload_config),
            "--root",
            str(root),
            "--music-config",
            str(music_config),
            "--batch-count",
            str(batch_count),
        ]
        if dry_run:
            batch_command.append("--dry-run")
        runner(batch_command, True, project_root)
        batch_ran = True

    return {
        "daily_command": daily_command,
        "batch_command": batch_command,
        "batch_ran": batch_ran,
    }


def _run_command(command: list[str], check: bool, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(command, check=check, cwd=cwd)
