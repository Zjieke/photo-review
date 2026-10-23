"""Resumable folder inventory, thumbnails, Windows OCR and activity metadata."""
import datetime
import json
import os
import sqlite3
import subprocess
import time
import uuid
from pathlib import Path
from PIL import Image, ImageOps
from app_paths import OUT, STATE_DIR, ensure_data_dirs
from folder_library import PICTURES, VIDEOS, media_files, selected_folder, signature
from model_manager import atomic_json


def video_thumbnail(path, target):
    import imageio_ffmpeg
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), '-v', 'error', '-nostdin', '-i', str(path),
                    '-frames:v', '1', '-vf', 'scale=960:960:force_original_aspect_ratio=decrease',
                    '-y', str(target)], timeout=45, check=True, capture_output=True,
                   creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0) if os.name == 'nt' else 0)


def scan(root=None, output=OUT, state=STATE_DIR, ocr=None):
    root = Path(root or selected_folder(state) or '')
    if not root.is_dir() or not selected_folder(state):
        raise ValueError('请先在网页中选择照片文件夹。')
    root = root.resolve()
    output, state = Path(output), Path(state)
    ensure_data_dirs(output.parent)
    previews = output / 'previews'; previews.mkdir(exist_ok=True)
    try:
        import pillow_heif
        pillow_heif.register_heif_opener()
    except ImportError:
        pass
    if ocr is None:
        from windows_ocr import recognize
        ocr = recognize
    entries = list(media_files(root))
    old = json.loads((output / 'full_results.json').read_text(encoding='utf-8')) if (output / 'full_results.json').exists() else []
    numbers = {row['uuid']: row['number'] for row in old}
    next_number = max(numbers.values(), default=0) + 1
    rows, inventory, media, index = [], [], {}, {}
    skipped, failed, text_read = 0, 0, 0
    start = time.time()
    with sqlite3.connect(state / 'folder-analysis.sqlite3') as cache:
        cache.execute('CREATE TABLE IF NOT EXISTS results(uuid TEXT PRIMARY KEY, fingerprint TEXT, data TEXT)')
        for position, (path, available) in enumerate(entries, 1):
            if not available:
                skipped += 1
                continue
            identifier = str(uuid.uuid5(uuid.NAMESPACE_URL, os.path.normcase(str(path))))
            fingerprint = signature(path)
            date = datetime.datetime.fromtimestamp(path.stat().st_mtime).astimezone().isoformat()
            video = path.suffix.lower() in VIDEOS
            screenshot = any(word in path.stem.lower() for word in ('screenshot', 'screen shot', '截图', '截屏'))
            thumbnail = 'previews/' + identifier + '.jpg'
            base = dict(uuid=identifier, filename=path.name, date=date, favorite=False, hidden=False,
                        screenshot=screenshot, original=str(path), preview=str(path), source='original')
            existing = cache.execute('SELECT fingerprint,data FROM results WHERE uuid=?', (identifier,)).fetchone()
            if existing and existing[0] == json.dumps(fingerprint) and (output / thumbnail).is_file():
                row = json.loads(existing[1])
            else:
                row = dict(base, thumbnail='', ocr='', visual=[], analysis_status='complete', ocr_status='not_applicable')
                try:
                    if video:
                        video_thumbnail(path, output / thumbnail)
                    else:
                        with Image.open(path) as im:
                            exif_date = im.getexif().get(36867) or im.getexif().get(306)
                            if exif_date:
                                try: row['date'] = datetime.datetime.strptime(str(exif_date)[:19], '%Y:%m:%d %H:%M:%S').astimezone().isoformat()
                                except ValueError: pass
                            im = ImageOps.exif_transpose(im).convert('RGB')
                            im.thumbnail((1400, 1400)); im.save(output / thumbnail, quality=80)
                        row['ocr'], row['ocr_status'] = ocr(output / thumbnail)
                    row['thumbnail'] = thumbnail
                except Exception:
                    row['analysis_status'] = 'failed'; failed += 1
                cache.execute('INSERT OR REPLACE INTO results VALUES(?,?,?)',
                              (identifier, json.dumps(fingerprint), json.dumps(row, ensure_ascii=False)))
                cache.commit()
            if row.get('ocr_status') == 'complete': text_read += 1
            if not video:
                if identifier not in numbers:
                    numbers[identifier] = next_number; next_number += 1
                row['number'] = numbers[identifier]; rows.append(row)
            inventory.append(dict(uuid=identifier, filename=path.name, date=row['date'], day=row['date'][:10],
                kind='video' if video else 'photo', screenshot=screenshot, favorite=False, hidden=False,
                deletable=True, bytes=fingerprint[0], local_bytes=fingerprint[0], thumbnail=row['thumbnail'], available=True))
            media[identifier] = {'path': str(path), 'kind': 'video' if video else 'photo'}
            index[identifier] = {'path': str(path), 'root': str(root), 'signature': fingerprint}
            atomic_json(output / 'analysis_progress.json', dict(photos=len(rows), videos=sum(x['kind']=='video' for x in inventory),
                processed=position, total=len(entries), completed=len(rows), skipped=skipped, failed=failed,
                ocr_completed=text_read, elapsed_seconds=round(time.time()-start)))
    atomic_json(output / 'full_results.json', rows)
    atomic_json(output / 'full_inventory.json', rows)
    atomic_json(output / 'videos_not_analyzed.json', [x for x in inventory if x['kind']=='video'])
    atomic_json(state / 'activity_inventory.json', {'updated_at':time.time(),
                'size_basis':'本机原文件大小；时间优先采用照片 EXIF，缺失时使用文件修改时间。', 'items': inventory})
    atomic_json(state / 'activity_media_paths.json', media)
    atomic_json(state / 'folder-file-index.json', index)
    atomic_json(output / 'analysis_progress.json', dict(photos=len(rows), videos=sum(x['kind']=='video' for x in inventory),
        processed=len(entries), total=len(entries), completed=len(rows), skipped=skipped, failed=failed, ocr_completed=text_read))


if __name__ == '__main__':
    scan()
