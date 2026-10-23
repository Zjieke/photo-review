import collections,json,fcntl
from pathlib import Path
from multidim import DIMENSIONS,infer
from app_paths import CODE_DIR, DATA_ROOT as ROOT, OUT, STATE_DIR as WORK, ensure_data_dirs
ensure_data_dirs(ROOT)
def read_json(path,default):
 return json.loads(path.read_text()) if path.exists() else default
def atomic(path,text):
 tmp=path.with_suffix('.tmp');tmp.write_text(text);tmp.replace(path)
_build_lock=(WORK/'multidim-build.lock').open('a');fcntl.flock(_build_lock,fcntl.LOCK_EX)
source=read_json(OUT/'full_results.json',[])
manual=json.loads((WORK/'vlm_results.json').read_text()) if (WORK/'vlm_results.json').exists() else {}
auto=json.loads((WORK/'local_visual_results.json').read_text()) if (WORK/'local_visual_results.json').exists() else {}
qwen=json.loads((WORK/'qwen_visual_results.json').read_text()) if (WORK/'qwen_visual_results.json').exists() else {}
for result in qwen.values():
 for value in result.get('content',[]):
  if value not in DIMENSIONS['content'][1]:DIMENSIONS['content'][1].append(value)
vlm=auto|qwen|manual
source_ids={r['uuid'] for r in source}
sample={r['uuid']:r for r in read_json(WORK/'trial_sample.json',[]) if r['uuid'] in source_ids}
trial_order={u:i for i,u in enumerate(sample)}
legacy={r['uuid']:r for r in read_json(OUT/'多标签清单.json',{'items':[]}).get('items',[])}
# Visual similarity is a review aid, never an automatic duplicate/deletion decision.
from PIL import Image
hashes={};clusters={};parent={u:u for u in sample}
def find(u):
 while parent[u]!=u:parent[u]=parent[parent[u]];u=parent[u]
 return u
def union(a,b):parent[find(a)]=find(b)
for u,r in sample.items():
 with Image.open(OUT/r['thumbnail']) as im:
  ratio=im.width/im.height;gray=im.convert('L').resize((9,8));px=list(gray.getdata());h=0
  for y in range(8):
   for x in range(8):h=(h<<1)|int(px[y*9+x]>px[y*9+x+1])
  # Near-uniform images have uninformative hashes; skip them.
  if min(h.bit_count(),64-h.bit_count())>=8:hashes[u]=(h,ratio)
ids=list(hashes)
for i,a in enumerate(ids):
 for b in ids[i+1:]:
  ha,ra=hashes[a];hb,rb=hashes[b]
  if abs(ra-rb)<.03 and (ha^hb).bit_count()<=5:union(a,b)
for u in ids:clusters.setdefault(find(u),[]).append(u)
groups={};group_count=0
for members in clusters.values():
 if len(members)>1:
  group_count+=1
  for u in members:groups[u]=dict(id=f'S{group_count:02}',count=len(members),members=members)
items=[]
for row in source:
 row['preview_for_dimensions']=str(OUT/row['thumbnail'])
 dim,evidence=infer(row,vlm.get(row['uuid']))
 group=groups.get(row['uuid'])
 if group:dim['quality'].append('疑似相似图片')
 tags=list(dict.fromkeys(t for vs in dim.values() for t in vs))
 base=legacy.get(row['uuid'],{})|{k:row[k] for k in ['uuid','number','date','filename','thumbnail','source','hidden','favorite','analysis_status']}|dict(deletable=not(row['favorite'] or row['hidden']))
 caution=sorted(set(tags)&{'订单详情','支付转账','账单发票','体检病历','证件信息','含重要资料'})
 items.append({k:base[k] for k in ['uuid','number','date','filename','thumbnail','source','hidden','favorite','deletable','analysis_status']}|dict(search_text=row.get('ocr',''),tags=tags,dimensions=dim,evidence=evidence,caution=caution,trial=row['uuid'] in sample,trialOrder=trial_order.get(row['uuid'],99999),vlm=vlm.get(row['uuid']),similarity=group,legacy_tags=base.get('legacy_tags',base.get('tags',[]))))
