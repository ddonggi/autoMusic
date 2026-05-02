import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from automusic.prompts import (
    build_image_prompt,
    build_image_prompt_with_metadata,
    build_music_prompt,
    build_music_prompt_with_metadata,
)


class PromptTests(unittest.TestCase):
    def test_build_music_prompt_uses_brazilian_phonk_fields(self):
        config = {
            "duration_seconds": 180,
            "genre": "Brazilian phonk",
            "bpm_min": 132,
            "bpm_max": 138,
            "mood": ["aggressive", "adrenaline-charged", "focused"],
            "instruments": ["distorted 808 bass", "driving cowbell lead"],
            "texture": ["clipped saturation", "gritty street-gym atmosphere"],
            "vocals": "none",
            "negative_rules": ["no artist-name imitation", "no copyrighted song references"],
        }

        prompt = build_music_prompt(config)

        self.assertIn("180-second", prompt)
        self.assertIn("Brazilian phonk", prompt)
        self.assertIn("132-138 BPM", prompt)
        self.assertIn("distorted 808 bass", prompt)
        self.assertIn("driving cowbell lead", prompt)
        self.assertIn("instrumental", prompt)
        self.assertIn("no artist-name imitation", prompt)

    def test_build_image_prompt_derives_visual_prompt_without_copying_music_prompt(self):
        music_prompt = (
            "Create a 180-second Brazilian phonk track for intense workout sessions. "
            "132-138 BPM, aggressive and adrenaline-charged mood, distorted 808 bass."
        )
        metadata = {
            "genre": "Brazilian phonk",
            "mood": ["aggressive", "focused"],
            "texture": ["gritty street-gym atmosphere"],
        }

        image_prompt = build_image_prompt(music_prompt, metadata)

        self.assertIn("16:9", image_prompt)
        self.assertIn("Brazilian phonk", image_prompt)
        self.assertIn("workout", image_prompt.lower())
        self.assertIn("no text", image_prompt.lower())
        self.assertNotEqual(music_prompt, image_prompt)

    def test_build_music_prompt_with_metadata_uses_seeded_variant(self):
        config = {
            "duration_seconds": 180,
            "genre": "Brazilian phonk",
            "seed": 7,
            "prompt_variants": [
                {
                    "name": "accelerated-baile",
                    "bpm_min": 138,
                    "bpm_max": 144,
                    "mood": ["accelerated", "explosive"],
                    "instruments": ["fast baile-funk percussion", "sharp cowbell patterns"],
                    "texture": ["street-rave pressure"],
                }
            ],
            "negative_rules": ["no artist-name imitation", "no copyrighted song references"],
        }

        first = build_music_prompt_with_metadata(config)
        second = build_music_prompt_with_metadata(config)

        self.assertEqual(first["music_variant"], "accelerated-baile")
        self.assertEqual(first, second)
        self.assertIn("138-144 BPM", first["prompt"])
        self.assertIn("fast baile-funk percussion", first["prompt"])
        self.assertIn("street-rave pressure", first["prompt"])

    def test_build_music_prompt_includes_variant_arrangement_timeline(self):
        config = {
            "duration_seconds": 180,
            "genre": "Brazilian phonk",
            "seed": 4,
            "prompt_variants": [
                {
                    "name": "accelerated-baile",
                    "bpm_min": 138,
                    "bpm_max": 144,
                    "mood": ["accelerated", "explosive"],
                    "instruments": ["fast baile-funk percussion", "sharp cowbell patterns"],
                    "texture": ["street-rave pressure"],
                    "arrangement": [
                        "0:00-0:12 Intro: filtered cowbell teaser with low sub tension",
                        "0:12-0:38 Build: add fast baile percussion and snare rolls",
                        "0:38-1:12 First drop: full distorted 808 and aggressive cowbell hook",
                        "1:12-1:35 Breakdown: strip drums while keeping bass pulses",
                        "1:35-2:35 Climax: denser percussion and harder kick pressure",
                        "2:35-3:00 Outro: controlled wind-down with no abrupt ending",
                    ],
                }
            ],
        }

        result = build_music_prompt_with_metadata(config)
        prompt = result["prompt"]

        self.assertIn("Structure the track as a complete song, not a static loop.", prompt)
        self.assertIn("Arrangement timeline:", prompt)
        self.assertIn("0:00-0:12 Intro: filtered cowbell teaser", prompt)
        self.assertIn("1:35-2:35 Climax: denser percussion", prompt)
        self.assertIn("2:35-3:00 Outro: controlled wind-down", prompt)

    def test_build_music_prompt_uses_default_arrangement_when_variant_has_none(self):
        config = {
            "duration_seconds": 180,
            "genre": "Brazilian phonk",
            "seed": 0,
            "prompt_variants": [
                {
                    "name": "minimal-variant",
                    "mood": ["focused"],
                    "instruments": ["distorted 808 bass"],
                    "texture": ["gritty saturation"],
                }
            ],
        }

        prompt = build_music_prompt(config)

        self.assertIn("Arrangement timeline:", prompt)
        self.assertIn("0:00-0:15 Intro:", prompt)
        self.assertIn("0:15-0:45 Build:", prompt)
        self.assertIn("0:45-1:20 First drop:", prompt)
        self.assertIn("1:20-1:45 Breakdown:", prompt)
        self.assertIn("1:45-2:35 Climax:", prompt)
        self.assertIn("2:35-3:00 Outro:", prompt)

    def test_music_prompt_does_not_include_reference_song_titles(self):
        config = {
            "duration_seconds": 180,
            "genre": "Brazilian phonk",
            "seed": 0,
            "prompt_variants": [
                {
                    "name": "dark-mind",
                    "mood": ["dark", "focused"],
                    "instruments": ["distorted 808 bass", "aggressive cowbell lead"],
                    "texture": ["shadowy low-end pressure"],
                }
            ],
        }

        result = build_music_prompt_with_metadata(config)

        forbidden_titles = [
            "montagem rugada",
            "acelerada",
            "passo bem solto",
            "montagem tomada",
            "slay!",
            "montagem - pr funk",
            "murder in my mind",
            "rave",
            "metamorphosis",
            "avangard-lonown",
        ]
        lowered = result["prompt"].lower()
        for title in forbidden_titles:
            self.assertNotIn(title, lowered)

    def test_build_image_prompt_with_metadata_uses_album_cover_variant_and_safety_rules(self):
        config = {
            "seed": 3,
            "image_variants": [
                {
                    "name": "phonk-album-cover",
                    "visual_style": "phonk album cover composition",
                    "subject": "powerful central chrome object and abstract gym energy",
                    "palette": "black, red, silver, high contrast",
                    "texture": "grainy cover art, bold shadows",
                }
            ],
        }
        metadata = {
            "genre": "Brazilian phonk",
            "mood": ["aggressive"],
            "texture": ["wide low-end"],
        }

        result = build_image_prompt_with_metadata("music prompt", metadata, config)
        prompt = result["prompt"].lower()

        self.assertEqual(result["image_variant"], "phonk-album-cover")
        self.assertIn("album cover", prompt)
        self.assertIn("16:9", prompt)
        self.assertIn("no text", prompt)
        self.assertIn("no logos", prompt)
        self.assertIn("no watermark", prompt)
        self.assertIn("no real artist reference", prompt)


if __name__ == "__main__":
    unittest.main()
