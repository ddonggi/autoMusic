import asyncio
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from automusic.web_jobs import WebJobService
from automusic.prompts import build_music_prompt_with_metadata


class ImmediateExecutor:
    def submit(self, function, *args):
        return function(*args)


class DeferredExecutor:
    def submit(self, function, *args):
        self.function = function
        self.args = args


class WebJobServiceTests(unittest.TestCase):
    def test_start_uses_generated_default_prompt_for_none_and_whitespace(self):
        preset = {"genre": "Study focus ambient", "seed": 1}
        expected_prompt = str(build_music_prompt_with_metadata(preset)["prompt"])

        for requested_prompt in (None, "  \t\n  "):
            received_prompts = []

            async def track_generator(config, tracks_root, *, music_prompt=None):
                received_prompts.append(music_prompt)
                raise RuntimeError("stop after prompt capture")

            with tempfile.TemporaryDirectory() as tmp:
                service = WebJobService(
                    Path(tmp),
                    {"study": preset},
                    track_generator=track_generator,
                    image_generator=lambda prompt, output_path: output_path,
                    track_renderer=lambda track_dir: track_dir / "video.mp4",
                    executor=ImmediateExecutor(),
                )

                job = service.start("study", requested_prompt)

            self.assertEqual(job["music_prompt"], expected_prompt)
            self.assertEqual(received_prompts, [expected_prompt])

    def test_get_never_reads_partial_json_during_background_job_update(self):
        async def unused_track_generator(config, tracks_root, *, music_prompt=None):
            raise AssertionError("job should not run")

        with tempfile.TemporaryDirectory() as tmp:
            service = WebJobService(
                Path(tmp),
                {"study": {"genre": "Study focus ambient"}},
                track_generator=unused_track_generator,
                image_generator=lambda prompt, output_path: output_path,
                track_renderer=lambda track_dir: track_dir / "video.mp4",
                executor=DeferredExecutor(),
            )
            job = service.start("study", "Prompt")
            job_dir = service._job_dir(job["id"])
            job_path = job_dir / "job.json"
            original_write_text = Path.write_text
            original_replace = Path.replace
            write_started = threading.Event()
            allow_write_finish = threading.Event()
            read_errors = []

            def controlled_write_text(path, text, *args, **kwargs):
                if path == job_path:
                    with path.open("w") as handle:
                        midpoint = len(text) // 2
                        handle.write(text[:midpoint])
                        handle.flush()
                        write_started.set()
                        allow_write_finish.wait(timeout=1)
                        handle.write(text[midpoint:])
                    return len(text)
                return original_write_text(path, text, *args, **kwargs)

            def controlled_replace(path, target):
                if target == job_path:
                    write_started.set()
                    allow_write_finish.wait(timeout=1)
                return original_replace(path, target)

            updating_job = service.get(job["id"])
            with (
                patch.object(Path, "write_text", controlled_write_text),
                patch.object(Path, "replace", controlled_replace),
            ):
                worker = threading.Thread(
                    target=service._set_status,
                    args=(job_dir, updating_job, "generating_music"),
                )
                worker.start()
                write_started.wait(timeout=1)
                for _ in range(10):
                    try:
                        service.get(job["id"])
                    except json.JSONDecodeError as error:
                        read_errors.append(error)
                allow_write_finish.set()
                worker.join(timeout=1)

        self.assertFalse(read_errors)

    def test_completed_job_runs_full_lifecycle_with_custom_prompt_and_relative_assets(self):
        received_prompts = []

        async def track_generator(config, tracks_root, *, music_prompt=None):
            received_prompts.append(music_prompt)
            track_dir = tracks_root / "track-001"
            track_dir.mkdir(parents=True)
            (track_dir / "audio.wav").write_bytes(b"audio")
            (track_dir / "track.json").write_text(
                json.dumps(
                    {
                        "track_id": "track-001",
                        "status": "generated",
                        "genre": config["genre"],
                        "mood": ["calm"],
                        "texture": ["soft"],
                        "music_variant": "study",
                        "image_variant": None,
                        "music_prompt": music_prompt,
                        "image_prompt": None,
                        "duration_seconds": 1,
                        "audio_path": "audio.wav",
                        "image_path": None,
                    }
                )
            )
            return track_dir

        def image_generator(prompt, output_path):
            self.assertIn("study focus music video", prompt)
            output_path.write_bytes(b"image")
            return output_path

        def track_renderer(track_dir):
            output_path = track_dir / "video.mp4"
            output_path.write_bytes(b"video")
            return output_path

        presets = {
            "study": {
                "genre": "Study focus ambient",
                "image_context": "study focus music video",
            }
        }
        with tempfile.TemporaryDirectory() as tmp:
            service = WebJobService(
                Path(tmp),
                presets,
                track_generator=track_generator,
                image_generator=image_generator,
                track_renderer=track_renderer,
                executor=ImmediateExecutor(),
            )

            job = service.start("study", "Custom concentration prompt")
            stored = service.get(job["id"])
            audio_path = service.asset_path(job["id"], "audio")
            image_path = service.asset_path(job["id"], "image")
            video_path = service.asset_path(job["id"], "video")

        self.assertEqual(service.preset_ids, ["study"])
        self.assertEqual(service.preset_summaries()[0]["name"], "Study focus ambient")
        self.assertTrue(service.preset_summaries()[0]["default_prompt"])
        self.assertEqual(received_prompts, ["Custom concentration prompt"])
        self.assertEqual(stored["status"], "completed")
        self.assertEqual(set(stored["artifacts"]), {"audio", "image", "video"})
        self.assertTrue(all(not Path(path).is_absolute() for path in stored["artifacts"].values()))
        self.assertEqual((audio_path.name, image_path.name, video_path.name), ("audio.wav", "image.png", "video.mp4"))

    def test_image_failure_is_safe_and_preserves_audio_while_rejecting_invalid_assets(self):
        async def track_generator(config, tracks_root, *, music_prompt=None):
            track_dir = tracks_root / "track-001"
            track_dir.mkdir(parents=True)
            (track_dir / "audio.wav").write_bytes(b"audio")
            (track_dir / "track.json").write_text(
                json.dumps(
                    {
                        "track_id": "track-001",
                        "status": "generated",
                        "genre": config["genre"],
                        "mood": ["calm"],
                        "texture": ["soft"],
                        "music_variant": "study",
                        "music_prompt": music_prompt,
                        "duration_seconds": 1,
                        "audio_path": "audio.wav",
                        "image_path": None,
                    }
                )
            )
            return track_dir

        def image_generator(prompt, output_path):
            raise RuntimeError("secret-token-123")

        with tempfile.TemporaryDirectory() as tmp:
            service = WebJobService(
                Path(tmp),
                {"study": {"genre": "Study focus ambient"}},
                track_generator=track_generator,
                image_generator=image_generator,
                track_renderer=lambda track_dir: track_dir / "video.mp4",
                executor=ImmediateExecutor(),
            )

            job = service.start("study", "Prompt")
            stored = service.get(job["id"])
            audio_path = service.asset_path(job["id"], "audio")

            with self.assertRaises(ValueError):
                service.asset_path(job["id"], "../.env")
            with self.assertRaises(ValueError):
                service.asset_path(job["id"], "job.json")
            with self.assertRaises(FileNotFoundError):
                service.asset_path(job["id"], "video")

        self.assertEqual(stored["status"], "failed")
        self.assertEqual(set(stored["artifacts"]), {"audio"})
        self.assertEqual(audio_path.name, "audio.wav")
        self.assertIn("이미지", stored["error"])
        self.assertNotIn("secret-token-123", json.dumps(stored))


if __name__ == "__main__":
    unittest.main()
