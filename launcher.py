#!/usr/bin/env python3
"""Launch the local browser UI; scanning is always an explicit --scan operation."""
import argparse
import faulthandler
import importlib.util
import json
import os
import secrets
import signal
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from work.local_http import LocalHTTPServer

ROOT = Path(__file__).resolve().parent
WORK = ROOT / 'work'


def run_script(path, *args):
    print(f'[启动] 开始 {path.name}', flush=True)
    subprocess.run([sys.executable, str(path), *map(str, args)], cwd=ROOT, check=True)
    print(f'[启动] 完成 {path.name}', flush=True)


def require_modules(names):
    missing = [name for name in names if importlib.util.find_spec(name) is None]
    if missing:
        raise RuntimeError('缺少依赖：' + ', '.join(missing) +
                           '。请先创建虚拟环境，并运行 python -m pip install -r requirements.txt。'
                           '仅看演示可使用 --demo。')


def demo_handler(directory, instance):
    """Serve only the generated page, with no import or route to PhotoKit."""
    page = (directory / 'index.html').read_bytes()

    class DemoHandler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send(self, content, status=200, content_type='application/json; charset=utf-8'):
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(content)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            self.wfile.write(content)

        def do_GET(self):
            if self.headers.get('Host') not in {
                f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'
            }:
                return self.send(b'{"error":"Invalid host"}', 403)
            if self.path == '/api/health':
                data = {'ok': True, 'application': 'photo-review', 'mode': 'demo', 'instance': instance}
                return self.send(json.dumps(data).encode())
            if self.path in ('/', '/index.html'):
                return self.send(page, content_type='text/html; charset=utf-8')
            return self.send(b'{"error":"Not found"}', 404)

        def do_POST(self):
            return self.send(b'{"ok":false,"error":"Demo has no mutation APIs"}', 403)

    return DemoHandler


