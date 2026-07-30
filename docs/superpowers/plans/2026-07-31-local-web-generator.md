# Local Web Generator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run the AutoMusic creation pipeline from a localhost step-by-step UI with two presets, editable music prompts, background progress, and WAV/PNG/MP4 downloads.

**Architecture:** A Flask application serves one static wizard page and a narrow JSON API. `WebJobService` persists each job under `workspace/web-jobs`, submits the existing music and image generators to an executor, and calls a new single-track renderer; it never exposes environment variables or arbitrary filesystem paths. Preset context is moved into the prompt configuration so the existing phonk behavior remains compatible and the new study preset has matching music and image language.

**Tech Stack:** Python 3, Flask, standard-library `ThreadPoolExecutor`, PyYAML, existing Google GenAI/OpenAI clients, ffmpeg, HTML/CSS/browser JavaScript, `unittest`.

---

## File Structure

| Path | Responsibility |
| --- | --- |
| `requirements.txt` | Add Flask runtime dependency. |
| `configs/examples/study.yaml` | Study-focus music, image, and prompt context preset. |
| `src/automusic/prompts.py` | Read optional music/image context from a preset without changing current defaults. |
| `src/automusic/music.py` | Allow one caller-supplied music prompt while retaining generated metadata. |
| `src/automusic/render.py` | Render a single generated track into one MP4. |
| `src/automusic/web_jobs.py` | Persist, run, and report one background web generation job. |
| `src/automusic/web_app.py` | Create the Flask app and route validated API requests to `WebJobService`. |
| `src/automusic/templates/web/index.html` | Accessible three-step wizard markup. |
| `src/automusic/static/web/app.css` | Responsive visual system and progress states. |
| `src/automusic/static/web/app.js` | Preset selection, prompt edit state, job submission, polling, downloads. |
| `scripts/run_web.py` | Local-only server command that loads `.env` and preset files. |
| `tests/test_prompts.py` | Prompt-context and preset compatibility regression tests. |
| `tests/test_audio_render_upload.py` | Single-track ffmpeg command and renderer tests. |
| `tests/test_web_jobs.py` | Job state, asset persistence, dependency injection, and safe failure tests. |
| `tests/test_web_app.py` | HTTP API validation, state, and download route tests. |
| `docs/program-guide.md` | Korean local UI start/use guide and security notes. |
| `README.md` | Quick-start link to the web interface. |

### Task 1: Add the Study Preset and Context-Aware Prompt API

**Files:**
- Create: `configs/examples/study.yaml`
- Modify: `src/automusic/prompts.py`
- Modify: `tests/test_prompts.py`

- [ ] **Step 1: Write the failing music-context test**

```python
def test_build_music_prompt_uses_configured_music_context(self):
    prompt = build_music_prompt(
        {
            "duration_seconds": 180,
            "genre": "Study focus ambient",
            "music_context": "deep study and concentration sessions",
            "bpm_min": 70,
            "bpm_max": 78,
        }
    )

    self.assertIn("for deep study and concentration sessions", prompt)
    self.assertNotIn("intense workout sessions", prompt)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m unittest tests.test_prompts.PromptTests.test_build_music_prompt_uses_configured_music_context -v`

Expected: FAIL because the prompt currently hard-codes `intense workout sessions`.

- [ ] **Step 3: Add the minimal music context implementation**

```python
music_context = str(config.get("music_context", "intense workout sessions"))

parts = [
    f"Create a {duration}-second {genre} track for {music_context}.",
    # Existing prompt sections remain unchanged.
]
```

Place `music_context` after the genre lookup in `build_music_prompt_with_metadata`. Do not alter fallback genre, arrangement, or vocal behavior.

- [ ] **Step 4: Run the focused test to verify it passes**

Run: `.venv/bin/python -m unittest tests.test_prompts.PromptTests.test_build_music_prompt_uses_configured_music_context -v`

Expected: PASS.

- [ ] **Step 5: Write the failing image-context test**

