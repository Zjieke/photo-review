"""Render the real frontend with synthetic records only, without any Photos or API access.
Run: python3 work/build_frontend_fixture.py [output-directory]
Serve the output directory on a separate localhost port for isolated browser storage.
"""
import base64,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
DEST=Path(sys.argv[1]) if len(sys.argv)>1 else Path('/tmp/photo-review-ui-fixture')
DEST.mkdir(parents=True,exist_ok=True)
def encode(value):return json.dumps(value,ensure_ascii=False).replace('<','\\u003c')
def preview(index):
    palettes=[('#dbe8df','#8fae9a','#4f7963'),('#ece4d5','#c4a982','#8b7153'),('#dce5e9','#90a6b3','#58788b'),('#e8dfeb','#b69bc0','#816e91')]
    bg,mid,dark=palettes[index%len(palettes)]
    svg=f'<svg xmlns="http://www.w3.org/2000/svg" width="600" height="450" viewBox="0 0 600 450"><rect width="600" height="450" fill="{bg}"/><circle cx="450" cy="105" r="50" fill="white" opacity=".65"/><path d="M0 310 170 140 350 330 450 200 600 350V450H0Z" fill="{mid}"/><path d="M0 380 220 260 440 380 600 290V450H0Z" fill="{dark}"/><rect x="24" y="24" width="115" height="30" rx="15" fill="white" opacity=".85"/><text x="81" y="44" text-anchor="middle" font-family="sans-serif" font-size="13" fill="{dark}">DEMO {index+1:03}</text></svg>'
    return 'data:image/svg+xml;base64,'+base64.b64encode(svg.encode()).decode()
dimensions=[{'key':'type','title':'图片类型','values':['照片','截屏']},{'key':'topic','title':'主题场景','values':['旅行风景','演唱会','购物商品','美食','未分类']},{'key':'content','title':'画面内容','values':['山川湖泊','舞台现场','商品详情','餐饮记录','订单详情']},{'key':'quality','title':'整理提示','values':['疑似相似图片','清晰画面']},{'key':'source','title':'识别方式','values':['本机基础识别','本地视觉模型']}]
items=[]
for i in range(96):
    scene=i%4;topic=dimensions[1]['values'][scene];content=dimensions[2]['values'][scene]
    tags=['截屏' if scene==2 else '照片',topic,content,'清晰画面','本地视觉模型' if i%3==0 else '本机基础识别']
    if scene==2 and i%8==2:tags.append('订单详情')
    items.append({'uuid':f'fixture-{i+1:03}','number':i+1,'date':f'2026-10-{18-i//24:02}T{10+i%10:02}:15:00','filename':f'合成演示_{i+1:03}.jpg','thumbnail':preview(i),'source':'synthetic','hidden':False,'favorite':i==0,'deletable':i!=0,'analysis_status':'complete','search_text':'这是合成演示图片，用于前端布局与交互测试。','tags':tags,'dimensions':{d['key']:[t for t in tags if t in d['values']] for d in dimensions},'evidence':{topic:['合成演示数据']},'caution':[],'trial':i<8,'trialOrder':i,'vlm':{'status':'complete','model':'Qwen3.5-fixture' if i%3==0 else 'apple-vision-reference-classifier','reason':'合成图片：用于查看布局与交互，不对应任何真实照片。'},'similarity':None,'legacy_tags':[]})
payload={'items':items,'counts':{},'dimensions':dimensions,'vocabulary':[v for d in dimensions for v in d['values']],'scope':'full','total':len(items),'analysis':{'videos':12,'completed':96,'total':96,'failed':0},'cautionTags':['订单详情','已收藏','已隐藏'],'trial':{'total':8,'complete':8,'failed':0,'similar_groups':5},'fullVisual':{'qwen':32,'unresolved_topics':6,'unresolved_content':3,'total':96,'completed':96,'failed':0,'local':64,'manual':0,'similarity':5},'method':'合成数据，供界面测试'}
activity={'items':[]}
for i,r in enumerate(items):
    activity['items'].append({**{k:r[k] for k in ['uuid','date','filename','thumbnail']},'day':r['date'][:10],'kind':'photo','bytes':8_000_000+i*12000,'local_bytes':8_000_000+i*12000,'available':True,'screenshot':'截屏' in r['tags']})
