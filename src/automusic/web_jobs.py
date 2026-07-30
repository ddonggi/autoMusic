from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Callable
from uuid import UUID, uuid4

from .prompts import build_image_prompt_with_metadata, build_music_prompt
from .state import load_json, save_json


PUBLIC_ASSETS = {"audio", "image", "video"}


class WebJobService:
    def __init__(
        self,
        root: Path,
        presets: dict[str, dict[str, Any]],
        *,
        track_generator: Callable[..., Any],
        image_generator: Callable[..., Path],
        track_renderer: Callable[..., Path],
        executor: Any,
    ) -> None:
        self.root = root.resolve()
        self.presets = presets
        self.track_generator = track_generator
        self.image_generator = image_generator
        self.track_renderer = track_renderer
        self.executor = executor

    @property
    def preset_ids(self) -> list[str]:
        return list(self.presets)

    def preset_summaries(self) -> list[dict[str, str]]:
        return [
            {
                "id": preset_id,
                "name": str(config.get("genre", preset_id)),
                "default_prompt": build_music_prompt(config),
            }
            for preset_id, config in self.presets.items()
        ]

    def start(self, preset_id: str, music_prompt: str | None) -> dict[str, Any]:
        if preset_id not in self.presets:
            raise ValueError("Unknown preset")
        job_id = str(uuid4())
        job_dir = self._job_dir(job_id)
        job = {
            "id": job_id,
            "preset_id": preset_id,
            "music_prompt": music_prompt or "",
            "status": "queued",
            "error": None,
            "artifacts": {},
        }
        save_json(job_dir / "job.json", job)
        self.executor.submit(self._run, job_id)
        return self.get(job_id)

    def get(self, job_id: str) -> dict[str, Any]:
        return load_json(self._job_dir(job_id) / "job.json")

    def asset_path(self, job_id: str, asset: str) -> Path:
        if asset not in PUBLIC_ASSETS:
            raise ValueError("Unsupported asset")
        job_dir = self._job_dir(job_id)
        relative_path = self.get(job_id).get("artifacts", {}).get(asset)
        if not isinstance(relative_path, str):
            raise FileNotFoundError("Asset is not available")
        path = self._contained_path(job_dir, relative_path)
        if not path.is_file():
            raise FileNotFoundError("Asset is not available")
        return path

    def _run(self, job_id: str) -> None:
        job_dir = self._job_dir(job_id)
        job = self.get(job_id)
        preset = self.presets[job["preset_id"]]
        stage = "generating_music"
        try:
            self._set_status(job_dir, job, stage)
            track_dir = asyncio.run(
                self.track_generator(
                    preset,
                    job_dir,
                    music_prompt=job["music_prompt"],
                )
            )
            track_dir = Path(track_dir)
            track = load_json(track_dir / "track.json")
            self._set_artifact(job_dir, job, "audio", track_dir / track["audio_path"])

            stage = "generating_image"
            self._set_status(job_dir, job, stage)
            image_result = build_image_prompt_with_metadata(track["music_prompt"], track, preset)
            image_path = track_dir / "image.png"
            self.image_generator(str(image_result["prompt"]), image_path)
            track["status"] = "imaged"
            track["image_prompt"] = image_result["prompt"]
            track["image_variant"] = image_result["image_variant"]
            track["image_path"] = image_path.name
            save_json(track_dir / "track.json", track)
            self._set_artifact(job_dir, job, "image", image_path)

            stage = "rendering_video"
            self._set_status(job_dir, job, stage)
            video_path = Path(self.track_renderer(track_dir))
            self._set_artifact(job_dir, job, "video", video_path)
            self._set_status(job_dir, job, "completed")
        except Exception:
            self._set_status(job_dir, job, "failed", error=_safe_stage_error(stage))

    def _set_status(
        self,
        job_dir: Path,
        job: dict[str, Any],
        status: str,
        *,
        error: str | None = None,
    ) -> None:
        job["status"] = status
        job["error"] = error
        save_json(job_dir / "job.json", job)

    def _set_artifact(self, job_dir: Path, job: dict[str, Any], asset: str, path: Path) -> None:
        job["artifacts"][asset] = str(path.resolve().relative_to(job_dir.resolve()))
        save_json(job_dir / "job.json", job)

    def _job_dir(self, job_id: str) -> Path:
        if str(UUID(job_id)) != job_id:
            raise ValueError("Invalid job")
        return self.root / "workspace" / "web-jobs" / job_id

    @staticmethod
    def _contained_path(job_dir: Path, relative_path: str) -> Path:
        path = (job_dir / relative_path).resolve()
        if path == job_dir.resolve() or job_dir.resolve() not in path.parents:
            raise ValueError("Invalid asset path")
        return path


def _safe_stage_error(stage: str) -> str:
    messages = {
        "generating_music": "음악 생성 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.",
        "generating_image": "이미지 생성 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.",
        "rendering_video": "영상 렌더링 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.",
    }
    return messages.get(stage, "작업 처리 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.")