```python
def test_build_image_prompt_uses_configured_image_context(self):
    result = build_image_prompt_with_metadata(
        "music prompt",
        {"genre": "Study focus ambient", "mood": ["calm"], "texture": ["warm"]},
        {
            "image_context": "study focus music video",
            "image_variants": [{"name": "desk", "visual_style": "quiet desk", "subject": "books"}],
        },
    )

    self.assertIn("study focus music video", result["prompt"])
    self.assertNotIn("workout music video", result["prompt"])
```

- [ ] **Step 6: Run the image-context test to verify it fails**

Run: `.venv/bin/python -m unittest tests.test_prompts.PromptTests.test_build_image_prompt_uses_configured_image_context -v`

Expected: FAIL because the image prompt currently hard-codes `workout music video`.

- [ ] **Step 7: Add the minimal image context implementation**

```python
image_context = str(config.get("image_context", "workout music video"))
prompt = (
    f"Create a 16:9 cinematic background image for a {image_context}. "
    # Existing visual fields and safety rules remain unchanged.
)
```

Use this in `build_image_prompt_with_metadata` before formatting the image prompt.

- [ ] **Step 8: Run prompt tests to verify both new behaviors and compatibility**

Run: `.venv/bin/python -m unittest tests.test_prompts -v`

Expected: PASS, including existing Brazilian phonk workout assertions.

- [ ] **Step 9: Create the study preset**

Create `configs/examples/study.yaml` with the following top-level fields and values:

```yaml
duration_seconds: 180
genre: Study focus ambient
music_context: deep study and concentration sessions
image_context: study focus music video
bpm_min: 70
bpm_max: 78
mood: [calm, clear-minded, focused, non-distracting]
instruments: [soft piano, warm Rhodes, subtle synth pads, light percussion, gentle bass]
texture: [soft room tone, gentle rain ambience, warm tape texture]
vocals: none
temperature: 0.85
lyria_retries: 3
lyria_retry_delay_seconds: 30
negative_rules:
  - no lead vocals
  - no aggressive drums or sudden drops
  - no long silence
  - no abrupt ending
  - avoid static one-loop repetition
  - include subtle section changes
```

Add six named `prompt_variants`, each with a full six-section 0:00-3:00 arrangement: `lofi-library`, `rain-window-piano`, `deep-work-synth`, `night-study-rhodes`, `minimal-pulse-focus`, and `soft-cafe-jazz`. Add four `image_variants`: `minimal-study-desk`, `rainy-window-library`, `night-focus-workspace`, and `ambient-bookshelf`. Each image variant must set `visual_style`, `subject`, `palette`, and `texture` and remain text/logo/watermark free through the shared image safety rule.

- [ ] **Step 10: Add a study preset load regression test**

```python
from automusic.config import load_config

def test_study_preset_builds_study_music_and_image_prompts(self):
    config = load_config(Path("configs/examples/study.yaml"))
    music = build_music_prompt_with_metadata({**config, "seed": 0})
    image = build_image_prompt_with_metadata(music["prompt"], {**music, "genre": config["genre"]}, {**config, "seed": 0})

    self.assertIn("deep study and concentration sessions", music["prompt"])
    self.assertIn("study focus music video", image["prompt"])
```

- [ ] **Step 11: Run all prompt tests and commit**

Run: `.venv/bin/python -m unittest tests.test_prompts -v`

Expected: PASS.

```bash
git add configs/examples/study.yaml src/automusic/prompts.py tests/test_prompts.py
git commit -m "feat: add study focus music preset"
```

### Task 2: Support Explicit Web Prompts and One-Track MP4 Rendering

**Files:**
- Modify: `src/automusic/music.py`
- Modify: `src/automusic/render.py`
- Modify: `tests/test_music_generation.py`
- Modify: `tests/test_audio_render_upload.py`

- [ ] **Step 1: Write the failing explicit prompt test**

