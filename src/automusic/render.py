from __future__ import annotations

import subprocess
from pathlib import Path

from .state import load_json, save_json


def build_render_command(
    *,
    image_paths: list[Path],
    audio_paths: list[Path],
    output_path: Path,
    concat_file: Path,
    image_list_file: Path,
) -> list[str]:
    return [
        "ffmpeg",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(image_list_file),
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat_file),
        "-vf",
        "scale=1920:1080,format=yuv420p",
        "-c:v",
        "libx264",
        "-c:a",
        "aac",
        "-shortest",
        str(output_path),
    ]


def render_batch(
    batch_path: Path,
    tracks_root: Path,
    *,
    runner=subprocess.run,
) -> Path:
    batch = load_json(batch_path / "batch.json")
    audio_paths: list[Path] = []
    image_paths: list[Path] = []
    image_durations: list[float] = []
    for track_id in batch["track_ids"]:
        track_dir = tracks_root / track_id
        track = load_json(track_dir / "track.json")
        audio_paths.append(track_dir / track["audio_path"])
        image_paths.append(track_dir / track["image_path"])
        image_durations.append(float(track.get("duration_seconds") or 180.0))

    concat_file = batch_path / "audio_concat.txt"
    image_list_file = batch_path / "image_concat.txt"
    _write_concat_file(concat_file, audio_paths)
    _write_image_concat_file(image_list_file, image_paths, image_durations)
    output_path = batch_path / "video.mp4"
    command = build_render_command(
        image_paths=image_paths,
        audio_paths=audio_paths,
        output_path=output_path,
        concat_file=concat_file,
        image_list_file=image_list_file,
    )
    runner(command, check=True)
    batch["status"] = "rendered"
    batch["video_path"] = output_path.name
    save_json(batch_path / "batch.json", batch)
    return output_path


def _write_concat_file(path: Path, files: list[Path]) -> None:
    path.write_text("".join(f"file '{file.resolve()}'\n" for file in files))


def _write_image_concat_file(path: Path, files: list[Path], durations: list[float]) -> None:
    lines: list[str] = []
    for file, duration in zip(files, durations, strict=True):
        lines.append(f"file '{file.resolve()}'\n")
        lines.append(f"duration {duration}\n")
    if files:
        lines.append(f"file '{files[-1].resolve()}'\n")
    path.write_text("".join(lines))
