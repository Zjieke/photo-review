'use strict';
const payload=/*__DATA__*/;
const activityData=/*__ACTIVITY_DATA__*/;
const rows=payload.items, rowById=new Map(payload.items.map(r=>[r.uuid,r]));
// One shared selection registry for the label gallery and activity photos/videos.
const mediaById=new Map(activityData.items.map(r=>[r.uuid,{...r,tags:[]}]));
const protectedMediaIds=new Set([...activityData.items,...rows].filter(r=>r.deletable===false||r.favorite||r.hidden).map(r=>r.uuid));
for(const r of rows)mediaById.set(r.uuid,r);
const canSelect=r=>!!r&&r.deletable!==false&&!r.favorite&&!r.hidden&&!protectedMediaIds.has(r.uuid);
const selected=new Set(), active=new Set(), edits={}, storageExtras={};
const cardCache=new Map(), facetOpen=new Map();
let facetsDirty=true, searchComposing=false, searchTimer;
const storageKey='photo-label-review-oct19';
let page=1;const pageSize=60;let pageRows=[];
let editing=null, storageAvailable=true, similarGroup="";
try{let stored=JSON.parse(localStorage.getItem(storageKey)||'null');if(!stored){stored={selected:[],edits:{}};for(let i=0;i<localStorage.length;i++){const k=localStorage.key(i);if(k.startsWith('photo-label-review-v1-')){const old=JSON.parse(localStorage.getItem(k)||'{}');stored.selected.push(...(old.selected||[]));Object.assign(stored.edits,old.edits||{})}}}for(const id of stored.selected||[])if(canSelect(mediaById.get(id)))selected.add(id);Object.assign(edits,stored.edits||{});Object.assign(storageExtras,stored);delete storageExtras.selected;delete storageExtras.edits}catch{storageAvailable=false}
const el=id=>document.getElementById(id);
// Older saved results may contain workflow labels. Ignore them without erasing saved data.
const legacyReviewValues=['待复核','已确认可删','保留','无法识别'];
const hiddenWorkflowTags=new Set([...legacyReviewValues,'类型待确认','主题待确认','平台待确认','内容待确认','本地模型待确认','含重要资料']);
const visibleTags=values=>[...new Set(values.filter(t=>!hiddenWorkflowTags.has(t)))];
const labelDimensions=dimensions=>dimensions.filter(d=>d.key!=='review').map(d=>({...d,values:visibleTags(d.values)}));
payload.dimensions=labelDimensions(payload.dimensions);
const tags=r=>visibleTags(Array.isArray(edits[r.uuid])?edits[r.uuid]:(r.tags||[]));
const tagDimension=new Map(payload.dimensions.flatMap(d=>d.values.map(t=>[t,d.key])));
const scopeRows=()=>rows.filter(r=>!removed.has(r.uuid)&&(!r.hidden||el('includeHidden').checked)&&(el('reviewScope').value!=='trial'||r.trial)).sort((a,b)=>el('reviewScope').value==='trial'?a.trialOrder-b.trialOrder:0);
function matchesFacets(r){
 if(!active.size)return true;const values=tags(r);
 if(el('mode').value==='any')return [...active].some(t=>values.includes(t));
 if(el('mode').value==='all')return [...active].every(t=>values.includes(t));
 const groups=new Map();for(const t of active){const k=tagDimension.get(t)||'other';if(!groups.has(k))groups.set(k,[]);groups.get(k).push(t)}
 return [...groups.values()].every(group=>group.some(t=>values.includes(t)));
}
function renderTagGroups(container,r){
 container.replaceChildren();
 for(const d of payload.dimensions){const values=tags(r).filter(t=>d.values.includes(t));if(!values.length)continue;
  const line=document.createElement('div');line.className='dimension-line';const name=document.createElement('span');name.className='dimension-name';name.textContent=d.title;line.append(name);
  for(const t of values){const chip=document.createElement('span');chip.className='tag dim-'+d.key;chip.textContent=t;line.append(chip)}container.append(line);
 }
 const extra=tags(r).filter(t=>!tagDimension.has(t));if(extra.length){const line=document.createElement('div');line.className='dimension-line';line.textContent='其它：'+extra.join(' · ');container.append(line)}
}
function save(){try{localStorage.setItem(storageKey,JSON.stringify({...storageExtras,selected:[...selected],edits}))}catch{storageAvailable=false}if(!storageAvailable)el('saveNote').textContent='当前浏览器无法保存修改，刷新后勾选和手动标签可能丢失。'}
function button(text,handler,cls=''){const b=document.createElement('button');b.textContent=text;b.className=cls;b.onclick=handler;return b}
const searchAliases={'截图':'截屏','瑞幸咖啡':'瑞幸','luckin':'瑞幸','王者':'王者荣耀','电商':'购物'};
const normalizeSearch=s=>String(s||'').normalize('NFKC').toLowerCase();
function searchTerms(query){
 const vocabulary=[...new Set([...payload.dimensions.flatMap(d=>d.values),...Object.keys(searchAliases)])].map(normalizeSearch).sort((a,b)=>b.length-a.length);
 const terms=[];
 for(const part of normalizeSearch(query).trim().split(/[\s,，、;；]+/).filter(Boolean)){
  let rest=part,parsed=[];
  while(rest){const hit=vocabulary.find(t=>t.length>=2&&rest.startsWith(t));if(!hit){parsed=[];break}parsed.push(hit);rest=rest.slice(hit.length)}
  terms.push(...(parsed.length?parsed:[part]));
 }
 return terms.map(t=>searchAliases[t]||t);
}
function matchesSearch(r,terms){const haystack=normalizeSearch([r.filename,r.date,...tags(r),r.vlm?.reason||'',r.search_text||''].join(' '));return terms.every(t=>haystack.includes(t))}
function filtered(){const terms=searchTerms(el('search').value);return scopeRows().filter(r=>(!similarGroup||r.similarity?.id===similarGroup)&&(!el('onlySelected').checked||selected.has(r.uuid))&&matchesSearch(r,terms)&&matchesFacets(r))}

