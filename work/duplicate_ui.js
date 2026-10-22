const duplicateData=/*__DUPLICATE_DATA__*/;
let duplicateLimit=20;
const duplicateRows=new Map(rows.map(r=>[r.uuid,r]));
function duplicateGroups(){return (duplicateData.groups||[]).map(g=>({...g,items:g.items.filter(r=>!removed.has(r.uuid)&&duplicateRows.has(r.uuid))})).filter(g=>g.items.length>1).filter(g=>el('duplicateKind').value==='all'||g.kind===el('duplicateKind').value).filter(g=>!el('duplicateSearch').value.trim()||g.items.some(r=>(r.date+' '+r.filename).toLowerCase().includes(el('duplicateSearch').value.trim().toLowerCase()))).sort((a,b)=>el('duplicateSort').value==='count'?b.items.length-a.items.length:b.items.reduce((s,r)=>s+(r.bytes||0),0)-a.items.reduce((s,r)=>s+(r.bytes||0),0))}
function refreshDuplicateSelection(groups=duplicateGroups()){
 const unique=new Map(groups.flatMap(g=>g.items).map(r=>[r.uuid,r])),picked=[...unique.values()].filter(r=>selected.has(r.uuid));
 const summary=`${groups.filter(g=>g.kind==='exact').length} 组完全重复 · ${groups.filter(g=>g.kind==='similar').length} 组相似候选 · ${unique.size} 张 / ${activityBytes([...unique.values()].reduce((n,r)=>n+(r.bytes||0),0))} · 这些分组中已勾选 ${picked.length} 张 / ${activityBytes(picked.reduce((n,r)=>n+(r.bytes||0),0))}`;
 if(el('duplicateSummary').textContent!==summary)el('duplicateSummary').textContent=summary;
 el('duplicateDelete').textContent=`删除已勾选（${selected.size}）`;el('duplicateDelete').disabled=!apiToken||!selected.size||deletionBusy;el('duplicateDelete').title='删除全部页面的已勾选照片，继续后会先确认。';
 for(const card of el('duplicateCards').querySelectorAll('.card[data-photo-id]')){const row=duplicateRows.get(card.dataset.photoId);card.classList.toggle('selected',selected.has(row.uuid));const check=card.querySelector('input[type="checkbox"]');check.checked=selected.has(row.uuid);check.disabled=!canSelect(row);const note=card.querySelector('.duplicate-protection-note');if(note)note.hidden=canSelect(row)}
}
function renderDuplicates(){
 const groups=duplicateGroups();refreshDuplicateSelection(groups);
 el('duplicateCoverage').textContent=duplicateData.updated_at?`本地扫描 ${new Date(duplicateData.updated_at*1000).toLocaleString()}。范围 ${duplicateData.total} 张，${duplicateData.original_available} 张有本地原文件，${duplicateData.fingerprinted} 张生成有效相似指纹。未下载原图的照片不能确认完全重复；纯色或信息过少的图片不作相似匹配。`:'正在准备本地分组，稍后刷新页面查看。';
 const container=el('duplicateCards'),visible=groups.slice(0,duplicateLimit);el('duplicateMore').hidden=groups.length<=duplicateLimit;
 const signature=JSON.stringify(visible.map(g=>[g.id,g.suggested_keep,g.items.map(r=>r.uuid)]));
 if(container.dataset.signature===signature)return;
 const positions=new Map([...container.querySelectorAll('.duplicate-gallery')].map(g=>[g.dataset.groupId,g.scrollLeft]));
 const focused=container.contains(document.activeElement)?document.activeElement.dataset.focusKey:null;
 container.dataset.signature=signature;container.replaceChildren();
 if(!groups.length){container.append(activityText('p','没有符合条件的分组。试试切换类型，或清空搜索。','empty'));return}
 const fragment=document.createDocumentFragment();
 for(const g of visible){
  const section=document.createElement('article');section.className='panel duplicate-group';section.dataset.groupId=g.id;
  const heading=document.createElement('div');heading.className='duplicate-group-heading';
  const title=document.createElement('div');title.append(activityText('h3',`${g.kind==='exact'?'完全重复':'相似画面'} · ${g.items.length} 张`),activityText('p',`${g.items[0].date.slice(0,10)} · 原始文件 ${activityBytes(g.items.reduce((n,r)=>n+(r.bytes||0),0))}`,'duplicate-group-meta'));
  heading.append(title,activityText('span',g.kind==='exact'?'原文件一致':'相似候选','duplicate-kind '+g.kind));section.append(heading);
  const kept=g.items.find(r=>r.uuid===g.suggested_keep)||g.items[0];
  const operations=document.createElement('div');operations.className='duplicate-operations';
  const selectOthers=button('勾选其他照片',()=>{for(const item of g.items){const r=duplicateRows.get(item.uuid);if(item.uuid!==kept.uuid&&canSelect(r))selected.add(item.uuid)}save();refreshSelection()});selectOthers.title='勾选本组除参考保留外、允许删除的照片';selectOthers.dataset.focusKey=g.id+':select';
  const clearGroup=button('取消本组勾选',()=>{for(const r of g.items)selected.delete(r.uuid);save();refreshSelection()});clearGroup.dataset.focusKey=g.id+':clear';operations.append(selectOthers,clearGroup);section.append(operations);
  const gallery=document.createElement('div');gallery.className='duplicate-gallery';gallery.dataset.groupId=g.id;gallery.setAttribute('aria-label','本组照片，左右滚动比较');
  for(const item of g.items){
   const r=duplicateRows.get(item.uuid),card=document.createElement('article');card.className='card'+(selected.has(r.uuid)?' selected':'');card.dataset.photoId=r.uuid;
   const top=document.createElement('label');top.className='card-top';const check=document.createElement('input');check.type='checkbox';check.checked=selected.has(r.uuid);check.disabled=!canSelect(r);check.dataset.photoId=r.uuid;check.dataset.focusKey=g.id+':check:'+r.uuid;check.setAttribute('aria-label','勾选重复候选 '+item.filename);check.onchange=()=>{check.checked?selected.add(r.uuid):selected.delete(r.uuid);save();refreshSelection()};top.append(check,activityText('span',item.uuid===kept.uuid?'参考保留'+(item.favorite?' · 已收藏':' · 文件较大'):'候选照片',item.uuid===kept.uuid?'duplicate-reference':''));card.append(top);
   const open=button('',()=>{previewRows=g.items.map(x=>duplicateRows.get(x.uuid));previewIndex=previewRows.findIndex(x=>x.uuid===r.uuid);renderPreview();el('preview').showModal()},'image-button');open.dataset.focusKey=g.id+':open:'+r.uuid;open.setAttribute('aria-label','查看重复候选 '+item.filename);open.append(activityImage(item));card.append(open);
   const body=document.createElement('div');body.className='card-body';body.append(activityText('strong',item.bytes==null?'体积未知':activityBytes(item.bytes)),activityText('p',item.date.slice(0,19).replace('T',' '),'muted'),activityText('p',item.filename,'activity-filename'));
   const protection=activityText('p','已收藏或隐藏，不可勾选','caution duplicate-protection-note');protection.hidden=canSelect(r);body.append(protection);card.append(body);gallery.append(card);
  }
  section.append(gallery);fragment.append(section);
 }
 container.append(fragment);
 for(const gallery of container.querySelectorAll('.duplicate-gallery'))if(positions.has(gallery.dataset.groupId))gallery.scrollLeft=positions.get(gallery.dataset.groupId);
 if(focused){const target=[...container.querySelectorAll('[data-focus-key]')].find(n=>n.dataset.focusKey===focused);if(target)target.focus({preventScroll:true})}
}
function showDuplicateView(){el('libraryView').hidden=true;el('activityView').hidden=true;el('duplicateView').hidden=false;for(const id of ['libraryTab','activityTab','duplicateTab'])el(id).setAttribute('aria-pressed',String(id==='duplicateTab'));renderDuplicates()}
el('duplicateTab').onclick=showDuplicateView;
for(const id of ['libraryTab','activityTab']){const previous=el(id).onclick;el(id).onclick=()=>{el('duplicateView').hidden=true;el('duplicateTab').setAttribute('aria-pressed','false');previous()}}
function filterDuplicates(){duplicateLimit=20;renderDuplicates();el('duplicateScroll').scrollTop=0}
for(const id of ['duplicateKind','duplicateSort'])el(id).onchange=filterDuplicates;el('duplicateSearch').oninput=filterDuplicates;el('duplicateMore').onclick=()=>{duplicateLimit+=20;renderDuplicates()};el('duplicateDelete').onclick=()=>el('deleteSelected').click();
