from __future__ import annotations

import hashlib
import fcntl
import json
import os
import re
import tempfile
import wave
from pathlib import Path
from typing import Any

from .config import load_config


class LibraryService:
    """Read playable results without exposing filesystem paths to the browser."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.favorites_path = self.root / "workspace/library-favorites.json"

    def list_items(self) -> dict[str, Any]:
        records, unreadable = self._scan()
        items = [item for item, _ in records]
        favorites = self._read_favorites()
        for item in items:
            item['favorite'] = favorites.get(item.pop('_favorite_key'), False)
        items.sort(key=lambda item: (item["created_at"] or "", item["id"]), reverse=True)
        return {"items": items, "unreadable_count": unreadable}

    def _read_favorites(self) -> dict[str, bool]:
        try:
            if not self._safe_path(self.favorites_path, self.root):
                raise ValueError()
            if not self.favorites_path.exists():
                return {}
            data = self._read_json(self.favorites_path, self.root)
            if set(data) != {'version', 'items'} or type(data['version']) is not int or data['version'] != 1 or not isinstance(data['items'], dict):
                raise ValueError()
            if any(not re.fullmatch(r'[a-f0-9]{64}', key) or type(value) is not bool for key, value in data['items'].items()):
                raise ValueError()
            return data['items']
        except (OSError, ValueError, TypeError, RuntimeError):
            raise RuntimeError('즐겨찾기 정보를 읽을 수 없습니다. 저장 파일을 확인해 주세요.') from None

    def set_favorite(self, item_id: str, favorite: bool) -> dict[str, Any]:
        if type(favorite) is not bool:
            raise ValueError('즐겨찾기 설정을 확인해 주세요.')
        if not isinstance(item_id, str) or not re.fullmatch(r'[a-f0-9]{32}', item_id):
            raise FileNotFoundError('음원을 찾을 수 없습니다.')
        records, _ = self._scan()
        item = next((item for item, _ in records if item['id'] == item_id), None)
        if item is None:
            raise FileNotFoundError('음원을 찾을 수 없습니다.')
        temporary = None
        try:
            workspace = self.favorites_path.parent
            lock_path = workspace / '.library-favorites.lock'
            if not self._safe_path(workspace, self.root) or not self._safe_path(lock_path, self.root):
                raise ValueError()
            workspace.mkdir(parents=True, exist_ok=True)
            # Each caller opens a separate descriptor: flock serializes both threads and processes.
            fd = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, 'a+') as lock:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
                favorites = self._read_favorites()
                if favorite:
                    favorites[item['_favorite_key']] = True
                else:
                    favorites.pop(item['_favorite_key'], None)
                payload = json.dumps({'version': 1, 'items': favorites}, sort_keys=True)
                if len(payload.encode()) + 1 > 1_048_576:
                    raise ValueError()
                fd, name = tempfile.mkstemp(prefix='.library-favorites-', suffix='.tmp', dir=workspace)
                temporary = Path(name)
                with os.fdopen(fd, 'w', encoding='utf-8') as handle:
                    handle.write(payload + '\n')
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary, self.favorites_path)
                temporary = None
            return {'id': item_id, 'favorite': favorite}
        except (OSError, ValueError, TypeError, RuntimeError):
            raise RuntimeError('즐겨찾기를 저장하지 못했습니다. 다시 확인해 주세요.') from None
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    @staticmethod
    def _favorite_key(track: dict[str, Any], audio: Path) -> str:
        # Archive changes status/path/category labels, so they must not identify a preference.
        identity = {key: _text(track.get(key)) for key in ('track_id', 'created_at', 'music_prompt', 'model')}
        if not identity['track_id']:
            # Legacy records with no identity need a content fallback, independent of folder names.
            digest = hashlib.sha256()
            with audio.open('rb') as handle:
                for chunk in iter(lambda: handle.read(1_048_576), b''):
                    digest.update(chunk)
            identity['audio_sha256'] = digest.hexdigest()
        return hashlib.sha256(json.dumps(identity, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

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
                        "_favorite_key": self._favorite_key(track, audio),
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