```python
def test_generate_lyria_track_uses_explicit_prompt(self):
    prompts = []

    async def producer(prompt, config, music_result, target_seconds):
        prompts.append(prompt)
        return [b"\0" * 48_000 * 2 * 2]

    with tempfile.TemporaryDirectory() as tmp:
        asyncio.run(generate_lyria_track(
            {"duration_seconds": 1, "genre": "Brazilian phonk", "lyria_retries": 1},
            Path(tmp) / "tracks",
            music_prompt="A custom, gentle focus track.",
            music_chunk_producer=producer,
        ))

    self.assertEqual(prompts, ["A custom, gentle focus track."])
```

- [ ] **Step 2: Run the explicit prompt test to verify it fails**

Run: `.venv/bin/python -m unittest tests.test_music_generation.MusicGenerationTests.test_generate_lyria_track_uses_explicit_prompt -v`

Expected: FAIL because `generate_lyria_track` has no `music_prompt` keyword argument.

- [ ] **Step 3: Add the explicit prompt argument**

```python
async def generate_lyria_track(
    config: dict[str, Any],
    workspace_tracks: Path,
    *,
    music_prompt: str | None = None,
    music_chunk_producer: MusicChunkProducer | None = None,
) -> Path:
    music_result = build_music_prompt_with_metadata(config)
    prompt = music_prompt.strip() if music_prompt and music_prompt.strip() else str(music_result["prompt"])
```

Keep `music_result` for tempo, mood, variant, and track metadata. Store `prompt` in `track.json` exactly as the producer received it.

- [ ] **Step 4: Run music-generation tests to verify they pass**

Run: `.venv/bin/python -m unittest tests.test_music_generation -v`

Expected: PASS.

- [ ] **Step 5: Write the failing single-track render test**

```python
def test_render_track_runs_one_segment_command_and_returns_video(self):
    calls = []

    def fake_runner(command, check):
        calls.append((command, check))

    with tempfile.TemporaryDirectory() as tmp:
        track_dir = Path(tmp) / "track"
        track_dir.mkdir()
        save_json(track_dir / "track.json", {
            "audio_path": "audio.wav", "image_path": "image.png", "duration_seconds": 180.0,
        })
        (track_dir / "audio.wav").write_bytes(b"audio")
        (track_dir / "image.png").write_bytes(b"image")

        output = render_track(track_dir, runner=fake_runner)

    self.assertEqual(output.name, "video.mp4")
    self.assertEqual(len(calls), 1)
    self.assertTrue(calls[0][1])
```

- [ ] **Step 6: Run the renderer test to verify it fails**

Run: `.venv/bin/python -m unittest tests.test_audio_render_upload.AudioRenderUploadTests.test_render_track_runs_one_segment_command_and_returns_video -v`

Expected: FAIL because `render_track` does not exist.

- [ ] **Step 7: Add the single-track renderer**

```python
def render_track(track_dir: Path, *, runner=subprocess.run) -> Path:
    track = load_json(track_dir / "track.json")
    output_path = track_dir / "video.mp4"
    runner(build_segment_command(
        image_path=track_dir / track["image_path"],
        audio_path=track_dir / track["audio_path"],
        output_path=output_path,
        duration=float(track.get("duration_seconds") or 180.0),
    ), check=True)
    return output_path
```

Do not modify batch status or use concat files in this function.

- [ ] **Step 8: Run focused rendering tests**

Run: `.venv/bin/python -m unittest tests.test_audio_render_upload -v`

Expected: PASS; existing batch rendering remains covered.

- [ ] **Step 9: Commit the reusable pipeline additions**

```bash
git add src/automusic/music.py src/automusic/render.py tests/test_music_generation.py tests/test_audio_render_upload.py
git commit -m "feat: support custom prompts and single-track videos"
```

### Task 3: Implement Persistent Background Web Jobs

**Files:**
- Create: `src/automusic/web_jobs.py`
- Create: `tests/test_web_jobs.py`

- [ ] **Step 1: Write the failing job lifecycle test**

