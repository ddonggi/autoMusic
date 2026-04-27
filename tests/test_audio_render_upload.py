import json
import sys
import tempfile
import unittest
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from automusic.audio import write_pcm16_wav
from automusic.image import decode_image_response
from automusic.render import build_render_command, render_batch
from automusic.state import save_json
from automusic.youtube import build_video_body, should_skip_upload, update_batch_after_upload


class AudioRenderUploadTests(unittest.TestCase):
    def test_write_pcm16_wav_writes_valid_stereo_file(self):
        pcm = [b"\x00\x00\x00\x00" * 10]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "audio.wav"

            duration = write_pcm16_wav(pcm, path)

            with wave.open(str(path), "rb") as wav_file:
                channels = wav_file.getnchannels()
                sample_rate = wav_file.getframerate()
                frames = wav_file.getnframes()

        self.assertEqual(channels, 2)
        self.assertEqual(sample_rate, 48000)
        self.assertEqual(frames, 10)
        self.assertGreater(duration, 0)

    def test_decode_image_response_reads_b64_json(self):
        class ImageData:
            b64_json = "aGVsbG8="

        class Response:
            data = [ImageData()]

        self.assertEqual(decode_image_response(Response()), b"hello")

    def test_build_render_command_contains_expected_inputs(self):
        command = build_render_command(
            image_paths=[Path("one.png"), Path("two.png")],
            audio_paths=[Path("one.wav"), Path("two.wav")],
            output_path=Path("video.mp4"),
            concat_file=Path("audio.txt"),
            image_list_file=Path("images.txt"),
        )

        joined = " ".join(command)

        self.assertIn("ffmpeg", command[0])
        self.assertIn("audio.txt", joined)
        self.assertIn("images.txt", joined)
        self.assertIn("video.mp4", command)

    def test_render_batch_writes_image_durations(self):
        calls = []

        def fake_runner(command, check):
            calls.append((command, check))

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tracks_root = root / "tracks"
            batch_path = root / "batches" / "batch-001"
            batch_path.mkdir(parents=True)
            for track_id, duration in [("track-001", 180.0), ("track-002", 181.5)]:
                track_dir = tracks_root / track_id
                track_dir.mkdir(parents=True)
                (track_dir / "audio.wav").write_bytes(b"fake")
                (track_dir / "image.png").write_bytes(b"fake")
                save_json(
                    track_dir / "track.json",
                    {
                        "track_id": track_id,
                        "status": "batched",
                        "audio_path": "audio.wav",
                        "image_path": "image.png",
                        "duration_seconds": duration,
                    },
                )
            save_json(
                batch_path / "batch.json",
                {
                    "batch_id": "batch-001",
                    "status": "assembled",
                    "track_ids": ["track-001", "track-002"],
                    "video_path": "video.mp4",
                },
            )

            render_batch(batch_path, tracks_root, runner=fake_runner)
            image_list = (batch_path / "image_concat.txt").read_text()

        self.assertIn("duration 180.0", image_list)
        self.assertIn("duration 181.5", image_list)
        self.assertEqual(calls[0][1], True)

    def test_upload_skips_batch_with_existing_video_id(self):
        self.assertTrue(should_skip_upload({"youtube_video_id": "abc123"}))
        self.assertFalse(should_skip_upload({"youtube_video_id": None}))

    def test_update_batch_after_upload_records_video_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "batch.json"
            path.write_text(json.dumps({"status": "rendered"}))

            update_batch_after_upload(path, "abc123")

            batch = json.loads(path.read_text())

        self.assertEqual(batch["status"], "uploaded")
        self.assertEqual(batch["youtube_video_id"], "abc123")

    def test_build_video_body_defaults_to_private(self):
        body = build_video_body(
            {
                "title_template": "Daily Brazilian Phonk Mix",
                "description_template": "Generated workout mix",
                "tags": ["brazilian phonk", "workout"],
            }
        )

        self.assertEqual(body["snippet"]["title"], "Daily Brazilian Phonk Mix")
        self.assertEqual(body["status"]["privacyStatus"], "private")
        self.assertEqual(body["snippet"]["tags"], ["brazilian phonk", "workout"])


if __name__ == "__main__":
    unittest.main()
