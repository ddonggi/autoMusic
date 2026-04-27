from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .archive import archive_success
from .audio import write_pcm16_wav
from .batch import build_batch
from .prompts import build_image_prompt, build_music_prompt
from .state import load_json, save_json


def dry_run_music(config: dict, tracks_root: Path) -> Path:
    now = datetime.now(ZoneInfo("Asia/Seoul"))
    track_dir = _make_unique_dir(tracks_root, f"{now:%Y%m%d-%H%M%S}-dry-run")
    track_id = track_dir.name
    music_prompt = build_music_prompt(config)
    metadata = {
        "genre": config.get("genre", "Brazilian phonk"),
        "mood": config.get("mood", []),
        "texture": config.get("texture", []),
    }
    duration_seconds = write_pcm16_wav([b"\x00\x00\x00\x00" * 48_000], track_dir / "audio.wav")
    save_json(
        track_dir / "track.json",
        {
            "track_id": track_id,
            "status": "generated",
            "genre": metadata["genre"],
            "mood": metadata["mood"],
            "texture": metadata["texture"],
            "music_prompt": music_prompt,
            "image_prompt": None,
            "duration_seconds": duration_seconds,
            "audio_path": "audio.wav",
            "image_path": None,
            "batch_id": None,
            "created_at": now.isoformat(),
        },
    )
    return track_dir


def dry_run_image(track_dir: Path) -> Path:
    track_json = track_dir / "track.json"
    track = load_json(track_json)
    image_prompt = build_image_prompt(track["music_prompt"], track)
    image_path = track_dir / "image.png"
    image_path.write_bytes(_one_pixel_png())
    track["status"] = "imaged"
    track["image_prompt"] = image_prompt
    track["image_path"] = "image.png"
    save_json(track_json, track)
    return image_path


def dry_run_daily(config: dict, tracks_root: Path) -> Path:
    track_dir = dry_run_music(config, tracks_root)
    dry_run_image(track_dir)
    return track_dir


def _make_unique_dir(root: Path, base_name: str) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    candidate = root / base_name
    if not candidate.exists():
        candidate.mkdir()
        return candidate
    index = 2
    while True:
        candidate = root / f"{base_name}-{index:03d}"
        if not candidate.exists():
            candidate.mkdir()
            return candidate
        index += 1


def dry_run_batch_upload(root: Path) -> Path:
    tracks_root = root / "workspace" / "tracks"
    batches_root = root / "workspace" / "batches"
    batch_path = build_batch(tracks_root, batches_root, batch_count=10)
    batch = load_json(batch_path / "batch.json")
    (batch_path / "video.mp4").write_bytes(b"dry-run video")
    batch["status"] = "uploaded"
    batch["youtube_video_id"] = "dry-run-video-id"
    batch["archive_pending"] = True
    save_json(batch_path / "batch.json", batch)

    for track_id in batch["track_ids"]:
        track_path = tracks_root / track_id / "track.json"
        track = load_json(track_path)
        track["status"] = "uploaded"
        save_json(track_path, track)

    return archive_success(batch_path, tracks_root, root / "success")


def _one_pixel_png() -> bytes:
    return bytes.fromhex(
        "89504e470d0a1a0a0000000d4948445200000001000000010802000000907753de"
        "0000000c4944415408d763f8ffff3f0005fe02fea73581e40000000049454e44ae426082"
    )
