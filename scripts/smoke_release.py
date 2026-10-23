#!/usr/bin/env python3
"""Launch the real .app binary with an empty isolated data directory and no browser.

Never scans Photos, downloads weights, asks for Photos authorization, or deletes photos.
The environment deliberately has no Python on PATH and no access to user Python packages.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path


def tree_fingerprints(directory):
    return {str(p.relative_to(directory)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in directory.rglob('*') if p.is_file() and not p.is_symlink()}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('app', type=Path)
    args = parser.parse_args(argv)
    app = args.app.resolve()
    executable = app / 'Contents/MacOS/PhotoReview'
    project = app / 'Contents/Resources/project'
    if sys.platform != 'darwin' or not executable.is_file():
        parser.error('Pass a built Photo Review.app on macOS')
    before = tree_fingerprints(project)
    with socket.socket() as candidate:
        candidate.bind(('127.0.0.1', 0))
        port = candidate.getsockname()[1]
    processes = []
    with tempfile.TemporaryDirectory(prefix='photo-review-release-smoke-') as temporary:
        data = Path(temporary) / 'data'
        environment = os.environ.copy()
        environment.update({'PATH': '/nonexistent', 'PHOTO_REVIEW_DATA_DIR': str(data),
                            'PHOTO_REVIEW_PORT': str(port), 'PHOTO_REVIEW_NO_BROWSER': '1',
                            'PYTHONHOME': '/nonexistent', 'PYTHONPATH': '/nonexistent',
                            'PYTHONNOUSERSITE': '1', 'PYTHONDONTWRITEBYTECODE': '1'})
        python = app / 'Contents/Resources/runtime/bin/python3'
        probe = subprocess.run([str(python), '-I', '-c',
            'import sys, osxphotos, PIL, Vision, Quartz, mlx.core, mlx_vlm; '
            'assert sys.version_info[:2] == (3, 12); print(sys.prefix)'],
            env=environment, capture_output=True, text=True, timeout=60, check=True)
        if Path(probe.stdout.strip()).resolve() != python.parent.parent.resolve():
            raise RuntimeError('Runtime probe used an interpreter outside the application')
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        address = f'http://127.0.0.1:{port}/'
        try:
            first = subprocess.Popen([str(executable)], env=environment, start_new_session=True,
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            processes.append(first)
            deadline = time.monotonic() + 60
            health = None
            while time.monotonic() < deadline:
                try:
                    with opener.open(address + 'api/health', timeout=1) as response:
                        health = json.load(response)
                    if health.get('application') == 'photo-review':
                        break
                except (OSError, ValueError, urllib.error.URLError):
                    pass
                if first.poll() is not None:
                    raise RuntimeError(f'Native launcher exited early ({first.returncode})')
                time.sleep(.2)
            else:
                raise RuntimeError('Native launcher did not serve a healthy page within 60 seconds')
            with opener.open(address, timeout=5) as response:
                html = response.read().decode('utf-8')
            if '<html' not in html.lower():
                raise RuntimeError('Browser endpoint did not return HTML')
            if any(data.rglob('full_results.json')):
                raise RuntimeError('First launch unexpectedly created a Photos scan inventory')
            second = subprocess.Popen([str(executable)], env=environment, start_new_session=True,
                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            processes.append(second)
            if second.wait(timeout=20) != 0:
                raise RuntimeError('Second launcher failed to reuse the service')
            with opener.open(address + 'api/health', timeout=5) as response:
                second_health = json.load(response)
            if second_health.get('instance') != health.get('instance'):
                raise RuntimeError('Repeated launch changed the running service identity')
            with opener.open(address + 'api/setup', timeout=5) as response:
                setup = json.load(response)
            if not setup.get('packaged') or not setup.get('platform', {}).get('model_supported'):
                raise RuntimeError('Bundled local recognition runtime was not available')
            if setup.get('library', {}).get('has_scan'):
                raise RuntimeError('Empty isolated launch unexpectedly loaded a library')
            request = urllib.request.Request(address + 'api/app/quit', data=b'{}', method='POST',
                headers={'Content-Type': 'application/json', 'Origin': address.rstrip('/'),
                         'X-Review-Token': setup['token']})
            with opener.open(request, timeout=5) as response:
                if not json.load(response).get('ok'):
                    raise RuntimeError('Page quit operation was rejected')
            if first.wait(timeout=20) != 0:
                raise RuntimeError('Page quit did not close the native launcher cleanly')
            if tree_fingerprints(project) != before:
                raise RuntimeError('Runtime modified files in the bundled project')
            print('PASS: native launcher, isolated bundled Python, empty library, repeated launch, page quit, read-only project')
        except Exception:
            logfile = data / 'logs/launcher.log'
            if logfile.exists():
                print('Isolated synthetic startup log:\n' + logfile.read_text(errors='replace')[-10000:],
                      file=sys.stderr)
            raise
        finally:
            for process in processes:
                # Each launcher owns a new process group: no unrelated app/service is touched.
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
            for process in processes:
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    process.wait(timeout=5)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
