import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from automusic.batch import find_pending_batch
from automusic.batch_upload import run_batch_upload
from automusic.state import save_json


class BatchUploadResumeTests(unittest.TestCase):
    def test_find_pending_batch_prefers_oldest_incomplete_batch(self):
        with tempfile.TemporaryDirectory() as tmp:
            batches_root = Path(tmp) / "workspace" / "batches"
            old_batch = batches_root / "old-batch"
            new_batch = batches_root / "new-batch"
            archived_batch = batches_root / "done-batch"
            old_batch.mkdir(parents=True)
            new_batch.mkdir()
            archived_batch.mkdir()
            save_json(
                old_batch / "batch.json",
                {
                    "batch_id": "old-batch",
                    "status": "rendered",
                    "created_at": "2026-05-01T00:00:00+09:00",
                },
            )
            save_json(
                new_batch / "batch.json",
                {
                    "batch_id": "new-batch",
                    "status": "assembled",
                    "created_at": "2026-05-02T00:00:00+09:00",
                },
            )
            save_json(
                archived_batch / "batch.json",
                {
                    "batch_id": "done-batch",
                    "status": "archived",
                    "created_at": "2026-04-30T00:00:00+09:00",
                },
            )

            pending = find_pending_batch(batches_root)

        self.assertEqual(pending, old_batch)

    def test_run_batch_upload_reuses_rendered_batch_and_skips_render(self):
        calls = []

        def fake_render(batch_path, tracks_root):
            calls.append(("render", batch_path.name))
            return batch_path / "video.mp4"

        def fake_require_env(names):
            calls.append(("env", tuple(names)))

        def fake_upload(batch_path, config):
            calls.append(("upload", batch_path.name, config["title_template"]))
            return "video-123"

        def fake_archive(batch_path, tracks_root, success_root):
            calls.append(("archive", batch_path.name))
            return success_root / "batches" / batch_path.name

        notifications = []

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            batch_path = root / "workspace" / "batches" / "batch-001"
            batch_path.mkdir(parents=True)
            (batch_path / "video.mp4").write_bytes(b"video")
            (batch_path / "image.png").write_bytes(b"image")
            save_json(
                batch_path / "batch.json",
                {
                    "batch_id": "batch-001",
                    "status": "rendered",
                    "track_ids": ["track-001"],
                    "video_path": "video.mp4",
                    "image_path": "image.png",
                    "youtube_video_id": None,
                    "archive_pending": False,
                    "created_at": "2026-05-01T00:00:00+09:00",
                },
            )
            track_dir = root / "workspace" / "tracks" / "track-001"
            track_dir.mkdir(parents=True)
            save_json(track_dir / "track.json", {"track_id": "track-001", "status": "batched"})

            archived = run_batch_upload(
                root,
                {"title_template": "Workout Mix"},
                render_func=fake_render,
                require_youtube_env=fake_require_env,
                upload_func=fake_upload,
                archive_func=fake_archive,
                notifier=notifications.append,
            )
            expected_archive = root / "success" / "batches" / "batch-001"

        self.assertEqual(archived, expected_archive)
        self.assertNotIn(("render", "batch-001"), calls)
        self.assertIn(("env", ("YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET", "YOUTUBE_REFRESH_TOKEN")), calls)
        self.assertIn(("upload", "batch-001", "Workout Mix"), calls)
        self.assertIn(("archive", "batch-001"), calls)
        self.assertIn("batch-001", notifications[0].body)
        self.assertIn("video-123", notifications[0].body)

    def test_run_batch_upload_generates_shared_image_once_and_persists_prompt(self):
        image_calls = []

        def fake_image(prompt, output_path):
            image_calls.append((prompt, output_path))
            output_path.write_bytes(b"shared image")
            return output_path

        def fake_render(batch_path, tracks_root):
            batch = {
                **json.loads((batch_path / "batch.json").read_text()),
                "status": "rendered",
                "video_path": "video.mp4",
            }
            (batch_path / "video.mp4").write_bytes(b"video")
            save_json(batch_path / "batch.json", batch)
            return batch_path / "video.mp4"

        def fake_upload(batch_path, config):
            return "video-123"

        def fake_archive(batch_path, tracks_root, success_root):
            return success_root / "batches" / batch_path.name

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            batch_path = root / "workspace" / "batches" / "batch-001"
            batch_path.mkdir(parents=True)
            save_json(
                batch_path / "batch.json",
                {
                    "batch_id": "batch-001",
                    "status": "assembled",
                    "track_ids": ["track-001"],
                    "youtube_video_id": None,
                    "created_at": "2026-05-01T00:00:00+09:00",
                },
            )
            track_dir = root / "workspace" / "tracks" / "track-001"
            track_dir.mkdir(parents=True)
            save_json(
                track_dir / "track.json",
                {
                    "track_id": "track-001",
                    "status": "batched",
                    "music_prompt": "Create a focused study track.",
                    "genre": "Study focus ambient",
                    "mood": ["focused"],
                    "texture": ["soft"],
                },
            )

            run_batch_upload(
                root,
                {"image_context": "study focus music video"},
                image_generator=fake_image,
                render_func=fake_render,
                require_youtube_env=lambda names: None,
                upload_func=fake_upload,
                archive_func=fake_archive,
                notifier=lambda message: None,
            )

            batch = json.loads((batch_path / "batch.json").read_text())

        self.assertEqual(len(image_calls), 1)
        self.assertIn("study focus music video", image_calls[0][0])
        self.assertEqual(batch["image_path"], "image.png")
        self.assertEqual(batch["image_prompt"], image_calls[0][0])

    def test_run_batch_upload_archives_uploaded_pending_batch_without_upload(self):
        calls = []

        def fake_archive(batch_path, tracks_root, success_root):
            calls.append(("archive", batch_path.name))
            return success_root / "batches" / batch_path.name

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            batch_path = root / "workspace" / "batches" / "batch-001"
            batch_path.mkdir(parents=True)
            save_json(
                batch_path / "batch.json",
                {
                    "batch_id": "batch-001",
                    "status": "uploaded",
                    "track_ids": [],
                    "video_path": "video.mp4",
                    "youtube_video_id": "video-123",
                    "archive_pending": True,
                    "created_at": "2026-05-01T00:00:00+09:00",
                },
            )

            run_batch_upload(
                root,
                {},
                render_func=lambda batch_path, tracks_root: self.fail("render should be skipped"),
                require_youtube_env=lambda names: self.fail("env should be skipped"),
                upload_func=lambda batch_path, config: self.fail("upload should be skipped"),
                archive_func=fake_archive,
                notifier=lambda message: None,
            )

        self.assertEqual(calls, [("archive", "batch-001")])

    def test_run_batch_upload_sends_failure_notification_when_youtube_env_missing(self):
        notifications = []

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            batch_path = root / "workspace" / "batches" / "batch-001"
            batch_path.mkdir(parents=True)
            (batch_path / "video.mp4").write_bytes(b"video")
            (batch_path / "image.png").write_bytes(b"image")
            save_json(
                batch_path / "batch.json",
                {
                    "batch_id": "batch-001",
                    "status": "rendered",
                    "track_ids": [],
                    "video_path": "video.mp4",
                    "image_path": "image.png",
                    "youtube_video_id": None,
                    "archive_pending": False,
                    "created_at": "2026-05-01T00:00:00+09:00",
                },
            )

            with self.assertRaisesRegex(RuntimeError, "missing youtube credentials"):
                run_batch_upload(
                    root,
                    {},
                    render_func=lambda batch_path, tracks_root: self.fail("render should be skipped"),
                    require_youtube_env=lambda names: (_ for _ in ()).throw(
                        RuntimeError("missing youtube credentials")
                    ),
                    upload_func=lambda batch_path, config: self.fail("upload should not run"),
                    archive_func=lambda batch_path, tracks_root, success_root: success_root,
                    notifier=notifications.append,
                )

        self.assertEqual(len(notifications), 1)
        self.assertIn("실패", notifications[0].subject)
        self.assertIn("batch-001", notifications[0].body)
        self.assertIn("youtube_credentials", notifications[0].body)
        self.assertIn("missing youtube credentials", notifications[0].body)


if __name__ == "__main__":
    unittest.main()
