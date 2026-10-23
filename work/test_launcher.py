"""Launcher integration tests use generated SVGs and never scan or delete photos."""
import importlib.util
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from http.server import BaseHTTPRequestHandler
from unittest.mock import patch
from local_http import LocalHTTPServer

ROOT = Path(__file__).resolve().parents[1]
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


class LauncherTests(unittest.TestCase):
    def test_loopback_bind_does_not_use_reverse_dns(self):
        with patch('socket.getfqdn', side_effect=AssertionError('reverse DNS must not run')):
            with LocalHTTPServer(('127.0.0.1', 0), BaseHTTPRequestHandler) as server:
                self.assertEqual(server.server_name, '127.0.0.1')
                self.assertGreater(server.server_port, 0)

    def test_loopback_transport_rejects_external_bind(self):
        with self.assertRaises(ValueError):
            LocalHTTPServer(('0.0.0.0', 0), BaseHTTPRequestHandler)

    def start(self, root, *flags, stdlib_only=False):
        port = free_port()
        args = [sys.executable, '-u'] + (['-S'] if stdlib_only else [])
        process = subprocess.Popen(args + [str(root / 'launcher.py'), '--no-browser', '--port', str(port), *flags],
                                   cwd=root, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                   bufsize=1, start_new_session=sys.platform != 'win32',
                                   env={**os.environ, 'PHOTO_REVIEW_STARTUP_DIAGNOSTICS':'1'})
        process.captured_lines = []
        def capture():
            for line in process.stdout:
                process.captured_lines.append(line)
        process.output_reader = threading.Thread(target=capture, daemon=True)
        process.output_reader.start()
        self.addCleanup(self.stop, process)
        url = f'http://127.0.0.1:{port}'
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if process.poll() is not None:
                self.fail('launcher exited before ready:\n' + self.stop(process))
            try:
                with OPENER.open(url + '/api/health', timeout=.5) as response:
                    health = json.load(response)
                return process, url, health
            except (urllib.error.URLError, OSError):
                time.sleep(.05)
        self.fail('launcher readiness timed out; captured startup diagnostics:\n' + self.stop(process))

    @staticmethod
    def stop(process):
        if hasattr(process, 'captured_output'):
            return process.captured_output
        # Kill the whole isolated test process group, including any render child.
        # Always reap it, even when graceful shutdown times out.
        try:
            if sys.platform == 'win32':
                subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True)
            else: os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                if sys.platform == 'win32': process.kill()
                else: os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait(timeout=5)
        process.output_reader.join(timeout=1)
        if process.output_reader.is_alive():
            try:
                if sys.platform == 'win32': process.kill()
                else: os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.output_reader.join(timeout=1)
        process.stdout.close()
        process.captured_output = ''.join(process.captured_lines)
        return process.captured_output

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
        fixture = next(Path(line) for line in output.splitlines() if line.replace(chr(92),'/').endswith('/index.html'))
        if sys.platform != 'win32':
            self.assertFalse(fixture.parent.exists(), 'temporary demo data must be removed on shutdown')
        else:
            shutil.rmtree(fixture.parent, ignore_errors=True)

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