```python
def test_job_service_creates_assets_and_marks_job_completed(self):
    class ImmediateExecutor:
        def submit(self, fn, *args):
            fn(*args)

    async def fake_track_generator(config, tracks_root, *, music_prompt=None):
        track_dir = tracks_root / "track"
        track_dir.mkdir(parents=True)
        (track_dir / "audio.wav").write_bytes(b"audio")
        save_json(track_dir / "track.json", {
            "genre": config["genre"], "mood": [], "texture": [], "music_prompt": music_prompt,
            "audio_path": "audio.wav", "image_path": None, "duration_seconds": 180.0,
        })
        return track_dir

    def fake_image_generator(prompt, output_path):
        output_path.write_bytes(b"image")
        return output_path

    def fake_renderer(track_dir):
        output_path = track_dir / "video.mp4"
        output_path.write_bytes(b"video")
        return output_path

    with tempfile.TemporaryDirectory() as tmp:
        service = WebJobService(
            Path(tmp),
            {"phonk": {"genre": "Brazilian phonk"}},
            track_generator=fake_track_generator,
            image_generator=fake_image_generator,
            track_renderer=fake_renderer,
            executor=ImmediateExecutor(),
        )
        created = service.start("phonk", "Custom phonk prompt")
        job = service.get(created["job_id"])

        self.assertEqual(job["status"], "completed")
        self.assertEqual(job["music_prompt"], "Custom phonk prompt")
        self.assertTrue(service.asset_path(job["job_id"], "audio").exists())
        self.assertTrue(service.asset_path(job["job_id"], "image").exists())
        self.assertTrue(service.asset_path(job["job_id"], "video").exists())
```

- [ ] **Step 2: Run the lifecycle test to verify it fails**

Run: `.venv/bin/python -m unittest tests.test_web_jobs.WebJobServiceTests.test_job_service_creates_assets_and_marks_job_completed -v`

Expected: FAIL because `automusic.web_jobs` does not exist.

- [ ] **Step 3: Create the job service with explicit dependencies**

Create `WebJobService` with this public interface:

```python
class WebJobService:
    def __init__(self, root: Path, presets: dict[str, dict[str, Any]], *, track_generator, image_generator, track_renderer, executor):
        self.root = root
        self.presets = presets
        self.track_generator = track_generator
        self.image_generator = image_generator
        self.track_renderer = track_renderer
        self.executor = executor

    @property
    def preset_ids(self) -> set[str]:
        return set(self.presets)

    def preset_summaries(self) -> list[dict[str, str]]:
        return [{"id": key, "name": value["genre"], "default_prompt": str(build_music_prompt_with_metadata(value)["prompt"])} for key, value in self.presets.items()]

    def start(self, preset_id: str, music_prompt: str | None) -> dict[str, Any]:
        raise NotImplementedError

    def get(self, job_id: str) -> dict[str, Any] | None:
        raise NotImplementedError

    def asset_path(self, job_id: str, asset: str) -> Path | None:
        raise NotImplementedError
```

`start` must generate an opaque UUID, create `workspace/web-jobs/<uuid>/job.json`, set `queued`, and submit `_run_job`. `_run_job` must set these states in order: `generating_music`, `generating_image`, `rendering_video`, `completed`. Store artifacts only by relative names in `job.json`:

```python
{
    "job_id": job_id,
    "preset_id": preset_id,
    "status": "queued",
    "music_prompt": effective_prompt,
    "artifacts": {"audio": None, "image": None, "video": None},
    "error": None,
}
```

Run the asynchronous existing generator with `asyncio.run`. After music, build the image prompt using `build_image_prompt_with_metadata`, update `track.json` exactly as `scripts/run_daily.py` does, and then call `track_renderer`. Set each completed artifact to a path relative to the job directory.

- [ ] **Step 4: Run the lifecycle test to verify it passes**

Run: `.venv/bin/python -m unittest tests.test_web_jobs.WebJobServiceTests.test_job_service_creates_assets_and_marks_job_completed -v`

Expected: PASS.

- [ ] **Step 5: Write the failing safe-failure and asset allowlist tests**

