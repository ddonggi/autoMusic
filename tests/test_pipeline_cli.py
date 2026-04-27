import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from automusic.pipeline import dry_run_batch_upload, dry_run_daily, dry_run_image, dry_run_music
from automusic.state import save_json


class PipelineCliTests(unittest.TestCase):
    def test_dry_run_music_creates_generated_track_without_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = {"duration_seconds": 180, "genre": "Brazilian phonk"}

            track_dir = dry_run_music(config, root / "workspace" / "tracks")
            track = json.loads((track_dir / "track.json").read_text())

        self.assertEqual(track["status"], "generated")
        self.assertEqual(track["audio_path"], "audio.wav")
        self.assertIsNone(track["image_path"])

    def test_dry_run_music_generates_unique_track_dirs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tracks_root = root / "workspace" / "tracks"

            first = dry_run_music({"duration_seconds": 180}, tracks_root)
            second = dry_run_music({"duration_seconds": 180}, tracks_root)

        self.assertNotEqual(first.name, second.name)

    def test_dry_run_image_updates_generated_track(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            track_dir = dry_run_music({"duration_seconds": 180}, root / "workspace" / "tracks")

            dry_run_image(track_dir)
            track = json.loads((track_dir / "track.json").read_text())

        self.assertEqual(track["status"], "imaged")
        self.assertEqual(track["image_path"], "image.png")
        self.assertTrue(track["image_prompt"])

    def test_dry_run_daily_creates_generated_and_imaged_track(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = {
                "duration_seconds": 180,
                "genre": "Brazilian phonk",
                "bpm_min": 132,
                "bpm_max": 138,
                "mood": ["aggressive"],
                "instruments": ["distorted 808 bass"],
                "texture": ["gritty street-gym atmosphere"],
                "vocals": "none",
            }

            track_dir = dry_run_daily(config, root / "workspace" / "tracks")
            track = json.loads((track_dir / "track.json").read_text())

        self.assertEqual(track["status"], "imaged")
        self.assertEqual(track["audio_path"], "audio.wav")
        self.assertEqual(track["image_path"], "image.png")
        self.assertTrue(track["music_prompt"])
        self.assertTrue(track["image_prompt"])

    def test_dry_run_batch_upload_requires_ten_tracks_and_archives_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tracks_root = root / "workspace" / "tracks"
            tracks_root.mkdir(parents=True)
            for index in range(10):
                track_dir = tracks_root / f"track-{index:02d}"
                track_dir.mkdir()
                (track_dir / "audio.wav").write_bytes(b"fake")
                (track_dir / "image.png").write_bytes(b"fake")
                save_json(
                    track_dir / "track.json",
                    {
                        "track_id": f"track-{index:02d}",
                        "status": "imaged",
                        "created_at": f"2026-04-27T00:{index:02d}:00+09:00",
                        "audio_path": "audio.wav",
                        "image_path": "image.png",
                    },
                )

            archived_batch = dry_run_batch_upload(root)

            self.assertTrue(archived_batch.exists())
            self.assertTrue((root / "success" / "tracks" / "track-00").exists())
            self.assertFalse((root / "workspace" / "tracks" / "track-00").exists())


if __name__ == "__main__":
    unittest.main()