function invalidateLibrary(){facetsDirty=true}
// Reset only for a deliberate query change; polling and selection retain the viewport.
function renderLibraryFromStart(){page=1;render();el('libraryScroll').scrollTop=0}

// Facet counts change with data, not with every checkbox click.
function renderFilters(){
 if(facetsDirty){
  for(const section of el('filters').querySelectorAll('details[data-dimension]'))facetOpen.set(section.dataset.dimension,section.open);
  const counts={},scoped=scopeRows();
  for(const r of scoped)for(const t of tags(r))counts[t]=(counts[t]||0)+1;
  const extras=[...new Set(scoped.flatMap(r=>tags(r)).filter(t=>!tagDimension.has(t)))];
  const focusedTag=document.activeElement?.closest('#filters button[data-tag]')?.dataset.tag;
  const fragment=document.createDocumentFragment();
  for(const d of [...payload.dimensions,{key:'extra',title:'其它标签',values:extras}]){
   const values=d.values.filter(t=>counts[t]||active.has(t));if(!values.length)continue;
   const section=document.createElement('details');section.className='facet-group';section.dataset.dimension=d.key;
   section.open=facetOpen.has(d.key)?facetOpen.get(d.key):['type','topic'].includes(d.key);
   const summary=document.createElement('summary');summary.textContent=d.title;
   const total=document.createElement('span');total.className='count';total.textContent=values.length;summary.append(total);section.append(summary);
   for(const t of values){
    const b=button('',()=>{active.has(t)?active.delete(t):active.add(t);renderLibraryFromStart()},'filter');b.dataset.tag=t;
    const label=document.createElement('span');label.textContent=t;const count=document.createElement('span');count.className='count';count.textContent=counts[t]||0;b.append(label,count);section.append(b);
   }fragment.append(section);
  }
  el('filters').replaceChildren(fragment);facetsDirty=false;
  if(focusedTag){const replacement=[...el('filters').querySelectorAll('button[data-tag]')].find(b=>b.dataset.tag===focusedTag);replacement?.focus({preventScroll:true})}
 }
 for(const b of el('filters').querySelectorAll('button[data-tag]')){const on=active.has(b.dataset.tag);b.classList.toggle('on',on);b.setAttribute('aria-pressed',String(on))}
 el('activeSummary').replaceChildren();
 for(const t of active)el('activeSummary').append(button(t+' ×',()=>{active.delete(t);renderLibraryFromStart()},'active-chip'));
 if(similarGroup)el('activeSummary').append(button('相似组 '+similarGroup+' ×',()=>{similarGroup='';renderLibraryFromStart()},'active-chip'));
 el('toggleFilters').textContent=active.size?`筛选 · ${active.size}`:'筛选标签';
}
function refreshSelection(){
 updateDeleteButton();
 for(const card of document.querySelectorAll('[data-photo-id]')){
  const r=mediaById.get(card.dataset.photoId);if(!r)continue;
  if(card.matches('input')){card.checked=selected.has(r.uuid);card.disabled=!canSelect(r)}
  else{card.classList.toggle('selected',selected.has(r.uuid));const check=card.querySelector('input[type="checkbox"]');if(check){check.checked=selected.has(r.uuid);check.disabled=!canSelect(r)}}
 }
 el('selectionDock').dataset.active=String(selected.size>0);
 el('selectionCount').textContent=selected.size?`已勾选 ${selected.size.toLocaleString()} 项`:'还没有勾选';
 el('selectionHint').textContent=selected.size?'包含其它视图与筛选外的选择，确认后统一处理':'勾选照片或视频后，可统一确认删除';
 el('clearAllSelected').disabled=!selected.size||deletionBusy;
 el('export').disabled=!selected.size;
 el('clearVisible').disabled=!pageRows.some(r=>selected.has(r.uuid));
 el('selectVisible').disabled=!pageRows.some(r=>canSelect(r));
 if(typeof refreshDuplicateSelection==='function'&&!el('duplicateView').hidden)refreshDuplicateSelection();
 if(typeof refreshActivitySelection==='function')refreshActivitySelection();
 if(el('onlySelected').checked&& !el('libraryView').hidden)render();
}
function createPhotoCard(r){
 const card=document.createElement('article');card.className='card';card.dataset.photoId=r.uuid;
 const top=document.createElement('div');top.className='card-top';
 const label=document.createElement('label'),check=document.createElement('input');check.type='checkbox';check.setAttribute('aria-label',`勾选照片 ${r.number}`);
 check.onchange=()=>{check.checked?selected.add(r.uuid):selected.delete(r.uuid);save();refreshSelection()};
 label.append(check,document.createTextNode('#'+String(r.number).padStart(3,'0')));
 const date=document.createElement('time');date.textContent=r.date.slice(0,10);top.append(label,date);
 const imageButton=button('',()=>openPreview(r),'image-button');imageButton.disabled=!r.thumbnail;imageButton.setAttribute('aria-label',`放大照片 ${r.number}`);
 const image=document.createElement('img');if(r.thumbnail)image.src=r.thumbnail;image.alt=`照片 ${r.number}`;image.loading='lazy';image.decoding='async';image.onerror=()=>{image.alt='本地预览暂时无法读取'};imageButton.append(image);
 const body=document.createElement('div');body.className='card-body';
 const chips=document.createElement('div');chips.className='card-tags';
 const brief=tags(r);
 for(const t of brief.slice(0,5)){const chip=document.createElement('span');chip.className='tag dim-'+(tagDimension.get(t)||'other');chip.textContent=t;chips.append(chip)}
 if(brief.length>5){const more=document.createElement('span');more.className='tag tag-more';more.textContent='+'+(brief.length-5);chips.append(more)}
 body.append(chips);
 if(!canSelect(r)){const p=document.createElement('p');p.className='caution';p.textContent='已收藏或隐藏，不可勾选';body.append(p)}
 const details=document.createElement('details');details.className='card-detail-tags';const summary=document.createElement('summary');summary.textContent='全部标签与识别依据';details.append(summary);
 const full=document.createElement('div');renderTagGroups(full,r);details.append(full);
 if(r.vlm?.reason){const reason=document.createElement('p');reason.className='visual-reason';reason.textContent=r.vlm.reason;details.append(reason)}
 const ul=document.createElement('ul');
 for(const [t,hits]of Object.entries(r.evidence||{})){if(hiddenWorkflowTags.has(t))continue;const li=document.createElement('li');li.textContent=t+'：'+hits.join('、');ul.append(li)}
 if(r.trial&&r.legacy_tags){const original=visibleTags(r.legacy_tags);if(original.length){const li=document.createElement('li');li.textContent='原关键词标签：'+original.join('、');ul.append(li)}}
 if(ul.children.length)details.append(ul);body.append(details);
 const footer=document.createElement('div');footer.className='card-footer';const source=document.createElement('span');source.className='muted';
 source.textContent=edits[r.uuid]?'已手动编辑':r.vlm?.model?.startsWith('Qwen3.5')?'Qwen 增强识别':r.vlm?.model==='apple-vision-reference-classifier'?'本机基础识别':r.vlm?.status==='complete'?'看图分类建议':'文字与基础分类';
 footer.append(source,button('编辑标签',()=>{editing=r;el('tagInput').value=tags(r).join('，');el('editor').showModal();el('tagInput').focus()},'edit'));body.append(footer);
 if(r.similarity)body.append(button(`相似组 ${r.similarity.id} · ${r.similarity.count} 张`,()=>{similarGroup=r.similarity.id;el('reviewScope').value='trial';active.clear();el('search').value='';facetsDirty=true;renderLibraryFromStart()},'similar-link'));
 card.append(top,imageButton,body);return card;
}
function render(appendOnly=false){
 appendOnly=appendOnly===true;updateDeleteButton();
 if(!el('activityView').hidden)renderActivities();
 if(!el('duplicateView').hidden)renderDuplicates();
 renderFilters();const visible=filtered();
 page=Math.min(Math.max(1,page),Math.max(1,Math.ceil(visible.length/pageSize)));
 pageRows=visible.slice(0,page*pageSize);
 el('resultCount').textContent=visible.length.toLocaleString()+' 张';
 el('pageStatus').textContent=`已加载 ${pageRows.length.toLocaleString()} / ${visible.length.toLocaleString()} 张 · 滚动继续加载`;
 el('status').textContent=active.size||el('search').value||el('onlySelected').checked?`当前筛选找到 ${visible.length.toLocaleString()} 张照片`:'';
 el('loadMore').hidden=pageRows.length>=visible.length;el('loadEnd').hidden=pageRows.length<visible.length;
 const grid=el('grid'),wanted=new Set(pageRows.map(r=>r.uuid));
 for(const child of [...grid.children])if(!wanted.has(child.dataset.photoId)||cardCache.get(child.dataset.photoId)!==child)child.remove();
 if(!visible.length){grid.replaceChildren();const d=document.createElement('div');d.className='empty';d.innerHTML='<strong>没有找到匹配的照片</strong><p>试试更短的关键词，或减少筛选条件。</p>';d.append(button('清除筛选',()=>el('reset').click()));grid.append(d)}
 for(let i=0;i<pageRows.length;i++){
  const r=pageRows[i];let card=cardCache.get(r.uuid);
  if(!card){card=createPhotoCard(r);cardCache.set(r.uuid,card)}
  const current=grid.children[i];if(current!==card)grid.insertBefore(card,current||null);
  card.classList.toggle('selected',selected.has(r.uuid));const check=card.querySelector('input');check.checked=selected.has(r.uuid);check.disabled=!canSelect(r);
 }
 // Drop detached cards so scrolling/filtering does not retain the entire library in memory.
 for(const [id,card]of cardCache)if(!card.isConnected)cardCache.delete(id);
 el('selectionDock').dataset.active=String(selected.size>0);
 el('selectionCount').textContent=selected.size?`已勾选 ${selected.size.toLocaleString()} 项`:'还没有勾选';
 el('selectionHint').textContent=selected.size?'包含其它视图与筛选外的选择，确认后统一处理':'勾选照片或视频后，可统一确认删除';
 el('clearAllSelected').disabled=!selected.size||deletionBusy;el('export').disabled=!selected.size;
 el('selectVisible').disabled=!pageRows.some(r=>canSelect(r));el('clearVisible').disabled=!pageRows.some(r=>selected.has(r.uuid));
}

