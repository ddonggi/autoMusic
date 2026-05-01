import json
import shutil
import subprocess
import sys
import tempfile
import unittest
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from automusic.audio import write_pcm16_wav
from automusic.image import decode_image_response
from automusic.render import build_concat_command, build_segment_command, render_batch
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

    def test_build_segment_command_contains_expected_inputs(self):
        command = build_segment_command(
            image_path=Path("one.png"),
            audio_path=Path("one.wav"),
            output_path=Path("segment.mp4"),
            duration=180.0,
        )

        joined = " ".join(command)

        self.assertIn("ffmpeg", command[0])
        self.assertIn("one.png", joined)
        self.assertIn("one.wav", joined)
        self.assertIn("segment.mp4", command)
        self.assertIn("180.0", command)

    def test_build_concat_command_contains_expected_inputs(self):
        command = build_concat_command(
            concat_file=Path("video_concat.txt"),
            output_path=Path("video.mp4"),
        )

        joined = " ".join(command)

        self.assertIn("ffmpeg", command[0])
        self.assertIn("video_concat.txt", joined)
        self.assertIn("video.mp4", command)
        self.assertIn("copy", command)

    def test_render_batch_writes_segment_concat_and_runs_all_commands(self):
        calls = []

        def fake_runner(command, check):
            calls.append((command, check))
            output_path = Path(command[-1])
            if output_path.name.startswith("segment_"):
                output_path.write_bytes(b"fake segment")

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
            segment_list = (batch_path / "video_concat.txt").read_text()
            batch = json.loads((batch_path / "batch.json").read_text())

        self.assertIn("segment_000.mp4", segment_list)
        self.assertIn("segment_001.mp4", segment_list)
        self.assertEqual(len(calls), 3)
        self.assertTrue(all(call[1] for call in calls))
        self.assertEqual(batch["duration_seconds"], 361.5)

    def test_render_batch_video_stream_matches_two_audio_segments(self):
        if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
            self.skipTest("ffmpeg and ffprobe are required")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tracks_root = root / "tracks"
            batch_path = root / "batches" / "batch-001"
            batch_path.mkdir(parents=True)
            for track_id in ["track-001", "track-002"]:
                track_dir = tracks_root / track_id
                track_dir.mkdir(parents=True)
                write_pcm16_wav([b"\x00\x00\x00\x00" * 48_000], track_dir / "audio.wav")
                (track_dir / "image.png").write_bytes(_one_pixel_png())
                save_json(
                    track_dir / "track.json",
                    {
                        "track_id": track_id,
                        "status": "batched",
                        "audio_path": "audio.wav",
                        "image_path": "image.png",
                        "duration_seconds": 1.0,
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

            output = render_batch(batch_path, tracks_root)
            probe = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    "stream=codec_type,duration",
                    "-of",
                    "json",
                    str(output),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            streams = json.loads(probe.stdout)["streams"]

        durations = {stream["codec_type"]: float(stream["duration"]) for stream in streams}
        self.assertGreaterEqual(durations["video"], 1.9)
        self.assertGreaterEqual(durations["audio"], 1.9)

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


def _one_pixel_png() -> bytes:
    return bytes.fromhex(
        "89504e470d0a1a0a0000000d4948445200000001000000010802000000907753de"
        "0000000c4944415408d763f8ffff3f0005fe02fea73581e40000000049454e44ae426082"
    )
