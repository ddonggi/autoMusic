import plistlib
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from automusic.automation import run_automation
from automusic.launchd import render_launchd_plist
from automusic.state import save_json


class AutomationScheduleTests(unittest.TestCase):
    def test_run_automation_skips_batch_when_less_than_batch_count(self):
        calls = []

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_tracks(root, 9)

            result = run_automation(
                project_root=Path("/project"),
                root=root,
                music_config=Path("/project/configs/examples/music.yaml"),
                upload_config=Path("/project/configs/examples/upload.yaml"),
                batch_count=10,
                python_path=Path("/python"),
                runner=lambda command, check, cwd: calls.append((command, check, cwd)),
            )

        self.assertFalse(result["batch_ran"])
        self.assertEqual(len(calls), 1)
        self.assertIn("run_daily.py", calls[0][0][1])

    def test_run_automation_runs_batch_when_ten_tracks_are_ready(self):
        calls = []

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_tracks(root, 10)

            result = run_automation(
                project_root=Path("/project"),
                root=root,
                music_config=Path("/project/configs/examples/music.yaml"),
                upload_config=Path("/project/configs/examples/upload.yaml"),
                batch_count=10,
                python_path=Path("/python"),
                runner=lambda command, check, cwd: calls.append((command, check, cwd)),
            )

        self.assertTrue(result["batch_ran"])
        self.assertEqual(len(calls), 2)
        self.assertIn("run_daily.py", calls[0][0][1])
        self.assertIn("run_batch_upload.py", calls[1][0][1])

    def test_run_automation_runs_batch_when_pending_batch_exists(self):
        calls = []

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            batch_path = root / "workspace" / "batches" / "batch-001"
            batch_path.mkdir(parents=True)
            save_json(
                batch_path / "batch.json",
                {
                    "batch_id": "batch-001",
                    "status": "rendered",
                    "created_at": "2026-05-01T00:00:00+09:00",
                },
            )

            result = run_automation(
                project_root=Path("/project"),
                root=root,
                music_config=Path("/project/configs/examples/music.yaml"),
                upload_config=Path("/project/configs/examples/upload.yaml"),
                batch_count=10,
                python_path=Path("/python"),
                runner=lambda command, check, cwd: calls.append((command, check, cwd)),
            )

        self.assertTrue(result["batch_ran"])
        self.assertEqual(len(calls), 2)
        self.assertIn("run_batch_upload.py", calls[1][0][1])

    def test_render_launchd_plist_schedules_noon_automation(self):
        payload = render_launchd_plist(
            label="com.automusic.daily",
            python_path=Path("/project/.venv/bin/python"),
            automation_script=Path("/project/scripts/run_automation.py"),
            project_root=Path("/project"),
            logs_dir=Path("/project/logs"),
            hour=12,
            minute=0,
        )

        plist = plistlib.loads(payload)

        self.assertEqual(plist["Label"], "com.automusic.daily")
        self.assertEqual(plist["StartCalendarInterval"], {"Hour": 12, "Minute": 0})
        self.assertEqual(plist["WorkingDirectory"], "/project")
        self.assertEqual(
            plist["ProgramArguments"],
            [
                "/project/.venv/bin/python",
                "/project/scripts/run_automation.py",
                "--project-root",
                "/project",
            ],
        )
        self.assertEqual(plist["StandardOutPath"], "/project/logs/launchd.out.log")
        self.assertEqual(plist["StandardErrorPath"], "/project/logs/launchd.err.log")


def _write_tracks(root: Path, count: int) -> None:
    tracks_root = root / "workspace" / "tracks"
    for index in range(count):
        track_dir = tracks_root / f"track-{index:02d}"
        track_dir.mkdir(parents=True)
        save_json(
            track_dir / "track.json",
            {
                "track_id": f"track-{index:02d}",
                "status": "imaged",
                "created_at": f"2026-05-01T00:{index:02d}:00+09:00",
                "batch_id": None,
            },
        )


if __name__ == "__main__":
    unittest.main()
