import contextlib
import importlib.util
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from automusic.image import generate_image
from automusic.music import generate_lyria_track
from automusic.render import render_track
from automusic.web_app import create_app, create_default_service


def load_run_web_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "run_web.py"
    spec = importlib.util.spec_from_file_location("automusic_run_web_test", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


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
        if job_id == "empty":
            return None
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

    def test_create_default_service_loads_fixture_presets_with_injected_executor(self):
        class ImmediateExecutor:
            def submit(self, function, *args):
                return function(*args)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            examples = root / "configs" / "examples"
            examples.mkdir(parents=True)
            (examples / "music.yaml").write_text("genre: Brazilian phonk\n")
            (examples / "study.yaml").write_text("genre: Study focus ambient\n")
            executor = ImmediateExecutor()

            service = create_default_service(root, executor=executor)

        self.assertEqual(service.preset_ids, ["phonk", "study"])
        self.assertEqual(service.presets["phonk"]["genre"], "Brazilian phonk")
        self.assertEqual(service.presets["study"]["genre"], "Study focus ambient")
        self.assertIs(service.track_generator, generate_lyria_track)
        self.assertIs(service.image_generator, generate_image)
        self.assertIs(service.track_renderer, render_track)
        self.assertIs(service.executor, executor)

    def test_run_web_normalizes_localhost_before_starting_app(self):
        module = load_run_web_module()
        run_arguments = {}

        class FakeApp:
            def run(self, **kwargs):
                run_arguments.update(kwargs)

        with (
            patch.object(module, "load_dotenv"),
            patch.object(module, "create_default_service", return_value=object()),
            patch.object(module, "create_app", return_value=FakeApp()),
            patch.object(sys, "argv", ["run_web.py", "--host", "localhost"]),
        ):
            module.main()

        self.assertEqual(run_arguments["host"], "127.0.0.1")
        self.assertFalse(run_arguments["debug"])

    def test_run_web_rejects_external_host_with_korean_message(self):
        module = load_run_web_module()
        stderr = io.StringIO()

        with (
            patch.object(sys, "argv", ["run_web.py", "--host", "0.0.0.0"]),
            contextlib.redirect_stderr(stderr),
            self.assertRaises(SystemExit),
        ):
            module.parse_args()

        self.assertIn("외부 네트워크 공개는 지원하지 않습니다.", stderr.getvalue())

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
        empty_job = self.client.get("/api/jobs/empty")
        download = self.client.get("/api/jobs/job-001/downloads/audio")
        missing_asset = self.client.get("/api/jobs/job-001/downloads/video")
        self.addCleanup(download.close)

        self.assertEqual(status.status_code, 200)
        self.assertEqual(status.get_json()["status"], "completed")
        self.assertEqual(missing_job.status_code, 404)
        self.assertEqual(empty_job.status_code, 404)
        self.assertIn("찾을 수 없습니다", empty_job.get_json()["error"])
        self.assertEqual(download.status_code, 200)
        self.assertEqual(download.data, b"audio")
        self.assertIn("attachment", download.headers["Content-Disposition"])
        self.assertEqual(missing_asset.status_code, 404)


if __name__ == "__main__":
    unittest.main()
