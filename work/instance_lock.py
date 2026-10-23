"""One packaged backend per data directory, with identity-checked browser reuse."""
import fcntl
import json
import os
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit


class InstanceLock:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.record = self.directory / 'browser-service.json'
        descriptor = os.open(self.directory / 'browser-service.lock', os.O_CREAT | os.O_RDWR, 0o600)
        self.file = os.fdopen(descriptor, 'a+')
        self.owned = False
        try:
            fcntl.flock(self.file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.owned = True
        except BlockingIOError:
            pass

    def existing_url(self, timeout=20):
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                record = json.loads(self.record.read_text())
                url = record['url']
                parts = urlsplit(url)
                if parts.scheme != 'http' or parts.hostname != '127.0.0.1' or not parts.port or parts.path != '/':
                    raise ValueError('invalid local URL')
                with opener.open(url + 'api/health', timeout=1) as response:
                    health = json.load(response)
                if health.get('application') == 'photo-review' and health.get('instance') == record['instance']:
                    return url
            except (OSError, ValueError, KeyError):
                pass
            time.sleep(.1)
        raise RuntimeError('照片整理正在启动或退出，请稍候再打开。')

    def publish(self, url, instance):
        if not self.owned:
            raise RuntimeError('instance lock not held')
        from model_manager import atomic_json
        atomic_json(self.record, {'url': url, 'instance': instance})
        os.chmod(self.record, 0o600)

    def close(self):
        if self.owned:
            self.record.unlink(missing_ok=True)
            fcntl.flock(self.file, fcntl.LOCK_UN)
        self.file.close()
