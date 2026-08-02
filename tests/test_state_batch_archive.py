import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from automusic.archive import archive_success
from automusic.batch import build_batch
from automusic.state import save_json, transition_track_status


class StateBatchArchiveTests(unittest.TestCase):
    def test_transition_track_status_allows_expected_flow(self):
        track = {"status": "generated"}

        transition_track_status(track, "batched")

        self.assertEqual(track["status"], "batched")

    def test_transition_track_status_rejects_invalid_jump(self):
        track = {"status": "generated"}

        with self.assertRaisesRegex(ValueError, "generated -> uploaded"):
            transition_track_status(track, "uploaded")

    def test_build_batch_selects_oldest_ten_generated_tracks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tracks_root = root / "workspace" / "tracks"
            batches_root = root / "workspace" / "batches"
            tracks_root.mkdir(parents=True)
            for index in range(12):
                track_dir = tracks_root / f"track-{index:02d}"
                track_dir.mkdir()
                save_json(
                    track_dir / "track.json",
                    {
                        "track_id": f"track-{index:02d}",
                        "status": "generated",
                        "created_at": f"2026-04-27T00:{index:02d}:00+09:00",
                        "audio_path": "audio.wav",
                    },
                )

            batch_path = build_batch(tracks_root, batches_root, batch_count=10)
            batch = json.loads((batch_path / "batch.json").read_text())

        self.assertEqual(len(batch["track_ids"]), 10)
        self.assertEqual(batch["track_ids"][0], "track-00")
        self.assertEqual(batch["track_ids"][-1], "track-09")

    def test_build_batch_uses_generated_tracks_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tracks_root = root / "workspace" / "tracks"
            batches_root = root / "workspace" / "batches"
            tracks_root.mkdir(parents=True)
            for index in range(3):
                track_dir = tracks_root / f"track-{index:02d}"
                track_dir.mkdir()
                save_json(
                    track_dir / "track.json",
                    {
                        "track_id": f"track-{index:02d}",
                        "status": "generated" if index < 2 else "legacy",
                        "created_at": f"2026-04-27T00:0{index}:00+09:00",
                        "audio_path": "audio.wav",
                    },
                )

            batch_path = build_batch(tracks_root, batches_root, batch_count=2)
            batch = json.loads((batch_path / "batch.json").read_text())

        self.assertEqual(batch["track_ids"], ["track-00", "track-01"])

    def test_archive_success_moves_uploaded_batch_and_tracks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "workspace"
            success = root / "success"
            tracks_root = workspace / "tracks"
            batch_root = workspace / "batches" / "batch-001"
            tracks_root.mkdir(parents=True)
            batch_root.mkdir(parents=True)
            for track_id in ["track-001", "track-002"]:
                track_dir = tracks_root / track_id
                track_dir.mkdir()
                save_json(track_dir / "track.json", {"track_id": track_id, "status": "uploaded"})
            save_json(
                batch_root / "batch.json",
                {
                    "batch_id": "batch-001",
                    "status": "uploaded",
                    "track_ids": ["track-001", "track-002"],
                    "youtube_video_id": "abc123",
                },
            )

            archived_batch = archive_success(batch_root, tracks_root, success)

            self.assertEqual(archived_batch, success / "batches" / "batch-001")
            self.assertTrue((success / "tracks" / "track-001").exists())
            self.assertTrue((success / "tracks" / "track-002").exists())
            self.assertTrue((success / "batches" / "batch-001").exists())


if __name__ == "__main__":
    unittest.main()
