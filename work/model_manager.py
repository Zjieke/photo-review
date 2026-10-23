"""Explicit, resumable model downloads. Only pinned catalog files can be fetched."""
import hashlib
import json
import os
import shutil
import ssl
import sys
import threading
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit
from model_catalog import CATALOG, WINDOWS_CATALOG


def atomic_json(path, value):
    descriptor, temporary = tempfile.mkstemp(prefix='.' + path.name, dir=path.parent)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=False)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def read_json(path, default):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return default


class DownloadPaused(Exception):
    pass


def allowed_download_url(url):
    parts = urlsplit(url)
    host = parts.hostname or ''
    return parts.scheme == 'https' and (host == 'huggingface.co' or
            host.endswith('.huggingface.co') or host.endswith('.hf.co'))


class ModelRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        if not allowed_download_url(newurl):
            raise ValueError('模型下载地址不受支持。')
        return super().redirect_request(request, fp, code, message, headers, newurl)


def download_opener():
    try:
        import certifi
        context = ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        context = ssl.create_default_context()
    return urllib.request.build_opener(ModelRedirect(), urllib.request.HTTPSHandler(context=context))


class ModelManager:
    def __init__(self, directory, state_dir, catalog=None, opener=None):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.state_file = Path(state_dir) / 'model-settings.json'
        self.catalog = (WINDOWS_CATALOG if sys.platform == 'win32' else CATALOG) if catalog is None else catalog
        self.opener = opener
        self.lock = threading.RLock()
        self.thread = None
        self.cancel = threading.Event()
        self.active = None
        self.states = {}
        self.selected = read_json(self.state_file, {}).get('selected', '')

    def entry(self, identifier):
        if not isinstance(identifier, str) or identifier not in self.catalog:
            raise ValueError('请选择列表中的模型。')
        return self.catalog[identifier]

    def path(self, identifier):
        name = self.entry(identifier)['directory']
        if not isinstance(name, str) or Path(name).name != name or name in ('', '.', '..'):
            raise ValueError('模型目录名称无效。')
        path = self.directory / name
        if path.is_symlink() or path.resolve().parent != self.directory.resolve():
            raise ValueError('模型目录包含不支持的链接。')
        return path

    def _file(self, identifier, name):
        path = self.path(identifier) / name
        if path.is_symlink() or path.with_suffix(path.suffix + '.part').is_symlink():
            raise ValueError('模型目录包含不支持的链接。')
        if path.parent.resolve() != self.path(identifier).resolve():
            raise ValueError('模型文件路径无效。')
        return path

    def ready(self, identifier):
        entry = self.entry(identifier)
        marker = read_json(self.path(identifier) / '.verified.json', {})
        if marker.get('revision') != entry['revision']:
            return False
        return all(self._file(identifier, name).is_file() and self._file(identifier, name).stat().st_size == size
                   for name, size, _, _ in entry['files'])

    def downloaded(self, identifier):
        count = 0
        for name, size, _, _ in self.entry(identifier)['files']:
            target = self._file(identifier, name)
            part = target.with_suffix(target.suffix + '.part')
            candidate = target if target.is_file() else part
            if candidate.is_file():
                count += min(candidate.stat().st_size, size)
        return count

    def snapshot(self):
        result = []
        with self.lock:
            for identifier, entry in self.catalog.items():
                total = sum(file[1] for file in entry['files'])
                ready = self.ready(identifier)
                count = self.downloaded(identifier)
                state = dict(self.states.get(identifier, {}))
                if not state or state.get('state') not in ('downloading', 'failed'):
                    state['state'] = 'ready' if ready else 'paused' if count else 'not_installed'
                result.append({key: entry[key] for key in ('id', 'name', 'description', 'license')} |
                              {'size_bytes': total, 'total_bytes': total, 'downloaded_bytes': count,
                               'error': '', 'selected': self.selected == identifier} | state)
        return result

    def select(self, identifier):
        with self.lock:
            if not self.ready(identifier):
                raise ValueError('请先完成模型下载。')
            self.selected = identifier
            atomic_json(self.state_file, {'selected': identifier})

    def download(self, identifier):
        self.entry(identifier)
        with self.lock:
            if self.thread and self.thread.is_alive():
                if self.active == identifier:
                    return
                raise ValueError('请先暂停当前下载。')
            needed = sum(f[1] for f in self.entry(identifier)['files']) - self.downloaded(identifier)
            if shutil.disk_usage(self.directory).free < needed + 256 * 1024 * 1024:
                raise ValueError('剩余空间不足，请清理磁盘后重试。')
            self.path(identifier).mkdir(parents=True, exist_ok=True)
            self.cancel.clear()
            self.active = identifier
            self.states[identifier] = {'state': 'downloading', 'error': ''}
            self.thread = threading.Thread(target=self._run, args=(identifier,), daemon=True)
            self.thread.start()

    def pause(self, identifier):
        self.entry(identifier)
        with self.lock:
            if self.active == identifier:
                self.cancel.set()

    def close(self):
        self.cancel.set()
        if self.thread:
            self.thread.join(timeout=1)

    def _verify(self, path, size, algorithm, expected):
        if not path.is_file() or path.stat().st_size != size:
            return False
        digest = hashlib.sha256() if algorithm == 'sha256' else hashlib.sha1()
        if algorithm == 'git-sha1':
            digest.update(f'blob {size}\0'.encode())
        with path.open('rb') as stream:
            while chunk := stream.read(1024 * 1024):
                if self.cancel.is_set():
                    raise DownloadPaused()
                digest.update(chunk)
        return digest.hexdigest() == expected

    def _download_file(self, identifier, file):
        name, size, algorithm, expected = file
        target = self._file(identifier, name)
        part = target.with_suffix(target.suffix + '.part')
        if self._verify(target, size, algorithm, expected):
            return
        if target.exists():
            target.unlink()
        if self._verify(part, size, algorithm, expected):
            part.replace(target)
            return
        offset = part.stat().st_size if part.exists() else 0
        if offset >= size:
            part.unlink()
            offset = 0
        entry = self.entry(identifier)
        url = f"https://huggingface.co/{entry['repo']}/resolve/{entry['revision']}/{name}"
        request = urllib.request.Request(url, headers={'User-Agent': 'PhotoReview/0.2', 'Accept-Encoding': 'identity'})
        if offset:
            request.add_header('Range', f'bytes={offset}-')
        opener = self.opener or download_opener()
        with opener.open(request, timeout=20) as response:
            status = response.status
            if status == 206:
                expected_range = f'bytes {offset}-{size - 1}/{size}'
                if response.headers.get('Content-Range') != expected_range:
                    raise ValueError('模型服务器返回了不匹配的文件片段，请重试。')
            elif status == 200:
                offset = 0
            else:
                raise ValueError('模型服务器暂时不可用，请重试。')
            with part.open('ab' if offset else 'wb') as stream:
                received = offset
                while True:
                    if self.cancel.is_set():
                        raise DownloadPaused()
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    received += len(chunk)
                    if received > size:
                        raise ValueError('下载文件大小不匹配，请重试。')
                    stream.write(chunk)
        if received < size:
            raise ValueError('下载中断，已下载部分已保留；点击继续下载即可续传。')
        if not self._verify(part, size, algorithm, expected):
            part.unlink(missing_ok=True)
            raise ValueError('模型校验未通过，请重新下载。')
        part.replace(target)

    def _run(self, identifier):
        try:
            for file in self.entry(identifier)['files']:
                if self.cancel.is_set():
                    raise DownloadPaused()
                self._download_file(identifier, file)
            atomic_json(self.path(identifier) / '.verified.json',
                        {'revision': self.entry(identifier)['revision'], 'verified_at': time.time()})
            self.select(identifier)
            with self.lock:
                self.states[identifier] = {'state': 'ready', 'error': ''}
        except DownloadPaused:
            with self.lock:
                self.states[identifier] = {'state': 'paused', 'error': ''}
        except Exception as error:
            message = str(error) if isinstance(error, ValueError) else '下载中断，请检查网络后重试；已下载部分会保留。'
            with self.lock:
                self.states[identifier] = {'state': 'failed', 'error': message}