for i in range(12):
    activity['items'].append({'uuid':f'fixture-video-{i}','date':f'2026-10-{18-i//3:02}T21:30:00','day':f'2026-10-{18-i//3:02}','filename':f'合成视频_{i+1}.mov','thumbnail':preview(i+100),'kind':'video','bytes':450_000_000,'local_bytes':0,'available':False,'screenshot':False})
activity['items'].sort(key=lambda r:r['date'])
groups=[]
for i in range(6):
    members=[{**r,'bytes':8_000_000+j*120000} for j,r in enumerate(items[i*5:i*5+5])]
    groups.append({'id':f'fixture-group-{i}','kind':'exact' if i==0 else 'similar','items':members,'suggested_keep':members[0]['uuid']})
duplicates={'groups':groups,'updated_at':1792620000,'total':96,'original_available':96,'fingerprinted':96}
mock="""// Synthetic fixture: all application fetch calls terminate here. No Photos API is reachable.
window.fetch=async function(url,options){const path=String(url).split('?')[0];let data;
if(path==='/api/status')data={ok:true,token:'synthetic-token',authorization:'authorized',deleted:[]};
else if(path==='/api/local-model-progress')data={phase:'running',processed:63,total:96,failed:0};
else if(path==='/api/local-model-updates')data={items:[],updated_at:1};
else if(path==='/api/setup')data={ok:true,token:'synthetic-token',packaged:false,platform:{supported:false,model_supported:false,message:'合成演示不读取图库，也不下载模型。'},library:{has_scan:true,photos:96,videos:12},job:{kind:null,state:'idle',message:''},models:[{id:'qwen35-4b',name:'Qwen3.5 4B · 4-bit',description:'在本机补充画面与内容标签',size_bytes:3061139393,total_bytes:3061139393,downloaded_bytes:0,state:'not_installed',selected:false}],library_revision:1};
else if(path==='/api/authorize')data={ok:true,authorization:'authorized'};
else throw new Error('合成演示禁止删除照片或访问真实服务。');
return {ok:true,status:200,json:async()=>data};};
"""
app=(ROOT/'review_app.js').read_text().replace('/*__DATA__*/',encode(payload)).replace('/*__ACTIVITY_DATA__*/',encode(activity)).replace('/*__DELETION_UI__*/',(ROOT/'deletion_ui.js').read_text()).replace('/*__ACTIVITY_UI__*/',(ROOT/'activity_ui.js').read_text()).replace('/*__DUPLICATE_UI__*/',(ROOT/'duplicate_ui.js').read_text().replace('/*__DUPLICATE_DATA__*/',encode(duplicates))).replace('/*__REVIEW_MOTION__*/',(ROOT/'review_motion.js').read_text())
app=app.replace("const storageKey='photo-label-review-oct19'", "const storageKey='photo-label-review-synthetic-fixture'").replace('photo-activity-names-v1','photo-activity-names-synthetic-fixture')
html=(ROOT/'review_template.html').read_text().replace('/*__REVIEW_APP__*/',mock+app).replace('/*__REVIEW_STYLE__*/',(ROOT/'review_style.css').read_text()).replace('/*__ACTIVITY_STYLE__*/',(ROOT/'activity_style.css').read_text()).replace('/*__ACTIVITY_SECTION__*/',(ROOT/'activity_section.html').read_text()).replace('/*__DUPLICATE_SECTION__*/',(ROOT/'duplicate_section.html').read_text())
for marker,filename in [('SETUP_SECTION','setup_section.html'),('SETUP_STYLE','setup_style.css'),('SETUP_UI','setup_ui.js')]:
    html=html.replace('/*__'+marker+'__*/',(ROOT/filename).read_text())
html=html.replace('<title>照片整理 · 本地图库</title>','<title>照片整理 · 合成界面演示</title>').replace('<body data-input="pointer">','<body data-input="pointer"><div role="note" style="padding:7px 16px;text-align:center;background:#fbf3e6;color:#8a5a21;font-size:12px">合成演示数据 · 不连接照片图库 · 删除操作已隔离</div>')
assert '/*__' not in html,'Unresolved template marker'
tmp=DEST/'index.html.tmp';tmp.write_text(html);tmp.replace(DEST/'index.html')
print(DEST/'index.html')
