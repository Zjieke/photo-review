"""Real Windows executable acceptance with synthetic media, never a user library."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
import zipfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('zip')
    parser.add_argument('--inference', action='store_true')
    args = parser.parse_args()
    temporary = Path(tempfile.mkdtemp(prefix='照片 整理 Windows '))
    process = None
    try:
        with zipfile.ZipFile(args.zip) as archive: archive.extractall(temporary)
        app = temporary / 'Photo Review'
        installer = Path(args.zip).with_name(Path(args.zip).stem + '-Setup.exe').resolve()
        installed = temporary / '安装 路径'
        subprocess.run([str(installer), '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART',
                        '/DIR=' + str(installed), '/LOG=' + str(temporary/'installer.log')], check=True, timeout=180)
        assert (installed/'PhotoReview.exe').is_file() and (installed/'runtime/pythonw.exe').is_file()
        # Test the actual installed files, in a Chinese path, after a real installer run.
        app = installed
        data = temporary / '用户 数据'; data.mkdir()
        photos = temporary / '测试 照片'; photos.mkdir()
        environment = {**os.environ, 'PHOTO_REVIEW_DATA_DIR':str(data), 'PHOTO_REVIEW_NO_BROWSER':'1',
                       'PYTHONHOME':str(temporary / 'invalid-python'), 'PYTHONPATH':str(temporary / 'invalid-modules'),
                       'PATH':str(temporary / 'no-system-python'), 'PYTHONUTF8':'1'}
        process = subprocess.Popen([str(app / 'PhotoReview.exe')], env=environment)
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        record = data / 'work/browser-service.json'
        deadline = time.monotonic() + 60
        while not record.exists() and time.monotonic() < deadline:
            if process.poll() is not None: raise RuntimeError('Native launcher exited: ' + (data / 'logs/launcher.log').read_text(encoding='utf-8'))
            time.sleep(.1)
        service = json.loads(record.read_text(encoding='utf-8')); url = service['url'].rstrip('/')
        def get(route):
            with opener.open(url + route, timeout=20) as response: return json.load(response)
        state = get('/api/setup'); token = state['token']
        def post(route, body=None):
            request = urllib.request.Request(url + route, json.dumps(body or {}).encode(), headers={
                'Origin':url, 'Content-Type':'application/json', 'X-Review-Token':token})
            with opener.open(request, timeout=30) as response: return json.load(response)
        def wait_job():
            deadline = time.monotonic() + 1200
            while time.monotonic() < deadline:
                snapshot = get('/api/setup')
                if snapshot['job']['state'] not in ('running','stopping'):
                    assert snapshot['job']['state'] == 'completed', snapshot['job']
                    return snapshot
                time.sleep(1)
            raise RuntimeError('Synthetic job timed out')
        assert state['packaged'] and state['platform']['folder_mode'] and state['platform']['model_supported']
        assert not state['library']['has_scan'] and state['models'][0]['state'] == 'not_installed'
        with opener.open(url + '/', timeout=20) as response:
            assert '选择照片文件夹' in response.read().decode('utf-8')
        again = subprocess.run([str(app / 'PhotoReview.exe')], env=environment, timeout=60)
        assert again.returncode == 0
        assert json.loads(record.read_text(encoding='utf-8')) == service
        # Fixtures are drawn by bundled Python; it also tests the actual WinRT OCR APIs.
        clean = {**environment}; clean.pop('PYTHONHOME'); clean.pop('PYTHONPATH')
        script = temporary / 'fixture.py'
        script.write_text('''import asyncio,sys,json
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from PIL import Image,ImageDraw,ImageFont
from folder_library import save_folder
from windows_ocr import _read
import subprocess,imageio_ffmpeg
folder,state=Path(sys.argv[2]),Path(sys.argv[3])
image=Image.new('RGB',(1000,650),'white');draw=ImageDraw.Draw(image)
font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',62)
draw.text((70,65),'PHOTO REVIEW 2026',font=font,fill='black')
draw.rectangle((230,300,600,600),fill='burlywood');draw.polygon([(180,300),(420,140),(650,300)],fill='red')
image.save(folder/'sample.png')
subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-v','error','-f','lavfi','-i','color=c=blue:s=320x240:d=1',
                '-c:v','libx264','-pix_fmt','yuv420p','-y',str(folder/'clip.mp4')],check=True)
text,status=asyncio.run(_read(folder/'sample.png'))
assert status=='complete' and 'PHOTO' in text.upper(),(text,status)
print('Native Windows OCR:',text)
save_folder(folder,state)
''', encoding='utf-8')
        subprocess.run([str(app/'runtime/python.exe'),'-X','utf8',str(script),str(app/'project/work'),str(photos),str(data/'work')],
                       env=clean, check=True, timeout=120)
        post('/api/library/scan'); scanned = wait_job()
        assert scanned['library']['photos'] == 1 and scanned['library']['videos'] == 1 and scanned['library']['ocr_completed'] == 1, scanned
        rows = json.loads((data/'outputs/full_results.json').read_text(encoding='utf-8')); identifier=rows[0]['uuid']
        assert rows[0]['thumbnail'] and (data/'outputs'/rows[0]['thumbnail']).exists()
        assert (data/'work/activity_inventory.json').exists() and (data/'outputs/duplicate_groups.json').exists()
        activity=json.loads((data/'work/activity_inventory.json').read_text(encoding='utf-8'))['items']
        video=next(item for item in activity if item['kind']=='video')
        assert video['thumbnail'] and video['bytes']>0
        with opener.open(url+'/api/activity-preview/'+video['uuid'],timeout=120) as response:
            assert response.status==200 and response.headers.get('Content-Type')=='video/mp4' and response.read(16)
        if args.inference:
            model = get('/api/setup')['models'][0]
            post('/api/models/download', {'id':model['id']})
            deadline = time.monotonic()+1200
            while time.monotonic()<deadline:
                current = get('/api/setup')['models'][0]
                if current['state']=='ready': break
                if current['state']=='failed': raise RuntimeError(current['error'])
                time.sleep(3)
            else: raise RuntimeError('Model download timed out')
            post('/api/recognition/start', {'id':model['id']}); wait_job()
            result=json.loads((data/'work/qwen_visual_results.json').read_text(encoding='utf-8'))
            assert result[identifier]['status']=='complete' and result[identifier]['content'],result
            print('Actual CPU image recognition:',result[identifier]['topic'],result[identifier]['content'], flush=True)
            # The second run must reuse cache, retaining the successful result exactly.
            before=(data/'work/qwen_visual_results.json').read_bytes()
            post('/api/recognition/start',{'id':model['id']});wait_job()
            assert (data/'work/qwen_visual_results.json').read_bytes()==before
        # Only a synthetic fixture is recycled, never a user file or a permanent unlink.
        status=get('/api/status'); assert status['trash_label']=='回收站'
        import uuid
        ids=[identifier,video['uuid']]
        deleted=post('/api/trash',{'requestId':str(uuid.uuid4()),'uuids':ids,'confirmed':True})
        assert set(deleted['deleted'])==set(ids) and not (photos/'sample.png').exists() and not (photos/'clip.mp4').exists()
        post('/api/app/quit'); assert process.wait(timeout=150)==0
        assert not record.exists()
        print('PASS: native Windows launch, isolated Python, OCR, folder scan, activities, duplicates, '
              'optional model download/inference/cache, synthetic Recycle Bin deletion, reuse and exit', flush=True)
    finally:
        if process and process.poll() is None:
            subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],capture_output=True)
            process.wait(timeout=30)
        installed = temporary / '安装 路径'
        if (installed/'unins000.exe').is_file():
            cache_existed=(temporary/'用户 数据/work/folder-analysis.sqlite3').exists()
            subprocess.run([str(installed/'unins000.exe'), '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART'],
                           timeout=120, check=True)
            if cache_existed:
                assert (temporary/'用户 数据/work/folder-analysis.sqlite3').exists(), 'Uninstall must preserve user data'
        if os.environ.get('PHOTO_REVIEW_KEEP_SMOKE')=='1':
            print('Synthetic diagnostics retained:',temporary)
        else: shutil.rmtree(temporary,ignore_errors=True)


if __name__ == '__main__': main()
