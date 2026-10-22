"""Loopback review server; only explicit, authenticated selection requests can trash assets."""
import re
import mimetypes
import base64
import os
import json
import secrets
import subprocess
import threading
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit, parse_qs

ROOT = Path(__file__).resolve().parent
OUT = ROOT.parent / 'outputs'
HELPER = ROOT / 'native/截图清理助手.app/Contents/MacOS/PhotosTrash'
ORIGIN = 'http://127.0.0.1:8778'
INSTANCE_ID = os.environ.get('PHOTO_REVIEW_INSTANCE_ID', secrets.token_urlsafe(24))
TOKEN = secrets.token_urlsafe(32)
PASSWORD_FILE=ROOT/'lan-access-password.txt'
if not PASSWORD_FILE.exists():
    fd=os.open(PASSWORD_FILE,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as f:f.write(secrets.token_urlsafe(12))
LAN_PASSWORD=PASSWORD_FILE.read_text().strip()
LOCK = threading.Lock()

def allowed_asset_ids(label_items, activity_items):
    """Merge analyzed photos and activity media, with protection winning conflicts."""
    candidates=set()
    protected=set()
    for items,is_activity in ((label_items,False),(activity_items,True)):
        for item in items:
            uuid=item.get('uuid')
            if not isinstance(uuid,str) or not uuid:continue
            if item.get('favorite',False) or item.get('hidden',False) or item.get('deletable') is False:
                protected.add(uuid)
            if not is_activity or item.get('kind') in ('photo','video'):
                candidates.add(uuid)
    return candidates-protected

def read_json(path, default):
    return json.loads(path.read_text()) if path.exists() else default

ACTIVITY_INVENTORY=ROOT/'activity_inventory.json'
ALLOWED = allowed_asset_ids(
    read_json(OUT/'多标签清单.json', {'items':[]}).get('items',[]),
    read_json(ACTIVITY_INVENTORY, {}).get('items',[]))
VIDEO_PREVIEW_LOCK=threading.Lock()
ACTIVITY_MEDIA=json.loads((ROOT/'activity_media_paths.json').read_text()) if (ROOT/'activity_media_paths.json').exists() else {}
JOURNAL = OUT/'delete-receipts'
JOURNAL.mkdir(parents=True,exist_ok=True)

def native(action, ids=None):
    if not HELPER.is_file():
        if action=='status':
            return {'ok':True,'authorization':'helper_missing','error':'尚未构建照片助手。请运行 python3 launcher.py --build-helper。'}
        raise RuntimeError('请先运行 python3 launcher.py --build-helper 构建照片助手。')
    with tempfile.TemporaryDirectory(prefix='photo-review-') as tmp:
        request_path = Path(tmp)/'request.json'
        response_path = Path(tmp)/'response.json'
        request_path.write_text(json.dumps({'action':action, 'uuids':ids}))
        result = subprocess.run(['/usr/bin/open','-n','-W','-a',str(HELPER.parents[2]),'--args',str(request_path),str(response_path)],
                                text=True, capture_output=True, timeout=180)
        if result.returncode or not response_path.exists():
            raise RuntimeError('照片助手未能完成操作。请检查系统照片权限。')
        return json.loads(response_path.read_text())

def validate_ids(ids):
    if not isinstance(ids,list) or not ids or len(ids)>120 or any(not isinstance(i,str) for i in ids):
        raise ValueError('每批可删除 1–120 项媒体，请分批提交。')
    if len(set(ids))!=len(ids) or not set(ids)<=ALLOWED:
        raise ValueError('清单含重复、受保护或不属于当前图库清单的媒体。')
    return sorted(ids)

def receipts():
    return [json.loads(p.read_text()) for p in JOURNAL.glob('*.json')]

def write_receipt(path,data):
    tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(data,ensure_ascii=False));tmp.replace(path)

