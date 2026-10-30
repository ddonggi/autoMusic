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
from automusic.prompts import build_music_prompt_with_metadata
from automusic.web_app import create_app, create_default_service


ROOT = Path(__file__).resolve().parents[1]
VARIANTS = {
    'fitness': ['rugged-cowbell', 'accelerated-baile', 'loose-step', 'tomada-drive',
                'slay-energy', 'pr-funk-pressure', 'dark-mind', 'rave-metamorphosis', 'avant-garde-phonk'],
    'fitness-metal': ['groove-metal', 'thrash-drive', 'halftime-breakdown', 'industrial-metal', 'melodic-metal'],
    'fitness-rock': ['hard-rock', 'garage-rock', 'punk-drive', 'alternative-rock', 'arena-rock'],
}


class Deferred:
    def __init__(self):
        self.calls = []

    def submit(self, fn, *args):
        self.calls.append((fn, args))


class FitnessGenresTests(unittest.TestCase):
    def test_categories_are_independent_instrumentals_with_natural_progression(self):
        for category, names in VARIANTS.items():
            with self.subTest(category=category):
                config = load_config(ROOT / 'configs/categories' / f'{category}.yaml')
                self.assertNotRegex((ROOT / 'configs/categories' / f'{category}.yaml').read_text(), r'(?m)^source:')
                expected_genre = {'fitness': 'Fitness phonk', 'fitness-metal': 'Fitness metal', 'fitness-rock': 'Fitness rock'}
                self.assertEqual(config['genre'], expected_genre[category])
                self.assertEqual(config['vocals'], 'none')
                self.assertEqual(config['timing_mode'], 'natural')
                self.assertTrue(config['replace_instruments'])
                self.assertEqual([v['name'] for v in config['prompt_variants']], names)
                self.assertEqual(config['duration_seconds'], 180)
                self.assertEqual(config['batch_count'], 10)
                self.assertNotIn('wide low-end', config.get('texture', []))
                directions = set()
                for variant in config['prompt_variants']:
                    result = build_music_prompt_with_metadata(config, variant_id=variant['name'])
                    directions.add(result['performance_direction'])
                    self.assertTrue(result['performance_direction'])
                    self.assertIn(result['performance_direction'], result['prompt'])
                    self.assertIn('Instrumental only, no vocals', result['prompt'])
                    self.assertIn('loose guide', result['prompt'])
                    self.assertIn('naturally resolved ending', result['prompt'])
                    self.assertEqual(result['instruments'], variant['instruments'])
                    self.assertGreaterEqual(len(result['arrangement']), 4)
                    self.assertLessEqual(len(result['arrangement']), 6)
                    self.assertFalse(any(re.search(r'\d+:\d{2}', stage) for stage in result['arrangement']))
                    self.assertGreaterEqual(len(result['title_options'] or config.get('title_options', [])), 2)
                    if category != 'fitness':
                        self.assertNotIn('cowbell', result['prompt'].lower())
                        self.assertNotIn('808', result['prompt'])
                self.assertEqual(len(directions), len(names))

    def test_real_category_files_are_discovered_and_preserved_in_web_snapshots(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(ROOT / 'configs/categories', root / 'configs/categories')
            executor = Deferred()
            service = create_default_service(root, executor=executor)
            try:
                async def generate(config, target, **kwargs):
                    directory = target / 'mock-track'
                    directory.mkdir(parents=True)
                    (directory / 'audio.wav').write_bytes(b'mock audio')
                    (directory / 'track.json').write_text(json.dumps({'audio_path': 'audio.wav', 'title': 'Mock'}))
                    return directory

                service.track_generator = generate
                client = create_app(service).test_client()
                headers = {'X-CSRF-Token': client.application.config['CSRF_TOKEN']}
                categories = {c['id']: c for c in client.get('/api/categories').get_json()['items']}
                for category, names in VARIANTS.items():
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
                            self.assertEqual(snapshot['vocals'], 'none')
                            self.assertEqual(snapshot['timing_mode'], 'natural')
                            self.assertEqual(snapshot['lyria_retries'], 1)
                            fn, args = executor.calls[-1]
                            fn(*args)
                            self.assertEqual(service.get(job['id'])['status'], 'completed')
                self.assertEqual(len(executor.calls), 19)
            finally:
                service.close()

    def test_scheduler_selector_accepts_new_category_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(ROOT / 'configs/categories', root / 'configs/categories')
            selector = root / 'configs/category.conf'
            for category in ('fitness-metal', 'fitness-rock'):
                selector.write_text(f'music_category {category}\n')
                self.assertEqual(load_music_category(selector), category)
                path = resolve_music_config_path(root, selector)
                self.assertEqual(load_config(path)['vocals'], 'none')


if __name__ == '__main__':
    unittest.main()
