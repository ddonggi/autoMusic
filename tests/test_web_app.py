import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from automusic.web_app import create_app


class FakeService:
    def __init__(self, audio_path: Path) -> None:
        self.audio_path = audio_path
        self.start_calls = []

    @property
    def preset_ids(self):
        return ["study"]

    def preset_summaries(self):
        return [
            {
                "id": "study",
                "name": "Study focus ambient",
                "default_prompt": "Create a calm study track.",
            }
        ]

    def start(self, preset_id, music_prompt):
        self.start_calls.append((preset_id, music_prompt))
        return {"id": "job-001", "status": "queued"}

    def get(self, job_id):
        if job_id != "job-001":
            raise FileNotFoundError(job_id)
        return {"id": job_id, "status": "completed", "artifacts": {"audio": "audio.wav"}}

    def asset_path(self, job_id, asset):
        if job_id != "job-001" or asset != "audio":
            raise FileNotFoundError(asset)
        return self.audio_path


class WebAppTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        audio_path = Path(self.temporary_directory.name) / "audio.wav"
        audio_path.write_bytes(b"audio")
        self.service = FakeService(audio_path)
        self.client = create_app(self.service).test_client()

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_wizard_and_presets_route(self):
        page = self.client.get("/")
        response = self.client.get("/api/presets")

        self.assertEqual(page.status_code, 200)
        self.assertIn("3단계", page.get_data(as_text=True))
        self.assertEqual(response.get_json()[0]["id"], "study")

    def test_create_job_validates_input_and_starts_known_preset(self):
        invalid = self.client.post("/api/jobs", json={"preset_id": "missing"})
        blank = self.client.post("/api/jobs", json={"preset_id": "study", "music_prompt": "  "})
        wrong_type = self.client.post("/api/jobs", json={"preset_id": "study", "music_prompt": 1})
        default_prompt = self.client.post("/api/jobs", json={"preset_id": "study"})
        valid = self.client.post(
            "/api/jobs",
            json={"preset_id": "study", "music_prompt": "Custom study prompt"},
        )

        self.assertEqual(invalid.status_code, 400)
        self.assertIn("프리셋", invalid.get_json()["error"])
        self.assertEqual(blank.status_code, 400)
        self.assertIn("프롬프트", blank.get_json()["error"])
        self.assertEqual(wrong_type.status_code, 400)
        self.assertEqual(default_prompt.status_code, 202)
        self.assertEqual(valid.status_code, 202)
        self.assertEqual(valid.get_json()["id"], "job-001")
        self.assertEqual(
            self.service.start_calls,
            [("study", None), ("study", "Custom study prompt")],
        )

    def test_status_and_download_routes_hide_missing_jobs_and_assets(self):
        status = self.client.get("/api/jobs/job-001")
        missing_job = self.client.get("/api/jobs/missing")
        download = self.client.get("/api/jobs/job-001/downloads/audio")
        missing_asset = self.client.get("/api/jobs/job-001/downloads/video")

        self.assertEqual(status.status_code, 200)
        self.assertEqual(status.get_json()["status"], "completed")
        self.assertEqual(missing_job.status_code, 404)
        self.assertEqual(download.status_code, 200)
        self.assertEqual(download.data, b"audio")
        self.assertIn("attachment", download.headers["Content-Disposition"])
        self.assertEqual(missing_asset.status_code, 404)
        download.close()


if __name__ == "__main__":
    unittest.main()
