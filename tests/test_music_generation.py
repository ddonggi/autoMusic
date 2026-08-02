import asyncio
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from automusic.music import generate_lyria_track


class MusicGenerationTests(unittest.TestCase):
    def test_generate_lyria_track_normalizes_and_stores_custom_music_prompt(self):
        received_prompts = []

        async def producer(prompt, config, music_result, target_seconds):
            received_prompts.append(prompt)
            return [b"\0" * 48_000 * 2 * 2]

        custom_prompt = "  A quiet custom study focus arrangement.  "
        normalized_prompt = "A quiet custom study focus arrangement."
        with tempfile.TemporaryDirectory() as tmp:
            track_dir = asyncio.run(
                generate_lyria_track(
                    {"duration_seconds": 1, "genre": "Brazilian phonk"},
                    Path(tmp) / "tracks",
                    music_prompt=custom_prompt,
                    music_chunk_producer=producer,
                )
            )
            track = json.loads((track_dir / "track.json").read_text())

        self.assertEqual(received_prompts, [normalized_prompt])
        self.assertEqual(track["music_prompt"], normalized_prompt)

    def test_generate_lyria_track_falls_back_for_whitespace_only_music_prompt(self):
        received_prompts = []

        async def producer(prompt, config, music_result, target_seconds):
            received_prompts.append(prompt)
            return [b"\0" * 48_000 * 2 * 2]

        with tempfile.TemporaryDirectory() as tmp:
            track_dir = asyncio.run(
                generate_lyria_track(
                    {"duration_seconds": 1, "genre": "Brazilian phonk"},
                    Path(tmp) / "tracks",
                    music_prompt="  \t\n  ",
                    music_chunk_producer=producer,
                )
            )
            track = json.loads((track_dir / "track.json").read_text())

        self.assertEqual(received_prompts, [track["music_prompt"]])
        self.assertIn("Create a 1-second Brazilian phonk track", track["music_prompt"])

    def test_generate_lyria_track_retries_transient_music_errors(self):
        attempts = 0

        async def flaky_producer(prompt, config, music_result, target_seconds):
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                raise RuntimeError("1006 abnormal closure [internal]")
            return [b"\0" * 48_000 * 2 * 2]

        with tempfile.TemporaryDirectory() as tmp:
            tracks_root = Path(tmp) / "workspace" / "tracks"
            track_dir = asyncio.run(
                generate_lyria_track(
                    {
                        "duration_seconds": 1,
                        "genre": "Brazilian phonk",
                        "lyria_retries": 3,
                        "lyria_retry_delay_seconds": 0,
                    },
                    tracks_root,
                    music_chunk_producer=flaky_producer,
                )
            )
            track = json.loads((track_dir / "track.json").read_text())
            audio_exists = (track_dir / "audio.wav").exists()

        self.assertEqual(attempts, 3)
        self.assertEqual(track["status"], "generated")
        self.assertEqual(track["audio_path"], "audio.wav")
        self.assertTrue(audio_exists)

    def test_generate_lyria_track_does_not_leave_empty_dir_after_music_failure(self):
        async def failing_producer(prompt, config, music_result, target_seconds):
            raise RuntimeError("1006 abnormal closure [internal]")

        with tempfile.TemporaryDirectory() as tmp:
            tracks_root = Path(tmp) / "workspace" / "tracks"
            with self.assertRaisesRegex(RuntimeError, "1006 abnormal closure"):
                asyncio.run(
                    generate_lyria_track(
                        {
                            "duration_seconds": 1,
                            "genre": "Brazilian phonk",
                            "lyria_retries": 1,
                            "lyria_retry_delay_seconds": 0,
                        },
                        tracks_root,
                        music_chunk_producer=failing_producer,
                    )
                )

            created_tracks = list(tracks_root.iterdir()) if tracks_root.exists() else []

        self.assertEqual(created_tracks, [])


if __name__ == "__main__":
    unittest.main()
