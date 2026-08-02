from __future__ import annotations

import asyncio
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Awaitable, Callable
from zoneinfo import ZoneInfo

from .audio import write_pcm16_wav
from .prompts import build_music_prompt_with_metadata, build_track_title
from .state import save_json

MusicChunkProducer = Callable[[str, dict[str, Any], dict[str, Any], int], Awaitable[list[bytes]]]


def build_audio_filename(title: str, now: datetime) -> str:
    title_slug = _filename_slug(title)
    return f"{title_slug}-{now:%Y%m%d-%H%M%S}.wav"


def _filename_slug(value: str) -> str:
    words = re.findall(r"[a-z0-9]+", value.lower())
    return "-".join(words)[:48] or "music"


def make_track_id(now: datetime, slug: str = "music") -> str:
    return f"{now:%Y%m%d-%H%M%S}-{slug}"


async def generate_lyria_track(
    config: dict[str, Any],
    workspace_tracks: Path,
    *,
    music_prompt: str | None = None,
    music_chunk_producer: MusicChunkProducer | None = None,
) -> Path:
    now = datetime.now(ZoneInfo("Asia/Seoul"))
    music_result = build_music_prompt_with_metadata(config)
    genre_slug = _filename_slug(str(config.get("genre", "music")))
    base_track_id = make_track_id(now, genre_slug)
    normalized_music_prompt = music_prompt.strip() if music_prompt is not None else ""
    prompt = normalized_music_prompt or str(music_result["prompt"])
    target_seconds = int(config.get("duration_seconds", 180))
    producer = music_chunk_producer or _generate_lyria_pcm_chunks
    pcm_chunks = await _produce_music_with_retries(producer, prompt, config, music_result, target_seconds)

    track_dir = _make_unique_dir(workspace_tracks, base_track_id)
    track_id = track_dir.name
    title = build_track_title(config, music_result)
    audio_filename = build_audio_filename(title, now)
    audio_path = track_dir / audio_filename
    duration_seconds = write_pcm16_wav(pcm_chunks, audio_path)
    save_json(
        track_dir / "track.json",
        {
            "track_id": track_id,
            "status": "generated",
            "genre": config.get("genre", "Brazilian phonk"),
            "mood": music_result["mood"],
            "texture": music_result["texture"],
            "music_variant": music_result["music_variant"],
            "title": title,
            "music_prompt": prompt,
            "duration_seconds": duration_seconds,
            "audio_path": audio_filename,
            "batch_id": None,
            "created_at": now.isoformat(),
        },
    )
    return track_dir


async def _generate_lyria_pcm_chunks(
    prompt: str,
    config: dict[str, Any],
    music_result: dict[str, Any],
    target_seconds: int,
) -> list[bytes]:
    from google import genai
    from google.genai import types

    client = genai.Client(http_options={"api_version": "v1alpha"})
    pcm_chunks: list[bytes] = []

    async with client.aio.live.music.connect(model="models/lyria-realtime-exp") as session:
        await session.set_weighted_prompts(
            prompts=[types.WeightedPrompt(text=prompt, weight=1.0)]
        )
        await session.set_music_generation_config(
            config=types.LiveMusicGenerationConfig(
                bpm=int(config.get("bpm", music_result.get("bpm") or config.get("bpm_min", 136))),
                temperature=float(config.get("temperature", 1.1)),
            )
        )
        await session.play()
        max_bytes = target_seconds * 48_000 * 2 * 2
        async for message in session.receive():
            chunks = getattr(message.server_content, "audio_chunks", [])
            for chunk in chunks:
                pcm_chunks.append(chunk.data)
            if sum(len(chunk) for chunk in pcm_chunks) >= max_bytes:
                await session.stop()
                break
            await asyncio.sleep(0)
    return pcm_chunks


async def _produce_music_with_retries(
    producer: MusicChunkProducer,
    prompt: str,
    config: dict[str, Any],
    music_result: dict[str, Any],
    target_seconds: int,
) -> list[bytes]:
    max_attempts = max(1, int(config.get("lyria_retries", 3)))
    delay_seconds = max(0.0, float(config.get("lyria_retry_delay_seconds", 30)))
    for attempt in range(1, max_attempts + 1):
        try:
            return await producer(prompt, config, music_result, target_seconds)
        except Exception as exc:
            if attempt >= max_attempts or not _is_retryable_music_error(exc):
                raise
            print(
                f"Lyria generation failed on attempt {attempt}/{max_attempts}: {exc}. Retrying...",
                file=sys.stderr,
            )
            if delay_seconds:
                await asyncio.sleep(delay_seconds)
    raise RuntimeError("Lyria generation failed without returning audio")


def _is_retryable_music_error(error: BaseException) -> bool:
    text = f"{type(error).__name__}: {error}".lower()
    retryable_markers = [
        "1006",
        "abnormal closure",
        "connection reset",
        "connectionclosed",
        "timeout",
        "temporarily unavailable",
        "unavailable",
        "503",
    ]
    return any(marker in text for marker in retryable_markers)


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


# Future lyric/text hook based on the user's original generate_content sketch:
#
# response = client.models.generate_content(
#     model="lyria-3-pro-preview",
#     contents=prompt,
#     config=types.GenerateContentConfig(response_modalities=["AUDIO", "TEXT"]),
# )
# lyrics = []
# audio_data = None
# for part in response.parts:
#     if part.text is not None:
#         lyrics.append(part.text)
#     elif part.inline_data is not None:
#         audio_data = part.inline_data.data
