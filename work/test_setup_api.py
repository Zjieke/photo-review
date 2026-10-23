"""Setup mutations never run from an untrusted origin or a mere status read."""
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import Mock, patch
import review_server as service
from instance_lock import InstanceLock


class SetupApiTests(unittest.TestCase):
    def setUp(self):
        self.jobs = Mock()
        self.jobs.snapshot.return_value = {'ok': True, 'library': {'has_scan': False}, 'models': []}
        self.jobs.platform_status.return_value = {'model_supported': True}
        self.patch = patch.object(service, 'runtime', return_value=self.jobs)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.server = service.ThreadingHTTPServer(('127.0.0.1', 0), service.Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.close)
        self.origin = f'http://127.0.0.1:{self.server.server_port}'
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)

    def request(self, path, body=None, headers=None):
        base = {'Content-Type': 'application/json', 'Origin': self.origin, 'X-Review-Token': service.TOKEN}
        base.update(headers or {})
        request = urllib.request.Request(self.origin + path, headers=base,
            data=json.dumps(body).encode() if body is not None else None)
        with self.opener.open(request, timeout=3) as response:
            return json.load(response)

    def test_status_read_is_passive_and_uses_no_photo_helper(self):
        with patch.object(service, 'native', side_effect=AssertionError('no Photos for setup')):
            state = self.request('/api/setup')
        self.assertEqual(state['token'], service.TOKEN)
        self.jobs.start_scan.assert_not_called()
        self.jobs.models.download.assert_not_called()

    def test_every_task_route_rejects_wrong_origin_and_token_before_actions(self):
        routes = ['/api/library/scan', '/api/library/folder', '/api/tasks/stop', '/api/models/download',
                  '/api/models/pause', '/api/models/select', '/api/recognition/start', '/api/app/quit']
        for route in routes:
            for headers in ({'Origin': 'https://example.invalid'}, {'X-Review-Token': 'invalid'}):
                with self.subTest(route=route, headers=headers):
                    with self.assertRaises(urllib.error.HTTPError) as error:
                        self.request(route, {}, headers)
                    self.assertEqual(error.exception.code, 403)
                    error.exception.close()
        self.assertFalse(self.jobs.mock_calls)

    def test_explicit_actions_route_without_running_real_jobs(self):
        self.assertTrue(self.request('/api/library/scan', {})['ok'])
        self.jobs.start_scan.assert_called_once_with()
        self.assertTrue(self.request('/api/models/download', {'id': 'qwen35-4b'})['ok'])
        self.jobs.models.download.assert_called_once_with('qwen35-4b')
        self.assertTrue(self.request('/api/recognition/start', {'id': 'qwen35-4b'})['ok'])
        self.jobs.start_recognition.assert_called_once_with('qwen35-4b')
        self.assertTrue(self.request('/api/tasks/stop', {})['ok'])
        self.jobs.stop.assert_called_once_with()


class InstanceTests(unittest.TestCase):
    def test_second_launch_cannot_take_lock_or_erase_owner_record(self):
        with tempfile.TemporaryDirectory() as directory:
            first = InstanceLock(directory)
            second = InstanceLock(directory)
            try:
                self.assertTrue(first.owned)
                self.assertFalse(second.owned)
                first.publish('http://127.0.0.1:9001/', 'test-instance')
                second.close()
                self.assertTrue(first.record.exists())
            finally:
                first.close()
            self.assertFalse((Path(directory) / 'browser-service.json').exists())
            again = InstanceLock(directory)
            self.assertTrue(again.owned)
            again.close()

    def test_reuse_requires_matching_health_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            owner = InstanceLock(directory)
            owner.publish('http://127.0.0.1:9001/', 'right-instance')
            other = InstanceLock(directory)
            try:
                response = Mock()
                response.__enter__ = Mock(return_value=response)
                response.__exit__ = Mock(return_value=False)
                response.read.return_value = b'{"application":"photo-review","instance":"wrong-instance"}'
                opener = Mock()
                opener.open.return_value = response
                with patch('instance_lock.urllib.request.build_opener', return_value=opener):
                    with self.assertRaises(RuntimeError):
                        other.existing_url(timeout=.01)
                    response.read.return_value = b'{"application":"photo-review","instance":"right-instance"}'
                    self.assertEqual(other.existing_url(timeout=1), 'http://127.0.0.1:9001/')
            finally:
                other.close()
                owner.close()


if __name__ == '__main__':
    unittest.main()
