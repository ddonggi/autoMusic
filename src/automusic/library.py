from __future__ import annotations

import hashlib
import json
import re
import wave
from pathlib import Path
from typing import Any

from .config import load_config


class LibraryService:
    """Read playable results without exposing filesystem paths to the browser."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def list_items(self) -> dict[str, Any]:
        records, unreadable = self._scan()
        items = [item for item, _ in records]
        items.sort(key=lambda item: (item["created_at"] or "", item["id"]), reverse=True)
        return {"items": items, "unreadable_count": unreadable}

    def asset_path(self, item_id: str) -> Path:
        if not isinstance(item_id, str) or not re.fullmatch(r"[a-f0-9]{32}", item_id):
            raise ValueError("Invalid library item")
        # Recheck metadata and file boundaries on every request, including after a move.
        records, _ = self._scan()
        for item, path in records:
            if item["id"] == item_id:
                return path
        raise FileNotFoundError("Audio is not available")

    def _scan(self) -> tuple[list[tuple[dict[str, Any], Path]], int]:
        records: list[tuple[dict[str, Any], Path]] = []
        seen: set[Path] = set()
        unreadable = 0
        categories = self._genre_categories()
        locations = (
            (self.root / "workspace/tracks", "*/track.json", "automation"),
            (self.root / "success/tracks", "*/track.json", "archived"),
            (self.root / "workspace/web-jobs", "*/*/track.json", "web"),
        )
        for base, pattern, source in locations:
            if not self._safe_path(base, self.root) or not base.is_dir():
                continue
            for metadata_path in sorted(base.glob(pattern)):
                try:
                    if not self._safe_path(metadata_path, base):
                        raise ValueError("Invalid metadata path")
                    job = {}
                    if source == "web":
                        job_dir = metadata_path.parent.parent
                        job = self._read_json(job_dir / "job.json", base)
                        if job.get("status") != "completed":
                            continue
                    track = self._read_json(metadata_path, base)
                    if track.get("status") not in {"generated", "batched", "uploaded", "archived"}:
                        continue
                    audio_name = track.get("audio_path")
                    if not isinstance(audio_name, str) or Path(audio_name).is_absolute():
                        raise ValueError("Invalid audio path")
                    audio = metadata_path.parent / audio_name
                    if not self._safe_path(audio, metadata_path.parent) or audio.suffix.lower() != ".wav":
                        raise ValueError("Invalid audio file")
                    audio = audio.resolve()
                    if source == "web":
                        artifact = job.get("artifacts", {}).get("audio")
                        if not isinstance(artifact, str) or (job_dir / artifact).resolve() != audio:
                            raise ValueError("Unpublished web audio")
                    if audio in seen:
                        continue
                    with wave.open(str(audio), "rb") as wav:
                        frames, rate = wav.getnframes(), wav.getframerate()
                        if frames <= 0 or rate <= 0:
                            raise ValueError("Empty audio")
                        duration = frames / rate
                    item_id = hashlib.sha256(
                        str(metadata_path.relative_to(self.root)).encode()
                    ).hexdigest()[:32]
                    category = _text(track.get("category_id")) or _text(job.get("category_id"))
                    category = category or _text(job.get("preset_id")) or categories.get(track.get("genre"))
                    item = {
                        "id": item_id,
                        "title": _text(track.get("title")) or audio.stem,
                        "category_id": category,
                        "variant_id": _text(track.get("music_variant")) or _text(job.get("variant_id")),
                        "created_at": _text(track.get("created_at")),
                        "duration_seconds": duration,
                        "music_prompt": _text(track.get("music_prompt")),
                        "model": _text(track.get("model")),
                        "source": source,
                        "audio_url": f"/api/library/{item_id}/audio",
                        "download_url": f"/api/library/{item_id}/download",
                    }
                    records.append((item, audio))
                    seen.add(audio)
                except (OSError, ValueError, TypeError, AttributeError, EOFError, wave.Error):
                    unreadable += 1
        return records, unreadable

    def _genre_categories(self) -> dict[str, str]:
        categories: dict[str, list[str]] = {}
        base = self.root / "configs/categories"
        if not self._safe_path(base, self.root):
            return {}
        for path in sorted(base.glob("*.yaml")):
            if not self._safe_path(path, base):
                continue
            try:
                genre = _text(load_config(path).get("genre"))
                if genre:
                    categories.setdefault(genre, []).append(path.stem)
            except Exception:
                # Category labels are optional enrichment; invalid YAML must not hide audio.
                continue
        # Older tracks have only genre. Ambiguous matches stay unknown.
        return {genre: names[0] for genre, names in categories.items() if len(names) == 1}

    def _read_json(self, path: Path, boundary: Path) -> dict[str, Any]:
        if not self._safe_path(path, boundary) or path.stat().st_size > 1_048_576:
            raise ValueError("Invalid metadata")
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("Invalid metadata")
        return data

    def _safe_path(self, path: Path, boundary: Path) -> bool:
        try:
            resolved = path.resolve()
            if not resolved.is_relative_to(boundary.resolve()):
                return False
            candidate = path
            while candidate != self.root:
                if candidate.is_symlink() or candidate.parent == candidate:
                    return False
                candidate = candidate.parent
            return True
        except (OSError, ValueError, RuntimeError):
            return False


def _text(value: Any) -> str | None:
    return value if isinstance(value, str) and value.strip() else None
