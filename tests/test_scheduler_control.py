import importlib.util
import json
import plistlib
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))


class SchedulerControlTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.plist = self.root / 'agent.plist'
        self.script = self.root / 'scripts' / 'run_automation.py'
        self.script.parent.mkdir()
        self.script.touch()
        self.payload = {
            'Label': 'com.automusic.daily',
            'ProgramArguments': [sys.executable, str(self.script), '--project-root', str(self.root)],
            'WorkingDirectory': str(self.root),
            'StartCalendarInterval': {'Hour': 12, 'Minute': 0},
            'RunAtLoad': False,
        }
        self.write_plist()
        self.disabled = False
        self.override_present = True
        self.running = False
        self.registered = True
        self.failed_operation = None
        self.calls = []

    def write_plist(self):
        self.plist.write_bytes(plistlib.dumps(self.payload))
        self.plist.chmod(0o600)

    def runner(self, argv, **kwargs):
        self.calls.append(argv)
        op = argv[1]
        if op == self.failed_operation:
            return subprocess.CompletedProcess(argv, 1, '', 'secret token')
        if op == 'print-disabled':
            value = 'true' if self.disabled else 'false'
            entry = '"com.automusic.daily" => ' + value if self.override_present else ''
            return subprocess.CompletedProcess(argv, 0, 'disabled services = {\n ' + entry + '\n}', '')
        if op == 'bootstrap':
            self.registered = True
            return subprocess.CompletedProcess(argv, 0, '', '')
        if op == 'print':
            if not self.registered:
                return subprocess.CompletedProcess(argv, 113, '', 'Could not find service')
            state = 'running' if self.running else 'waiting'
            return subprocess.CompletedProcess(argv, 0, 'gui/501/com.automusic.daily = {\n state = ' + state + '\n}', '')
        if op in ('disable', 'enable'):
            self.override_present = True
            self.disabled = op == 'disable'
            return subprocess.CompletedProcess(argv, 0, '', '')
        raise AssertionError(argv)

    def service(self, **kwargs):
        from automusic.scheduler import SchedulerService
        return SchedulerService(self.root, runner=self.runner, plist_path=self.plist,
                                platform='Darwin', uid=501, **kwargs)

    def test_status_is_read_only_and_idle_is_enabled(self):
        result = self.service().status()
        self.assertEqual(result['state'], 'enabled')
        self.assertTrue(result['registered'])
        self.assertFalse(result['running'])
        self.assertEqual(result['schedule'], {'hour': 12, 'minute': 0})
        self.assertEqual([c[1] for c in self.calls], ['print', 'print-disabled'])
        self.assertFalse((self.root / 'workspace' / 'scheduler').exists())

    def test_failed_query_is_unknown_not_disabled(self):
        self.failed_operation = 'print'
        result = self.service().status()
        self.assertEqual(result['state'], 'unknown')
        self.assertIsNone(result['enabled'])
        self.assertIsNone(result['registered'])
        self.assertNotIn('secret', json.dumps(result))
        with self.assertRaises(RuntimeError):
            self.service().set_enabled(True)
        self.assertTrue(all(c[1] in ('print', 'print-disabled') for c in self.calls))

    def test_unparseable_output_is_unknown(self):
        service = self.service()
        service.runner = lambda argv, **kw: subprocess.CompletedProcess(argv, 0, 'unrecognized', '')
        self.assertEqual(service.status()['state'], 'unknown')

    def test_wrong_project_cannot_be_controlled(self):
        self.payload['WorkingDirectory'] = '/other'
        self.write_plist()
        service = self.service()
        self.assertEqual(service.status()['state'], 'unknown')
        with self.assertRaises(RuntimeError):
            service.set_enabled(False)
        self.assertEqual(self.calls, [])

    def test_missing_and_unsupported(self):
        self.plist.unlink()
        self.assertEqual(self.service().status()['state'], 'not_installed')
        from automusic.scheduler import SchedulerService
        self.assertEqual(SchedulerService(self.root, platform='Linux', runner=self.runner).status()['state'], 'unsupported')
        self.assertEqual(self.calls, [])

    def test_disable_does_not_stop_active_work_and_persists(self):
        self.running = True
        result = self.service().set_enabled(False)
        self.assertEqual(result['state'], 'disabled')
        self.assertTrue(result['running'])
        self.assertFalse(result['enabled'])
        self.assertFalse(self.service().admit_run())
        self.assertTrue(self.service().admit_run(manual=True))
        self.assertFalse(any(c[1] in ('bootout', 'unload', 'stop', 'kill', 'kickstart') for c in self.calls))
        self.assertTrue(any(c[1:] == ['disable', 'gui/501/com.automusic.daily'] for c in self.calls))

    def test_existing_admission_survives_disable_next_admission_blocked(self):
        service = self.service()
        self.assertTrue(service.admit_run())
        service.set_enabled(False)
        self.assertFalse(service.admit_run())
        # No cancellation handle or process-termination command exists.
        self.assertFalse(any(c[1] in ('bootout', 'stop', 'kill', 'unload') for c in self.calls))

    def test_enable_restores_gate_only_after_verified_os_enable(self):
        service = self.service()
        service.set_enabled(False)
        result = service.set_enabled(True)
        self.assertTrue(result['enabled'])
        self.assertTrue(self.service().admit_run())

    def test_failed_disable_keeps_gate_closed_and_reports_partial_failure(self):
        self.failed_operation = 'disable'
        service = self.service()
        with self.assertRaisesRegex(RuntimeError, '스케줄러'):
            service.set_enabled(False)
        self.assertFalse(self.service().admit_run())
        self.assertEqual(service.status()['state'], 'partial_failure')

    def test_failed_enable_keeps_gate_closed(self):
        service = self.service()
        service.set_enabled(False)
        self.failed_operation = 'enable'
        with self.assertRaises(RuntimeError):
            service.set_enabled(True)
        self.assertFalse(self.service().admit_run())

    def test_corrupt_gate_blocks_execution(self):
        service = self.service()
        service.set_enabled(False)
        (self.root / 'workspace' / 'scheduler' / 'gate.json').write_text('{bad')
        self.assertFalse(service.admit_run())
        self.assertEqual(service.status()['state'], 'unknown')

    def test_disabled_override_survives_fresh_service(self):
        self.disabled = True
        self.assertEqual(self.service().status()['state'], 'disabled')
        self.assertFalse(self.service().admit_run())

    def test_relogin_disabled_unregistered_service_can_be_enabled_safely(self):
        self.disabled = True
        self.registered = False
        service = self.service()
        status = service.status()
        self.assertEqual(status['state'], 'disabled')
        self.assertFalse(status['registered'])
        self.assertFalse(service.admit_run())
        result = service.set_enabled(True)
        self.assertEqual(result['state'], 'enabled')
        self.assertIn(['/bin/launchctl', 'bootstrap', 'gui/501', str(self.plist)], self.calls)
        self.assertFalse(any(c[1] in ('kickstart', 'start', 'load') for c in self.calls))

    def test_booted_out_service_without_override_can_be_enabled(self):
        self.override_present = False
        self.registered = False
        service = self.service()
        status = service.status()
        self.assertFalse(status['registered'])
        self.assertFalse(status['running'])
        self.assertFalse(status['enabled'])
        result = service.set_enabled(True)
        self.assertEqual(result['state'], 'enabled')
        self.assertTrue(result['registered'])
        self.assertIn(['/bin/launchctl', 'bootstrap', 'gui/501', str(self.plist)], self.calls)

    def test_booted_out_service_without_override_can_be_disabled(self):
        self.override_present = False
        self.registered = False
        service = self.service()
        result = service.set_enabled(False)
        self.assertEqual(result['state'], 'disabled')
        self.assertFalse(result['registered'])
        self.assertFalse(result['enabled'])
        self.assertIn(['/bin/launchctl', 'disable', 'gui/501/com.automusic.daily'], self.calls)
        self.assertFalse(self.service().admit_run())

    def test_idempotent_post_write_observation_failure_raises(self):
        self.disabled = True
        service = self.service()
        original = service._write_gate
        def save_then_fail(*args):
            original(*args)
            self.failed_operation = 'print'
        with patch.object(service, '_write_gate', side_effect=save_then_fail):
            with self.assertRaises(RuntimeError):
                service.set_enabled(False)

    def test_timeout_does_not_leak_and_never_claims_disabled(self):
        service = self.service()
        def timeout(argv, **kw):
            raise subprocess.TimeoutExpired(argv, 5, output='private token')
        service.runner = timeout
        status = service.status()
        self.assertEqual(status['state'], 'unknown')
        self.assertIsNone(status['enabled'])
        self.assertNotIn('private', json.dumps(status))

    def test_invalid_enabled_type_is_rejected_without_commands(self):
        for value in (1, 'true', None):
            with self.assertRaises(ValueError):
                self.service().set_enabled(value)
        self.assertEqual(self.calls, [])

    def test_external_plist_symlink_rejected(self):
        target = self.root / 'target.plist'
        self.plist.rename(target)
        self.plist.symlink_to(target)
        self.assertEqual(self.service().status()['state'], 'unknown')
        self.assertEqual(self.calls, [])

    def test_disable_is_serialized_before_next_admission(self):
        entered = threading.Event()
        release = threading.Event()
        attempted = threading.Event()
        finished = threading.Event()
        errors = []
        admissions = []
        service = self.service()
        original = service.runner
        def held_runner(argv, **kw):
            if argv[1] == 'disable':
                entered.set()
                if not release.wait(3):
                    raise RuntimeError('test synchronization timeout')
            return original(argv, **kw)
        service.runner = held_runner
        def disable():
            try:
                service.set_enabled(False)
            except Exception as exc:
                errors.append(exc)
        def admit():
            attempted.set()
            admissions.append(self.service().admit_run())
            finished.set()
        writer = threading.Thread(target=disable)
        reader = threading.Thread(target=admit)
        writer.start()
        try:
            self.assertTrue(entered.wait(3))
            reader.start()
            self.assertTrue(attempted.wait(3))
            self.assertFalse(finished.is_set())
        finally:
            release.set()
            writer.join(3)
            if reader.ident is not None:
                reader.join(3)
        self.assertEqual(errors, [])
        self.assertEqual(admissions, [False])
        self.assertFalse(writer.is_alive())
        self.assertFalse(reader.is_alive())

    def test_disabled_idempotent_request_still_installs_local_gate(self):
        self.disabled = True
        service = self.service()
        service.set_enabled(False)
        data = json.loads((self.root / 'workspace' / 'scheduler' / 'gate.json').read_text())
        self.assertFalse(data['enabled'])
        self.assertFalse(data['transition_failed'])

    def test_failed_post_change_observation_is_not_success(self):
        service = self.service()
        original = service.runner
        def failing_verification(argv, **kw):
            result = original(argv, **kw)
            if argv[1] == 'disable':
                self.failed_operation = 'print'
            return result
        service.runner = failing_verification
        with self.assertRaises(RuntimeError):
            service.set_enabled(False)
        self.assertFalse(self.service().admit_run())
        self.assertEqual(service.status()['state'], 'unknown')

    def test_gate_save_failure_cannot_change_os_state(self):
        service = self.service()
        with patch.object(service, '_write_gate', side_effect=OSError('private token')):
            with self.assertRaises(RuntimeError) as error:
                service.set_enabled(False)
        self.assertNotIn('private', str(error.exception))
        self.assertTrue(all(c[1] in ('print', 'print-disabled') for c in self.calls))

    def test_opted_in_automation_finishes_batch_after_scheduler_disable(self):
        from automusic.automation import run_automation
        pending = self.root / 'workspace' / 'batches' / 'pending'
        pending.mkdir(parents=True)
        (pending / 'batch.json').write_text(json.dumps({'batch_id': 'pending', 'status': 'rendered'}))
        service = self.service()
        self.assertTrue(service.admit_run())
        commands = []
        def command_runner(command, check, cwd):
            commands.append(command)
            if len(commands) == 1:
                service.set_enabled(False)
        result = run_automation(project_root=self.root, root=self.root,
                                music_config=self.root / 'music.yaml',
                                upload_config=self.root / 'upload.yaml',
                                runner=command_runner, batch_upload_enabled=True)
        self.assertTrue(result['batch_ran'])
        self.assertEqual(len(commands), 2)
        self.assertTrue(commands[1][1].endswith('/scripts/run_batch_upload.py'))
        self.assertFalse(service.admit_run())

    def test_manual_cli_bypasses_disabled_gate_explicitly(self):
        service = self.service()
        service.set_enabled(False)
        spec = importlib.util.spec_from_file_location('run_automation_manual', Path(__file__).resolve().parents[1] / 'scripts/run_automation.py')
        cli = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cli)
        result = {'daily_command': ['fake'], 'batch_ran': False}
        with patch.object(cli, 'SchedulerService', return_value=service), \
                patch.object(cli, 'resolve_music_config_path', return_value=self.root / 'music.yaml'), \
                patch.object(cli, 'load_dotenv'), \
                patch.object(cli, 'load_config', return_value={}), \
                patch.object(cli, 'run_automation', return_value=result) as run:
            with patch.object(sys, 'argv', ['run_automation.py', '--project-root', str(self.root), '--manual']):
                cli.main()
            run.assert_called_once()

    def test_gate_blocks_cli_before_dotenv_and_automation(self):
        spec = importlib.util.spec_from_file_location('run_automation_cli', Path(__file__).resolve().parents[1] / 'scripts/run_automation.py')
        cli = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cli)
        with patch.object(cli, 'SchedulerService') as cls, patch.object(cli, 'load_dotenv') as env, patch.object(cli, 'run_automation') as run:
            cls.return_value.admit_run.return_value = False
            with patch.object(sys, 'argv', ['run_automation.py', '--project-root', str(self.root)]):
                cli.main()
            env.assert_not_called()
            run.assert_not_called()


if __name__ == '__main__':
    unittest.main()
