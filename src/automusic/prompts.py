from __future__ import annotations

from typing import Any


def build_music_prompt(config: dict[str, Any]) -> str:
    duration = int(config.get("duration_seconds", 180))
    genre = str(config.get("genre", "Brazilian phonk"))
    bpm_min = config.get("bpm_min")
    bpm_max = config.get("bpm_max")
    bpm = f"{bpm_min}-{bpm_max} BPM" if bpm_min and bpm_max else "high-energy BPM"
    mood = _join(config.get("mood", []))
    instruments = _join(config.get("instruments", []))
    texture = _join(config.get("texture", []))
    vocals = str(config.get("vocals", "none")).lower()
    negative_rules = _join(config.get("negative_rules", []))

    vocal_text = "instrumental focus"
    if vocals in {"none", "instrumental"}:
        vocal_text = "instrumental, no lead vocals"
    elif vocals == "sparse_chants":
        vocal_text = "instrumental focus with sparse crowd-style chants"

    parts = [
        f"Create a {duration}-second {genre} track for intense workout sessions.",
        f"{bpm}, {mood} mood." if mood else f"{bpm}.",
        f"Use {instruments}." if instruments else "",
        f"Texture: {texture}." if texture else "",
        vocal_text + ".",
        "Keep high energy throughout with clean structure for looping.",
        f"Rules: {negative_rules}." if negative_rules else "",
    ]
    return " ".join(part for part in parts if part).strip()


def build_image_prompt(music_prompt: str, metadata: dict[str, Any]) -> str:
    genre = str(metadata.get("genre", "Brazilian phonk"))
    mood = _join(metadata.get("mood", [])) or "aggressive, focused"
    texture = _join(metadata.get("texture", [])) or "gritty, high contrast"
    return (
        "Create a 16:9 cinematic background image for a workout music video. "
        f"Visualize the energy of {genre}: {mood}, {texture}. "
        "Dark urban gym atmosphere, concrete and metal textures, dramatic side light, "
        "subtle motion-blur feeling, powerful rhythm, no text, no logos, no watermark, "
        "safe for a YouTube thumbnail and full-screen video background."
    )


def _join(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return ", ".join(str(item) for item in value)
