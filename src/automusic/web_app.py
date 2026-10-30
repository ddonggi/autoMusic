from __future__ import annotations

import atexit
import secrets
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from flask import Flask, jsonify, render_template, request, send_file

from .config import load_config, _load_yaml
from .music import generate_lyria_track
from .web_jobs import WebJobService


def _validate_category_source(path: Path, boundary: Path, seen: frozenset[Path] = frozenset()) -> None:
    resolved = path.resolve()
    if boundary not in resolved.parents or path.is_symlink() or resolved in seen or len(seen) > 32:
        raise ValueError('카테고리 상속 경로를 확인해 주세요.')
    if path.suffix == '.json':
        loaded = json.loads(path.read_text())
    elif path.suffix in {'.yaml','.yml'}:
        loaded = _load_yaml(path.read_text())
    else:
        raise ValueError('카테고리 파일 형식을 확인해 주세요.')
    if not isinstance(loaded,dict):
        raise ValueError('카테고리 설정 형식을 확인해 주세요.')
    if path.suffix != '.json' and loaded.get('source') is not None:
        source = loaded['source']
        if not isinstance(source,str):
            raise ValueError('카테고리 상속 경로를 확인해 주세요.')
        _validate_category_source(path.parent/source,boundary,seen | {resolved})


def create_default_service(root: Path, executor: Any | None = None) -> WebJobService:
    root = root.resolve()
    categories_root = root / 'configs' / 'categories'
    # Configs are server-owned, never selected by a client-supplied path.
    if categories_root.resolve() != categories_root:
        raise ValueError('카테고리 저장 경로를 확인해 주세요.')
    presets = {}
    for path in sorted(categories_root.glob('*.yaml')):
        _validate_category_source(path,categories_root)
        config = load_config(path)
        variants = config.get('prompt_variants') or []
        if not isinstance(variants,list) or any(not isinstance(v,dict) or not isinstance(v.get('name'),str) or not v['name'] or v['name'] == 'random' for v in variants):
            raise ValueError('세부 변형 설정을 확인해 주세요.')
        if len({v['name'] for v in variants}) != len(variants):
            raise ValueError('세부 변형 이름이 중복되었습니다.')
        presets[path.stem] = config
    service = WebJobService(root, presets, track_generator=generate_lyria_track,
                            executor=executor if executor is not None else ThreadPoolExecutor(max_workers=1))
    atexit.register(service.close)
    return service


