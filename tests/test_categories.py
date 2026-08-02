import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from automusic.categories import load_category_config, load_music_category, resolve_music_config_path


class CategoryConfigTests(unittest.TestCase):
    def test_load_music_category_supports_space_and_equals_syntax(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            space_path = root / "space.conf"
            equals_path = root / "equals.conf"
            space_path.write_text("# comment\nmusic_category phonk\n")
            equals_path.write_text("music_category=study\n")

            self.assertEqual(load_music_category(space_path), "phonk")
            self.assertEqual(load_music_category(equals_path), "study")

    def test_resolve_category_file_and_load_source_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            categories = root / "configs" / "categories"
            categories.mkdir(parents=True)
            (categories / "base.yaml").write_text("genre: Fitness focus\n")
            category_path = categories / "fitness.yaml"
            category_path.write_text("source: base.yaml\n")
            selector = root / "configs" / "category.conf"
            selector.write_text("music_category fitness\n")

            resolved = resolve_music_config_path(root, selector)
            loaded = load_category_config(resolved)

        self.assertEqual(resolved, category_path.resolve())
        self.assertEqual(loaded["genre"], "Fitness focus")

    def test_unknown_category_fails_with_creation_hint(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            selector = root / "category.conf"
            selector.write_text("music_category cafe\n")

            with self.assertRaisesRegex(FileNotFoundError, "cafe.yaml"):
                resolve_music_config_path(root, selector)


if __name__ == "__main__":
    unittest.main()
