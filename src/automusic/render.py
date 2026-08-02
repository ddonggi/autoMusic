from __future__ import annotations

import subprocess
from pathlib import Path

from .state import load_json, save_json


def build_segment_command(
    *,
    image_path: Path,
    audio_path: Path,
    output_path: Path,
    duration: float,
) -> list[str]:
    return [
        "ffmpeg",
        "-y",
        "-loop",
        "1",
        "-t",
        str(duration),
        "-i",
        str(image_path),
        "-i",
        str(audio_path),
        "-vf",
        "scale=1920:1080,format=yuv420p",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-tune",
        "stillimage",
        "-c:a",
        "aac",
        "-shortest",
        str(output_path),
    ]


def build_concat_command(*, concat_file: Path, output_path: Path) -> list[str]:
    return [
        "ffmpeg",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat_file),
        "-c",
        "copy",
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
    image_path = batch_path / str(batch.get("image_path") or "")
    if not image_path.is_file():
        raise RuntimeError(f"Batch image does not exist: {image_path}")
    image_durations: list[float] = []
    for track_id in batch["track_ids"]:
        track_dir = tracks_root / track_id
        track = load_json(track_dir / "track.json")
        audio_paths.append(track_dir / track["audio_path"])
        image_durations.append(float(track.get("duration_seconds") or 180.0))

    segment_paths: list[Path] = []
    for index, (audio_path, duration) in enumerate(zip(audio_paths, image_durations, strict=True)):
        segment_path = batch_path / f"segment_{index:03d}.mp4"
        command = build_segment_command(
            image_path=image_path,
            audio_path=audio_path,
            output_path=segment_path,
            duration=duration,
        )
        runner(command, check=True)
        segment_paths.append(segment_path)

    concat_file = batch_path / "video_concat.txt"
    _write_concat_file(concat_file, segment_paths)
    output_path = batch_path / "video.mp4"
    command = build_concat_command(
        output_path=output_path,
        concat_file=concat_file,
    )
    runner(command, check=True)
    batch["status"] = "rendered"
    batch["video_path"] = output_path.name
    batch["duration_seconds"] = sum(image_durations)
    save_json(batch_path / "batch.json", batch)
    return output_path


def _write_concat_file(path: Path, files: list[Path]) -> None:
    path.write_text("".join(f"file '{file.resolve()}'\n" for file in files))
