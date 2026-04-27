import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from automusic.config import load_config
from automusic.secrets import load_required_env


class ConfigTests(unittest.TestCase):
    def test_load_config_reads_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "music.json"
            path.write_text('{"duration_seconds": 180, "genre": "Brazilian phonk"}\n')

            loaded = load_config(path)

        self.assertEqual(loaded["duration_seconds"], 180)
        self.assertEqual(loaded["genre"], "Brazilian phonk")

    def test_load_config_reads_simple_yaml(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "music.yaml"
            path.write_text(
                "duration_seconds: 180\n"
                "genre: Brazilian phonk\n"
                "mood:\n"
                "  - aggressive\n"
                "  - focused\n"
            )

            loaded = load_config(path)

        self.assertEqual(loaded["duration_seconds"], 180)
        self.assertEqual(loaded["genre"], "Brazilian phonk")
        self.assertEqual(loaded["mood"], ["aggressive", "focused"])

    def test_load_required_env_reads_only_environment(self):
        old_value = os.environ.get("GEMINI_API_KEY")
        os.environ["GEMINI_API_KEY"] = "test-key"
        try:
            loaded = load_required_env(["GEMINI_API_KEY"])
        finally:
            if old_value is None:
                os.environ.pop("GEMINI_API_KEY", None)
            else:
                os.environ["GEMINI_API_KEY"] = old_value

        self.assertEqual(loaded["GEMINI_API_KEY"], "test-key")

    def test_load_required_env_rejects_missing_values(self):
        old_value = os.environ.pop("OPENAI_API_KEY", None)
        try:
            with self.assertRaisesRegex(RuntimeError, "OPENAI_API_KEY"):
                load_required_env(["OPENAI_API_KEY"])
        finally:
            if old_value is not None:
                os.environ["OPENAI_API_KEY"] = old_value


if __name__ == "__main__":
    unittest.main()