let previewRows=[], previewIndex=0;
function openPreview(row){
 previewRows=filtered().filter(r=>r.thumbnail);
 previewIndex=previewRows.findIndex(r=>r.uuid===row.uuid);
 if(previewIndex<0)return;
 renderPreview();el('preview').showModal();
}
function renderPreview(){
 const r=previewRows[previewIndex];if(!r)return;
 el('previewTitle').textContent=`照片 #${r.number} · ${r.date.slice(0,10)}`;
 el('previewPosition').textContent=`第 ${previewIndex+1} / ${previewRows.length} 张 · 打开预览时的筛选结果`;
 el('previewImage').src=r.thumbnail;el('previewImage').alt=`照片 ${r.number} 大图`;
 renderTagGroups(el('previewTags'),r);el('previewReason').textContent=r.vlm?.status==='complete'?(r.vlm.model?.startsWith('Qwen3.5')?'本地模型依据：':r.vlm.model==='apple-vision-reference-classifier'?'本机依据：':'画面依据：')+r.vlm.reason:'当前为文字与基础分类建议';
 el('previewPrevious').disabled=previewIndex===0;
 el('previewNext').disabled=previewIndex===previewRows.length-1;
 el('previewToggle').disabled=!canSelect(r);
 el('previewToggle').textContent=!canSelect(r)?'已收藏或隐藏，不可勾选':selected.has(r.uuid)?'✓ 已勾选 · 空格取消':'勾选待删除 · 空格';
 el('previewToggle').setAttribute('aria-pressed',selected.has(r.uuid));
 el('previewSelection').textContent=`已勾选 ${selected.size} 项待统一确认删除`;
}
function stepPreview(delta){
 const next=previewIndex+delta;if(next<0||next>=previewRows.length)return;
 previewIndex=next;renderPreview();
}
function togglePreview(){
 const r=previewRows[previewIndex];if(!r||!canSelect(r))return;
 selected.has(r.uuid)?selected.delete(r.uuid):selected.add(r.uuid);
 save();refreshSelection();renderPreview();
}
el('reviewScope').onchange=()=>{active.clear();similarGroup='';facetsDirty=true;renderLibraryFromStart()};
el('previewPrevious').onclick=()=>stepPreview(-1);
el('previewNext').onclick=()=>stepPreview(1);
el('previewToggle').onclick=togglePreview;
el('closePreview').onclick=()=>el('preview').close();
el('preview').addEventListener('keydown',e=>{
 if(e.altKey||e.ctrlKey||e.metaKey||['SELECT','INPUT','TEXTAREA'].includes(e.target.tagName))return;
 if(e.key==='ArrowLeft'){e.preventDefault();stepPreview(-1)}
 else if(e.key==='ArrowRight'){e.preventDefault();stepPreview(1)}
 else if(e.key===' '){e.preventDefault();if(!e.repeat)togglePreview()}
});