def create_app(service: Any, *, library_service=None, scheduler_service=None) -> Flask:
    app = Flask(__name__)
    app.config.update(MAX_CONTENT_LENGTH=128 * 1024, CSRF_TOKEN=secrets.token_urlsafe(32))
    if library_service is None and hasattr(service, 'root'):
        from .library import LibraryService
        library_service = LibraryService(service.root)
    if scheduler_service is None and hasattr(service, 'root'):
        from .scheduler import SchedulerService
        scheduler_service = SchedulerService(service.root)

    @app.before_request
    def protect_local_requests():
        if request.host.split(':')[0].lower() not in {'localhost','127.0.0.1'}:
            return _error('로컬 주소로 접속해 주세요.',403)
        if request.method in {'POST','PUT','PATCH','DELETE'}:
            origin = request.headers.get('Origin')
            if origin:
                parsed = urlsplit(origin)
                if parsed.scheme != request.scheme or parsed.netloc.lower() != request.host.lower() or parsed.path not in ('','/') or parsed.query or parsed.fragment:
                    return _error('허용되지 않은 요청 출처입니다.',403)
            if not secrets.compare_digest(request.headers.get('X-CSRF-Token',''), app.config['CSRF_TOKEN']):
                return _error('화면을 새로고침한 후 다시 시도해 주세요.',403)

    @app.after_request
    def secure_headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'same-origin'
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; media-src 'self'; frame-ancestors 'none'; base-uri 'none'"
        return response

    @app.errorhandler(413)
    def too_large(_):
        return _error('요청 내용이 너무 큽니다.',413)

    @app.errorhandler(500)
    def internal_error(_):
        return _error('요청을 처리할 수 없습니다. 잠시 후 다시 시도해 주세요.',500)

    @app.get('/')
    def index():
        return render_template('web/index.html',csrf_token=app.config['CSRF_TOKEN'])

    @app.get('/api/presets')
    def presets():
        return jsonify(service.preset_summaries())

    @app.get('/api/categories')
    def categories():
        return jsonify({'items':service.category_summaries()})

    @app.post('/api/previews')
    def preview():
        data = request.get_json(silent=True)
        if not isinstance(data,dict) or set(data) - {'category_id','variant_id'}:
            return _error('요청 내용을 확인해 주세요.')
        try:
            if not isinstance(data.get('category_id'), str):
                raise ValueError()
            result = service.create_preview(data.get('category_id'),data.get('variant_id'))
            return jsonify(result),201
        except (ValueError,TypeError,KeyError):
            return _error('유효한 카테고리와 세부 변형을 선택해 주세요.')

    @app.post('/api/jobs')
    def create_job():
        data = request.get_json(silent=True)
        if not isinstance(data,dict) or set(data) != {'preview_id','music_prompt','request_id'}:
            return _error('미리보기와 프롬프트, 요청 식별자를 확인해 주세요.')
        try:
            return jsonify(service.start_preview(data['preview_id'],data['music_prompt'],data['request_id'])),202
        except (ValueError,TypeError,KeyError):
            return _error('요청 내용이 잘못되었거나 이미 처리된 미리보기입니다. 내용을 확인해 주세요.')
        except RuntimeError:
            return _error('작업을 시작할 수 없습니다.',503)

    @app.get('/api/jobs')
    def jobs():
        return jsonify({'items':service.list_jobs()})

    @app.get('/api/jobs/<job_id>')
    def get_job(job_id):
        try:
            job = service.get(job_id)
            if job is None:
                return _not_found()
            return jsonify(service.public_job(job))
        except (FileNotFoundError,ValueError):
            return _not_found()

    @app.get('/api/jobs/<job_id>/audio')
    def audio(job_id):
        return job_audio(job_id,False)

    @app.get('/api/jobs/<job_id>/downloads/<asset>')
    def download(job_id,asset):
        if asset != 'audio':
            return _not_found()
        return job_audio(job_id,True)

    def job_audio(job_id,attachment):
        try:
            path = service.asset_path(job_id,'audio')
            return send_file(path,mimetype='audio/wav',as_attachment=attachment,download_name=path.name,conditional=True)
        except (OSError,ValueError):
            return _not_found()

    @app.get('/api/library')
    def library():
        try:
            return jsonify(library_service.list_items())
        except (OSError, RuntimeError):
            return _error('라이브러리 정보를 읽을 수 없습니다. 저장 상태를 확인해 주세요.',503)

    @app.post('/api/library/<result_id>/favorite')
    def library_favorite(result_id):
        data = request.get_json(silent=True)
        if not isinstance(data,dict) or set(data) != {'favorite'} or type(data['favorite']) is not bool:
            return _error('즐겨찾기 설정을 확인해 주세요.')
        try:
            return jsonify(library_service.set_favorite(result_id,data['favorite']))
        except FileNotFoundError:
            return _not_found()
        except ValueError:
            return _error('즐겨찾기 설정을 확인해 주세요.')
        except (OSError, RuntimeError):
            return _error('즐겨찾기를 저장하지 못했습니다. 다시 확인해 주세요.',503)

    @app.get('/api/library/<result_id>/audio')
    def library_audio(result_id):
        return library_file(result_id,False)

    @app.get('/api/library/<result_id>/download')
    def library_download(result_id):
        return library_file(result_id,True)

    def library_file(result_id,attachment):
        try:
            path = library_service.asset_path(result_id)
            return send_file(path,mimetype='audio/wav',as_attachment=attachment,download_name=path.name,conditional=True)
        except (OSError,ValueError):
            return _not_found()

    @app.get('/api/dashboard')
    def dashboard():
        try:
            items = library_service.list_items()['items']
        except (OSError, RuntimeError):
            return _error('라이브러리 정보를 읽을 수 없습니다. 저장 상태를 확인해 주세요.',503)
        jobs = service.list_jobs()
        return jsonify({'track_count':len(items), 'total_duration_seconds':sum(i.get('duration_seconds') or 0 for i in items),
                        'active_jobs':[j for j in jobs if j['status'] in ('queued','generating_music')],
                        'recent_errors':[j for j in jobs if j['status'] in ('failed','interrupted')][:10]})

    @app.get('/api/scheduler')
    def scheduler_status():
        try:
            result = scheduler_service.status()
            return jsonify(result),503 if result.get('state') in ('unknown','partial_failure') else 200
        except (ValueError,RuntimeError,OSError):
            return _error('스케줄러 상태를 확인할 수 없습니다.',503)

    @app.post('/api/scheduler')
    def scheduler_change():
        data = request.get_json(silent=True)
        if not isinstance(data,dict) or set(data) != {'enabled'} or type(data['enabled']) is not bool:
            return _error('스케줄러 설정을 확인해 주세요.')
        try:
            result = scheduler_service.set_enabled(data['enabled'])
            return jsonify(result),503 if result.get('state') in ('unknown','partial_failure') or result.get('error') else 200
        except (ValueError,RuntimeError,OSError):
            return _error('스케줄러 설정을 변경할 수 없습니다.',503)

    return app


def _error(message,status=400):
    return jsonify({'error':message}),status


def _not_found():
    return _error('요청한 작업 또는 파일을 찾을 수 없습니다.',404)
