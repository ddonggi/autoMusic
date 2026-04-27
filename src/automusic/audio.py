from __future__ import annotations

import wave
from pathlib import Path
from typing import Iterable


def write_pcm16_wav(
    pcm_chunks: Iterable[bytes],
    output_path: Path,
    *,
    sample_rate: int = 48_000,
    channels: int = 2,
) -> float:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    total_bytes = 0
    with wave.open(str(output_path), "wb") as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        for chunk in pcm_chunks:
            wav_file.writeframes(chunk)
            total_bytes += len(chunk)

    frames = total_bytes // (channels * 2)
    return frames / sample_rate
