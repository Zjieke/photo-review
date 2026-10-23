"""Private, CPU-compatible llama.cpp subprocess. Images never leave loopback."""
import atexit
import base64
import io
import json
import os
import secrets
import socket
import subprocess
import time
import urllib.request
from pathlib import Path
from app_paths import PROJECT_DIR, STATE_DIR


def runtime_path():
    return PROJECT_DIR.parent / 'engine' / 'llama-server.exe'


class GGUFModel:
    def __init__(self, path):
        path = Path(path)
        models = [file for file in path.glob('*.gguf') if not file.name.startswith('mmproj-')]
        projectors = list(path.glob('mmproj-*.gguf'))
        if len(models) != 1 or len(projectors) != 1 or not runtime_path().is_file():
            raise RuntimeError('请先在网页中下载完整模型，并使用 Windows 完整启动包。')
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
        self.url = f'http://127.0.0.1:{port}'
        self.key = secrets.token_urlsafe(32)
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        self.log = (STATE_DIR / 'model-engine.log').open('w', encoding='utf-8')
        self.process = subprocess.Popen([str(runtime_path()), '-m', str(models[0]), '--mmproj', str(projectors[0]),
            '--host', '127.0.0.1', '--port', str(port), '--api-key', self.key, '--no-webui',
            '--ctx-size', '4096', '--n-gpu-layers', '0', '--no-mmproj-offload', '--parallel', '1'],
            stdin=subprocess.DEVNULL, stdout=self.log, stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0) if os.name == 'nt' else 0)
        atexit.register(self.close)
        try:
            deadline = time.monotonic() + 180
            while time.monotonic() < deadline:
                if self.process.poll() is not None:
                    raise RuntimeError('本地模型引擎启动失败（代码 '+str(self.process.returncode)+'），请检查内存和系统兼容性。')
                try:
                    request = urllib.request.Request(self.url + '/health', headers={'Authorization': 'Bearer ' + self.key})
                    with self.opener.open(request, timeout=2) as response:
                        if json.load(response).get('status') == 'ok':
                            return
                except OSError:
                    pass
                time.sleep(.2)
            raise RuntimeError('模型加载超时，请释放内存后重试。')
        except Exception:
            self.close(); raise

    def generate(self, prompt, image, max_tokens=170):
        stream = io.BytesIO(); image.save(stream, format='JPEG', quality=85)
        data = base64.b64encode(stream.getvalue()).decode('ascii')
        body = {'messages': [{'role': 'user', 'content': [
            {'type': 'text', 'text': prompt}, {'type': 'image_url', 'image_url': {'url': 'data:image/jpeg;base64,' + data}}]}],
            'temperature': 0, 'max_tokens': max_tokens,
            'response_format': {'type': 'json_object'}}
        request = urllib.request.Request(self.url + '/v1/chat/completions', json.dumps(body).encode(),
            headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + self.key})
        with self.opener.open(request, timeout=300) as response:
            return json.load(response)['choices'][0]['message']['content']

    def close(self):
        process = getattr(self, 'process', None)
        if process and process.poll() is None:
            process.terminate()
            try: process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill(); process.wait(timeout=5)
        if getattr(self, 'log', None): self.log.close()