```python
def test_job_service_records_safe_stage_error_and_keeps_audio(self):
    class ImmediateExecutor:
        def submit(self, fn, *args):
            fn(*args)

    async def fake_track_generator(config, tracks_root, *, music_prompt=None):
        track_dir = tracks_root / "track"
        track_dir.mkdir(parents=True)
        (track_dir / "audio.wav").write_bytes(b"audio")
        save_json(track_dir / "track.json", {"genre": config["genre"], "mood": [], "texture": [], "music_prompt": music_prompt, "audio_path": "audio.wav", "image_path": None, "duration_seconds": 180.0})
        return track_dir

    with tempfile.TemporaryDirectory() as tmp:
        service = WebJobService(Path(tmp), {"study": {"genre": "Study focus ambient"}}, track_generator=fake_track_generator, image_generator=lambda prompt, path: (_ for _ in ()).throw(RuntimeError("OPENAI_API_KEY=secret")), track_renderer=lambda track_dir: track_dir / "video.mp4", executor=ImmediateExecutor())
        job = service.get(service.start("study", None)["job_id"])

    self.assertEqual(job["status"], "failed")
    self.assertIsNotNone(job["artifacts"]["audio"])
    self.assertNotIn("secret", job["error"])

def test_job_service_only_returns_known_completed_assets(self):
    # Use the completed lifecycle fixture, delete its video file, and assert all three paths are rejected.
    self.assertIsNone(service.asset_path(job_id, "../.env"))
    self.assertIsNone(service.asset_path(job_id, "job.json"))
    self.assertIsNone(service.asset_path(job_id, "video"))
```

- [ ] **Step 6: Run the failure tests to verify they fail**

Run: `.venv/bin/python -m unittest tests.test_web_jobs.WebJobServiceTests.test_job_service_records_safe_stage_error_and_keeps_audio tests.test_web_jobs.WebJobServiceTests.test_job_service_only_returns_known_completed_assets -v`

Expected: FAIL because safe error translation and the asset allowlist are not implemented.

- [ ] **Step 7: Add safe failures and asset validation**

Add these constants and behavior in `web_jobs.py`:

```python
PUBLIC_ASSETS = {"audio": "audio.wav", "image": "image.png", "video": "video.mp4"}
PUBLIC_STAGE_ERRORS = {
    "generating_music": "음악 생성 중 오류가 발생했습니다.",
    "generating_image": "이미지 생성 중 오류가 발생했습니다.",
    "rendering_video": "영상 렌더링 중 오류가 발생했습니다.",
}
```

When a stage raises, preserve already-set artifacts, write `failed` and the mapped Korean error only, and return. `asset_path` must accept only keys in `PUBLIC_ASSETS`, resolve the stored artifact, and reject it unless it remains inside the job directory and exists as a regular file.

- [ ] **Step 8: Run all web job tests and commit**

Run: `.venv/bin/python -m unittest tests.test_web_jobs -v`

Expected: PASS.

```bash
git add src/automusic/web_jobs.py tests/test_web_jobs.py
git commit -m "feat: add persistent web generation jobs"
```

### Task 4: Add Flask Routes and the Three-Step Wizard

**Files:**
- Modify: `requirements.txt`
- Create: `src/automusic/web_app.py`
- Create: `src/automusic/templates/web/index.html`
- Create: `src/automusic/static/web/app.css`
- Create: `src/automusic/static/web/app.js`
- Create: `tests/test_web_app.py`

- [ ] **Step 1: Add Flask to the runtime requirements**

Add exactly this line to `requirements.txt`:

```text
Flask>=3.0.0
```

- [ ] **Step 2: Write failing route tests**

