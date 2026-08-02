from __future__ import annotations

import random
from typing import Any


DEFAULT_MUSIC_VARIANT = {
    "name": "base-phonk",
    "mood": [],
    "instruments": [],
    "texture": [],
}

DEFAULT_MUSIC_ARRANGEMENT = [
    "0:00-0:15 Intro: filtered cowbell motif, sub bass tension, and restrained kick hints",
    "0:15-0:45 Build: introduce the main drum groove, sharper cowbell phrases, and rising saturation",
    "0:45-1:20 First drop: full 808 bass, hard kick, and the clearest workout hook",
    "1:20-1:45 Breakdown: strip back the drums, leave atmospheric bass pulses, then rebuild pressure",
    "1:45-2:35 Climax: denser percussion, stronger low-end movement, and the highest energy section",
    "2:35-3:00 Outro: reduce layers while keeping momentum, ending cleanly without a sudden cutoff",
]

DEFAULT_IMAGE_VARIANTS = [
    {
        "name": "cyberpunk-gym",
        "visual_style": "cyberpunk gym scene",
        "subject": "athletic silhouette training in a neon-lit urban fitness space",
        "palette": "electric cyan, magenta, black, high contrast",
        "texture": "rainy neon haze, chrome reflections, cinematic shadows",
    },
    {
        "name": "bodybuilder-shadow",
        "visual_style": "dramatic fitness portrait",
        "subject": "powerful bodybuilder silhouette in a gritty gym",
        "palette": "deep black, steel gray, warm highlights",
        "texture": "sweat, chalk dust, hard rim light, heavy shadows",
    },
    {
        "name": "phonk-album-cover",
        "visual_style": "phonk album cover composition",
        "subject": "powerful central chrome object and abstract gym energy",
        "palette": "black, red, silver, high contrast",
        "texture": "grainy cover art, bold shadows, sharp graphic framing",
    },
]


def build_music_prompt(config: dict[str, Any]) -> str:
    return str(build_music_prompt_with_metadata(config)["prompt"])


def build_music_prompt_with_metadata(config: dict[str, Any]) -> dict[str, Any]:
    variant = _select_variant(config.get("prompt_variants"), config.get("seed"), DEFAULT_MUSIC_VARIANT)
    duration = int(config.get("duration_seconds", 180))
    genre = str(config.get("genre", "Brazilian phonk"))
    bpm_min = variant.get("bpm_min", config.get("bpm_min"))
    bpm_max = variant.get("bpm_max", config.get("bpm_max"))
    bpm = f"{bpm_min}-{bpm_max} BPM" if bpm_min and bpm_max else "high-energy BPM"
    mood_values = _merge_lists(config.get("mood", []), variant.get("mood", []))
    instrument_values = _merge_lists(config.get("instruments", []), variant.get("instruments", []))
    texture_values = _merge_lists(config.get("texture", []), variant.get("texture", []))
    mood = _join(mood_values)
    instruments = _join(instrument_values)
    texture = _join(texture_values)
    arrangement_values = _arrangement_values(variant.get("arrangement") or config.get("arrangement"))
    arrangement = _format_arrangement(arrangement_values)
    vocals = str(config.get("vocals", "none")).lower()
    negative_rules = _join(config.get("negative_rules", []))
    music_context = str(config.get("music_context", "intense workout sessions"))

    vocal_text = "instrumental focus"
    if vocals in {"none", "instrumental"}:
        vocal_text = "instrumental, no lead vocals"
    elif vocals == "sparse_chants":
        vocal_text = "instrumental focus with sparse crowd-style chants"

    parts = [
        f"Create a {duration}-second {genre} track for {music_context}.",
        f"{bpm}, {mood} mood." if mood else f"{bpm}.",
        f"Use {instruments}." if instruments else "",
        f"Texture: {texture}." if texture else "",
        vocal_text + ".",
        "Structure the track as a complete song, not a static loop.",
        arrangement,
        f"Rules: {negative_rules}." if negative_rules else "",
    ]
    prompt = " ".join(part for part in parts if part).strip()
    return {
        "prompt": prompt,
        "music_variant": variant["name"],
        "bpm": _numeric_bpm(bpm_min, bpm_max),
        "mood": mood_values,
        "instruments": instrument_values,
        "texture": texture_values,
        "arrangement": arrangement_values,
    }


def build_image_prompt(music_prompt: str, metadata: dict[str, Any]) -> str:
    return str(build_image_prompt_with_metadata(music_prompt, metadata, {})["prompt"])


def build_image_prompt_with_metadata(
    music_prompt: str,
    metadata: dict[str, Any],
    config: dict[str, Any] | None = None,
) -> dict[str, str]:
    config = config or {}
    variant = _select_variant(config.get("image_variants"), config.get("seed"), DEFAULT_IMAGE_VARIANTS[0])
    genre = str(metadata.get("genre", "Brazilian phonk"))
    mood = _join(metadata.get("mood", [])) or "aggressive, focused"
    texture = _join(metadata.get("texture", [])) or "gritty, high contrast"
    image_context = str(config.get("image_context", "workout music video"))
    prompt = (
        f"Create a 16:9 cinematic background image for a {image_context}. "
        f"Visualize the energy of {genre}: {mood}, {texture}. "
        f"Style: {variant.get('visual_style', 'cyberpunk gym scene')}. "
        f"Subject: {variant.get('subject', 'athletic silhouette in a training space')}. "
        f"Palette: {variant.get('palette', 'high contrast cinematic colors')}. "
        f"Texture: {variant.get('texture', 'dramatic light and gritty atmosphere')}. "
        "No text, no logos, no watermark, no real artist reference. "
        "Safe for a YouTube thumbnail and full-screen video background."
    )
    return {"prompt": prompt, "image_variant": str(variant["name"])}


def _join(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return ", ".join(str(item) for item in value)


def _select_variant(variants: Any, seed: Any, default: dict[str, Any]) -> dict[str, Any]:
    normalized = list(variants or [])
    if not normalized:
        return dict(default)
    if seed is None:
        return dict(random.choice(normalized))
    rng = random.Random(str(seed))
    return dict(normalized[rng.randrange(len(normalized))])


def _merge_lists(base: Any, additions: Any) -> list[str]:
    merged: list[str] = []
    for value in (_as_list(base) + _as_list(additions)):
        text = str(value)
        if text and text not in merged:
            merged.append(text)
    return merged


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _arrangement_values(value: Any) -> list[str]:
    values = [str(item).strip() for item in _as_list(value or DEFAULT_MUSIC_ARRANGEMENT)]
    return [item for item in values if item]


def _format_arrangement(values: list[str]) -> str:
    timeline = " ".join(_with_period(value) for value in values)
    return f"Arrangement timeline: {timeline}" if timeline else ""


def _with_period(value: str) -> str:
    return value if value.endswith((".", "!", "?")) else value + "."


def _numeric_bpm(bpm_min: Any, bpm_max: Any) -> int | None:
    if bpm_min is None and bpm_max is None:
        return None
    try:
        if bpm_min is not None and bpm_max is not None:
            return round((int(bpm_min) + int(bpm_max)) / 2)
        return int(bpm_min or bpm_max)
    except (TypeError, ValueError):
        return None
