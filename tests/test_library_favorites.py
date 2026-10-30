import json
import shutil
import sys
import tempfile
import unittest
import wave
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from automusic.library import LibraryService
from automusic.web_app import create_app


class LibraryFavoriteTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.library=LibraryService(self.root)
        for name in ('one','two'):
            folder=self.root/'workspace/tracks'/name
            folder.mkdir(parents=True)
            with wave.open(str(folder/'song.wav'),'wb') as wav:
                wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(8000)
                wav.writeframes(b'\0\0'*80)
            (folder/'track.json').write_text(json.dumps({'track_id':name,'status':'generated','title':name,'audio_path':'song.wav','created_at':'2026-10-29T00:00:00+09:00'}))
        self.original={p:p.read_bytes() for p in (self.root/'workspace/tracks').rglob('*') if p.is_file()}
        app=create_app(object(),library_service=self.library)
        self.client=app.test_client()
        self.headers={'X-CSRF-Token':app.config['CSRF_TOKEN']}

    def items(self):
        return {x['title']:x for x in self.library.list_items()['items']}

    def test_persistence_toggle_and_original_files_unchanged(self):
        item=self.items()['one']
        self.assertIs(item['favorite'],False)
        self.assertEqual(self.library.set_favorite(item['id'],True),{'id':item['id'],'favorite':True})
        other=LibraryService(self.root)
        self.assertTrue(next(x for x in other.list_items()['items'] if x['id']==item['id'])['favorite'])
        self.library.set_favorite(item['id'],False)
        self.assertFalse(self.items()['one']['favorite'])
        self.assertEqual(self.original,{p:p.read_bytes() for p in self.original})

    def test_archive_move_keeps_favorite_without_changing_route_id_contract(self):
        item=self.items()['one']
        self.library.set_favorite(item['id'],True)
        destination=self.root/'success/tracks'
        destination.mkdir(parents=True)
        shutil.move(str(self.root/'workspace/tracks/one'),str(destination/'one'))
        moved=self.items()['one']
        self.assertTrue(moved['favorite'])
        self.assertEqual(moved['source'],'archived')
        self.assertEqual(self.library.asset_path(moved['id']).name,'song.wav')

    def test_concurrent_instances_do_not_lose_updates(self):
        items=list(self.items().values())
        def update(item):
            return LibraryService(self.root).set_favorite(item['id'],True)
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(update,items))
        self.assertTrue(all(x['favorite'] for x in self.items().values()))

    def test_api_csrf_strict_bool_missing_ids(self):
        item=self.items()['one']; route=f"/api/library/{item['id']}/favorite"
        self.assertEqual(self.client.post(route,json={'favorite':True}).status_code,403)
        for value in (1,'true',None,[],{}):
            self.assertEqual(self.client.post(route,json={'favorite':value},headers=self.headers).status_code,400)
        self.assertEqual(self.client.post('/api/library/'+'f'*32+'/favorite',json={'favorite':True},headers=self.headers).status_code,404)
        result=self.client.post(route,json={'favorite':True},headers=self.headers)
        self.assertEqual(result.status_code,200)
        self.assertEqual(result.json,{'id':item['id'],'favorite':True})
        self.assertNotIn('_favorite_key',str(self.client.get('/api/library').json))

    def test_corruption_and_write_failure_are_not_success(self):
        item=self.items()['one']; route=f"/api/library/{item['id']}/favorite"
        self.library.set_favorite(item['id'],True)
        with patch('automusic.library.os.replace',side_effect=OSError('SECRET')):
            response=self.client.post(route,json={'favorite':False},headers=self.headers)
        self.assertEqual(response.status_code,503)
        self.assertNotIn('SECRET',str(response.json))
        self.assertTrue(self.items()['one']['favorite'])
        self.library.favorites_path.write_text('{broken')
        self.assertEqual(self.client.get('/api/library').status_code,503)
        self.assertEqual(self.client.post(route,json={'favorite':False},headers=self.headers).status_code,503)
        self.assertEqual(self.library.favorites_path.read_text(),'{broken')

    def test_favorite_storage_symlink_rejected(self):
        item=self.items()['one']
        outside=self.root/'outside.json'; outside.write_text('{}')
        self.library.favorites_path.symlink_to(outside)
        with self.assertRaises(RuntimeError):
            self.library.set_favorite(item['id'],True)
        self.assertEqual(outside.read_text(),'{}')

    def test_legacy_content_key_survives_move_and_status_change(self):
        folder=self.root/'workspace/tracks/one'
        metadata=json.loads((folder/'track.json').read_text())
        metadata.pop('track_id')
        (folder/'track.json').write_text(json.dumps(metadata))
        item=self.items()['one']
        self.library.set_favorite(item['id'],True)
        metadata['status']='archived'
        (folder/'track.json').write_text(json.dumps(metadata))
        destination=self.root/'success/tracks'
        destination.mkdir(parents=True)
        shutil.move(str(folder),str(destination/'renamed'))
        self.assertTrue(self.items()['one']['favorite'])

    def test_invalid_storage_schema_and_lock_symlink_fail_safely(self):
        item=self.items()['one']
        for payload in ({}, {'version':1,'items':{'bad':True}}, {'version':1,'items':{'a'*64:1}}):
            self.library.favorites_path.write_text(json.dumps(payload))
            response=self.client.post(f"/api/library/{item['id']}/favorite",json={'favorite':True},headers=self.headers)
            self.assertEqual(response.status_code,503)
        self.library.favorites_path.unlink()
        outside=self.root/'outside-lock'; outside.write_text('preserve')
        (self.root/'workspace/.library-favorites.lock').unlink(missing_ok=True)
        (self.root/'workspace/.library-favorites.lock').symlink_to(outside)
        with self.assertRaises(RuntimeError):
            self.library.set_favorite(item['id'],True)
        self.assertEqual(outside.read_text(),'preserve')


if __name__=='__main__': unittest.main()
