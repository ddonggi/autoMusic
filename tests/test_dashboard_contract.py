import functools
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from automusic.music import generate_lyria_track
from automusic.web_app import create_app, create_default_service


class ImmediateExecutor:
    def submit(self, function, *args):
        function(*args)


class FakeScheduler:
    def __init__(self):
        self.changes = []

    def status(self):
        return {"state": "disabled", "supported": True, "installed": True,
                "enabled": False, "running": False, "registered": True,
                "schedule": {"hour": 12, "minute": 0}, "category_id": "study",
                "error": None, "observed_at": "2026-10-23T00:00:00+00:00"}

    def set_enabled(self, enabled):
        self.changes.append(enabled)
        return {**self.status(), "state": "enabled" if enabled else "disabled", "enabled": enabled}


class DashboardContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        source = Path(__file__).resolve().parents[1] / "configs"
        shutil.copytree(source / "categories", self.root / "configs/categories")
        self.service = create_default_service(self.root, executor=ImmediateExecutor())
        self.addCleanup(self.service.close)
        self.calls = []

        async def producer(prompt, config, result, target):
            self.calls.append((prompt, result["music_variant"]))
            return [b"\x00\x00" * 48000 * 2]

        self.service.track_generator = functools.partial(generate_lyria_track, music_chunk_producer=producer)
        self.scheduler = FakeScheduler()
        self.app = create_app(self.service, scheduler_service=self.scheduler)
        self.client = self.app.test_client()
        self.headers = {"X-CSRF-Token": self.app.config["CSRF_TOKEN"], "Origin": "http://localhost"}

    def test_selected_preview_to_library_and_range_download(self):
        page = self.client.get("/")
        self.assertEqual(page.status_code, 200)
        self.assertIn(self.app.config["CSRF_TOKEN"], page.get_data(as_text=True))
        categories = self.client.get("/api/categories").json["items"]
        self.assertEqual({item["id"] for item in categories}, {"study", "phonk", "lofi", "fitness", "cafe"})
        category = next(item for item in categories if item["id"] == "study")
        variant_id = category["variants"][0]["id"]
        preview = self.client.post("/api/previews", json={"category_id": "study", "variant_id": variant_id}, headers=self.headers)
        self.assertEqual(preview.status_code, 201)
        self.assertEqual(preview.json["variant_id"], variant_id)
        prompt = "A quiet study piece, slowly evolving piano and soft strings."
        payload = {"preview_id": preview.json["id"], "music_prompt": prompt, "request_id": str(uuid4())}
        response = self.client.post("/api/jobs", json=payload, headers=self.headers)
        self.assertEqual(response.status_code, 202)
        job = response.json
        self.assertEqual(job["status"], "completed")
        self.assertEqual(job["music_prompt"], prompt)
        self.assertEqual(job["variant_id"], variant_id)
        self.assertEqual(self.calls, [(prompt, variant_id)])
        repeated = self.client.post("/api/jobs", json=payload, headers=self.headers)
        self.assertEqual(repeated.json["id"], job["id"])
        self.assertEqual(len(self.calls), 1)
        result = self.client.get("/api/library").json
        self.assertEqual(result["unreadable_count"], 0)
        self.assertEqual(len(result["items"]), 1)
        item = result["items"][0]
        self.assertEqual(item["music_prompt"], prompt)
        self.assertEqual(item["category_id"], "study")
        self.assertEqual(item["variant_id"], variant_id)
        self.assertAlmostEqual(item["duration_seconds"], 1)
        audio = self.client.get(item["audio_url"], headers={"Range": "bytes=0-43"})
        self.addCleanup(audio.close)
        self.assertEqual(audio.status_code, 206)
        self.assertEqual(audio.data[:4], b"RIFF")
        download = self.client.get(item["download_url"])
        self.addCleanup(download.close)
        self.assertEqual(download.status_code, 200)
        self.assertIn("attachment", download.headers["Content-Disposition"])
        self.assertNotIn(str(self.root), json.dumps(result))
        dashboard = self.client.get("/api/dashboard").json
        self.assertEqual(dashboard["track_count"], 1)
        self.assertEqual(dashboard["active_jobs"], [])
        self.assertEqual(dashboard["total_duration_seconds"], 1)

    def test_scheduler_csrf_and_foreign_origin_cannot_mutate(self):
        self.assertEqual(self.client.get("/api/scheduler").json["state"], "disabled")
        self.assertEqual(self.scheduler.changes, [])
        response = self.client.post("/api/scheduler", json={"enabled": True})
        self.assertEqual(response.status_code, 403)
        response = self.client.post("/api/scheduler", json={"enabled": True},
                                    headers={**self.headers, "Origin": "https://example.com"})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.scheduler.changes, [])
        response = self.client.post("/api/scheduler", json={"enabled": False}, headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.scheduler.changes, [False])


if __name__ == "__main__":
    unittest.main()
