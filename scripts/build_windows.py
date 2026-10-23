"""Build on Windows x64. End users need no Python, compiler, or model service."""
import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path
from build_release import copy_project, sha256
from pe_dependencies import verify_msvc

ROOT = Path(__file__).resolve().parents[1]
PYTHON_URL = ('https://github.com/astral-sh/python-build-standalone/releases/download/20261021/'
              'cpython-3.12.15%2B20261021-x86_64-pc-windows-msvc-install_only_stripped.tar.gz')
PYTHON_SHA = 'aac5d331fc3307343f95928fdbea4583f0d53973d08c7e1d081884fbd229a0e1'
ENGINE_URL = 'https://github.com/ggml-org/llama.cpp/releases/download/b11829/llama-b11829-bin-win-cpu-x64.zip'
ENGINE_SHA = 'c534f35ce9c842f3bc224fadaecc82e1b49768f63e8320922f6dbd603f66395e'


def fetch(url, expected, path):
    if not path.exists():
        urllib.request.urlretrieve(url, path)
    if sha256(path) != expected:
        path.unlink(missing_ok=True)
        raise RuntimeError('Upstream archive hash mismatch')
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', default='0.3.0-preview.2')
    args = parser.parse_args()
    if sys.platform != 'win32' or platform.machine().lower() not in ('amd64', 'x86_64'):
        raise RuntimeError('Build on Windows x64')
    dist = ROOT / 'dist'; dist.mkdir(exist_ok=True)
    cache = ROOT / 'build/windows-downloads'; cache.mkdir(parents=True, exist_ok=True)
    app = dist / 'Photo Review'
    if app.exists(): shutil.rmtree(app)
    app.mkdir()
    with tarfile.open(fetch(PYTHON_URL, PYTHON_SHA, cache / 'python.tar.gz')) as archive:
        archive.extractall(app, filter='data')
    (app / 'python').rename(app / 'runtime')
    runtime = app / 'runtime'
    python = runtime / 'python.exe'
    if not python.is_file() or not (runtime / 'pythonw.exe').is_file():
        raise RuntimeError('Unexpected standalone Python layout')
    copy_project(app / 'project')
    shutil.copy2(ROOT / 'requirements-windows.txt', app / 'project')
    (app / 'project/docs').mkdir()
    for name in ('windows.md', 'local-model.md', 'packaging.md'):
        shutil.copy2(ROOT / 'docs' / name, app / 'project/docs' / name)
    environment = {**os.environ, 'PYTHONUTF8':'1', 'PYTHONNOUSERSITE':'1', 'PYTHONDONTWRITEBYTECODE':'1'}
    for name in ('PYTHONHOME','PYTHONPATH','VIRTUAL_ENV'): environment.pop(name, None)
    subprocess.run([str(python), '-m', 'pip', 'install', '--no-compile', '--only-binary=:all:',
                    '--report', str(cache / 'dependencies.json'), '-r', str(ROOT / 'requirements-windows.txt')],
                   env=environment, check=True)
    subprocess.run([str(python), '-m', 'pip', 'check'], env=environment, check=True)
    engine = app / 'engine'; engine.mkdir()
    with zipfile.ZipFile(fetch(ENGINE_URL, ENGINE_SHA, cache / 'llama.zip')) as archive:
        for entry in archive.infolist():
            target = engine / entry.filename
            if not target.resolve().is_relative_to(engine.resolve()): raise RuntimeError('Invalid archive path')
        archive.extractall(engine)
    server = next(engine.rglob('llama-server.exe'))
    if server.parent != engine:
        for file in server.parent.iterdir(): shutil.move(str(file), str(engine / file.name))
    # These redistributable DLLs already ship with standalone Python / PyWinRT.
    # An engine subprocess cannot use a DLL merely loaded in its Python parent.
    msvc = [runtime/'vcruntime140.dll', runtime/'vcruntime140_1.dll',
            runtime/'Lib/site-packages/winrt/msvcp140.dll']
    for source in msvc:
        if not source.is_file(): raise RuntimeError('Missing bundled Microsoft runtime: '+source.name)
        for directory in (engine, runtime):
            target = directory/source.name
            if target.resolve() != source.resolve(): shutil.copy2(source,target)
    verify_msvc(app)
    # Keep all DLLs and upstream license files. The model weights are separate downloads.
    csc = Path(os.environ['WINDIR']) / 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
    subprocess.run([str(csc), '/nologo', '/target:winexe', '/platform:x64', '/utf8output',
                    '/reference:System.Windows.Forms.dll', '/out:' + str(app / 'PhotoReview.exe'),
                    str(ROOT / 'work/native/WindowsLauncher.cs')], check=True)
    report = json.loads((cache / 'dependencies.json').read_text(encoding='utf-8'))
    # Preserve the executable's own licensing/build notice and exact binary digest.
    ffmpeg = subprocess.check_output([str(python), '-c', 'import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())'],
                                    env=environment, text=True).strip()
    license_dir = app / 'project/third_party/licenses'
    license_dir.mkdir(parents=True,exist_ok=True)
    ffmpeg_notice = subprocess.run([ffmpeg,'-L'], capture_output=True,text=True,check=True)
    (license_dir/'ffmpeg-binary-notice.txt').write_text(ffmpeg_notice.stdout+ffmpeg_notice.stderr,encoding='utf-8')
    build_notice = subprocess.run([ffmpeg,'-buildconf'], capture_output=True,text=True,check=True)
    (license_dir/'ffmpeg-build-configuration.txt').write_text(build_notice.stdout+build_notice.stderr,encoding='utf-8')
    manifest = dict(version=args.version, platform='Windows-x64', minimum_windows='Windows 10 1809',
        python_sha256=PYTHON_SHA, engine='llama.cpp b11829 CPU', engine_sha256=ENGINE_SHA,
        ffmpeg_sha256=sha256(Path(ffmpeg)),
        app_local_msvc={source.name:sha256(source) for source in msvc},
        model_weights_included=False, authenticode_signed=False,
        dependencies=[{'name':item['metadata']['name'], 'version':item['metadata']['version'],
                       'sha256':item['download_info']['archive_info'].get('hashes',{}).get('sha256')}
                      for item in report['install']])
    (app / 'build-manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    name = 'Photo-Review-' + args.version + '-Windows-x64'
    (app / '使用说明.txt').write_text('完整解压后双击 PhotoReview.exe，网页将自动打开。\n'
        '在“图库与模型”选择照片文件夹并扫描，增强模型可在页面按需下载。\n'
        '用户数据保存在 %LOCALAPPDATA%\\Photo Review，更新时只替换程序文件夹。\n'
        '测试版未进行 Authenticode 签名。支持 Windows 10 1809+/11 x64。\n', encoding='utf-8')
    archive_path = Path(shutil.make_archive(str(dist / name), 'zip', dist, 'Photo Review'))
    (dist / (name + '.zip.sha256')).write_text(sha256(archive_path) + '  ' + archive_path.name + '\n')
    (dist / (name + '.manifest.json')).write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    compiler = Path(os.environ['ProgramFiles(x86)']) / 'Inno Setup 6/ISCC.exe'
    subprocess.run([str(compiler), '/DReleaseVersion=' + args.version,
                    str(ROOT / 'scripts/windows-installer.iss')], check=True)
    installer = dist / (name + '-Setup.exe')
    (dist / (installer.name + '.sha256')).write_text(sha256(installer) + '  ' + installer.name + '\n')
    print(archive_path, archive_path.stat().st_size, sha256(archive_path), flush=True)
    print(installer, installer.stat().st_size, sha256(installer), flush=True)


if __name__ == '__main__': main()
