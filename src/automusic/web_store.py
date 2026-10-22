"""Single-process, atomic local dashboard state (no automatic paid retries)."""
from __future__ import annotations

import fcntl
import json
import os
import threading
from pathlib import Path
from uuid import uuid4


def atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f'.{path.name}.{uuid4().hex}.tmp')
    try:
        with temporary.open('x', encoding='utf-8') as handle:
            json.dump(value, handle, ensure_ascii=False, sort_keys=True)
            handle.write('\n')
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


class WebStore:
    def __init__(self, root: Path):
        workspace = root / 'workspace'
        if workspace.is_symlink() or workspace.resolve() != workspace:
            raise RuntimeError('웹 저장 경로를 확인해 주세요.')
        self.directory = workspace / 'web-jobs'
        self.directory.mkdir(parents=True, exist_ok=True)
        if self.directory.resolve() != self.directory:
            raise RuntimeError('웹 저장 경로를 확인해 주세요.')
        self.lock = threading.RLock()
        lock_path = self.directory / '.dashboard.lock'
        if lock_path.is_symlink():
            raise RuntimeError('웹 잠금 경로를 확인해 주세요.')
        self.handle = lock_path.open('a+')
        try:
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.handle.close()
            raise RuntimeError('이미 실행 중인 웹 서버가 있습니다.') from None
        self.path = self.directory / '.dashboard-state.json'
        try:
            if self.path.is_symlink():
                raise RuntimeError('웹 상태 경로를 확인해 주세요.')
            self.state = json.loads(self.path.read_text()) if self.path.exists() else {'previews':{},'requests':{},'jobs':{}}
            if not isinstance(self.state, dict) or any(not isinstance(self.state.get(k), dict) for k in ('previews','requests','jobs')):
                raise RuntimeError('웹 상태 파일을 확인해 주세요.')
        except Exception:
            self.close()
            raise RuntimeError('웹 상태 파일을 읽을 수 없습니다.') from None

    def save(self):
        atomic_json(self.path, self.state)

    def close(self):
        if not self.handle.closed:
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
            self.handle.close()