def serve(handler, port, instance, no_browser=False, instance_lock=None):
    print(f'[启动] 绑定 127.0.0.1:{port}', flush=True)
    try:
        server = LocalHTTPServer(('127.0.0.1', port), handler)
    except OSError as exc:
        if instance_lock:
            server = LocalHTTPServer(('127.0.0.1', 0), handler)
        else:
            raise RuntimeError(f'端口 {port} 无法使用；不会复用该端口上的其他服务。'
                               '请关闭占用程序，或使用 --port 8779。') from exc
    server.allowed_hosts = {'127.0.0.1', 'localhost'}
    server.daemon_threads = True
    print('[启动] 端口已绑定，启动请求线程', flush=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f'http://127.0.0.1:{server.server_port}/'
    try:
        # Check this exact instance before opening any page; never reuse an unrelated listener.
        print('[启动] 校验本机服务身份', flush=True)
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(url + 'api/health', timeout=5) as response:
            health = json.load(response)
        if health.get('application') != 'photo-review' or health.get('instance') != instance:
            raise RuntimeError('服务身份校验失败，未打开浏览器。')
        if instance_lock:
            instance_lock.publish(url, instance)
        faulthandler.cancel_dump_traceback_later()
        print(f'已就绪：{url}', flush=True)
        print('关闭终端或按 Ctrl+C 停止服务；关闭浏览器标签页不会停止服务。', flush=True)
        if not no_browser:
            webbrowser.open(url)
        while thread.is_alive():
            time.sleep(.5)
    finally:
        print('[停止] 正在关闭本机服务', flush=True)
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
        if 'review_server' in sys.modules:
            sys.modules['review_server'].close_runtime()


def main(argv=None):
    parser = argparse.ArgumentParser(description='照片整理器 · macOS 开发预览（浏览器界面）')
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument('--demo', action='store_true', help='仅标准库的合成演示，不访问照片图库')
    actions.add_argument('--scan', action='store_true', help='明确扫描本机照片图库，完成后退出')
    actions.add_argument('--build-helper', action='store_true', help='编译并临时签名 macOS 照片助手')
    parser.add_argument('--packaged', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--port', type=int, default=int(os.environ.get('PHOTO_REVIEW_PORT', '8778')), help='本机端口，默认 8778')
    parser.add_argument('--no-browser', action='store_true', help='启动后不自动打开浏览器')
    args = parser.parse_args(argv)
    args.no_browser = args.no_browser or os.environ.get('PHOTO_REVIEW_NO_BROWSER') == '1'
    if sys.version_info < (3, 11):
        parser.error('需要 Python 3.11 或更新版本。')
    if not 1 <= args.port <= 65535:
        parser.error('--port 必须在 1 至 65535 之间。')
    if os.environ.get('PHOTO_REVIEW_STARTUP_DIAGNOSTICS') == '1':
        # Opt-in diagnostics for hung CI startup; contains stacks, not library data.
        faulthandler.dump_traceback_later(10, repeat=True)
    instance_lock = None
    if args.packaged:
        os.environ.setdefault('PHOTO_REVIEW_DATA_DIR', str(Path.home() / 'Library/Application Support/Photo Review'))
        os.environ['PHOTO_REVIEW_PACKAGED'] = '1'
        os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
        os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
        sys.dont_write_bytecode = True
    sys.path.insert(0, str(WORK))
    from app_paths import OUT, DATA_ROOT, STATE_DIR, ensure_data_dirs
    try:
        if args.packaged:
            ensure_data_dirs()
            for directory in (DATA_ROOT, OUT, STATE_DIR):
                directory.chmod(0o700)
            from instance_lock import InstanceLock
            instance_lock = InstanceLock(STATE_DIR)
            if not instance_lock.owned:
                url = instance_lock.existing_url()
                if not args.no_browser:
                    webbrowser.open(url)
                print(f'已打开正在运行的照片整理：{url}', flush=True)
                return 0
        if args.build_helper:
            run_script(ROOT / 'scripts/build_helper.py')
            return 0
        if args.scan:
            if sys.platform != 'darwin':
                raise RuntimeError('真实图库扫描目前只支持 macOS。')
            require_modules(('PIL', 'osxphotos', 'Vision', 'Quartz'))
            for name in ('full_analysis.py', 'build_activity_inventory.py',
                         'find_photo_duplicates.py', 'build_multidim.py'):
                print(f'正在执行：{name}', flush=True)
                run_script(WORK / name)
            print('扫描完成。运行 python3 launcher.py 打开页面；此步骤不会删除照片。')
            return 0
        instance = secrets.token_urlsafe(24)
        if args.demo:
            with tempfile.TemporaryDirectory(prefix='photo-review-demo-') as directory:
                run_script(WORK / 'build_frontend_fixture.py', directory)
                serve(demo_handler(Path(directory), instance), args.port, instance, args.no_browser)
        else:
            if sys.platform != 'darwin':
                raise RuntimeError('当前真实图库版本只支持 macOS；可以用 --demo 查看合成演示。')
            require_modules(('PIL',))
            run_script(WORK / 'build_multidim.py')
            if not (OUT / 'full_results.json').exists():
                print('当前没有扫描记录，打开空界面。可在网页“图库与模型”中开始扫描。', flush=True)
            os.environ['PHOTO_REVIEW_INSTANCE_ID'] = instance
            sys.path.insert(0, str(WORK))
            import review_server
            serve(review_server.Handler, args.port, instance, args.no_browser, instance_lock)
        return 0
    except KeyboardInterrupt:
        print('\n服务已停止。', flush=True)
        return 0
    except (RuntimeError, subprocess.CalledProcessError, OSError) as exc:
        print(f'启动未完成：{exc}', file=sys.stderr)
        return 1
    finally:
        faulthandler.cancel_dump_traceback_later()
        if instance_lock:
            instance_lock.close()


if __name__ == '__main__':
    def stop(signum, frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, stop)
    raise SystemExit(main())
