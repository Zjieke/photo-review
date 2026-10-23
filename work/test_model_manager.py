"""Download verification with tiny synthetic bytes; no network or model runtime."""
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit

from model_manager import ModelManager, allowed_download_url, atomic_json


IDENTIFIER = 'synthetic-model'


def digest(data, algorithm):
    if algorithm == 'git-sha1':
        return hashlib.sha1(f'blob {len(data)}\0'.encode() + data).hexdigest()
    return hashlib.sha256(data).hexdigest()


def catalog(files, directory='synthetic-model'):
    return {IDENTIFIER: {
        'id': IDENTIFIER, 'name': 'Synthetic model', 'description': 'Test bytes only',
        'license': 'MIT', 'repo': 'test/synthetic-model', 'revision': 'test-revision',
        'directory': directory,
        'files': [(name, len(data), algorithm, digest(data, algorithm))
                  for name, data, algorithm in files],
    }}


class Response:
    def __init__(self, data, status=200, headers=None, chunk_size=None, first_read=None):
        self.data = data
        self.status = status
        self.headers = headers or {}
        self.chunk_size = chunk_size
        self.first_read = first_read
        self.position = 0

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, count):
        if self.chunk_size:
            count = min(count, self.chunk_size)
        chunk = self.data[self.position:self.position + count]
        self.position += len(chunk)
        if chunk and self.first_read:
            callback, self.first_read = self.first_read, None
            callback()
        return chunk


class Opener:
    def __init__(self, response):
        self.response = response
        self.requests = []

    def open(self, request, timeout):
        self.requests.append(request)
        return self.response(request)


class ModelManagerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.models = self.root / 'models'
        self.state = self.root / 'state'
        self.state.mkdir()
        self.files = [('config.json', b'{"model":"synthetic"}', 'git-sha1'),
                      ('model.safetensors', b'0123456789', 'sha256')]

    def manager(self, files=None, opener=None, directory='synthetic-model'):
        manager = ModelManager(self.models, self.state,
                               catalog=catalog(self.files if files is None else files, directory),
                               opener=opener)
        self.addCleanup(manager.close)
        return manager

    def start_and_join(self, manager):
        with patch('model_manager.shutil.disk_usage', return_value=SimpleNamespace(free=1024 ** 3)):
            manager.download(IDENTIFIER)
        manager.thread.join(timeout=3)
        self.assertFalse(manager.thread.is_alive(), 'synthetic download did not finish')

    def test_first_download_verifies_both_digest_types_and_restart_restores_ready(self):
        data = {name: content for name, content, _ in self.files}
        opener = Opener(lambda request: Response(data[Path(urlsplit(request.full_url).path).name]))
        manager = self.manager(opener=opener)
        self.assertEqual(manager.snapshot()[0]['state'], 'not_installed')
        self.start_and_join(manager)
        self.assertTrue(manager.ready(IDENTIFIER))
        self.assertEqual(manager.snapshot()[0]['state'], 'ready')
        self.assertEqual(manager.selected, IDENTIFIER)
        self.assertEqual(len(opener.requests), 2)
        for name, content in data.items():
            self.assertEqual((manager.path(IDENTIFIER) / name).read_bytes(), content)
        self.assertEqual(json.loads(manager.state_file.read_text())['selected'], IDENTIFIER)
        reopened = self.manager(opener=Opener(lambda request: self.fail('ready restart must not use network')))
        self.assertTrue(reopened.ready(IDENTIFIER))
        self.assertEqual(reopened.snapshot()[0]['state'], 'ready')
        self.assertTrue(reopened.snapshot()[0]['selected'])

    def test_range_resume_and_server_ignoring_range_both_produce_exact_file(self):
        for ignores_range in (False, True):
            with self.subTest(ignores_range=ignores_range):
                files = [('model.safetensors', b'0123456789', 'sha256')]
                opener = Opener(lambda request: Response(
                    b'0123456789' if ignores_range else b'3456789',
                    status=200 if ignores_range else 206,
                    headers={} if ignores_range else {'Content-Range': 'bytes 3-9/10'}))
                manager = self.manager(files=files, opener=opener, directory='resume-'+str(ignores_range))
                manager.path(IDENTIFIER).mkdir()
                (manager.path(IDENTIFIER) / 'model.safetensors.part').write_bytes(b'012')
                self.start_and_join(manager)
                self.assertEqual(opener.requests[0].get_header('Range'), 'bytes=3-')
                self.assertTrue(manager.ready(IDENTIFIER))
                self.assertEqual((manager.path(IDENTIFIER) / 'model.safetensors').read_bytes(), b'0123456789')

    def test_hash_mismatch_never_marks_ready_and_retry_can_complete(self):
        files = [('model.safetensors', b'0123456789', 'sha256')]
        opener = Opener(lambda request: Response(b'XXXXXXXXXX'))
        manager = self.manager(files=files, opener=opener)
        self.start_and_join(manager)
        self.assertEqual(manager.snapshot()[0]['state'], 'failed')
        self.assertFalse(manager.ready(IDENTIFIER))
        self.assertFalse((manager.path(IDENTIFIER) / '.verified.json').exists())
        self.assertFalse((manager.path(IDENTIFIER) / 'model.safetensors.part').exists())
        opener.response = lambda request: Response(b'0123456789')
        self.start_and_join(manager)
        self.assertTrue(manager.ready(IDENTIFIER))
        self.assertEqual(manager.snapshot()[0]['state'], 'ready')

    def test_pause_retains_partial_bytes_then_resumes_from_saved_offset(self):
        files = [('model.safetensors', b'0123456789', 'sha256')]
        opener = Opener(None)
        manager = self.manager(files=files, opener=opener)
        opener.response = lambda request: Response(b'0123456789', chunk_size=3,
                                                   first_read=lambda: manager.pause(IDENTIFIER))
        self.start_and_join(manager)
        part = manager.path(IDENTIFIER) / 'model.safetensors.part'
        self.assertEqual(part.read_bytes(), b'012')
        self.assertEqual(manager.snapshot()[0]['state'], 'paused')
        self.assertFalse(manager.ready(IDENTIFIER))
        opener.response = lambda request: Response(b'3456789', status=206,
                                                   headers={'Content-Range': 'bytes 3-9/10'})
        self.start_and_join(manager)
        self.assertEqual(opener.requests[-1].get_header('Range'), 'bytes=3-')
        self.assertTrue(manager.ready(IDENTIFIER))
        self.assertFalse(part.exists())

    def test_invalid_range_response_keeps_existing_partial_bytes_for_retry(self):
        files = [('model.safetensors', b'0123456789', 'sha256')]
        manager = self.manager(files=files, opener=Opener(lambda request: Response(
            b'3456789', status=206, headers={'Content-Range': 'bytes 0-9/10'})))
        manager.path(IDENTIFIER).mkdir()
        part = manager.path(IDENTIFIER) / 'model.safetensors.part'
        part.write_bytes(b'012')
        self.start_and_join(manager)
        self.assertEqual(manager.snapshot()[0]['state'], 'failed')
        self.assertFalse(manager.ready(IDENTIFIER))
        self.assertEqual(part.read_bytes(), b'012')

    def test_truncated_response_preserves_bytes_and_can_resume(self):
        files = [('model.safetensors', b'0123456789', 'sha256')]
        opener = Opener(lambda request: Response(b'012'))
        manager = self.manager(files=files, opener=opener)
        self.start_and_join(manager)
        self.assertEqual(manager.snapshot()[0]['state'], 'failed')
        part = manager.path(IDENTIFIER) / 'model.safetensors.part'
        self.assertEqual(part.read_bytes(), b'012')
        self.assertFalse(manager.ready(IDENTIFIER))
        opener.response = lambda request: Response(b'3456789', status=206,
                                                   headers={'Content-Range': 'bytes 3-9/10'})
        self.start_and_join(manager)
        self.assertEqual(opener.requests[-1].get_header('Range'), 'bytes=3-')
        self.assertTrue(manager.ready(IDENTIFIER))

    def test_atomic_json_never_follows_predictable_temporary_symlinks(self):
        target = self.state / 'model-settings.json'
        outside = self.root / 'untouched.txt'
        outside.write_text('original')
        target.with_suffix('.tmp').symlink_to(outside)
        atomic_json(target, {'selected': IDENTIFIER})
        self.assertEqual(outside.read_text(), 'original')
        self.assertEqual(json.loads(target.read_text()), {'selected': IDENTIFIER})

    def test_invalid_identifiers_are_rejected_without_starting_a_thread(self):
        manager = self.manager(opener=Opener(lambda request: self.fail('must not download')))
        for identifier in ('missing', '../outside', '', None, []):
            with self.subTest(identifier=identifier), self.assertRaises(ValueError):
                manager.download(identifier)
        self.assertIsNone(manager.thread)

    def test_model_directory_traversal_and_symlink_are_rejected(self):
        outside = self.root / 'outside'
        outside.mkdir()
        sentinel = outside / 'sentinel'
        sentinel.write_text('untouched')
        for directory in ('../outside', str(outside)):
            manager = self.manager(directory=directory)
            with self.subTest(directory=directory), self.assertRaises(ValueError):
                manager.path(IDENTIFIER)
        manager = self.manager()
        (self.models / 'synthetic-model').symlink_to(outside, target_is_directory=True)
        with self.assertRaises(ValueError):
            manager.path(IDENTIFIER)
        self.assertEqual(sentinel.read_text(), 'untouched')

    def test_file_traversal_and_file_or_partial_symlinks_are_rejected(self):
        manager = self.manager()
        manager.path(IDENTIFIER).mkdir()
        outside = self.root / 'outside'
        outside.write_bytes(b'untouched')
        for name in ('../outside', str(outside), 'nested/file'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                manager._file(IDENTIFIER, name)
        for filename in ('model.safetensors', 'model.safetensors.part'):
            link = manager.path(IDENTIFIER) / filename
            link.symlink_to(outside)
            with self.subTest(filename=filename), self.assertRaises(ValueError):
                manager._file(IDENTIFIER, 'model.safetensors')
            link.unlink()
        self.assertEqual(outside.read_bytes(), b'untouched')

    def test_untrusted_download_hosts_and_cleartext_urls_are_rejected(self):
        self.assertTrue(allowed_download_url('https://huggingface.co/test/model'))
        self.assertTrue(allowed_download_url('https://cdn-lfs.hf.co/model'))
        for url in ('http://huggingface.co/model', 'file:///tmp/model',
                    'https://huggingface.co.evil.example/model', 'https://example.com/model'):
            with self.subTest(url=url):
                self.assertFalse(allowed_download_url(url))


if __name__ == '__main__':
    unittest.main()
