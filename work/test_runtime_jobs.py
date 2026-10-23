"""Background jobs with short fake scripts; no Photos, network, or models."""
import json
import os
from pathlib import Path
import signal
import sqlite3
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from unittest.mock import patch

from runtime_jobs import RuntimeJobs


class FakeModels:
    def __init__(self, root):
        self.root = root
        self.selected = None
        self.closed = False

    def snapshot(self):
        return [{'id': 'synthetic', 'state': 'ready'}]

    def ready(self, identifier):
        return identifier == 'synthetic'

    def select(self, identifier):
        if not self.ready(identifier):
            raise ValueError('unknown fake model')
        self.selected = identifier

    def path(self, identifier):
        return self.root / identifier

    def close(self):
        self.closed = True


class RuntimeJobsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.code = self.root / 'code'
        self.code.mkdir()
        self.data = self.root / 'user data'
        self.models = FakeModels(self.root / 'models')
        self.callbacks = []
        self.jobs = RuntimeJobs(on_scan=lambda: self.callbacks.append('refreshed'),
                                data_root=self.data, code_dir=self.code, models=self.models)
        self.addCleanup(self.jobs.close)
        platform = patch.object(RuntimeJobs, 'platform_status', return_value={
            'supported': True, 'model_supported': True, 'message': ''})
        platform.start()
        self.addCleanup(platform.stop)
        folder = patch('folder_library.selected_folder', return_value=self.root)
        folder.start(); self.addCleanup(folder.stop)
        self.scan_script = 'folder_analysis.py' if sys.platform == 'win32' else 'full_analysis.py'
        for name in ('full_analysis.py', 'build_activity_inventory.py',
                     'find_photo_duplicates.py', 'build_multidim.py'):
            self.script(name, 'pass')
        self.script(self.scan_script, 'pass')

    def script(self, name, source):
        (self.code / name).write_text(textwrap.dedent(source))

    def wait_for(self, condition, message):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if condition():
                return
            time.sleep(.02)
        self.fail(message)

    def wait_finished(self):
        self.jobs.thread.join(timeout=6)
        self.assertFalse(self.jobs.thread.is_alive(), 'fake background job did not finish')

    def test_scan_returns_in_background_rejects_concurrency_and_refreshes_after_success(self):
        self.script(self.scan_script, '''
            import json, os, time
            from pathlib import Path
            root = Path(os.environ['PHOTO_REVIEW_DATA_DIR'])
            (root / 'entered').write_text('yes')
            while not (root / 'continue').exists(): time.sleep(.02)
            (root / 'outputs' / 'full_results.json').write_text('[{"uuid":"synthetic"}]')
            (root / 'outputs' / 'analysis_progress.json').write_text(json.dumps({'photos':1,'videos':0,'processed':1}))
        ''')
        started = time.monotonic()
        self.jobs.start_scan()
        self.assertLess(time.monotonic() - started, 1)
        self.wait_for(lambda: (self.data / 'entered').exists(), 'fake scan did not enter')
        self.assertTrue(self.jobs.thread.is_alive())
        with self.assertRaisesRegex(ValueError, '已有任务'):
            self.jobs.start_scan()
        self.assertEqual(self.callbacks, [])
        (self.data / 'continue').write_text('yes')
        self.wait_finished()
        snapshot = self.jobs.snapshot()
        self.assertEqual(snapshot['job']['state'], 'completed')
        self.assertEqual(snapshot['library']['photos'], 1)
        self.assertTrue(snapshot['library']['has_scan'])
        self.assertEqual(self.callbacks, ['refreshed'])
        self.assertIsNone(self.jobs.process)

    def test_failed_scan_retains_existing_inventory_and_is_retryable(self):
        inventory = self.jobs.out / 'full_results.json'
        original = '[{"uuid":"previous-good-result"}]'
        inventory.write_text(original)
        self.script(self.scan_script, 'raise RuntimeError("synthetic failure")')
        self.jobs.start_scan()
        self.wait_finished()
        status = self.jobs.snapshot()['job']
        self.assertEqual(status['state'], 'failed')
        self.assertIn('重试', status['message'])
        self.assertEqual(inventory.read_text(), original)
        self.assertEqual(self.callbacks, [])
        self.script(self.scan_script, 'pass')
        self.jobs.start_scan()
        self.wait_finished()
        self.assertEqual(self.jobs.snapshot()['job']['state'], 'completed')
        self.assertEqual(inventory.read_text(), original)
        self.assertEqual(self.callbacks, ['refreshed'])

    @unittest.skipIf(sys.platform == 'win32', 'POSIX process-group signal semantics; Windows tree cleanup is tested in the native bundle smoke')
    def test_stopping_scan_terminates_worker_process_and_its_child(self):
        self.script(self.scan_script, '''
            import os, signal, subprocess, sys, time
            from pathlib import Path
            root = Path(os.environ['PHOTO_REVIEW_DATA_DIR'])
            child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])
            def stop(signum, frame):
                child.wait(timeout=3)
                (root / 'child-reaped').write_text(str(child.returncode))
                raise SystemExit(0)
            signal.signal(signal.SIGTERM, stop)
            (root / 'child-pid').write_text(str(child.pid))
            while True:
                if (root / 'work' / 'task-stop').exists(): stop(None, None)
                time.sleep(.02)
        ''')
        self.jobs.start_scan()
        self.wait_for(lambda: (self.data / 'child-pid').exists(), 'fake child was not started')
        child_pid = int((self.data / 'child-pid').read_text())
        process = self.jobs.process
        try:
            self.jobs.stop()
            self.wait_finished()
            self.assertEqual(self.jobs.snapshot()['job']['state'], 'paused')
            self.assertIsNotNone(process.poll())
            self.assertTrue((self.data / 'child-reaped').exists())
            with self.assertRaises(ProcessLookupError):
                os.kill(child_pid, 0)
            self.assertEqual(self.callbacks, [])
            self.assertIsNone(self.jobs.process)
        finally:
            # Also clean up the synthetic child if the assertion exposes a bug.
            try:
                os.kill(child_pid, signal.SIGKILL)
            except ProcessLookupError:
                pass

    def test_recognition_stop_checkpoints_current_image_and_preserves_prior_cache(self):
        (self.jobs.out / 'full_results.json').write_text('[{"uuid":"synthetic"}]')
        self.script('qwen_local_labeler.py', '''
            import json, os, signal, sqlite3, time
            from pathlib import Path
            root = Path(os.environ['PHOTO_REVIEW_DATA_DIR'])
            db = sqlite3.connect(root / 'work' / 'synthetic-cache.sqlite3')
            db.execute('CREATE TABLE results(uuid TEXT PRIMARY KEY)')
            db.execute('INSERT INTO results VALUES (?)', ('previous-result',))
            db.commit()
            def stop(signum, frame):
                db.execute('INSERT INTO results VALUES (?)', ('current-result',))
                db.commit()
                db.close()
                (root / 'outputs' / 'local_model_progress.json').write_text(json.dumps({'processed':2,'total':3,'phase':'paused'}))
                raise SystemExit(0)
            signal.signal(signal.SIGTERM, stop)
            (root / 'model-path').write_text(os.environ['PHOTO_REVIEW_MODEL_PATH'])
            (root / 'recognition-ready').write_text('yes')
            while True:
                if (root / 'work' / 'task-stop').exists(): stop(None, None)
                time.sleep(.02)
        ''')
        self.jobs.start_recognition('synthetic')
        self.wait_for(lambda: (self.data / 'recognition-ready').exists(), 'fake recognizer did not enter')
        self.jobs.stop()
        self.wait_finished()
        snapshot = self.jobs.snapshot()
        self.assertEqual(snapshot['job']['state'], 'paused')
        self.assertEqual(snapshot['job']['progress'], {'processed': 2, 'total': 3})
        with sqlite3.connect(self.jobs.state_dir / 'synthetic-cache.sqlite3') as connection:
            self.assertEqual({row[0] for row in connection.execute('SELECT uuid FROM results')},
                             {'previous-result', 'current-result'})
        self.assertEqual((self.data / 'model-path').read_text(), str(self.models.path('synthetic')))
        self.assertEqual(self.models.selected, 'synthetic')
        self.assertEqual(self.callbacks, [])
        self.assertIsNone(self.jobs.process)

    def test_interrupted_state_restarts_as_paused_without_spawning_a_process(self):
        for previous in ('running', 'stopping'):
            self.jobs.state_file.write_text(json.dumps({'kind': 'recognize', 'state': previous}))
            restarted = RuntimeJobs(data_root=self.data, code_dir=self.code, models=FakeModels(self.root))
            self.addCleanup(restarted.close)
            self.assertEqual(restarted.snapshot()['job']['state'], 'paused')
            self.assertIsNone(restarted.process)
            self.assertIsNone(restarted.thread)

    def test_recognition_requires_scan_and_a_ready_model_before_starting(self):
        with self.assertRaisesRegex(ValueError, '先扫描'):
            self.jobs.start_recognition('synthetic')
        (self.jobs.out / 'full_results.json').write_text('[]')
        with self.assertRaisesRegex(ValueError, '模型下载'):
            self.jobs.start_recognition('missing')
        self.assertIsNone(self.jobs.thread)


if __name__ == '__main__':
    unittest.main()