payload=dict(items=items,counts=dict(collections.Counter(t for r in items for t in r['tags'])),vocabulary=list(dict.fromkeys(t for _,vs in DIMENSIONS.values() for t in vs)),dimensions=[dict(key=k,title=name,values=vs) for k,(name,vs) in DIMENSIONS.items()],scope='full',total=len(items),analysis=read_json(OUT/'analysis_progress.json',dict(photos=len(source),videos=0,completed=sum(r.get('analysis_status')=='complete' for r in source),failed=sum(r.get('analysis_status')=='failed' for r in source),unavailable=sum(r.get('analysis_status')=='unavailable' for r in source),processed=len(source),pending=0)),cautionTags=['订单详情','支付转账','账单发票','体检病历','证件信息','含重要资料','已收藏','已隐藏'],trial=dict(total=len(sample),complete=sum(vlm.get(u,{}).get('status')=='complete' for u in sample),failed=sum(vlm.get(u,{}).get('status')=='failed' for u in sample),similar_groups=group_count),fullVisual=dict(qwen=sum(r['uuid'] in qwen for r in source),unresolved_topics=sum(r['dimensions']['topic']==['主题待确认'] for r in items),unresolved_content=sum(r['dimensions']['content']==['内容待确认'] for r in items),total=len(items),completed=sum(vlm.get(r['uuid'],{}).get('status')=='complete' for r in source),failed=sum(vlm.get(r['uuid'],{}).get('status')=='failed' for r in source),local=sum(auto.get(r['uuid'],{}).get('status')=='complete' for r in source if r['uuid'] not in manual),manual=sum(r['uuid'] in manual for r in source),similarity=sum(auto.get(r['uuid'],{}).get('reference_used',False) for r in source)),method='本机 Apple Vision 画面分类与 OCR；可选本地视觉模型增强标签，删除由用户勾选确认')
atomic(OUT/'多标签清单.json',json.dumps(payload,ensure_ascii=False,indent=2))
template=(CODE_DIR/'review_template.html').read_text()
embedded=json.dumps(payload,ensure_ascii=False).replace('<','\\u003c')
app=(CODE_DIR/'review_app.js').read_text().replace('/*__DATA__*/',embedded).replace('/*__DELETION_UI__*/',(CODE_DIR/'deletion_ui.js').read_text()).replace('/*__REVIEW_MOTION__*/',(CODE_DIR/'review_motion.js').read_text())
html=template.replace('/*__REVIEW_APP__*/',app).replace('/*__REVIEW_STYLE__*/',(CODE_DIR/'review_style.css').read_text())
activity=json.loads((WORK/'activity_inventory.json').read_text()) if (WORK/'activity_inventory.json').exists() else {'items':[]}
activity_ui=(CODE_DIR/'activity_ui.js').read_text()
html=html.replace('/*__ACTIVITY_DATA__*/',json.dumps(activity,ensure_ascii=False).replace('<','\\u003c'))
html=html.replace('/*__ACTIVITY_STYLE__*/',(CODE_DIR/'activity_style.css').read_text()).replace('/*__ACTIVITY_SECTION__*/',(CODE_DIR/'activity_section.html').read_text()).replace('/*__ACTIVITY_UI__*/',activity_ui)
duplicates=json.loads((OUT/'duplicate_groups.json').read_text()) if (OUT/'duplicate_groups.json').exists() else {'groups':[]}
duplicate_ui=(CODE_DIR/'duplicate_ui.js').read_text().replace('/*__DUPLICATE_DATA__*/',json.dumps(duplicates,ensure_ascii=False).replace('<','\\u003c'))
html=html.replace('/*__DUPLICATE_SECTION__*/',(CODE_DIR/'duplicate_section.html').read_text()).replace('/*__DUPLICATE_UI__*/',duplicate_ui)
for marker,filename in [('SETUP_SECTION','setup_section.html'),('SETUP_STYLE','setup_style.css'),('SETUP_UI','setup_ui.js')]:
 html=html.replace('/*__'+marker+'__*/',(CODE_DIR/filename).read_text())
assert '/*__' not in html,'Unresolved template marker'
atomic(OUT/'截图多标签审阅.html',html)
(OUT/'多维标签试跑.json').write_text(json.dumps(dict(trial=payload['trial'],items=[r for r in items if r['trial']]),ensure_ascii=False,indent=2))
print(json.dumps(payload['trial'],ensure_ascii=False))