def trash(request, adapter=native):
    ids=validate_ids(request.get('uuids'))
    key=request.get('requestId','')
    if not isinstance(key,str) or len(key)!=36 or any(c not in '0123456789abcdef-' for c in key):
        raise ValueError('请求编号无效。')
    if request.get('confirmed') is not True: raise ValueError('请先确认删除。')
    path=JOURNAL/(key+'.json')
    with LOCK:
        if path.exists():
            old=json.loads(path.read_text())
            if old['ids']!=ids: raise ValueError('请求编号与媒体清单不一致。')
            return old.get('result',{'ok':False,'uncertain':True,'error':'此请求状态待核对，请勿重复提交。'})
        blocked=set()
        for r in receipts():
            if r['state'] in ('pending','uncertain','done'): blocked.update(r['ids'])
        if blocked.intersection(ids): raise ValueError('部分媒体已经处理或操作结果尚未确定，请刷新页面。')
        check=adapter('check',ids)
        if not check.get('ok'): return check
        record={'ids':ids,'state':'pending'}
        write_receipt(path,record)
        try:
            result=adapter('trash',ids)
            if result.get('ok') and set(result.get('deleted',[]))!=set(ids):
                result={'ok':False,'uncertain':True,'error':'返回的删除清单不匹配，请到照片应用核对。'}
        except Exception:
            result={'ok':False,'uncertain':True,'error':'未收到确定结果，请到照片应用核对，勿重复删除。'}
        record.update(state='done' if result.get('ok') else 'uncertain' if result.get('uncertain') else 'failed',result=result)
        write_receipt(path,record)
        return result

