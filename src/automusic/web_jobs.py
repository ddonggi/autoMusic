from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from uuid import UUID, uuid4

from .prompts import DEFAULT_MUSIC_VARIANT, build_music_prompt, build_music_prompt_with_metadata
from .state import load_json
from .web_store import WebStore, atomic_json

PUBLIC_ASSETS = {'audio'}
CONFIG_FIELDS = {'genre','seed','duration_seconds','bpm_min','bpm_max','mood','instruments','texture',
                 'arrangement','vocals','negative_rules','music_context','prompt_variants','replace_instruments','title_options',
                 'timing_mode','performance_direction','vocal_direction'}
PUBLIC_FIELDS = ('id','category_id','variant_id','music_prompt','status','created_at','started_at',
                 'completed_at','title','duration_seconds','error')


def now():
    return datetime.now(timezone.utc).isoformat()


def canonical_id(value):
    if not isinstance(value, str) or str(UUID(value)) != value:
        raise ValueError('요청 식별자를 확인해 주세요.')
    return value


class WebJobService:
    def __init__(self, root: Path, presets: dict[str, dict[str, Any]], *, track_generator: Callable[..., Any], executor: Any):
        self.root = root.resolve()
        self.presets = presets
        self.track_generator = track_generator
        self.executor = executor
        self.store = WebStore(self.root)
        self._closed = False
        try:
            # Legacy jobs remain readable; only valid, contained records are imported.
            for path in self.store.directory.glob('*/job.json'):
                try:
                    job_id = canonical_id(path.parent.name)
                    if self._job_dir(job_id) != path.parent.resolve():
                        continue
                    record = load_json(path)
                    if isinstance(record, dict) and record.get('id') == job_id:
                        self.store.state['jobs'].setdefault(job_id, record)
                except (OSError, ValueError, TypeError):
                    continue
            for job in self.store.state['jobs'].values():
                if job.get('status') in ('queued', 'generating_music'):
                    job.update(status='interrupted', completed_at=now(), error='서버 재시작으로 작업이 중단되었습니다. 자동 재실행하지 않습니다.')
                # Repair the derived job record from authoritative state.
                self._save_job(self._job_dir(job['id']), job)
            self.store.save()
        except Exception:
            self.store.close()
            raise

    def close(self):
        if self._closed:
            return
        # Workers must finish before releasing process ownership.
        shutdown = getattr(self.executor, 'shutdown', None)
        if shutdown:
            shutdown(wait=True)
        self.store.close()
        self._closed = True

    @property
    def preset_ids(self):
        return list(self.presets)

    def category_summaries(self):
        return [{'id':key,'label':str(config.get('genre',key)),
                 'variants':[{'id':str(v['name']),'label':str(v['name'])} for v in config.get('prompt_variants') or [DEFAULT_MUSIC_VARIANT]]}
                for key, config in self.presets.items()]

    def preset_summaries(self):
        return [{'id':key,'name':str(config.get('genre',key)),'default_prompt':build_music_prompt(config)} for key,config in self.presets.items()]

    def create_preview(self, category_id, variant_id):
        if category_id not in self.presets or not isinstance(variant_id, str):
            raise ValueError('유효한 카테고리와 세부 변형을 선택해 주세요.')
        config = deepcopy({k:v for k,v in self.presets[category_id].items() if k in CONFIG_FIELDS})
        # A disconnected paid request must never be retried by the web worker.
        config['lyria_retries'] = 1
        result = build_music_prompt_with_metadata(config, variant_id=variant_id)
        public = {'id':str(uuid4()),'category_id':category_id,'variant_id':result['music_variant'],
                  'prompt':result['prompt'],'details':{'genre':config.get('genre'),'bpm':result['bpm'],
                  'instruments':result['instruments'],'mood':result['mood'],'arrangement':result['arrangement'],
                  'duration_seconds':config.get('duration_seconds',180)},'model':'lyria-3.5'}
        with self.store.lock:
            if self._closed:
                raise RuntimeError('웹 서버가 종료되었습니다.')
            # Bound unused drafts; consumed previews remain part of the durable deduplication ledger.
            available = [key for key,value in self.store.state['previews'].items() if not value.get('job_id')]
            if len(available) >= 1000:
                del self.store.state['previews'][available[0]]
            self.store.state['previews'][public['id']] = {'public':public,'config':config,'result':result}
            self.store.save()
        return deepcopy(public)

    def start_preview(self, preview_id, music_prompt, request_id, *, legacy=False):
        canonical_id(preview_id)
        canonical_id(request_id)
        if not isinstance(music_prompt, str) or not music_prompt.strip() or len(music_prompt) > 20000:
            raise ValueError('프롬프트는 1~20,000자로 입력해 주세요.')
        prompt = music_prompt.strip()
        with self.store.lock:
            if self._closed:
                raise RuntimeError('웹 서버가 종료되었습니다.')
            state = self.store.state
            previous = state['requests'].get(request_id)
            if previous:
                if previous['preview_id'] != preview_id or previous['prompt'] != prompt:
                    raise ValueError('같은 요청 식별자로 다른 내용을 보낼 수 없습니다.')
                return self.public_job(state['jobs'][previous['job_id']])
            preview = state['previews'].get(preview_id)
            if preview is None:
                raise ValueError('미리보기를 다시 만들어 주세요.')
            if preview.get('job_id'):
                job = state['jobs'][preview['job_id']]
                if job['music_prompt'] != prompt:
                    raise ValueError('이미 생성한 미리보기입니다. 새 미리보기를 만들어 주세요.')
                return self.public_job(job)
            if sum(j.get('status') in ('queued','generating_music') for j in state['jobs'].values()) >= 10:
                raise ValueError('대기 중인 작업이 많습니다. 잠시 후 다시 시도해 주세요.')
            job_id = str(uuid4())
            job = {'id':job_id,'preset_id':preview['public']['category_id'],
                   'category_id':preview['public']['category_id'],'variant_id':preview['public']['variant_id'],
                   'music_prompt':prompt,'status':'queued','created_at':now(),'started_at':None,'completed_at':None,
                   'title':None,'duration_seconds':None,'error':None,'artifacts':{},
                   'snapshot':deepcopy(preview['config']),'resolved_music_result':deepcopy(preview['result']),'legacy':legacy}
            before = deepcopy(state)
            preview['job_id'] = job_id
            state['requests'][request_id] = {'preview_id':preview_id,'prompt':prompt,'job_id':job_id}
            state['jobs'][job_id] = job
            # One authoritative atomic write reserves preview + request + job before submit.
            try:
                self.store.save()
            except Exception:
                self.store.state = before
                raise RuntimeError('작업을 저장할 수 없습니다.') from None
            try:
                self._save_job(self._job_dir(job_id), job)
                self.executor.submit(self._run, job_id)
            except Exception:
                self._set_status(self._job_dir(job_id), job, 'failed', error='작업을 시작할 수 없습니다. 새 미리보기로 다시 시도해 주세요.')
            return self.public_job(self.get(job_id))

    def start(self, preset_id, music_prompt):
        preview = self.create_preview(preset_id, 'random')
        result = self.start_preview(preview['id'], music_prompt.strip() if music_prompt and music_prompt.strip() else preview['prompt'], str(uuid4()), legacy=True)
        return self.get(result['id'])

    def get(self, job_id):
        self._job_dir(job_id)
        with self.store.lock:
            record = self.store.state['jobs'].get(job_id)
            if record is None:
                raise FileNotFoundError(job_id)
            return deepcopy(record)

    def list_jobs(self):
        with self.store.lock:
            jobs = sorted(self.store.state['jobs'].values(), key=lambda j:(j.get('created_at') or '',j['id']), reverse=True)
            return [self.public_job(j) for j in jobs]

    def public_job(self, job):
        result = {key:job.get(key) for key in PUBLIC_FIELDS}
        result['category_id'] = job.get('category_id',job.get('preset_id'))
        available = job.get('status') == 'completed' and isinstance(job.get('artifacts',{}).get('audio'),str)
        result['audio_url'] = f"/api/jobs/{job['id']}/audio" if available else None
        result['download_url'] = f"/api/jobs/{job['id']}/downloads/audio" if available else None
        return result

    def asset_path(self, job_id, asset):
        if asset not in PUBLIC_ASSETS:
            raise ValueError('지원하지 않는 파일입니다.')
        job_dir = self._job_dir(job_id)
        job = self.get(job_id)
        relative = job.get('artifacts',{}).get(asset)
        if job.get('status') != 'completed' or not isinstance(relative,str):
            raise FileNotFoundError('파일을 찾을 수 없습니다.')
        path = self._contained_path(job_dir,relative)
        if not path.is_file():
            raise FileNotFoundError('파일을 찾을 수 없습니다.')
        return path

    def _run(self, job_id):
        job_dir = self._job_dir(job_id)
        job = self.get(job_id)
        try:
            self._set_status(job_dir,job,'generating_music')
            kwargs = {'music_prompt':job['music_prompt']}
            if not job.get('legacy'):
                kwargs['resolved_music_result'] = deepcopy(job['resolved_music_result'])
            track_dir = Path(asyncio.run(self.track_generator(deepcopy(job['snapshot']), job_dir, **kwargs))).resolve()
            if job_dir not in track_dir.parents:
                raise ValueError('결과 경로를 확인할 수 없습니다.')
            track = load_json(self._contained_path(track_dir, 'track.json'))
            path = self._contained_path(track_dir, track['audio_path'])
            if not path.is_file():
                raise FileNotFoundError('음원 파일이 없습니다.')
            self._set_artifact(job_dir, job, 'audio', path)
            job.update(title=track.get('title'), duration_seconds=track.get('duration_seconds'))
            self._set_status(job_dir,job,'completed')
        except Exception:
            self._set_status(job_dir,job,'failed',error='음악 생성 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.')

    def _set_status(self, job_dir, job, status, *, error=None):
        with self.store.lock:
            job.update(status=status,error=error)
            if status == 'generating_music':
                job['started_at'] = now()
            if status in ('completed','failed','interrupted'):
                job['completed_at'] = now()
            self.store.state['jobs'][job['id']] = deepcopy(job)
            self.store.save()
            self._save_job(job_dir,job)

    def _set_artifact(self, job_dir, job, asset, path):
        job['artifacts'][asset] = str(path.resolve().relative_to(job_dir))

    @staticmethod
    def _save_job(job_dir, job):
        atomic_json(job_dir / 'job.json', job)

    def _job_dir(self, job_id):
        canonical_id(job_id)
        path = self.store.directory / job_id
        if path.resolve() != path or self.store.directory not in path.resolve().parents:
            raise ValueError('잘못된 작업 경로입니다.')
        return path

    @staticmethod
    def _contained_path(job_dir, relative_path):
        if not isinstance(relative_path,str) or Path(relative_path).is_absolute() or '..' in Path(relative_path).parts:
            raise ValueError('잘못된 파일 경로입니다.')
        path = (job_dir / relative_path).resolve()
        if job_dir.resolve() not in path.parents:
            raise ValueError('잘못된 파일 경로입니다.')
        return path
