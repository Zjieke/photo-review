"""Packaging boundaries: tests never copy or scan the user's Photos library."""
import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('build_release', ROOT / 'scripts/build_release.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class ReleaseBuildTests(unittest.TestCase):
    def test_copy_excludes_runtime_and_private_files(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name) / 'source'
            target = Path(name) / 'bundle'
            (root / 'work/native').mkdir(parents=True)
            (root / 'scripts').mkdir()
            for filename in ('launcher.py', 'LICENSE', 'README.md', 'THIRD_PARTY_NOTICES.md',
                             'requirements.txt', 'requirements-model.txt', 'requirements-bundle.txt',
                             'requirements-bundle-lock.txt', 'work/native/PhotosTrash.swift',
                             'scripts/build_helper.py', 'work/app_paths.py', 'work/review_app.js'):
                (root / filename).write_text('# public source\n')
            for filename in ('work/private.json', 'work/model.safetensors', 'work/private.jpg',
                             'work/test_local.py', 'work/session.log', 'work/cache.sqlite3'):
                (root / filename).write_text('private fixture')
            (root / 'outputs').mkdir()
            (root / 'outputs/full_results.json').write_text('private fixture')
            builder.copy_project(target, root)
            self.assertTrue((target / 'work/app_paths.py').is_file())
            self.assertTrue((target / 'work/review_app.js').is_file())
            self.assertFalse((target / 'outputs').exists())
            self.assertEqual({p.name for p in (target / 'work').iterdir()},
                             {'native', 'app_paths.py', 'review_app.js'})

    def test_script_pruning_keeps_python_and_removes_broken_aliases(self):
        with tempfile.TemporaryDirectory() as name:
            runtime = Path(name)
            binary = runtime / 'bin'
            binary.mkdir()
            (binary / 'python3.12').write_bytes(b'\xcf\xfa\xed\xfe')
            (binary / 'python3').symlink_to('python3.12')
            (binary / 'pydoc3.12').write_bytes(b'#!/build/python\n')
            (binary / 'pydoc3').symlink_to('pydoc3.12')
            builder.prune_runtime_scripts(runtime)
            self.assertEqual({p.name for p in binary.iterdir()}, {'python3', 'python3.12'})
            self.assertTrue((binary / 'python3').exists())

    def test_supplemental_licenses_are_in_release_source_whitelist(self):
        files = {str(path.relative_to(ROOT)) for path in builder.source_files()}
        self.assertIn('third_party/licenses/pyobjc-12.2.2-LICENSE.txt', files)
        self.assertIn('third_party/licenses/tokenizers-0.23.3-LICENSE.txt', files)
        self.assertIn('third_party/licenses/SOURCES.md', files)

    def test_corrupt_cached_runtime_is_rejected(self):
        with tempfile.TemporaryDirectory() as name:
            cache = Path(name)
            (cache / builder.RUNTIME_NAME).write_bytes(b'not the official runtime')
            with self.assertRaisesRegex(RuntimeError, 'SHA256 mismatch'):
                builder.download_runtime(cache)

    def test_runtime_environment_disables_user_packages(self):
        from unittest.mock import patch
        with patch.dict('os.environ', {'PYTHONHOME': '/bad', 'PYTHONPATH': '/bad', 'VIRTUAL_ENV': '/bad'}):
            env = builder.runtime_environment(Path('/unused'))
        self.assertNotIn('PYTHONHOME', env)
        self.assertNotIn('PYTHONPATH', env)
        self.assertNotIn('VIRTUAL_ENV', env)
        self.assertEqual(env['PYTHONNOUSERSITE'], '1')
        self.assertEqual(env['PYTHONDONTWRITEBYTECODE'], '1')

    def test_native_source_never_uses_a_system_python(self):
        source = (ROOT / 'work/native/BrowserLauncher.swift').read_text()
        self.assertIn('runtime/bin/python3', source)
        self.assertNotIn('/usr/bin/python', source)
        self.assertIn('"--packaged"', source)
        self.assertIn('environment.removeValue(forKey: "PYTHONPATH")', source)


if __name__ == '__main__':
    unittest.main()
