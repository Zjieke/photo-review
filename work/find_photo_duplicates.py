"""Read-only local image grouping. Exact means original-byte SHA256 equality."""
import collections,hashlib,json,math,sqlite3,time
from pathlib import Path
from PIL import Image,ImageStat,ImageOps
from app_paths import DATA_ROOT as ROOT, STATE_DIR as WORK, OUT, ensure_data_dirs
def atomic(path,data):
 tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(data,ensure_ascii=False));tmp.replace(path)
def fingerprint(path):
 s=path.stat();return [s.st_size,s.st_mtime_ns,s.st_ino]
def digest(path):
 before=fingerprint(path);h=hashlib.sha256()
 with path.open('rb') as source:
  while chunk:=source.read(1024*1024):h.update(chunk)
 if fingerprint(path)!=before:raise ValueError('file changed')
 return h.hexdigest()
def visual(path):
 with Image.open(path) as source:
  im=ImageOps.exif_transpose(source).convert('RGB');w,h=im.size
  gray=im.convert('L');st=ImageStat.Stat(gray)
  if st.stddev[0]<12:return None
  pixels=list(gray.resize((9,8)).getdata());d=0
  for y in range(8):
   for x in range(8):d=(d<<1)|int(pixels[y*9+x]>pixels[y*9+x+1])
  pixels=list(gray.resize((8,8)).getdata());mean=sum(pixels)/64;a=0
  for value in pixels:a=(a<<1)|int(value>mean)
  if min(d.bit_count(),64-d.bit_count())<7:return None
  colors=list(im.resize((2,2)).getdata());color=[v for pixel in colors for v in pixel]
  return {'d':d,'a':a,'ratio':w/h,'color':color,'w':w,'h':h}
def near(a,b):
 return abs(math.log(a['ratio']/b['ratio']))<.035 and (a['d']^b['d']).bit_count()<=5 and (a['a']^b['a']).bit_count()<=6 and sum(abs(x-y) for x,y in zip(a['color'],b['color']))/12<=18
class Tree:
 def __init__(self):self.root=None
 def add(self,value,identifier):
  if self.root is None:self.root=[value,[identifier],{}];return
  node=self.root
  while True:
   dist=(value^node[0]).bit_count()
   if dist==0:node[1].append(identifier);return
   if dist not in node[2]:node[2][dist]=[value,[identifier],{}];return
   node=node[2][dist]
 def search(self,value,radius=5):
  if self.root is None:return []
  stack=[self.root];result=[]
  while stack:
   node=stack.pop();dist=(value^node[0]).bit_count()
   if dist<=radius:result.extend(node[1])
   stack.extend(child for edge,child in node[2].items() if dist-radius<=edge<=dist+radius)
  return result

def run():
 ensure_data_dirs(OUT.parent)
 sources=json.loads((OUT/'full_results.json').read_text()) if (OUT/'full_results.json').exists() else []
 inventory=json.loads((WORK/'activity_inventory.json').read_text())['items'] if (WORK/'activity_inventory.json').exists() else []
 metadata={r['uuid']:r for r in inventory}
 deleted={u for p in (OUT/'delete-receipts').glob('*.json') for receipt in [json.loads(p.read_text())] if receipt.get('state')=='done' for u in receipt.get('ids',[])}
 records=[r for r in sources if not r.get('hidden') and r['uuid'] not in deleted];cache_path=WORK/'duplicate_hash_cache.json';cache=json.loads(cache_path.read_text()) if cache_path.exists() else {};hashes={};exact_buckets=collections.defaultdict(list);originals={};skipped=0
 progress=OUT/'duplicate_scan_progress.json'
 for index,row in enumerate(records):
  u=row['uuid'];entry=cache.setdefault(u,{})
  preview=OUT/row['thumbnail']
  try:
   sig=fingerprint(preview)
   if entry.get('preview_sig')!=sig:entry.update(preview_sig=sig,visual=visual(preview))
   if entry.get('visual'):hashes[u]=entry['visual']
  except (OSError,ValueError):skipped+=1
  original=Path(row.get('original') or '__missing__')
  try:
   if original.is_file():
    sig=fingerprint(original);originals[u]=(original,sig);exact_buckets[sig[0]].append(u)
  except OSError:pass
  if index%200==0:atomic(progress,{'phase':'fingerprints','processed':index,'total':len(records),'updated_at':time.time()})
 exact=collections.defaultdict(list);failures=0
 for size,members in exact_buckets.items():
  if len(members)<2:continue
  for u in members:
   original,sig=originals[u];entry=cache[u]
   try:
    if entry.get('original_sig')!=sig or not entry.get('sha256'):entry.update(original_sig=sig,sha256=digest(original))
    exact[entry['sha256']].append(u)
   except (OSError,ValueError):failures+=1
 exact_groups=[members for members in exact.values() if len(members)>1];exact_members={u for g in exact_groups for u in g}
 # Anchor groups avoid transitive chains that can merge different scenes.
 tree=Tree();similar=[];group_for={};by_id={r['uuid']:r for r in records}
 for u,v in hashes.items():
  if u in exact_members:continue
  candidates=tree.search(v['d']);anchor=next((a for a in candidates if near(v,hashes[a])),None)
  if anchor is None:tree.add(v['d'],u)
  else:
   if anchor not in group_for:group_for[anchor]=len(similar);similar.append([anchor])
   similar[group_for[anchor]].append(u)
 def group(kind,members):
  ordered=sorted(members,key=lambda u:(not by_id[u].get('favorite',False),-(metadata.get(u,{}).get('bytes') or 0),by_id[u]['date']))
  items=[]
  for u in ordered:
   row=by_id[u];m=metadata.get(u,{})
   items.append({k:row.get(k) for k in ('uuid','filename','date','thumbnail','favorite')}|{'bytes':m.get('bytes'),'preview_width':hashes.get(u,{}).get('w'),'preview_height':hashes.get(u,{}).get('h')})
  return {'id':kind+'-'+hashlib.sha256('|'.join(sorted(members)).encode()).hexdigest()[:12],'kind':kind,'items':items,'bytes':sum(r['bytes'] or 0 for r in items),'suggested_keep':ordered[0]}
 groups=[group('exact',m) for m in exact_groups]+[group('similar',m) for m in similar]
 groups.sort(key=lambda g:g['bytes'],reverse=True)
 payload={'updated_at':time.time(),'total':len(records),'fingerprinted':len(hashes),'original_available':len(originals),'preview_failed':skipped,'hash_failed':failures,'groups':groups,'method':'SHA256原文件逐字节校验；相似候选为预览dHash+aHash+画面色块与宽高比，保守分组，不代表同一内容或最佳照片'}
 atomic(cache_path,cache);atomic(OUT/'duplicate_groups.json',payload);atomic(progress,{'phase':'completed','processed':len(records),'total':len(records),'exact':len(exact_groups),'similar':len(similar),'updated_at':time.time()});print(json.dumps({k:v for k,v in payload.items() if k!='groups'},ensure_ascii=False));print('groups',len(exact_groups),len(similar))
if __name__=='__main__':run()
