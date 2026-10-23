"""User-started scan and recognition jobs, shared by the browser and bundled app."""
import importlib.util
import os
import platform
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from app_paths import CODE_DIR, DATA_ROOT, OUT, STATE_DIR, MODELS_DIR, ensure_data_dirs
from model_manager import ModelManager, atomic_json, read_json


def model_runtime_available():
    try:
        return importlib.util.find_spec('mlx_vlm') is not None and importlib.util.find_spec('mlx') is not None
    except (ImportError, ValueError):
        return False


class RuntimeJobs:
    def __init__(self, on_scan=None, data_root=None, code_dir=None, models=None):
        self.root = Path(data_root or DATA_ROOT)
        self.code = Path(code_dir or CODE_DIR)
        self.out = self.root / 'outputs'
        self.state_dir = self.root / 'work'
        ensure_data_dirs(self.root)
        self.models = models or ModelManager(self.state_dir / 'models', self.state_dir)
        self.on_scan = on_scan or (lambda: None)
        self.lock = threading.RLock()
        self.process = None
        self.thread = None
        self.cancel = threading.Event()
        self.state_file = self.state_dir / 'background-job.json'
        self.state = read_json(self.state_file, {'kind': None, 'state': 'idle', 'message': ''})
        if self.state.get('state') in ('running', 'stopping'):
            self.state.update(state='paused', message='上次任务已停止，可以继续；已保存的结果会保留。')

    def platform_status(self):
        supported = sys.platform == 'darwin'
        model_supported = supported and platform.machine() == 'arm64' and model_runtime_available()
        message = '' if model_supported else ('增强识别需要 Apple Silicon Mac 的完整安装包。' if supported
                                             else '当前图库功能需要 macOS；其他系统可查看合成演示。')
        return {'supported': supported, 'model_supported': model_supported, 'message': message}

    def snapshot(self):
        analysis = read_json(self.out / 'analysis_progress.json', {})
        inventory = self.out / 'full_results.json'
        with self.lock:
            job = dict(self.state)
        if job.get('kind') == 'scan' and job.get('stage') == 'full_analysis.py':
            job['progress'] = {'processed': analysis.get('processed', 0), 'total': analysis.get('photos', 0)}
        elif job.get('kind') == 'recognize':
            progress = read_json(self.out / 'local_model_progress.json', {})
            job['progress'] = {'processed': progress.get('processed', 0), 'total': progress.get('total', 0)}
        else:
            job.setdefault('progress', {})
        return {'ok': True, 'packaged': os.environ.get('PHOTO_REVIEW_PACKAGED') == '1',
                'platform': self.platform_status(),
                'library': {'has_scan': inventory.exists(), 'photos': analysis.get('photos', 0),
                            'videos': analysis.get('videos', 0)},
                'job': job, 'models': self.models.snapshot(),
                'library_revision': inventory.stat().st_mtime_ns if inventory.exists() else 0}

    def _state(self, **changes):
        with self.lock:
            self.state.update(changes, updated_at=time.time())
            atomic_json(self.state_file, self.state)

    def _start(self, kind, model_id=None):
        with self.lock:
            if self.thread and self.thread.is_alive():
                raise ValueError('已有任务正在进行，请先暂停。')
            self.cancel.clear()
            self.state = {'kind': kind, 'state': 'running', 'message': '正在准备…', 'progress': {}}
            self._state(model_id=model_id, stage='')
            self.thread = threading.Thread(target=self._run, args=(kind, model_id), daemon=True)
            self.thread.start()

    def start_scan(self):
        if not self.platform_status()['supported']:
            raise ValueError('图库扫描目前只支持 macOS。')
        self._start('scan')

    def start_recognition(self, identifier):
        if not self.platform_status()['model_supported']:
            raise ValueError('请使用 Apple Silicon Mac 的完整安装包进行增强识别。')
        if not (self.out / 'full_results.json').exists():
            raise ValueError('请先扫描图库。')
        if not self.models.ready(identifier):
            raise ValueError('请先完成模型下载。')
        self.models.select(identifier)
        self._start('recognize', identifier)

    def stop(self):
        with self.lock:
            if not self.thread or not self.thread.is_alive():
                return
            self.cancel.set()
            self._state(state='stopping', message='正在保存进度，当前图片处理完后暂停…')
            process = self.process
            if process and process.poll() is None:
                try:
                    if self.state['kind'] == 'recognize':
                        process.terminate()
                    else:
                        os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass

    def close(self):
        self.models.close()
        self.stop()
        if self.thread:
            self.thread.join(timeout=120)
        with self.lock:
            process = self.process
            if process and process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=5)

    def _run(self, kind, identifier):
        stages = [('full_analysis.py', '正在读取图库并进行基础识别…'),
                  ('build_activity_inventory.py', '正在整理照片与视频活动…'),
                  ('find_photo_duplicates.py', '正在查找重复与相似图片…'),
                  ('build_multidim.py', '正在生成整理结果…')] if kind == 'scan' else [
                      ('qwen_local_labeler.py', '正在本机增强识别…')]
        environment = {**os.environ, 'PHOTO_REVIEW_DATA_DIR': str(self.root),
                       'PYTHONUNBUFFERED': '1', 'PYTHONDONTWRITEBYTECODE': '1'}
        if identifier:
            environment['PHOTO_REVIEW_MODEL_PATH'] = str(self.models.path(identifier))
        try:
            with (self.state_dir / 'background-job.log').open('w') as log:
                for script, message in stages:
                    with self.lock:
                        if self.cancel.is_set():
                            break
                        self._state(stage=script, message=message)
                        self.process = subprocess.Popen([sys.executable, str(self.code / script)],
                            cwd=self.root, env=environment, stdout=log, stderr=subprocess.STDOUT,
                            start_new_session=True)
                        process = self.process
                    while process.poll() is None:
                        if self.cancel.wait(.2) and kind == 'scan':
                            try:
                                process.wait(timeout=5)
                            except subprocess.TimeoutExpired:
                                os.killpg(process.pid, signal.SIGKILL)
                                process.wait(timeout=5)
                        elif self.cancel.is_set():
                            time.sleep(.2)
                    if self.cancel.is_set():
                        break
                    if process.returncode:
                        raise RuntimeError('job failed')
            if self.cancel.is_set():
                self._state(state='paused', message='已暂停，已保存的结果会在继续时复用。')
            else:
                if kind == 'scan':
                    self.on_scan()
                self._state(state='completed', message='图库整理完成，点击查看结果。' if kind == 'scan' else '本地增强识别完成。')
        except Exception:
            message = ('扫描未完成。请检查“系统设置 → 隐私与安全性”中的照片及文件访问权限后重试。'
                       if kind == 'scan' else '增强识别未完成。请确认内存充足、模型已下载完整后重试；已有标签会保留。')
            self._state(state='failed', message=message)
        finally:
            with self.lock:
                self.process = None