el('editForm').onsubmit=e=>{e.preventDefault();const list=el('tagInput').value.split(/[,，、\n]/).map(t=>t.trim()).filter(Boolean);edits[editing.uuid]=visibleTags(list);if(!edits[editing.uuid].length)edits[editing.uuid]=['未分类'];save();cardCache.delete(editing.uuid);facetsDirty=true;el('editor').close();render()};

el('search').addEventListener('compositionstart',()=>{searchComposing=true;clearTimeout(searchTimer)});
el('search').addEventListener('compositionend',()=>{searchComposing=false;renderLibraryFromStart()});
el('search').oninput=()=>{clearTimeout(searchTimer);if(!searchComposing)searchTimer=setTimeout(()=>{renderLibraryFromStart()},100)};
el('includeHidden').onchange=()=>{facetsDirty=true;renderLibraryFromStart()};el('loadMore').onclick=()=>{page++;render(true)};el('mode').onchange=renderLibraryFromStart;el('onlySelected').onchange=renderLibraryFromStart;
el('reset').onclick=()=>{active.clear();similarGroup='';el('search').value='';el('onlySelected').checked=false;renderLibraryFromStart()};
const scrollLoader=new IntersectionObserver(entries=>{if(!el('libraryView').hidden&&entries.some(e=>e.isIntersecting)&&!el('loadMore').hidden&&!document.querySelector('dialog[open]')){page++;render(true)}},{root:el('libraryScroll'),rootMargin:'500px'});scrollLoader.observe(el('loadSentinel'));
el('selectVisible').onclick=()=>{pageRows.filter(r=>canSelect(r)).forEach(r=>selected.add(r.uuid));save();refreshSelection()};
el('clearVisible').onclick=()=>{pageRows.forEach(r=>selected.delete(r.uuid));save();refreshSelection()};
el('clearAllSelected').onclick=()=>{
 if(deletionBusy)return;
 selected.clear();pendingDeletion=[];save();refreshSelection();if(el('preview').open)renderPreview();
 if(storageAvailable)deletionStatus('已取消全部勾选（包括未加载和筛选范围外的项目），刷新后也不会恢复。');
};
el('density').onclick=()=>{const dense=document.body.classList.toggle('dense');el('density').textContent=dense?'宽松视图':'紧凑视图';el('density').setAttribute('aria-pressed',String(dense))};
el('export').onclick=()=>{const data={format:'photos-review-selection-v1',exportedAt:new Date().toISOString(),purpose:'人工勾选的待处理清单，尚未删除',items:rows.filter(r=>selected.has(r.uuid)).map(r=>({uuid:r.uuid,number:r.number,date:r.date,filename:r.filename,tags:tags(r),manuallyEdited:!!edits[r.uuid],caution:tags(r).filter(t=>payload.cautionTags.includes(t))}))};el('exportText').value=JSON.stringify(data,null,2);el('exportDialog').showModal()};
el('selectExport').onclick=()=>{el('exportText').focus();el('exportText').select()};
el('downloadExport').onclick=()=>{const blob=new Blob([el('exportText').value],{type:'application/json'});const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download='截图待处理清单.json';document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000)};
/*__DELETION_UI__*/
function updateLibrarySummary(){
 el('photoTotal').textContent=payload.fullVisual.total.toLocaleString();
 el('videoTotal').textContent=(payload.analysis.videos||0).toLocaleString();
 el('basicTotal').textContent=payload.fullVisual.completed.toLocaleString();
 el('scopeSummary').textContent='本地图库 · 照片与视频';
 el('trialSummary').textContent='直接勾选，统一删除';
}
updateLibrarySummary();

