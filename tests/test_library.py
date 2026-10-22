import json
import sys
import tempfile
import unittest
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from automusic.library import LibraryService


class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.service = LibraryService(self.root)

    def track(self, relative, **overrides):
        folder = self.root / relative
        folder.mkdir(parents=True, exist_ok=True)
        with wave.open(str(folder / "song.wav"), "wb") as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(8000)
            audio.writeframes(b"\x00\x00" * 8000)
        metadata = {
            "track_id": folder.name,
            "title": "Quiet Page",
            "status": "generated",
            "category_id": "study",
            "music_variant": "quiet-piano",
            "audio_path": "song.wav",
            "music_prompt": "Gentle piano for concentration",
            "created_at": "2026-10-23T12:00:00+09:00",
        }
        metadata.update(overrides)
        (folder / "track.json").write_text(json.dumps(metadata))
        return folder

    def test_combines_existing_archived_and_completed_web_tracks(self):
        self.track("workspace/tracks/one")
        self.track("success/tracks/two", status="archived")
        folder = self.track("workspace/web-jobs/job/three")
        (folder.parent / "job.json").write_text(json.dumps({
            "status": "completed", "category_id": "study",
            "artifacts": {"audio": "three/song.wav"},
        }))
        result = self.service.list_items()
        self.assertEqual(result["unreadable_count"], 0)
        self.assertEqual(len(result["items"]), 3)
        self.assertEqual({item["source"] for item in result["items"]},
                         {"automation", "archived", "web"})
        for item in result["items"]:
            self.assertEqual(item["duration_seconds"], 1)
            self.assertEqual(item["category_id"], "study")
            self.assertEqual(item["variant_id"], "quiet-piano")
            self.assertEqual(self.service.asset_path(item["id"]).name, "song.wav")
            self.assertNotIn(str(self.root), json.dumps(item))

    def test_incomplete_web_job_is_not_exposed(self):
        folder = self.track("workspace/web-jobs/job/one")
        (folder.parent / "job.json").write_text('{"status":"generating_music"}')
        self.assertEqual(self.service.list_items()["items"], [])

    def test_malformed_record_does_not_hide_good_record(self):
        self.track("workspace/tracks/good")
        folder = self.track("workspace/tracks/bad")
        (folder / "track.json").write_text("not json")
        result = self.service.list_items()
        self.assertEqual(len(result["items"]), 1)
        self.assertEqual(result["unreadable_count"], 1)

    def test_outside_audio_and_symlinked_directory_are_rejected(self):
        outside = self.track("private/outside")
        self.track("workspace/tracks/escape", audio_path=str(outside / "song.wav"))
        (self.root / "workspace/tracks/link").symlink_to(outside, target_is_directory=True)
        self.assertEqual(self.service.list_items()["items"], [])
        with self.assertRaises((ValueError, FileNotFoundError)):
            self.service.asset_path("../../private/outside/song.wav")

    def test_symlinked_storage_root_is_rejected(self):
        self.track("private/outside")
        (self.root / "workspace").mkdir()
        (self.root / "workspace/tracks").symlink_to(self.root / "private", target_is_directory=True)
        self.assertEqual(self.service.list_items()["items"], [])

    def test_non_wav_or_missing_audio_not_offered(self):
        one = self.track("workspace/tracks/one")
        (one / "song.wav").write_text("not audio")
        two = self.track("workspace/tracks/two")
        (two / "song.wav").unlink()
        self.assertEqual(self.service.list_items()["items"], [])

    def test_asset_is_revalidated_after_listing(self):
        folder = self.track("workspace/tracks/one")
        item = self.service.list_items()["items"][0]
        outside = self.track("private/outside")
        (folder / "song.wav").unlink()
        (folder / "song.wav").symlink_to(outside / "song.wav")
        with self.assertRaises(FileNotFoundError):
            self.service.asset_path(item["id"])

    def test_empty_and_legacy_metadata_stay_honest(self):
        self.assertEqual(self.service.list_items(), {"items": [], "unreadable_count": 0})
        self.track("workspace/tracks/legacy", category_id=None, created_at=None,
                   music_variant=None, model=None)
        item = self.service.list_items()["items"][0]
        self.assertIsNone(item["category_id"])
        self.assertIsNone(item["created_at"])
        self.assertIsNone(item["model"])

    def test_bad_category_yaml_does_not_hide_existing_audio(self):
        self.track("workspace/tracks/one", category_id=None, genre="Focus")
        categories = self.root / "configs/categories"
        categories.mkdir(parents=True)
        (categories / "broken.yaml").write_text("genre: [broken")
        self.assertEqual(len(self.service.list_items()["items"]), 1)

    def test_legacy_category_inferred_only_when_genre_unambiguous(self):
        self.track("workspace/tracks/one", category_id=None, genre="Focus")
        categories = self.root / "configs/categories"
        categories.mkdir(parents=True)
        (categories / "study.yaml").write_text("genre: Focus\n")
        self.assertEqual(self.service.list_items()["items"][0]["category_id"], "study")
        (categories / "cafe.yaml").write_text("genre: Focus\n")
        self.assertIsNone(self.service.list_items()["items"][0]["category_id"])


if __name__ == "__main__":
    unittest.main()
