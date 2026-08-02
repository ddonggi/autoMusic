import asyncio
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from automusic.prompts import build_music_prompt_with_metadata
from automusic.web_jobs import WebJobService


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
                    executor=ImmediateExecutor(),
                )
                job = service.start("study", requested_prompt)

            self.assertEqual(job["music_prompt"], expected_prompt)
            self.assertEqual(received_prompts, [expected_prompt])

    def test_completed_job_exposes_only_audio(self):
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
                        "audio_path": "audio.wav",
                        "music_prompt": music_prompt,
                    }
                )
            )
            return track_dir

        with tempfile.TemporaryDirectory() as tmp:
            service = WebJobService(
                Path(tmp),
                {"study": {"genre": "Study focus ambient"}},
                track_generator=track_generator,
                executor=ImmediateExecutor(),
            )
            job = service.start("study", "Custom concentration prompt")
            stored = service.get(job["id"])
            audio_path = service.asset_path(job["id"], "audio")

            with self.assertRaises(ValueError):
                service.asset_path(job["id"], "image")
            with self.assertRaises(ValueError):
                service.asset_path(job["id"], "video")

        self.assertEqual(stored["status"], "completed")
        self.assertEqual(set(stored["artifacts"]), {"audio"})
        self.assertEqual(received_prompts, ["Custom concentration prompt"])
        self.assertEqual(audio_path.name, "audio.wav")

    def test_get_never_reads_partial_json_during_background_job_update(self):
        async def unused_track_generator(config, tracks_root, *, music_prompt=None):
            raise AssertionError("job should not run")

        with tempfile.TemporaryDirectory() as tmp:
            service = WebJobService(
                Path(tmp),
                {"study": {"genre": "Study focus ambient"}},
                track_generator=unused_track_generator,
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
            from unittest.mock import patch

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


if __name__ == "__main__":
    unittest.main()