def media_range(header,size):
    if not header:return 0,size-1,200
    match=re.fullmatch(r'bytes=(\d*)-(\d*)',header)
    if not match or not any(match.groups()):raise ValueError('Invalid range')
    a,b=match.groups()
    if not a:
        count=int(b)
        if count<=0:raise ValueError('Invalid range')
        start=max(0,size-count);end=size-1
    else:start=int(a);end=min(int(b),size-1) if b else size-1
    if start>=size or end<start:raise ValueError('Invalid range')
    return start,end,206

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def reply(self,data,status=200):
        body=json.dumps(data,ensure_ascii=False).encode();self.send_response(status)
        self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Cache-Control','no-store')
        self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
    def host_ok(self):
        hosts=getattr(self.server,'allowed_hosts',{'127.0.0.1','localhost'})
        return self.headers.get('Host') in {f'{h}:{self.server.server_port}' for h in hosts}
    def authenticated(self):
        if self.client_address[0]=='127.0.0.1':return True
        expected='Basic '+base64.b64encode(('photos:'+LAN_PASSWORD).encode()).decode()
        if secrets.compare_digest(self.headers.get('Authorization',''),expected):return True
        body='请输入照片访问用户名和密码。'.encode()
        self.send_response(401);self.send_header('WWW-Authenticate','Basic realm="Photo Review", charset="UTF-8"')
        self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
        return False
    def activity_media(self,uuid,compatible=False):
        item=ACTIVITY_MEDIA.get(uuid)
        if not item or item.get('kind')!='video':return self.reply({'error':'Not found'},404)
        if any(uuid in r['ids'] for r in receipts() if r['state']=='done'):return self.reply({'error':'Not found'},404)
        target=Path(item['path'])
        if not target.is_file():return self.reply({'error':'原视频不在本机'},404)
        if compatible:
            directory=ROOT/'video-previews';directory.mkdir(exist_ok=True)
            cached=directory/(uuid+'.mp4')
            with VIDEO_PREVIEW_LOCK:
                if not cached.exists() or cached.stat().st_mtime<target.stat().st_mtime:
                    tmp=directory/(uuid+'.pending.mp4')
                    try:
                        result=subprocess.run(['/usr/bin/avconvert','--source',str(target),'--preset','Preset1280x720','--output',str(tmp),'--replace'],capture_output=True,timeout=180)
                        if result.returncode or not tmp.exists():raise RuntimeError('conversion failed')
                        tmp.replace(cached)
                    except Exception:
                        tmp.unlink(missing_ok=True)
                        return self.reply({'error':'无法准备兼容预览，请在照片应用观看'},503)
            target=cached
        size=target.stat().st_size
        try:start,end,status=media_range(self.headers.get('Range'),size)
        except ValueError:
            self.send_response(416);self.send_header('Content-Range',f'bytes */{size}');self.send_header('Content-Length','0');self.end_headers();return
        self.send_response(status);self.send_header('Content-Type',mimetypes.guess_type(target.name)[0] or 'video/quicktime')
        self.send_header('Accept-Ranges','bytes');self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Content-Length',str(end-start+1))
        if status==206:self.send_header('Content-Range',f'bytes {start}-{end}/{size}')
        self.end_headers()
        try:
            with target.open('rb') as f:
                f.seek(start);remaining=end-start+1
                while remaining>0:
                    chunk=f.read(min(1024*1024,remaining))
                    if not chunk:break
                    self.wfile.write(chunk);remaining-=len(chunk)
        except (BrokenPipeError,ConnectionResetError):pass
    def do_GET(self):
        if not self.host_ok(): return self.reply({'error':'Invalid host'},403)
        if not self.authenticated():return
        path=unquote(urlsplit(self.path).path)
        if path=='/api/health':
            return self.reply({'ok':True,'application':'photo-review','mode':'library','instance':INSTANCE_ID})
        if path.startswith('/api/activity-preview/'):
            return self.activity_media(path.removeprefix('/api/activity-preview/'),compatible=True)
        if path.startswith('/api/activity-media/'):
            return self.activity_media(path.removeprefix('/api/activity-media/'))
        if path=='/api/local-model-progress':
            p=OUT/'local_model_progress.json'
            return self.reply(json.loads(p.read_text()) if p.exists() else {'phase':'not_started'})
        if path=='/api/local-model-updates':
            p=OUT/'local_model_updates.json'
            if not p.exists(): return self.reply({'items':[]})
            data=json.loads(p.read_text())
            try: after=float(parse_qs(urlsplit(self.path).query).get('after',['0'])[0])
            except ValueError: after=0
            if data.get('updated_at',0)<=after:return self.reply({'items':[]})
            return self.reply(data)
        if path=='/api/status':
            try:
                status=native('status');status['token']=TOKEN
                status['deleted']=[i for r in receipts() if r['state']=='done' for i in r['ids']]
                return self.reply(status)
            except Exception as e: return self.reply({'ok':False,'error':str(e)},503)
        if path=='/': path='/截图多标签审阅.html'
        target=(OUT/path.lstrip('/')).resolve()
        if not target.is_relative_to(OUT.resolve()) or not (path=='/截图多标签审阅.html' or path.startswith('/previews/') and target.suffix=='.jpg') or not target.is_file():
            return self.reply({'error':'Not found'},404)
        data=target.read_bytes();self.send_response(200)
        self.send_header('Content-Type','text/html; charset=utf-8' if target.suffix=='.html' else 'image/jpeg')
        self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
    def do_POST(self):
        if not self.host_ok() or self.headers.get('Origin')!='http://'+self.headers.get('Host','') or not secrets.compare_digest(self.headers.get('X-Review-Token',''),TOKEN):
            return self.reply({'ok':False,'error':'请求来源校验失败，请刷新页面。'},403)
        if not self.authenticated():return
        try:
            length=int(self.headers.get('Content-Length','0'))
            if length<=0 or length>32000 or self.headers.get('Content-Type')!='application/json': raise ValueError('请求格式无效。')
            data=json.loads(self.rfile.read(length))
            if not isinstance(data,dict): raise ValueError('请求格式无效。')
            if self.path=='/api/authorize': result=native('authorize')
            elif self.path=='/api/trash': result=trash(data)
            else: return self.reply({'ok':False,'error':'Not found'},404)
            self.reply(result)
        except ValueError as e: self.reply({'ok':False,'error':str(e)},400)
        except Exception: self.reply({'ok':False,'error':'助手未完成请求，请检查照片访问权限后刷新页面。'},503)

if __name__=='__main__':
    from serve import main
    main()