```python
class WebAppTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.service = FakeWebJobService()
        self.client = create_app(self.service).test_client()

    def tearDown(self):
        self.tmp.cleanup()

    def test_presets_return_phonk_and_study_default_prompts(self):
        response = self.client.get("/api/presets")
        self.assertEqual(response.status_code, 200)
        self.assertEqual({item["id"] for item in response.get_json()["presets"]}, {"phonk", "study"})

    def test_job_creation_rejects_unknown_preset_and_blank_prompt(self):
        response = self.client.post("/api/jobs", json={"preset_id": "unknown", "music_prompt": ""})
        self.assertEqual(response.status_code, 400)

    def test_download_uses_attachment_and_rejects_unknown_asset(self):
        self.assertEqual(self.client.get("/api/jobs/job-1/downloads/audio").status_code, 200)
        self.assertEqual(self.client.get("/api/jobs/job-1/downloads/../job.json").status_code, 404)
```

`FakeWebJobService` must implement the same four public methods as `WebJobService`, return deterministic preset/job data, and point `audio` to a temporary WAV file.

- [ ] **Step 3: Run route tests to verify they fail**

Run: `.venv/bin/python -m unittest tests.test_web_app -v`

Expected: FAIL because `create_app` does not exist.

- [ ] **Step 4: Implement the Flask factory and validated routes**

Create `create_app(service: WebJobService) -> Flask` in `web_app.py` with these handlers:

```python
@app.get("/api/presets")
def presets():
    return jsonify({"presets": service.preset_summaries()})

@app.post("/api/jobs")
def create_job():
    payload = request.get_json(silent=True) or {}
    preset_id = payload.get("preset_id")
    prompt = payload.get("music_prompt")
    if not isinstance(preset_id, str) or preset_id not in service.preset_ids:
        return jsonify({"error": "지원하지 않는 장르입니다."}), 400
    if prompt is not None and (not isinstance(prompt, str) or not prompt.strip()):
        return jsonify({"error": "프롬프트는 비워 둘 수 없습니다."}), 400
    return jsonify(service.start(preset_id, prompt)), 202
```

Add `GET /api/jobs/<job_id>` returning 404 if `service.get` returns `None`. Add the download route using `service.asset_path`, `send_file(..., as_attachment=True, download_name=path.name)`, and a 404 for any absent asset. Do not echo request bodies into error responses.

- [ ] **Step 5: Run route tests to verify they pass**

Run: `.venv/bin/python -m unittest tests.test_web_app -v`

Expected: PASS.

- [ ] **Step 6: Build the accessible wizard markup**

Create `index.html` with only these persistent page sections:

```html
<header class="masthead"><a href="/">AutoMusic Studio</a><p>Local creation workspace</p></header>
<main class="wizard-shell">
  <ol class="steps" aria-label="생성 단계"><li class="is-active">01 장르</li><li>02 프롬프트</li><li>03 결과</li></ol>
  <section id="genre-step" aria-labelledby="genre-heading"></section>
  <section id="prompt-step" hidden aria-labelledby="prompt-heading"></section>
  <section id="result-step" hidden aria-labelledby="result-heading"></section>
</main>
<script type="module" src="/static/web/app.js"></script>
```

The JavaScript must create genre controls from `/api/presets`, set the selected preset's default prompt in a `<textarea>`, post `{preset_id, music_prompt}`, poll `/api/jobs/<id>` every two seconds only while status is not `completed` or `failed`, and render download links from `artifacts` only when their values exist. Use `textContent`, never `innerHTML`, for server-provided prompt/error text.

- [ ] **Step 7: Add responsive visual design and state behavior**

In `app.css`, create a high-contrast editorial workspace: warm off-white field, deep forest text, vermilion action color, one expressive serif display face with a local/system fallback, and a compact sans-serif control face. Design genre cards as large selectable panels; use visible focus rings; respect `prefers-reduced-motion`; collapse to one column below 720px. Avoid stock dashboard cards, gradients, and generic UI icon sets.

In `app.js`, show Korean stage labels for `queued`, `generating_music`, `generating_image`, `rendering_video`, `completed`, and `failed`. Disable navigation and the generate button while an active job is polling. On failure, keep any completed asset links visible and render the safe server error.

- [ ] **Step 8: Run the web app tests and commit**

Run: `.venv/bin/python -m unittest tests.test_web_app -v`

Expected: PASS.

