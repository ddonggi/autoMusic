import contextlib
import importlib.util
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from automusic.automation import run_automation


def load_script(name):
    path = Path(__file__).resolve().parents[1]/'scripts'/f'{name}.py'
    spec = importlib.util.spec_from_file_location(f'test_disabled_{name}',path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DisabledBatchTests(unittest.TestCase):
    def test_automation_defaults_to_daily_only_even_when_batch_ready(self):
        for dry_run in (False,True):
            with self.subTest(dry_run=dry_run), tempfile.TemporaryDirectory() as tmp:
                calls = []
                root = Path(tmp)
                with patch('automusic.automation.should_run_batch',return_value=True) as ready:
                    result = run_automation(project_root=root,root=root,music_config=root/'music.yaml',
                                            upload_config=root/'upload.yaml',dry_run=dry_run,
                                            runner=lambda command,check,cwd:calls.append(command))
                self.assertEqual(len(calls),1)
                self.assertTrue(calls[0][1].endswith('run_daily.py'))
                self.assertFalse(result['batch_ran'])
                self.assertIsNone(result['batch_command'])
                ready.assert_not_called()

    def test_batch_cli_disabled_before_dotenv_or_any_pipeline(self):
        cli = load_script('run_batch_upload')
        for text in ('batch_upload_enabled: false\n','title_template: test\n','batch_upload_enabled: "true"\n','batch_upload_enabled: 1\n'):
            for dry_run in (False,True):
                with self.subTest(text=text,dry_run=dry_run), tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    config = root/'upload.yaml'
                    config.write_text(text)
                    before = {p.relative_to(root):p.read_bytes() for p in root.rglob('*') if p.is_file()}
                    args = ['run_batch_upload.py','--config',str(config),'--root',str(root)]
                    if dry_run:
                        args.append('--dry-run')
                    with patch.object(sys,'argv',args), patch.object(cli,'load_dotenv') as env, patch.object(cli,'run_batch_upload') as live, patch.object(cli,'dry_run_batch_upload') as dry, contextlib.redirect_stdout(io.StringIO()) as out:
                        cli.main()
                    env.assert_not_called()
                    live.assert_not_called()
                    dry.assert_not_called()
                    self.assertIn('disabled',out.getvalue())
                    self.assertEqual(before,{p.relative_to(root):p.read_bytes() for p in root.rglob('*') if p.is_file()})

    def test_automation_cli_missing_setting_passes_false(self):
        cli = load_script('run_automation')
        result = {'daily_command':['fake'],'batch_ran':False}
        with tempfile.TemporaryDirectory() as tmp, patch.object(sys,'argv',['run_automation.py','--project-root',tmp,'--manual']), patch.object(cli,'SchedulerService') as scheduler, patch.object(cli,'load_config',return_value={}), patch.object(cli,'resolve_music_config_path',return_value=Path(tmp)/'music.yaml'), patch.object(cli,'load_dotenv'), patch.object(cli,'run_automation',return_value=result) as run, contextlib.redirect_stdout(io.StringIO()):
            scheduler.return_value.admit_run.return_value = True
            cli.main()
            self.assertIs(run.call_args.kwargs['batch_upload_enabled'],False)

    def test_unavailable_batch_config_is_disabled_before_credentials(self):
        cli = load_script('run_batch_upload')
        for config_text in (None, 'broken: ['):
            for dry_run in (False, True):
                with self.subTest(config_text=config_text,dry_run=dry_run), tempfile.TemporaryDirectory() as tmp:
                    config = Path(tmp)/'upload.yaml'
                    if config_text is not None:
                        config.write_text(config_text)
                    args = ['run_batch_upload.py','--config',str(config)] + (['--dry-run'] if dry_run else [])
                    with patch.object(sys,'argv',args), patch.object(cli,'load_dotenv') as env, patch.object(cli,'dry_run_batch_upload') as dry, patch.object(cli,'run_batch_upload') as live, contextlib.redirect_stdout(io.StringIO()) as out:
                        cli.main()
                    self.assertIn('disabled_config_unavailable',out.getvalue())
                    env.assert_not_called()
                    dry.assert_not_called()
                    live.assert_not_called()

    def test_explicit_false_blocks_pending_batch_without_scanning(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pending = root/'workspace/batches/pending'
            pending.mkdir(parents=True)
            (pending/'batch.json').write_text('{"batch_id":"pending","status":"rendered"}')
            for value in (False,1,'true'):
                calls = []
                with patch('automusic.automation.should_run_batch',side_effect=AssertionError('batch scan forbidden')):
                    result = run_automation(project_root=root,root=root,music_config=root/'music.yaml',upload_config=root/'upload.yaml',batch_upload_enabled=value,runner=lambda command,check,cwd:calls.append(command))
                self.assertFalse(result['batch_ran'])
                self.assertEqual(len(calls),1)
            self.assertTrue((pending/'batch.json').exists())

    def test_batch_cli_explicit_boolean_true_preserves_opt_in_dry_run(self):
        cli = load_script('run_batch_upload')
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp)/'upload.yaml'
            config.write_text('batch_upload_enabled: true\n')
            with patch.object(sys,'argv',['run_batch_upload.py','--config',str(config),'--dry-run']), patch.object(cli,'load_dotenv'), patch.object(cli,'dry_run_batch_upload',return_value='fake') as dry, contextlib.redirect_stdout(io.StringIO()):
                cli.main()
            dry.assert_called_once()


if __name__ == '__main__':
    unittest.main()
