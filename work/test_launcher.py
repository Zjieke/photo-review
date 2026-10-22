"""Launcher integration tests use generated SVGs and never scan or delete photos."""
import importlib.util
import json
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


class LauncherTests(unittest.TestCase):
    def start(self, root, *flags, stdlib_only=False):
        port = free_port()
        args = [sys.executable] + (['-S'] if stdlib_only else [])
        process = subprocess.Popen(args + [str(root / 'launcher.py'), '--no-browser', '--port', str(port), *flags],
                                   cwd=root, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        self.addCleanup(self.stop, process)
        url = f'http://127.0.0.1:{port}'
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if process.poll() is not None:
                self.fail('launcher exited before ready: ' + process.stdout.read())
            try:
                with OPENER.open(url + '/api/health', timeout=.5) as response:
                    health = json.load(response)
                return process, url, health
            except (urllib.error.URLError, OSError):
                time.sleep(.05)
        self.fail('launcher readiness timed out')

    @staticmethod
    def stop(process):
        if process.poll() is None:
            process.terminate()
        output, _ = process.communicate(timeout=5)
        return output

    def test_demo_requires_only_stdlib_and_exposes_no_photo_api(self):
        process, url, health = self.start(ROOT, '--demo', stdlib_only=True)
        self.assertEqual(health['mode'], 'demo')
        with OPENER.open(url, timeout=3) as response:
            html = response.read().decode()
        self.assertIn('合成', html)
        for path, method, headers, expected in (
            ('/api/status', 'GET', {}, 404),
            ('/api/trash', 'POST', {}, 403),
            ('/api/authorize', 'POST', {}, 403),
            ('/launcher.py', 'GET', {}, 404),
            ('/', 'GET', {'Host':'attacker.invalid'}, 403),
        ):
            request = urllib.request.Request(url + path, method=method,
                                             data=b'{}' if method=='POST' else None, headers=headers)
            with self.assertRaises(urllib.error.HTTPError) as error:
                OPENER.open(request, timeout=3)
            self.assertEqual(error.exception.code, expected)
            error.exception.close()
        output = self.stop(process)
        fixture = next(Path(line) for line in output.splitlines() if line.endswith('/index.html'))
        self.assertFalse(fixture.parent.exists(), 'temporary demo data must be removed on shutdown')

    def test_port_conflict_does_not_reuse_other_service(self):
        with socket.socket() as occupied:
            occupied.bind(('127.0.0.1', 0))
            occupied.listen()
            port = occupied.getsockname()[1]
            result = subprocess.run([sys.executable, '-S', str(ROOT / 'launcher.py'), '--demo',
                                     '--no-browser', '--port', str(port)], capture_output=True,
                                    text=True, timeout=15, cwd=ROOT)
        self.assertEqual(result.returncode, 1)
        self.assertIn('不会复用', result.stdout + result.stderr)
        self.assertNotIn('已就绪', result.stdout)

    @unittest.skipUnless(sys.platform == 'darwin' and importlib.util.find_spec('PIL'), 'macOS and Pillow required')
    def test_empty_checkout_opens_without_scanning(self):
        with tempfile.TemporaryDirectory(prefix='photo-review-empty-test-') as directory:
            root = Path(directory)
            (root / 'work').mkdir()
            shutil.copy2(ROOT / 'launcher.py', root / 'launcher.py')
            for path in (ROOT / 'work').iterdir():
                if path.is_file() and path.suffix in {'.py', '.js', '.html', '.css'}:
                    shutil.copy2(path, root / 'work' / path.name)
            process, url, health = self.start(root)
            self.assertEqual(health['mode'], 'library')
            with OPENER.open(url, timeout=3) as response:
                self.assertEqual(response.status, 200)
            self.assertFalse((root / 'outputs/full_inventory.json').exists())
            self.assertFalse((root / 'outputs/full_results.json').exists())
            with OPENER.open(url + '/api/status', timeout=3) as response:
                status = json.load(response)
            self.assertEqual(status['authorization'], 'helper_missing')
            self.assertIn('token', status)
            self.stop(process)


if __name__ == '__main__':
    unittest.main()
