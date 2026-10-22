import json
import sys
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
import unittest
from pathlib import Path
from uuid import uuid4
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from automusic.web_jobs import WebJobService
from automusic.web_app import create_app


class Deferred:
    def __init__(self):
        self.calls = []
    def submit(self, fn, *args):
        self.calls.append((fn, args))


class DashboardJobsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.executor = Deferred()
        self.received = []
        async def generate(config, target, *, music_prompt, resolved_music_result):
            self.received.append((config, music_prompt, resolved_music_result))
            path = target / 'track'
            path.mkdir(parents=True)
            (path / 'audio.wav').write_bytes(b'audio')
            (path / 'track.json').write_text(json.dumps({'audio_path':'audio.wav','title':'Title','duration_seconds':1}))
            return path
        self.config = {'genre':'Study','prompt_variants':[{'name':'a','mood':['calm']},{'name':'b','mood':['bright']}]}
        self.service = WebJobService(self.root, {'study':self.config}, track_generator=generate, executor=self.executor)
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(lambda: self.service.close())

    def test_selection_edit_and_duplicate_are_one_generation(self):
        preview = self.service.create_preview('study', 'b')
        request_id = str(uuid4())
        job = self.service.start_preview(preview['id'], 'edited prompt', request_id)
        self.assertEqual(job, self.service.start_preview(preview['id'], 'edited prompt', request_id))
        self.assertEqual(job['id'], self.service.start_preview(preview['id'], 'edited prompt', str(uuid4()))['id'])
        with self.assertRaises(ValueError):
            self.service.start_preview(preview['id'], 'different', request_id)
        self.assertEqual(len(self.executor.calls), 1)
        self.config['genre'] = 'changed'
        fn, args = self.executor.calls[0]
        fn(*args)
        self.assertEqual(self.received[0][0]['genre'], 'Study')
        self.assertEqual(self.received[0][1], 'edited prompt')
        self.assertEqual(self.received[0][2]['music_variant'], 'b')
        self.assertEqual(self.service.get(job['id'])['status'], 'completed')
        self.assertNotIn('snapshot', self.service.public_job(self.service.get(job['id'])))

    def test_lock_and_restart_interrupt_without_resubmit(self):
        preview = self.service.create_preview('study', 'random')
        job = self.service.start_preview(preview['id'], preview['prompt'], str(uuid4()))
        with self.assertRaises(RuntimeError):
            WebJobService(self.root, {}, track_generator=None, executor=Deferred())
        self.service.close()
        self.service = WebJobService(self.root, {'study':self.config}, track_generator=None, executor=Deferred())
        self.assertEqual(self.service.get(job['id'])['status'], 'interrupted')
        self.assertEqual(self.service.executor.calls, [])

    def test_job_directory_symlink_rejected(self):
        outside = self.root / 'outside'
        outside.mkdir()
        job_id = str(uuid4())
        (self.root / 'workspace/web-jobs' / job_id).symlink_to(outside, target_is_directory=True)
        with self.assertRaises(ValueError):
            self.service.get(job_id)

    def test_submit_failure_is_recorded(self):
        preview = self.service.create_preview('study', 'a')
        with patch.object(self.executor, 'submit', side_effect=RuntimeError('SECRET')):
            job = self.service.start_preview(preview['id'], 'prompt', str(uuid4()))
        self.assertEqual(job['status'], 'failed')
        self.assertNotIn('SECRET', str(job))

    def test_concurrent_requests_reserve_single_job(self):
        preview = self.service.create_preview('study','a')
        request_id = str(uuid4())
        barrier = threading.Barrier(4)
        def submit():
            barrier.wait(timeout=2)
            return self.service.start_preview(preview['id'],'prompt',request_id)['id']
        with ThreadPoolExecutor(max_workers=4) as pool:
            ids = list(pool.map(lambda _:submit(),range(4)))
        self.assertEqual(len(set(ids)),1)
        self.assertEqual(len(self.executor.calls),1)

    def test_failed_reservation_never_submits_or_reports_queued_success(self):
        preview = self.service.create_preview('study','a')
        request_id = str(uuid4())
        with patch.object(self.service.store,'save',side_effect=OSError('disk')):
            with self.assertRaises(RuntimeError):
                self.service.start_preview(preview['id'],'prompt',request_id)
        self.assertEqual(self.executor.calls,[])
        self.assertEqual(self.service.list_jobs(),[])
        job = self.service.start_preview(preview['id'],'prompt',request_id)
        self.assertEqual(job['status'],'queued')
        self.assertEqual(len(self.executor.calls),1)

    def test_worker_refuses_external_metadata_symlink(self):
        preview = self.service.create_preview('study','a')
        job = self.service.start_preview(preview['id'],'prompt',str(uuid4()))
        async def generate(config,target,**kwargs):
            target.mkdir(parents=True,exist_ok=True)
            directory = target/'track'
            directory.mkdir()
            external = self.root/'private.json'
            external.write_text('{"audio_path":"audio.wav"}')
            (directory/'track.json').symlink_to(external)
            (directory/'audio.wav').write_bytes(b'audio')
            return directory
        self.service.track_generator = generate
        fn,args = self.executor.calls[0]
        fn(*args)
        self.assertEqual(self.service.get(job['id'])['status'],'failed')

    def test_web_snapshot_disables_paid_retries(self):
        preview = self.service.create_preview('study','a')
        job = self.service.start_preview(preview['id'],'prompt',str(uuid4()))
        self.assertEqual(self.service.get(job['id'])['snapshot']['lyria_retries'],1)

    def test_audio_range_head_and_download(self):
        preview = self.service.create_preview('study','a')
        job = self.service.start_preview(preview['id'],'prompt',str(uuid4()))
        fn,args = self.executor.calls[0]
        fn(*args)
        client = create_app(self.service).test_client()
        response = client.get(f"/api/jobs/{job['id']}/audio",headers={'Range':'bytes=1-2'})
        self.addCleanup(response.close)
        self.assertEqual(response.status_code,206)
        self.assertEqual(response.data,b'ud')
        response = client.head(f"/api/jobs/{job['id']}/audio")
        self.addCleanup(response.close)
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.data,b'')
        self.assertEqual(response.headers['Content-Length'],'5')
        response = client.get(f"/api/jobs/{job['id']}/audio",headers={'Range':'bytes=99-100'})
        self.addCleanup(response.close)
        self.assertEqual(response.status_code,416)
        response = client.get(f"/api/jobs/{job['id']}/downloads/audio")
        self.addCleanup(response.close)
        self.assertIn('attachment',response.headers['Content-Disposition'])

    def test_dashboard_library_and_scheduler_adapters(self):
        class Library:
            def list_items(self):
                return {'items':[{'duration_seconds':2},{'duration_seconds':3}],'unreadable_count':1}
        class Scheduler:
            def __init__(self):
                self.calls = []
            def status(self):
                self.calls.append('get')
                return {'state':'unknown','enabled':None,'error':'확인 불가'}
            def set_enabled(self,value):
                self.calls.append(value)
                return {'state':'partial_failure','enabled':None,'error':'변경 실패'}
        scheduler = Scheduler()
        app = create_app(self.service,library_service=Library(),scheduler_service=scheduler)
        client = app.test_client()
        self.assertEqual(client.get('/api/dashboard').get_json()['total_duration_seconds'],5)
        self.assertEqual(client.get('/api/library').get_json()['unreadable_count'],1)
        self.assertEqual(client.get('/api/scheduler').status_code,503)
        response = client.post('/api/scheduler',json={'enabled':False},headers={'X-CSRF-Token':app.config['CSRF_TOKEN']})
        self.assertEqual(response.status_code,503)
        self.assertEqual(response.get_json()['state'],'partial_failure')
        self.assertEqual(scheduler.calls,['get',False])
        self.assertEqual(client.post('/api/scheduler',json={'enabled':1},headers={'X-CSRF-Token':app.config['CSRF_TOKEN']}).status_code,400)
        self.assertEqual(scheduler.calls,['get',False])

    def test_csrf_origin_and_api(self):
        app = create_app(self.service)
        client = app.test_client()
        response = client.get('/')
        token = app.config['CSRF_TOKEN']
        self.assertEqual(client.get('/api/categories').status_code, 200)
        body = {'category_id':'study','variant_id':'a'}
        self.assertEqual(client.post('/api/previews', json=body).status_code, 403)
        self.assertEqual(client.post('/api/previews', json=body, headers={'X-CSRF-Token':token,'Origin':'https://evil.test'}).status_code, 403)
        response = client.post('/api/previews', json=body, headers={'X-CSRF-Token':token})
        self.assertEqual(response.status_code, 201)
        preview = response.get_json()
        response = client.post('/api/jobs', json={'preview_id':preview['id'],'music_prompt':'edit','request_id':str(uuid4())}, headers={'X-CSRF-Token':token})
        self.assertEqual(response.status_code, 202)
        self.assertEqual(client.get('/api/jobs').get_json()['items'][0]['music_prompt'], 'edit')
        self.assertEqual(client.get('/api/jobs', headers={'Host':'evil.test'}).status_code, 403)


if __name__ == '__main__':
    unittest.main()
