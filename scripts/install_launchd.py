#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from automusic.launchd import render_launchd_plist


def main() -> None:
    default_project_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Install the AutoMusic daily launchd job.")
    parser.add_argument("--project-root", default=default_project_root, type=Path)
    parser.add_argument("--label", default="com.automusic.daily")
    parser.add_argument("--hour", default=12, type=int)
    parser.add_argument("--minute", default=0, type=int)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    project_root = args.project_root.resolve()
    python_path = project_root / ".venv" / "bin" / "python"
    if not python_path.exists():
        python_path = Path(sys.executable)
    logs_dir = project_root / "logs"
    plist_path = Path.home() / "Library" / "LaunchAgents" / f"{args.label}.plist"
    plist_bytes = render_launchd_plist(
        label=args.label,
        python_path=python_path,
        automation_script=project_root / "scripts" / "run_automation.py",
        project_root=project_root,
        logs_dir=logs_dir,
        hour=args.hour,
        minute=args.minute,
    )

    if args.dry_run:
        print(plist_bytes.decode())
        return

    logs_dir.mkdir(parents=True, exist_ok=True)
    plist_path.parent.mkdir(parents=True, exist_ok=True)
    plist_path.write_bytes(plist_bytes)
    subprocess.run(["launchctl", "unload", str(plist_path)], check=False)
    subprocess.run(["launchctl", "load", str(plist_path)], check=True)
    print(plist_path)


if __name__ == "__main__":
    main()
