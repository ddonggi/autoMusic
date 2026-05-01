from __future__ import annotations

import plistlib
from pathlib import Path


def render_launchd_plist(
    *,
    label: str,
    python_path: Path,
    automation_script: Path,
    project_root: Path,
    logs_dir: Path,
    hour: int = 12,
    minute: int = 0,
) -> bytes:
    plist = {
        "Label": label,
        "ProgramArguments": [
            str(python_path),
            str(automation_script),
            "--project-root",
            str(project_root),
        ],
        "WorkingDirectory": str(project_root),
        "StartCalendarInterval": {
            "Hour": hour,
            "Minute": minute,
        },
        "StandardOutPath": str(logs_dir / "launchd.out.log"),
        "StandardErrorPath": str(logs_dir / "launchd.err.log"),
        "RunAtLoad": False,
    }
    return plistlib.dumps(plist, sort_keys=False)