let localModelUpdateAt=0, localModelPollBusy=false;
el('showModelResults').onclick=()=>{el('libraryTab').click();el('reviewScope').value='all';active.clear();active.add('本地视觉模型');similarGroup='';facetsDirty=true;renderLibraryFromStart()};
async function pollLocalModel(){
 if(localModelPollBusy)return;localModelPollBusy=true;
 try{
  const status=await (await fetch('/api/local-model-progress',{cache:'no-store'})).json();
  const n=status.processed||0,total=status.total||0;
  const text={not_started:'尚未启动增强本地模型。',downloading:`正在下载本地 Qwen3.5-4B 模型 · ${status.percent||0}%（照片未上传）`,installing:'正在准备本地模型运行环境（照片未上传）。',loading:'正在加载本地看图模型……',benchmark:`正在验证本地模型 · ${status.benchmark_done||0}/${status.benchmark_total||20} 张样本`,running:`本地 Qwen 看图识别中 · 已处理 ${n}/${total} 张 · 图片推理在本机进行`,paused:`本地增强已暂停 · 已保存 ${n}/${total} 张，可在“图库与模型”中继续`,completed:`本地 Qwen 本批处理结束 · 成功 ${n}/${total} 张 · 失败 ${status.failed||0} 张 · 模型仍不确定 ${status.uncertain||0} 张`,validation_failed:'本地模型样本验证未通过，尚未批量处理。',failed:'增强任务未完成，可在“图库与模型”中检查状态后重试。'};
  el('localModelStatus').textContent=text[status.phase]||'正在准备本地模型……';
  const percent=total?Math.min(100,Math.round(n/total*100)):0;
  el('modelProgress').hidden=!total;el('modelProgress').setAttribute('aria-valuenow',String(percent));
  el('modelProgressFill').style.transform=`scaleX(${percent/100})`;
  el('modelPhase').textContent=({running:'增强识别',paused:'增强已暂停',completed:'增强已完成',not_started:'增强未启动',downloading:'模型下载中',installing:'模型准备中',loading:'模型加载中',benchmark:'模型验证中',validation_failed:'模型验证未通过',failed:'增强未完成'})[status.phase]||'增强识别';
  el('modelCompactProgress').textContent=total?`${n.toLocaleString()} / ${total.toLocaleString()}`:status.phase==='downloading'?`${status.percent||0}%`:'';
  const update=await (await fetch('/api/local-model-updates?after='+localModelUpdateAt,{cache:'no-store'})).json();
  if(update.items?.length){
   if(update.dimensions)update.dimensions=labelDimensions(update.dimensions);
   const dimensionsChanged=update.dimensions&&JSON.stringify(update.dimensions)!==JSON.stringify(payload.dimensions);
   if(update.dimensions){payload.dimensions=update.dimensions;tagDimension.clear();for(const d of payload.dimensions)for(const t of d.values)tagDimension.set(t,d.key)}
   for(const item of update.items){
    const existing=rowById.get(item.uuid);if(!existing)continue;
    const card=cardCache.get(item.uuid);
    const cardFields=r=>JSON.stringify([r.tags,r.evidence,r.vlm,r.thumbnail,r.deletable,r.source,r.analysis_status]);
    const changed=card&&(dimensionsChanged||cardFields(existing)!==cardFields({...existing,...item}));
    Object.assign(existing,item);
    if(changed){const wasOpen=card.querySelector('details')?.open;const replacement=createPhotoCard(existing);replacement.querySelector('details').open=!!wasOpen;cardCache.set(item.uuid,replacement)}
   }
   if(update.fullVisual)payload.fullVisual=update.fullVisual;
   localModelUpdateAt=update.updated_at;facetsDirty=true;updateLibrarySummary();render();if(el('preview').open)renderPreview();
   el('trialSummary').textContent=`本地 Qwen 已增强 ${payload.fullVisual.qwen||0} 张`;
  }
  el('showModelResults').hidden=!(payload.fullVisual.qwen>0);
 }catch(e){el('localModelStatus').textContent='本地模型进度暂时无法读取，已有标签仍可使用。';el('modelPhase').textContent='识别状态暂不可用';el('modelCompactProgress').textContent=''}
 finally{localModelPollBusy=false}
}
/*__ACTIVITY_UI__*/
/*__DUPLICATE_UI__*/
/*__REVIEW_MOTION__*/
save();render();pollLocalModel();setInterval(pollLocalModel,20000);
