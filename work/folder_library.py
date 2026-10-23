"""Explicitly selected local folders; never crawl a drive or download placeholders."""
import json
import os
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from app_paths import PROJECT_DIR, STATE_DIR
from model_manager import atomic_json, read_json

PICTURES = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tif', '.tiff', '.heic', '.heif', '.avif'}
VIDEOS = {'.mp4', '.mov', '.m4v', '.avi', '.mkv', '.webm', '.mts'}


def selected_folder(state=STATE_DIR):
    value = read_json(Path(state) / 'folder-library.json', {}).get('folder')
    return Path(value) if value else None


def save_folder(folder, state=STATE_DIR):
    folder = Path(folder).resolve(strict=True)
    if not folder.is_dir() or folder == Path(folder.anchor) or Path(state).resolve().is_relative_to(folder):
        raise ValueError('请选择存放照片的文件夹，不能选择整个磁盘或程序数据目录。')
    atomic_json(Path(state) / 'folder-library.json', {'folder': str(folder)})
    return folder


def pick_folder():
    if sys.platform != 'win32':
        raise ValueError('当前系统不使用文件夹模式。')
    helper = PROJECT_DIR.parent / 'PhotoReview.exe'
    if not helper.is_file():
        raise ValueError('请选择 Windows 完整启动包。')
    with tempfile.TemporaryDirectory(prefix='photo-review-picker-') as tmp:
        result = Path(tmp) / 'selection.json'
        subprocess.run([str(helper), '--pick-folder', str(result)], check=True, timeout=600)
        selection = json.loads(result.read_text(encoding='utf-8-sig')) if result.exists() else {}
    return save_folder(selection['folder']) if selection.get('folder') else None


def local_regular(path, root):
    """Reject symlinks, junctions, changed targets and online-only cloud files."""
    path, root = Path(path), Path(root).resolve()
    try:
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            return False
        for parent in (path, *path.parents):
            if parent.resolve() == root:
                break
            if parent.is_symlink() or getattr(parent, 'is_junction', lambda: False)():
                return False
        info = path.stat()
        attributes = getattr(info, 'st_file_attributes', 0)
        return stat.S_ISREG(info.st_mode) and not attributes & (0x1000 | 0x40000 | 0x400000)
    except OSError:
        return False


def media_files(root):
    root = Path(root).resolve()
    for current, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = sorted(name for name in dirs if not name.startswith('.') and
                         not (Path(current) / name).is_symlink() and
                         not getattr(Path(current) / name, 'is_junction', lambda: False)())
        for name in sorted(files):
            path = Path(current) / name
            if path.suffix.lower() in PICTURES | VIDEOS:
                yield path, local_regular(path, root)


def signature(path):
    info = path.stat()
    return [info.st_size, info.st_mtime_ns, info.st_ino]


def native(action, ids=None, state=STATE_DIR, recycler=None):
    """Delete only unchanged, scanned files under their recorded selected root."""
    if action in ('status', 'authorize'):
        return {'ok': True, 'authorization': 'authorized', 'trash_label': '回收站', 'source': 'folder'}
    records = read_json(Path(state) / 'folder-file-index.json', {})
    paths = []
    for identifier in ids or []:
        item = records.get(identifier, {})
        path, root = Path(item.get('path', '')), Path(item.get('root', ''))
        if not item or not local_regular(path, root) or signature(path) != item.get('signature'):
            return {'ok': False, 'error': '部分文件已变化、已移走或不在本机，请重新扫描后再试。'}
        paths.append(path)
    if action == 'check':
        return {'ok': True}
    if action != 'trash' or not paths:
        raise ValueError('操作无效。')
    if recycler is None:
        from send2trash import send2trash
        recycler = send2trash
    # Recycle Bin is the only deletion mechanism. Never fall back to unlink.
    recycler([str(path) for path in paths])
    return {'ok': True, 'deleted': list(ids)}
