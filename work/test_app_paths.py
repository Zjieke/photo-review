"""Runtime-path tests do not open Photos or import a model runtime."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


class AppPathsTests(unittest.TestCase):
    def inspect_paths(self, source, environment, ensure=False):
        code = "import app_paths,json; "
        if ensure:
            code += "app_paths.ensure_data_dirs(); "
        code += ("print(json.dumps({name:str(getattr(app_paths,name)) "
                 "for name in ('CODE_DIR','PROJECT_DIR','DATA_ROOT','OUT','STATE_DIR','MODELS_DIR')}))")
        result = subprocess.run([sys.executable, '-B', '-c', code], cwd=source,
                                env=environment, capture_output=True, text=True, check=True)
        return json.loads(result.stdout)

    def test_default_paths_keep_development_layout_without_import_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            work = root / 'work'
            work.mkdir()
            shutil.copyfile(Path(__file__).with_name('app_paths.py'), work / 'app_paths.py')
            environment = dict(os.environ)
            environment.pop('PHOTO_REVIEW_DATA_DIR', None)
            paths = self.inspect_paths(work, environment)
            self.assertEqual(paths['CODE_DIR'], str(work))
            self.assertEqual(paths['DATA_ROOT'], str(root))
            self.assertEqual(paths['OUT'], str(root / 'outputs'))
            self.assertFalse((root / 'outputs').exists())
            self.assertEqual({p.name for p in work.iterdir()}, {'app_paths.py'})

    def test_explicit_runtime_root_is_separate_and_created_only_on_request(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            work = root / 'bundle' / 'work'
            work.mkdir(parents=True)
            shutil.copyfile(Path(__file__).with_name('app_paths.py'), work / 'app_paths.py')
            data = root / 'Application Support' / 'Photo Review'
            environment = dict(os.environ, PHOTO_REVIEW_DATA_DIR=str(data))
            paths = self.inspect_paths(work, environment)
            self.assertFalse(data.exists())
            self.assertEqual(paths['CODE_DIR'], str(work))
            self.assertEqual(paths['PROJECT_DIR'], str(work.parent))
            self.assertEqual(paths['DATA_ROOT'], str(data))
            self.assertEqual(paths['STATE_DIR'], str(data / 'work'))
            self.assertEqual(paths['MODELS_DIR'], str(data / 'work' / 'models'))
            self.inspect_paths(work, environment, ensure=True)
            self.assertTrue((data / 'outputs').is_dir())
            self.assertTrue((data / 'work' / 'models').is_dir())
            self.assertFalse((work.parent / 'outputs').exists())


if __name__ == '__main__':
    unittest.main()