```bash
git add requirements.txt src/automusic/web_app.py src/automusic/templates/web/index.html src/automusic/static/web/app.css src/automusic/static/web/app.js tests/test_web_app.py
git commit -m "feat: add local music creation wizard"
```

### Task 5: Add the Local Server Command and Documentation

**Files:**
- Create: `scripts/run_web.py`
- Modify: `README.md`
- Modify: `docs/program-guide.md`
- Modify: `.gitignore`
- Test: `tests/test_web_app.py`

- [ ] **Step 1: Write the failing server configuration test**

```python
def test_create_default_service_loads_named_presets_from_project_root(self):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "configs" / "examples").mkdir(parents=True)
        (root / "configs" / "examples" / "music.yaml").write_text("genre: Brazilian phonk\n")
        (root / "configs" / "examples" / "study.yaml").write_text("genre: Study focus ambient\n")
        service = create_default_service(root, executor=ImmediateExecutor())

    self.assertEqual(service.preset_ids, {"phonk", "study"})
```

- [ ] **Step 2: Run the server configuration test to verify it fails**

Run: `.venv/bin/python -m unittest tests.test_web_app.WebAppTests.test_create_default_service_loads_named_presets_from_project_root -v`

Expected: FAIL because `create_default_service` does not exist.

- [ ] **Step 3: Add default service construction and server command**

Add `create_default_service(root: Path, *, executor=None) -> WebJobService` to `web_app.py`. It must load:

```python
{
    "phonk": load_config(root / "configs" / "examples" / "music.yaml"),
    "study": load_config(root / "configs" / "examples" / "study.yaml"),
}
```

Use production dependencies `generate_lyria_track`, `generate_image`, and `render_track`; use a `ThreadPoolExecutor(max_workers=1)` when no executor is supplied.

Create `scripts/run_web.py` that inserts `src` into `sys.path`, calls `load_dotenv(root / ".env")`, creates the default service, and starts Flask with only these parser values:

```python
parser.add_argument("--root", default=Path(__file__).resolve().parents[1], type=Path)
parser.add_argument("--host", default="127.0.0.1")
parser.add_argument("--port", default=8765, type=int)
```

Refuse a host other than `127.0.0.1` or `localhost` with `parser.error("외부 네트워크 공개는 지원하지 않습니다.")`. Start with `app.run(host="127.0.0.1" if args.host == "localhost" else args.host, port=args.port, debug=False)`.

- [ ] **Step 4: Run the server configuration test to verify it passes**

Run: `.venv/bin/python -m unittest tests.test_web_app.WebAppTests.test_create_default_service_loads_named_presets_from_project_root -v`

Expected: PASS.

- [ ] **Step 5: Document local usage in Korean**

Add this command and behavior to both `README.md` and `docs/program-guide.md`:

```bash
.venv/bin/python scripts/run_web.py
```

Explain that the UI opens at `http://127.0.0.1:8765`, API keys remain in `.env`, the server is local-only, generation costs apply, and one finished job offers separate WAV, PNG, MP4 downloads under `workspace/web-jobs/`. State explicitly that YouTube upload and the stopped daily scheduler are not triggered by this UI.

Add `.superpowers/` to `.gitignore` so local visual brainstorming files never enter commits.

- [ ] **Step 6: Run full verification**

Run:

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m compileall -q src scripts tests
git diff --check
```

Expected: every test passes, compilation has no output, and `git diff --check` has no output.

- [ ] **Step 7: Smoke-test the local-only server without live generation**

Run:

```bash
.venv/bin/python scripts/run_web.py --port 8765
```

In a second terminal, run:

```bash
curl --fail http://127.0.0.1:8765/api/presets
```

Expected: JSON with `phonk` and `study`; stop the server after the check. Do not submit a job because it would invoke paid APIs.

- [ ] **Step 8: Commit and push**

```bash
git add .gitignore README.md docs/program-guide.md scripts/run_web.py src/automusic/web_app.py tests/test_web_app.py
git commit -m "docs: add local web generator guide"
git push
```
