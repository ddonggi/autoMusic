import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


class RunDailyTests(unittest.TestCase):
    def test_run_daily_sends_failure_notification_when_music_generation_fails(self):
        module = _load_run_daily_module()
        notifications = []

        async def failing_track_generator(config, tracks_root):
            raise RuntimeError("1006 abnormal closure [internal]")

        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(RuntimeError, "1006 abnormal closure"):
                module.run_daily(
                    {"duration_seconds": 1, "genre": "Brazilian phonk"},
                    Path(tmp),
                    track_generator=failing_track_generator,
                    notification_sender=lambda notification: notifications.append(notification) or True,
                )

        self.assertEqual(len(notifications), 1)
        self.assertIn("음악 생성 실패", notifications[0].subject)
        self.assertIn("music_generation", notifications[0].body)
        self.assertIn("1006 abnormal closure", notifications[0].body)


def _load_run_daily_module():
    module_path = Path(__file__).resolve().parents[1] / "scripts" / "run_daily.py"
    spec = importlib.util.spec_from_file_location("run_daily_script", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load run_daily.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["run_daily_script"] = module
    spec.loader.exec_module(module)
    return module


if __name__ == "__main__":
    unittest.main()
