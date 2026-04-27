import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from automusic.prompts import build_image_prompt, build_music_prompt


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


if __name__ == "__main__":
    unittest.main()
