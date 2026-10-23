#!/usr/bin/env python3
"""Build an isolated, relocatable macOS browser launcher; never read photo data.

Requires macOS arm64, Python 3.12+, and Xcode Command Line Tools on the BUILDER.
The resulting application contains Python and all inference dependencies.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import platform
import plistlib
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_NAME = 'cpython-3.12.15+20261021-aarch64-apple-darwin-install_only_stripped.tar.gz'
RUNTIME_URL = ('https://github.com/astral-sh/python-build-standalone/releases/download/'
               '20261021/' + RUNTIME_NAME.replace('+', '%2B'))
# Official release asset digest, independently checked before extraction.
RUNTIME_SHA256 = '7b8d00b751db21cea87dc551a8f8165147c5fbc5251d5537d7e5497dde00a219'
MACHO_MAGICS = {b'\xfe\xed\xfa\xce', b'\xce\xfa\xed\xfe', b'\xfe\xed\xfa\xcf',
                b'\xcf\xfa\xed\xfe', b'\xca\xfe\xba\xbe', b'\xbe\xba\xfe\xca'}
SOURCE_SUFFIXES = {'.py', '.js', '.css', '.html', '.swift'}


def run(args, **kwargs):
    print('+ ' + ' '.join(map(str, args)), flush=True)
    return subprocess.run(list(map(str, args)), check=True, **kwargs)


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def download_runtime(cache):
    cache.mkdir(parents=True, exist_ok=True)
    archive = cache / RUNTIME_NAME
    if not archive.exists():
        partial = archive.with_suffix(archive.suffix + '.part')
        try:
            print('Downloading official standalone CPython (25 MB)...', flush=True)
            request = urllib.request.Request(RUNTIME_URL, headers={'User-Agent': 'photo-review-builder'})
            with urllib.request.urlopen(request, timeout=60) as source, partial.open('wb') as out:
                shutil.copyfileobj(source, out, 1024 * 1024)
            if sha256(partial) != RUNTIME_SHA256:
                raise RuntimeError('CPython download SHA256 mismatch')
            partial.replace(archive)
        finally:
            partial.unlink(missing_ok=True)
    if sha256(archive) != RUNTIME_SHA256:
        raise RuntimeError('Cached CPython SHA256 mismatch; remove the cache archive and retry')
    return archive


def source_files(root=ROOT):
    """Explicit source whitelist, independent of developer Git staging/runtime files."""
    files = [root / name for name in ('launcher.py', 'LICENSE', 'README.md',
                                     'THIRD_PARTY_NOTICES.md', 'requirements.txt',
                                     'requirements-model.txt', 'requirements-bundle.txt', 'requirements-bundle-lock.txt')]
    for file in (root / 'work').iterdir():
        if file.is_file() and file.suffix in SOURCE_SUFFIXES and not file.name.startswith('test_'):
            files.append(file)
    files += [root / 'work/native/PhotosTrash.swift', root / 'scripts/build_helper.py']
    files += [file for file in (root / 'third_party/licenses').glob('*')
              if file.is_file() and file.suffix in {'.txt', '.md'}]
    return sorted(files)


def copy_project(destination, root=ROOT):
    for file in source_files(root):
        if file.is_symlink():
            raise RuntimeError(f'Refusing source symlink: {file.relative_to(root)}')
        relative = file.relative_to(root)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(file, target)
    # A source whitelist intentionally excludes outputs, models, logs, auth, and caches.


def runtime_environment(runtime):
    environment = os.environ.copy()
    for key in ('PYTHONHOME', 'PYTHONPATH', 'VIRTUAL_ENV'):
        environment.pop(key, None)
    environment.update({'PYTHONNOUSERSITE': '1', 'PYTHONDONTWRITEBYTECODE': '1',
                        'PIP_DISABLE_PIP_VERSION_CHECK': '1',
                        'PIP_NO_INPUT': '1', 'PATH': '/usr/bin:/bin:/usr/sbin:/sbin'})
    return environment


def prune_runtime_scripts(runtime):
    # App invokes `python -m ...`; pip remains importable. Remove wrappers whose
    # absolute build-time shebangs cannot survive relocation, and their aliases.
    for file in (runtime / 'bin').iterdir():
        if file.is_file() and not file.is_symlink() and not file.name.startswith('python'):
            with file.open('rb') as stream:
                is_script = stream.read(2) == b'#!'
            if is_script:
                file.unlink()
    for file in (runtime / 'bin').iterdir():
        if file.is_symlink() and not file.exists():
            file.unlink()


def macho_files(root):
    for path in sorted(root.rglob('*'), key=lambda p: len(p.parts), reverse=True):
        if path.is_symlink() or not path.is_file():
            continue
        with path.open('rb') as stream:
            if stream.read(4) in MACHO_MAGICS:
                yield path


def sign_bundle(app, identity, entitlements):
    base = ['codesign', '--force', '--sign', identity]
    if identity != '-':
        base += ['--options', 'runtime', '--timestamp']
    else:
        base += ['--timestamp=none']
    for binary in macho_files(app):
        options = ['--entitlements', entitlements] if binary.name.startswith('python3') else []
        run(base + options + [binary], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    # Sign nested app resources after their binaries, then the outer app envelope.
    for nested in sorted(app.rglob('*.app'), key=lambda p: len(p.parts), reverse=True):
        run(base + [nested])
    run(base + [app])
    run(['codesign', '--verify', '--deep', '--strict', app])


def build(args):
    if sys.platform != 'darwin' or platform.machine() != 'arm64':
        raise RuntimeError('Build on an Apple Silicon Mac; cross builds are not supported')
    if sys.version_info < (3, 12):
        raise RuntimeError('The build machine needs Python 3.12+ (users do not need Python)')
    if not shutil.which('xcrun') or not shutil.which('codesign'):
        raise RuntimeError('The build machine needs Xcode Command Line Tools')
    if args.notary_profile and args.sign_identity == '-':
        raise RuntimeError('Notarization requires a Developer ID Application signing identity')
    if not re.fullmatch(r'\d+\.\d+\.\d+(?:-[a-z0-9.-]+)?', args.version):
        raise RuntimeError('Invalid version')
    dist = args.dist_dir.resolve()
    dist.mkdir(parents=True, exist_ok=True)
    flavor = ('notarized' if args.notary_profile else 'signed-unnotarized') if args.sign_identity != '-' else 'adhoc'
    basename = f'Photo-Review-{args.version}-macOS-arm64-{flavor}'
    target_app = dist / 'Photo Review.app'
    target_zip = dist / (basename + '.zip')
    if (target_app.exists() or target_zip.exists()) and not args.replace:
        raise RuntimeError('Output already exists; use --replace to replace only this release output')
    archive = download_runtime(args.cache_dir.expanduser())
    staging = (contextlib.nullcontext(tempfile.mkdtemp(prefix='photo-review-bundle-', dir=dist))
               if args.keep_staging else tempfile.TemporaryDirectory(prefix='photo-review-bundle-', dir=dist))
    with staging as stage_name:
        stage = Path(stage_name)
        app = stage / 'Photo Review.app'
        contents = app / 'Contents'
        resources = contents / 'Resources'
        resources.mkdir(parents=True)
        with tarfile.open(archive) as source:
            source.extractall(resources, filter='data')
        (resources / 'python').rename(resources / 'runtime')
        runtime = resources / 'runtime'
        python = runtime / 'bin/python3'
        project = resources / 'project'
        copy_project(project)
        environment = runtime_environment(runtime)
        run([python, '-m', 'pip', 'install', '--no-compile', '--report', stage / 'dependencies.json',
             '-r', ROOT / 'requirements-bundle.txt'], env=environment)
        run([python, '-m', 'pip', 'check'], env=environment)
        # Import the actual shipped dependencies, without loading a model or reading Photos.
        run([python, '-c', 'import osxphotos, PIL, Vision, Quartz, mlx.core, mlx_vlm; '
             'print("Bundled dependency imports OK")'], env=environment)
        run([python, project / 'scripts/build_helper.py'], env=environment)
        executable = contents / 'MacOS/PhotoReview'
        executable.parent.mkdir(parents=True)
        run(['xcrun', 'swiftc', '-O', '-target', 'arm64-apple-macosx14.0',
             ROOT / 'work/native/BrowserLauncher.swift', '-framework', 'AppKit', '-o', executable])
        info = {
            'CFBundleName': 'Photo Review', 'CFBundleDisplayName': '照片整理器',
            'CFBundleIdentifier': 'org.photo-review.browser', 'CFBundleExecutable': 'PhotoReview',
            'CFBundlePackageType': 'APPL', 'CFBundleVersion': args.version.split('-')[0],
            'CFBundleShortVersionString': args.version.split('-')[0],
            'LSMinimumSystemVersion': '14.0', 'LSUIElement': True,
            'NSHighResolutionCapable': True,
            'NSPhotoLibraryUsageDescription': '在你主动扫描图库时读取照片，并整理本地标签与分组。',
        }
        with (contents / 'Info.plist').open('wb') as stream:
            plistlib.dump(info, stream)
        dependency_report = json.loads((stage / 'dependencies.json').read_text())
        manifest = {
            'version': args.version, 'platform': 'macOS-arm64', 'minimum_macos': '14.0',
            'python_archive': RUNTIME_NAME, 'python_sha256': RUNTIME_SHA256,
            'signing': 'Developer ID' if args.sign_identity != '-' else 'ad-hoc testing only',
            'notarized': bool(args.notary_profile),
            'model_weights_included': False,
            'supplemental_licenses': ['pyobjc-12.2.2', 'tokenizers-0.23.3'],
            'dependencies': [{'name': item['metadata']['name'], 'version': item['metadata']['version'],
                              'sha256': item['download_info']['archive_info'].get('hashes', {}).get('sha256')}
                             for item in dependency_report['install']],
        }
        (resources / 'build-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
        # Do not leave pip caches, generated bytecode, or external absolute script shebangs.
        for cache in runtime.rglob('__pycache__'):
            shutil.rmtree(cache)
        prune_runtime_scripts(runtime)
        entitlements = stage / 'runtime-entitlements.plist'
        with entitlements.open('wb') as stream:
            plistlib.dump({'com.apple.security.cs.allow-jit': True}, stream)
        sign_bundle(app, args.sign_identity, entitlements)
        staging_zip = stage / target_zip.name
        run(['ditto', '-c', '-k', '--sequesterRsrc', '--keepParent', app, staging_zip])
        if args.notary_profile:
            submission = run(['xcrun', 'notarytool', 'submit', staging_zip, '--keychain-profile',
                              args.notary_profile, '--wait', '--output-format', 'json'],
                             capture_output=True, text=True)
            receipt = json.loads(submission.stdout)
            if receipt.get('status') != 'Accepted':
                raise RuntimeError('Apple notarization did not accept this build: ' + str(receipt.get('id', 'unknown')))
            run(['xcrun', 'stapler', 'staple', app])
            run(['xcrun', 'stapler', 'validate', app])
            staging_zip.unlink()
            run(['ditto', '-c', '-k', '--sequesterRsrc', '--keepParent', app, staging_zip])
        if target_app.exists():
            shutil.rmtree(target_app)
        shutil.move(app, target_app)
        shutil.move(staging_zip, target_zip)
        digest = sha256(target_zip)
        target_zip.with_suffix('.zip.sha256').write_text(f'{digest}  {target_zip.name}\n')
        (dist / (basename + '.manifest.json')).write_text(json.dumps(manifest, indent=2) + '\n')
        print(f'Built {target_zip} ({target_zip.stat().st_size / 1_000_000:.1f} MB)', flush=True)
        if flavor == 'adhoc':
            print('Ad-hoc testing build: not Developer ID signed/notarized; Gatekeeper may block it.')
    return target_zip


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', default='0.2.0')
    parser.add_argument('--cache-dir', type=Path, default=Path.home() / 'Library/Caches/PhotoReviewBuild')
    parser.add_argument('--dist-dir', type=Path, default=ROOT / 'dist')
    parser.add_argument('--replace', action='store_true')
    parser.add_argument('--keep-staging', action='store_true', help='Keep staging for builder diagnostics')
    parser.add_argument('--sign-identity', default=os.environ.get('PHOTO_REVIEW_SIGN_IDENTITY', '-'))
    parser.add_argument('--notary-profile', default=os.environ.get('PHOTO_REVIEW_NOTARY_PROFILE'))
    args = parser.parse_args(argv)
    try:
        build(args)
        return 0
    except (RuntimeError, OSError, subprocess.CalledProcessError, tarfile.TarError) as exc:
        print(f'Release build failed: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
