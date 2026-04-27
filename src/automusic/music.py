from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .audio import write_pcm16_wav
from .prompts import build_music_prompt
from .state import save_json


def make_track_id(now: datetime, slug: str = "brazilian-phonk") -> str:
    return f"{now:%Y%m%d-%H%M%S}-{slug}"


async def generate_lyria_track(config: dict[str, Any], workspace_tracks: Path) -> Path:
    from google import genai
    from google.genai import types

    now = datetime.now(ZoneInfo("Asia/Seoul"))
    track_id = make_track_id(now)
    track_dir = _make_unique_dir(workspace_tracks, track_id)
    track_id = track_dir.name
    prompt = build_music_prompt(config)
    target_seconds = int(config.get("duration_seconds", 180))
    client = genai.Client(http_options={"api_version": "v1alpha"})
    pcm_chunks: list[bytes] = []

    async with client.aio.live.music.connect(model="models/lyria-realtime-exp") as session:
        await session.set_weighted_prompts(
            prompts=[types.WeightedPrompt(text=prompt, weight=1.0)]
        )
        await session.set_music_generation_config(
            config=types.LiveMusicGenerationConfig(
                bpm=int(config.get("bpm", config.get("bpm_min", 136))),
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

    audio_path = track_dir / "audio.wav"
    duration_seconds = write_pcm16_wav(pcm_chunks, audio_path)
    save_json(
        track_dir / "track.json",
        {
            "track_id": track_id,
            "status": "generated",
            "genre": config.get("genre", "Brazilian phonk"),
            "mood": config.get("mood", []),
            "texture": config.get("texture", []),
            "music_prompt": prompt,
            "image_prompt": None,
            "duration_seconds": duration_seconds,
            "audio_path": "audio.wav",
            "image_path": None,
            "batch_id": None,
            "created_at": now.isoformat(),
        },
    )
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
