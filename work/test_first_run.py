"""First-run regressions using temporary synthetic inventories only."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from PIL import Image
import qwen_local_labeler as qwen
from qwen_local_cache import initialize_cache, save_result

SOURCE = Path(__file__).resolve().parent
BUILD_SOURCES = (
    'app_paths.py', 'file_lock.py', 'build_multidim.py', 'multidim.py', 'review_template.html', 'review_app.js',
    'review_style.css', 'review_motion.js', 'deletion_ui.js', 'activity_section.html',
    'activity_style.css', 'activity_ui.js', 'duplicate_section.html', 'duplicate_ui.js',
    'setup_section.html', 'setup_style.css', 'setup_ui.js',
)


def project(root):
    work = root / 'work'
    work.mkdir()
    for name in BUILD_SOURCES:
        shutil.copyfile(SOURCE / name, work / name)
    return work, root / 'outputs'


def record(identifier, **extra):
    return dict(uuid=identifier, number=1, date='2026-01-01T12:00:00',
                filename=identifier + '.jpg', thumbnail='previews/' + identifier + '.jpg',
                source='original', hidden=False, favorite=False, screenshot=False,
                analysis_status='complete', ocr='', visual=[], **extra)


def write_image(output, row):
    destination = output / row['thumbnail']
    destination.parent.mkdir(parents=True, exist_ok=True)
    Image.new('RGB', (12, 8), '#698c75').save(destination)


def label(reason='synthetic'):
    return dict(status='complete', model=qwen.DEFAULT_MODEL, type=['实拍照片'],
                topic=['生活记录'], platform=[], content=['人物'], reason=reason,
                uncertain=False)


class FirstBuildTests(unittest.TestCase):
    def test_empty_project_builds_without_any_runtime_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            work, output = project(root)
            subprocess.run([sys.executable, str(work / 'build_multidim.py')],
                           check=True, capture_output=True, text=True)
            data = json.loads((output / '多标签清单.json').read_text())
            self.assertEqual(data['items'], [])
            self.assertEqual(data['analysis']['photos'], 0)
            self.assertEqual(data['trial']['total'], 0)
            self.assertNotIn('/*__', (output / '截图多标签审阅.html').read_text())

    def test_first_import_needs_no_trial_legacy_or_manual_labels(self):
        with tempfile.TemporaryDirectory() as directory:
            work, output = project(Path(directory))
            row = record('synthetic-image')
            write_image(output, row)
            (output / 'full_results.json').write_text(json.dumps([row]))
            subprocess.run([sys.executable, str(work / 'build_multidim.py')],
                           check=True, capture_output=True, text=True)
            data = json.loads((output / '多标签清单.json').read_text())
            self.assertEqual([r['uuid'] for r in data['items']], [row['uuid']])
            self.assertEqual(data['analysis']['completed'], 1)
            self.assertFalse(data['items'][0]['trial'])
            self.assertFalse((work / 'vlm_results.json').exists())

    def test_readonly_code_builds_into_an_external_data_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            source = base / 'source'
            source.mkdir()
            work, unused_output = project(source)
            data = base / 'user data'
            output = data / 'outputs'
            row = record('external-preview')
            write_image(output, row)
            (output / 'full_results.json').write_text(json.dumps([row]))
            original_files = {path.relative_to(source): path.read_bytes()
                              for path in source.rglob('*') if path.is_file()}
            for path in work.iterdir():
                path.chmod(0o444)
            work.chmod(0o555)
            source.chmod(0o555)
            try:
                subprocess.run([sys.executable, str(work / 'build_multidim.py')],
                               env=dict(os.environ, PHOTO_REVIEW_DATA_DIR=str(data),
                                        PYTHONDONTWRITEBYTECODE='1'),
                               check=True, capture_output=True, text=True)
                payload = json.loads((output / '多标签清单.json').read_text())
                self.assertEqual([item['uuid'] for item in payload['items']], [row['uuid']])
                self.assertTrue((data / 'work' / 'multidim-build.lock').exists())
                self.assertTrue((data / 'work' / 'models').is_dir())
                self.assertFalse(unused_output.exists())
                self.assertEqual({path.relative_to(source): path.read_bytes()
                                  for path in source.rglob('*') if path.is_file()}, original_files)
            finally:
                source.chmod(0o755)
                work.chmod(0o755)
                for path in work.iterdir():
                    path.chmod(0o644)


class QwenFirstRunTests(unittest.TestCase):
    def test_pause_finishes_one_image_and_resume_reuses_that_result(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            work, output = project(root)
            rows = [record('first'), record('second')]
            for row in rows:
                write_image(output, row)
            (output / 'full_results.json').write_text(json.dumps(rows))
            seen = []
            def classify(row):
                seen.append(row['uuid'])
                qwen.signal.raise_signal(qwen.signal.SIGTERM)
                return label('saved before stopping')
            with patch.multiple(qwen, ROOT=root, WORK=work, OUT=output), \
                 patch.object(qwen, 'model_settings', return_value=(work / 'model', qwen.DEFAULT_MODEL, qwen.BASE_VERSION)), \
                 patch.object(qwen, 'load_local_model', return_value=(None, None, None)), \
                 patch.object(qwen, 'run_one', side_effect=classify), \
                 patch.object(qwen, 'mx', SimpleNamespace(clear_cache=lambda: None), create=True), \
                 patch.object(qwen.os, 'nice', create=True):
                qwen.main()
                status = json.loads((output / 'local_model_progress.json').read_text())
                self.assertEqual((status['phase'], status['processed'], status['total']), ('paused', 1, 2))
                preserved = json.loads((work / 'qwen_visual_results.json').read_text())
                self.assertEqual(set(preserved), {'second'})
                qwen.main()
            self.assertEqual(seen, ['second', 'first'])
            with contextlib.closing(sqlite3.connect(work / 'qwen_cache.sqlite3')) as connection, connection:
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM results WHERE status='complete'").fetchone()[0], 2)
            self.assertEqual(json.loads((work / 'qwen_visual_results.json').read_text())['second'], preserved['second'])

    def test_model_path_is_configurable_and_has_a_distinct_cache_version(self):
        with tempfile.TemporaryDirectory() as directory:
            custom = Path(directory) / 'custom-model'
            with patch.dict(os.environ, {'PHOTO_REVIEW_MODEL_PATH': str(custom)}):
                path, name, version = qwen.model_settings()
            self.assertEqual(path, custom.resolve())
            self.assertEqual(name, 'custom-model')
            self.assertNotEqual(version, qwen.BASE_VERSION)

    def test_missing_model_explains_setup_before_importing_mlx(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(RuntimeError, '下载完整模型' if sys.platform == 'win32' else 'PHOTO_REVIEW_MODEL_PATH'):
                qwen.load_local_model(Path(directory) / 'missing-model')

    def test_whole_current_inventory_uses_cache_and_ignores_stale_queue(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            work, output = project(root)
            rows = [record('already-done'), record('retry-me'), record('new-image'),
                    record('missing-preview'), record('video', kind='video')]
            for row in rows:
                if row['uuid'] != 'missing-preview':
                    write_image(output, row)
            (output / 'full_results.json').write_text(json.dumps(rows))
            (work / 'qwen_queue.json').write_text('["obsolete-queue-entry"]')
            with contextlib.closing(sqlite3.connect(work / 'qwen_cache.sqlite3')) as connection, connection:
                initialize_cache(connection)
                save_result(connection, 'already-done', qwen.BASE_VERSION, label('keep this result'))
                save_result(connection, 'retry-me', qwen.BASE_VERSION, error='previous failure')
                preserved = connection.execute('SELECT data FROM results WHERE uuid=?', ('already-done',)).fetchone()[0]
            seen = []
            def classify(row):
                seen.append(row['uuid'])
                return label()
            with patch.multiple(qwen, ROOT=root, WORK=work, OUT=output), \
                 patch.object(qwen, 'model_settings', return_value=(work / 'model', qwen.DEFAULT_MODEL, qwen.BASE_VERSION)), \
                 patch.object(qwen, 'load_local_model', return_value=(None, None, None)), \
                 patch.object(qwen, 'run_one', side_effect=classify), \
                 patch.object(qwen, 'mx', SimpleNamespace(clear_cache=lambda: None), create=True), \
                 patch.object(qwen.os, 'nice', create=True):
                qwen.main()
            self.assertEqual(set(seen), {'retry-me', 'new-image'})
            self.assertEqual(set(json.loads((work / 'qwen_queue.json').read_text())),
                             {'already-done', 'retry-me', 'new-image'})
            with contextlib.closing(sqlite3.connect(work / 'qwen_cache.sqlite3')) as connection, connection:
                self.assertEqual(connection.execute('SELECT data FROM results WHERE uuid=?', ('already-done',)).fetchone()[0], preserved)
            status = json.loads((output / 'local_model_progress.json').read_text())
            self.assertEqual((status['phase'], status['processed'], status['total']), ('completed', 3, 3))
            self.assertFalse((work / 'qwen_benchmark.json').exists())

    def test_model_switch_failure_retains_labels_and_does_not_restore_deleted_assets(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            work, output = project(root)
            rows = [record('keep-label'), record('replace-label'), record('published-only'), record('deleted')]
            for row in rows:
                write_image(output, row)
            (output / 'full_results.json').write_text(json.dumps(rows))
            receipts = output / 'delete-receipts'
            receipts.mkdir()
            (receipts / 'synthetic.json').write_text(json.dumps({'state': 'done', 'ids': ['deleted']}))
            prior = {identifier: label('older successful label') for identifier in
                     ['keep-label', 'replace-label', 'published-only', 'deleted', 'no-longer-in-library']}
            (work / 'qwen_visual_results.json').write_text(json.dumps(prior))
            with contextlib.closing(sqlite3.connect(work / 'qwen_cache.sqlite3')) as connection, connection:
                initialize_cache(connection)
                for identifier in ['keep-label', 'replace-label', 'deleted', 'no-longer-in-library']:
                    save_result(connection, identifier, 'model-a', prior[identifier])
            seen = []
            def classify(row):
                seen.append(row['uuid'])
                if row['uuid'] == 'replace-label':
                    return label('model b succeeded')
                raise ValueError('synthetic model b failure')
            with patch.multiple(qwen, ROOT=root, WORK=work, OUT=output), \
                 patch.object(qwen, 'model_settings', return_value=(work / 'model-b', 'Model B', 'model-b')), \
                 patch.object(qwen, 'load_local_model', return_value=(None, None, None)), \
                 patch.object(qwen, 'run_one', side_effect=classify), \
                 patch.object(qwen, 'mx', SimpleNamespace(clear_cache=lambda: None), create=True), \
                 patch.object(qwen.os, 'nice', create=True):
                qwen.main()
            self.assertNotIn('deleted', seen)
            published = json.loads((work / 'qwen_visual_results.json').read_text())
            self.assertEqual(set(published), {'keep-label', 'replace-label', 'published-only'})
            self.assertEqual(published['keep-label'], prior['keep-label'])
            self.assertEqual(published['published-only'], prior['published-only'])
            self.assertEqual(published['replace-label']['reason'], 'model b succeeded')
            with contextlib.closing(sqlite3.connect(work / 'qwen_cache.sqlite3')) as connection, connection:
                old = connection.execute('SELECT status,data FROM results WHERE uuid=? AND version=?', ('keep-label', 'model-a')).fetchone()
                self.assertEqual(old[0], 'complete')
                self.assertEqual(json.loads(old[1]), prior['keep-label'])
                self.assertEqual(connection.execute('SELECT status FROM results WHERE uuid=? AND version=?', ('keep-label', 'model-b')).fetchone()[0], 'failed')
            status = json.loads((output / 'local_model_progress.json').read_text())
            self.assertEqual((status['processed'], status['total'], status['failed']), (1, 3, 2))
            updates = json.loads((output / 'local_model_updates.json').read_text())
            self.assertEqual({row['uuid'] for row in updates['items']}, set(published))

    def test_empty_library_does_not_require_model_installation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            work, output = project(root)
            with patch.multiple(qwen, ROOT=root, WORK=work, OUT=output), \
                 patch.object(qwen, 'load_local_model', side_effect=AssertionError('model must not load')), \
                 patch.object(qwen.os, 'nice', create=True):
                qwen.main()
            status = json.loads((output / 'local_model_progress.json').read_text())
            self.assertEqual((status['phase'], status['processed'], status['total']), ('completed', 0, 0))

    def test_queue_excludes_nonlocal_and_outside_preview_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / 'outputs'
            output.mkdir()
            row = record('ok')
            write_image(output, row)
            (root / 'outside.jpg').write_bytes(b'not a preview')
            rows = [row, row, dict(row, uuid='outside', thumbnail='../outside.jpg'),
                    dict(row, uuid='missing', thumbnail=''), dict(row, uuid='movie', ismovie=True)]
            self.assertEqual(qwen.available_queue(rows, output), ['ok'])


class StableNumberTests(unittest.TestCase):
    def test_activity_inventory_uses_runtime_state_on_a_first_scan(self):
        spec = importlib.util.spec_from_file_location('synthetic_activity_inventory', SOURCE / 'build_activity_inventory.py')
        activity = importlib.util.module_from_spec(spec)
        from datetime import datetime
        photo = SimpleNamespace(uuid='local-photo', date=datetime(2026, 1, 2, 12),
                                hidden=False, favorite=False, ismovie=False, path=None,
                                path_derivatives=[], original_filesize=2000,
                                screenshot=False, original_filename='synthetic.jpg')
        fake_photos = SimpleNamespace(PhotosDB=lambda: SimpleNamespace(photos=lambda: [photo]))
        with patch.dict(sys.modules, {'osxphotos': fake_photos}):
            spec.loader.exec_module(activity)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / 'outputs'
            state = root / 'work'
            with patch.multiple(activity, ROOT=state, OUT=output), \
                 contextlib.redirect_stdout(io.StringIO()):
                activity.main()
            inventory = json.loads((state / 'activity_inventory.json').read_text())
            self.assertEqual([item['uuid'] for item in inventory['items']], ['local-photo'])
            self.assertEqual(json.loads((state / 'activity_media_paths.json').read_text()), {})
            self.assertTrue((output / 'previews').is_dir())

    def test_legacy_analysis_cache_moves_to_runtime_state_without_changing_source(self):
        spec = importlib.util.spec_from_file_location('synthetic_full_analysis_cache', SOURCE / 'full_analysis.py')
        analysis = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {'osxphotos': SimpleNamespace(PhotosDB=None)}):
            spec.loader.exec_module(analysis)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / 'outputs'
            output.mkdir()
            (root / 'work').mkdir()
            legacy = output / 'analysis_cache.sqlite3'
            with contextlib.closing(sqlite3.connect(legacy)) as connection, connection:
                connection.execute('CREATE TABLE results(uuid TEXT PRIMARY KEY, fingerprint TEXT, data TEXT)')
                connection.execute('INSERT INTO results VALUES(?,?,?)', ('saved-image', 'v1', '{"analysis_status":"complete"}'))
            original_bytes = legacy.read_bytes()
            with patch.object(analysis, 'OUT', output):
                destination = analysis.analysis_cache_path()
                self.assertEqual(destination, root / 'work' / 'analysis_cache.sqlite3')
                with contextlib.closing(sqlite3.connect(destination)) as connection, connection:
                    self.assertEqual(connection.execute('SELECT uuid FROM results').fetchall(), [('saved-image',)])
                    connection.execute('INSERT INTO results VALUES(?,?,?)', ('new-image', 'v1', '{}'))
                analysis.analysis_cache_path()
                with contextlib.closing(sqlite3.connect(destination)) as connection, connection:
                    self.assertEqual(connection.execute('SELECT COUNT(*) FROM results').fetchone()[0], 2)
            self.assertEqual(legacy.read_bytes(), original_bytes)

    def test_rescan_keeps_existing_numbers_when_an_older_photo_is_added(self):
        # Import with a PhotosDB stub; this test never opens the real Photos library.
        spec = importlib.util.spec_from_file_location('synthetic_full_analysis', SOURCE / 'full_analysis.py')
        analysis = importlib.util.module_from_spec(spec)
        photos_module = SimpleNamespace(PhotosDB=None)
        with patch.dict(sys.modules, {'osxphotos': photos_module}):
            spec.loader.exec_module(analysis)
        class InlinePool:
            def __init__(self, **kwargs): pass
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def map(self, function, rows, **kwargs): return map(function, rows)
        from datetime import datetime
        def photo(identifier, date):
            return SimpleNamespace(uuid=identifier, original_filename=identifier+'.jpg',
                                   date=datetime.fromisoformat(date), favorite=False, hidden=False,
                                   screenshot=False, ismovie=False, path=None, path_derivatives=[])
        first = photo('existing', '2026-01-02T12:00:00')
        older = photo('new-older-photo', '2026-01-01T12:00:00')
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'outputs'
            current = [first]
            photos_module.PhotosDB = lambda: SimpleNamespace(photos=lambda: current)
            with patch.object(analysis, 'OUT', output), \
                 patch.object(analysis.concurrent.futures, 'ProcessPoolExecutor', InlinePool), \
                 patch.object(analysis, 'analyze', side_effect=lambda row: dict(row, thumbnail='', analysis_status='unavailable')), \
                 contextlib.redirect_stdout(io.StringIO()):
                analysis.main()
                first_data = json.loads((output / 'full_results.json').read_text())
                current.append(older)
                analysis.main()
                second_data = json.loads((output / 'full_results.json').read_text())
            first_numbers = {row['uuid']: row['number'] for row in first_data}
            second_numbers = {row['uuid']: row['number'] for row in second_data}
            self.assertEqual(second_numbers['existing'], first_numbers['existing'])
            self.assertGreater(second_numbers['new-older-photo'], second_numbers['existing'])


if __name__ == '__main__':
    unittest.main()
