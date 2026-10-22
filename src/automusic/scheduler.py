"""Fixed local launchd control and persistent admission for future automation runs.

The default CLI observes this gate. Explicit --manual runs bypass it. Admission
holds a short interprocess lock, never a lock over the music/upload lifetime.
"""
from __future__ import annotations

import fcntl
import json
import os
import platform as platform_module
import plistlib
import re
import stat
import subprocess
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .categories import load_music_category

LABEL = 'com.automusic.daily'
SAFE_ERROR = '스케줄러 상태를 확인할 수 없습니다.'
CHANGE_ERROR = '스케줄러 변경을 확인하지 못했습니다. 상태를 새로고침해 주세요.'


class SchedulerService:
    def __init__(self, root: Path, *, runner: Callable | None = None,
                 plist_path: Path | None = None, platform: str | None = None,
                 uid: int | None = None):
        self.root = Path(root).resolve()
        self.runner = runner or subprocess.run
        self.platform = platform if platform is not None else platform_module.system()
        self.uid = os.getuid() if uid is None else uid
        self.domain = f'gui/{self.uid}'
        self.target = f'{self.domain}/{LABEL}'
        self.plist_path = plist_path or Path.home() / 'Library' / 'LaunchAgents' / f'{LABEL}.plist'
        self.control_dir = self.root / 'workspace' / 'scheduler'
        self.gate_path = self.control_dir / 'gate.json'

    def _command(self, op: str):
        target = self.domain if op in ('print-disabled', 'bootstrap') else self.target
        argv = ['/bin/launchctl', op, target]
        if op == 'bootstrap':
            argv.append(str(self.plist_path))
        return self.runner(argv, capture_output=True,
                           text=True, timeout=5, check=False, shell=False)

    def _validated_plist(self) -> dict:
        path = self.plist_path
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o022:
            raise ValueError(SAFE_ERROR)
        with path.open('rb') as stream:
            data = plistlib.load(stream)
        args = data.get('ProgramArguments')
        script = self.root / 'scripts' / 'run_automation.py'
        if (data.get('Label') != LABEL or not isinstance(args, list) or len(args) != 4
                or not all(isinstance(value, str) for value in args)
                or args[1:] != [str(script), '--project-root', str(self.root)]
                or data.get('WorkingDirectory') != str(self.root)
                or data.get('RunAtLoad') is not False
                or data.get('KeepAlive', False) is not False
                or data.get('StartInterval') is not None
                or data.get('WatchPaths') is not None
                or data.get('QueueDirectories') is not None):
            raise ValueError(SAFE_ERROR)
        executable = Path(args[0])
        if (not executable.is_absolute() or not executable.is_file()
                or not os.access(executable, os.X_OK)
                or not re.fullmatch(r'python(?:\d+(?:\.\d+)*)?', executable.name)
                or not script.is_file() or script.resolve() != script):
            raise ValueError(SAFE_ERROR)
        schedule = data.get('StartCalendarInterval')
        if (not isinstance(schedule, dict) or set(schedule) != {'Hour', 'Minute'}
                or type(schedule['Hour']) is not int or not 0 <= schedule['Hour'] <= 23
                or type(schedule['Minute']) is not int or not 0 <= schedule['Minute'] <= 59):
            raise ValueError(SAFE_ERROR)
        return schedule

    def _read_gate(self) -> dict | None:
        # Reject external links even though this state is private to the project.
        if self.control_dir.is_symlink() or self.control_dir.resolve() != self.control_dir:
            raise ValueError(SAFE_ERROR)
        if self.gate_path.is_symlink():
            raise ValueError(SAFE_ERROR)
        if not self.gate_path.exists():
            return None
        data = json.loads(self.gate_path.read_text(encoding='utf-8'))
        if (not isinstance(data, dict) or type(data.get('enabled')) is not bool
                or type(data.get('transition_failed')) is not bool):
            raise ValueError(SAFE_ERROR)
        return data

    @contextmanager
    def _locked(self):
        if self.control_dir.is_symlink() or self.control_dir.resolve() != self.control_dir:
            raise ValueError(SAFE_ERROR)
        self.control_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        lock_path = self.control_dir / 'control.lock'
        fd = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def _write_gate(self, enabled: bool, failed: bool):
        fd, name = tempfile.mkstemp(prefix='.gate-', dir=self.control_dir)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                json.dump({'enabled': enabled, 'transition_failed': failed}, stream)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, self.gate_path)
            directory = os.open(self.control_dir, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            if os.path.exists(name):
                os.unlink(name)

    @staticmethod
    def _os_enabled(output: str) -> bool:
        if not re.search(r'disabled services\s*=\s*\{', output) or not output.rstrip().endswith('}'):
            raise ValueError(SAFE_ERROR)
        overrides = re.findall(r'"' + re.escape(LABEL) + r'"\s*=>\s*(true|false)', output)
        if LABEL in output and len(overrides) != 1:
            raise ValueError(SAFE_ERROR)
        return not overrides or overrides[0] == 'false'

    def status(self) -> dict:
        result = dict(supported=self.platform == 'Darwin', installed=None,
                      enabled=None, registered=None, running=None, state='unknown',
                      schedule=None, category_id=None, error=None,
                      observed_at=datetime.now(timezone.utc).isoformat())
        if not result['supported']:
            result['state'] = 'unsupported'
            return result
        try:
            if not self.plist_path.exists() and not self.plist_path.is_symlink():
                result.update(installed=False, state='not_installed')
                return result
            result['installed'] = True
            schedule = self._validated_plist()
            result['schedule'] = {'hour': schedule['Hour'], 'minute': schedule['Minute']}
            try:
                result['category_id'] = load_music_category(self.root / 'configs' / 'category.conf')
            except (OSError, ValueError):
                pass
            gate = self._read_gate()
            service = self._command('print')
            disabled = self._command('print-disabled')
            if disabled.returncode != 0:
                raise ValueError(SAFE_ERROR)
            os_enabled = self._os_enabled(disabled.stdout)
            # A missing label is distinct from a failed GUI-domain query.
            # print-disabled above must succeed before accepting code 113.
            if service.returncode == 113:
                result.update(registered=False, running=False, enabled=False, state='disabled')
                if gate is not None and (gate['transition_failed'] or gate['enabled'] != os_enabled):
                    result.update(state='partial_failure', error=CHANGE_ERROR)
                return result
            if service.returncode != 0:
                raise ValueError(SAFE_ERROR)
            match = re.search(r'^\s*state\s*=\s*(running|waiting|not running)\s*$', service.stdout, re.M)
            if not match:
                raise ValueError(SAFE_ERROR)
            gate_enabled = gate is None or gate['enabled']
            effective = os_enabled and gate_enabled
            partial = gate is not None and (gate['transition_failed'] or gate_enabled != os_enabled)
            result.update(registered=True, running=match[1] == 'running', enabled=effective,
                          state='partial_failure' if partial else ('enabled' if effective else 'disabled'),
                          error=CHANGE_ERROR if partial else None)
        except (OSError, ValueError, TypeError, AttributeError, plistlib.InvalidFileException, subprocess.SubprocessError):
            result.update(state='unknown', enabled=None, error=SAFE_ERROR)
        return result

    def set_enabled(self, enabled: bool) -> dict:
        if type(enabled) is not bool:
            raise ValueError('스케줄러 설정은 켜기 또는 끄기여야 합니다.')
        try:
            with self._locked():
                before = self.status()
                if (before['registered'] is None
                        or before['state'] in ('unknown', 'unsupported', 'not_installed')):
                    raise RuntimeError(SAFE_ERROR)
                if (before['enabled'] is enabled and before['state'] != 'partial_failure'
                        and before['registered'] is True):
                    self._write_gate(enabled, False)
                    after = self.status()
                    if after['enabled'] is not enabled or after['state'] not in ('enabled', 'disabled'):
                        self._write_gate(False, True)
                        raise RuntimeError(CHANGE_ERROR)
                    return after
                # Close admission before touching launchd; failure keeps it closed.
                self._write_gate(False, True)
                command = self._command('enable' if enabled else 'disable')
                if command.returncode != 0:
                    raise RuntimeError(CHANGE_ERROR)
                if enabled and before['registered'] is False:
                    bootstrap = self._command('bootstrap')
                    if bootstrap.returncode != 0:
                        raise RuntimeError(CHANGE_ERROR)
                # Verify OS state separately while the admission lock is held.
                verified = self.status()
                if (verified['registered'] is None or verified['state'] == 'unknown'
                        or (enabled and verified['registered'] is not True)):
                    raise RuntimeError(CHANGE_ERROR)
                check = self._command('print-disabled')
                if check.returncode != 0:
                    raise RuntimeError(CHANGE_ERROR)
                actual_enabled = self._os_enabled(check.stdout)
                if actual_enabled is not enabled:
                    raise RuntimeError(CHANGE_ERROR)
                self._write_gate(enabled, False)
                after = self.status()
                if after['enabled'] is not enabled or after['state'] not in ('enabled', 'disabled'):
                    self._write_gate(False, True)
                    raise RuntimeError(CHANGE_ERROR)
                return after
        except (OSError, ValueError, subprocess.SubprocessError):
            raise RuntimeError(CHANGE_ERROR) from None

    def admit_run(self, *, manual: bool = False) -> bool:
        """Linearization point for a run; a later disable never cancels it."""
        if manual:
            return True
        try:
            with self._locked():
                gate = self._read_gate()
                if gate is not None and not gate['enabled']:
                    return False
                observed = self.status()
                if observed['state'] in ('not_installed', 'unsupported'):
                    return gate is None or gate['enabled']
                return observed['enabled'] is True and observed['state'] == 'enabled'
        except (OSError, ValueError, subprocess.SubprocessError):
            return False
