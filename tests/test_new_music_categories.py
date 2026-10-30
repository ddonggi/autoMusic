import json
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from automusic.categories import load_music_category, resolve_music_config_path
from automusic.config import load_config
from automusic.prompts import build_image_prompt_with_metadata, build_music_prompt_with_metadata, build_track_title
from automusic.web_app import create_app, create_default_service


ROOT = Path(__file__).resolve().parents[1]
VARIANTS = {
    'jazz': ['piano-trio', 'brushed-swing', 'bossa-lounge', 'late-night-sax', 'jazz-waltz'],
    'sleep': ['felt-piano-night', 'warm-pad-drift', 'rain-room', 'ambient-guitar', 'soft-strings'],
    'japan-city-pop': ['neon-cruise', 'city-funk', 'coastal-breeze', 'rainy-city-ballad', 'night-fusion'],
}
GENRES = {'jazz': 'Jazz', 'sleep': 'Sleep ambient', 'japan-city-pop': 'Japanese city pop'}


class Deferred:
    def __init__(self):
        self.calls = []

    def submit(self, fn, *args):
        self.calls.append((fn, args))


class NewMusicCategoriesTests(unittest.TestCase):
    def test_all_fifteen_prompts_are_distinct_instrumentals(self):
        for category, names in VARIANTS.items():
            with self.subTest(category=category):
                path = ROOT / 'configs/categories' / f'{category}.yaml'
                config = load_config(path)
                self.assertNotRegex(path.read_text(), r'(?m)^source:')
                self.assertEqual(config['genre'], GENRES[category])
                self.assertEqual(config['vocals'], 'none')
                self.assertEqual(config['timing_mode'], 'natural')
                self.assertEqual(config['duration_seconds'], 180)
                self.assertTrue(config['replace_instruments'])
                self.assertEqual([v['name'] for v in config['prompt_variants']], names)
                prompts = set()
                for variant in config['prompt_variants']:
                    result = build_music_prompt_with_metadata(config, variant_id=variant['name'])
                    prompt = result['prompt']
                    prompts.add(prompt)
                    self.assertIn('Instrumental only, no vocals', prompt)
                    self.assertIn('loose guide', prompt)
                    self.assertIn('naturally resolved ending', prompt)
                    self.assertNotIn('Brazilian phonk', prompt)
                    self.assertNotIn('intense workout sessions', prompt)
                    self.assertNotIn('high-energy BPM', prompt)
                    self.assertEqual(result['instruments'], variant['instruments'])
                    self.assertTrue(result['performance_direction'])
                    self.assertIn(result['performance_direction'], prompt)
                    self.assertGreaterEqual(len(result['title_options']), 3)
                    self.assertIn(build_track_title(config, result), result['title_options'])
                    self.assertGreaterEqual(len(result['arrangement']), 4)
                    self.assertLessEqual(len(result['arrangement']), 6)
                    self.assertFalse(any(re.search(r'\d+:\d{2}', stage) for stage in result['arrangement']))
                    image = build_image_prompt_with_metadata(prompt, {**result, 'genre': config['genre']}, config)
                    self.assertNotIn('Brazilian phonk', image['prompt'])
                    if category == 'sleep':
                        self.assertGreaterEqual(variant['bpm_min'], 45)
                        self.assertLessEqual(variant['bpm_max'], 65)
                        self.assertNotRegex(' '.join(result['instruments']).lower(), r'\b(drums?|kick|snare|hi-hat)\b')
                self.assertEqual(len(prompts), 5)
                self.assertIn(build_music_prompt_with_metadata(config, variant_id='random')['music_variant'], names)
                with self.assertRaises(ValueError):
                    build_music_prompt_with_metadata(config, variant_id='not-a-real-variant')

    def test_web_discovery_previews_and_mock_completed_snapshots(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(ROOT / 'configs/categories', root / 'configs/categories')
            executor = Deferred()
            service = create_default_service(root, executor=executor)
            try:
                async def generate(config, target, **kwargs):
                    folder = target / 'mock-track'
                    folder.mkdir(parents=True)
                    (folder / 'audio.wav').write_bytes(b'mock audio')
                    (folder / 'track.json').write_text(json.dumps({'audio_path': 'audio.wav', 'title': 'Mock'}))
                    return folder

                service.track_generator = generate
                client = create_app(service).test_client()
                headers = {'X-CSRF-Token': client.application.config['CSRF_TOKEN']}
                categories = {c['id']: c for c in client.get('/api/categories').get_json()['items']}
                for category, names in VARIANTS.items():
                    self.assertIn(category, categories)
                    self.assertEqual([v['id'] for v in categories[category]['variants']], names)
                    config = load_config(root / 'configs/categories' / f'{category}.yaml')
                    for name in names:
                        with self.subTest(category=category, variant=name):
                            response = client.post('/api/previews', json={'category_id': category, 'variant_id': name}, headers=headers)
                            self.assertEqual(response.status_code, 201)
                            preview = response.get_json()
                            self.assertEqual(preview['prompt'], build_music_prompt_with_metadata(config, variant_id=name)['prompt'])
                            job = service.start_preview(preview['id'], preview['prompt'], str(uuid4()))
                            snapshot = service.get(job['id'])['snapshot']
                            self.assertEqual(snapshot['genre'], GENRES[category])
                            self.assertEqual(snapshot['timing_mode'], 'natural')
                            self.assertEqual(snapshot['vocals'], 'none')
                            self.assertEqual(snapshot['lyria_retries'], 1)
                            fn, args = executor.calls[-1]
                            fn(*args)
                            self.assertEqual(service.get(job['id'])['status'], 'completed')
                self.assertEqual(len(executor.calls), 15)
            finally:
                service.close()

    def test_scheduler_category_selector_without_changing_real_settings(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(ROOT / 'configs/categories', root / 'configs/categories')
            selector = root / 'configs/category.conf'
            for category in VARIANTS:
                selector.write_text(f'music_category {category}\n')
                self.assertEqual(load_music_category(selector), category)
                self.assertEqual(resolve_music_config_path(root, selector).stem, category)


if __name__ == '__main__':
    unittest.main()
