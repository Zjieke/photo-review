let activityDay='', activityLimit=60, activityNames={}, activityPreviewId='';
const activityDrafts=new Map();
try{activityNames=JSON.parse(localStorage.getItem('photo-activity-names-v1')||'{}')}catch{}
const activityBytes=n=>n>=1e9?(n/1e9).toFixed(2)+' GB':n>=1e6?(n/1e6).toFixed(1)+' MB':Math.round(n/1e3)+' KB';
function activityGroups(){
 const groups=new Map(),includeScreens=el('activityScreens').checked;
 for(const r of activityData.items){
  if(removed.has(r.uuid)||(!includeScreens&&r.screenshot))continue;
  if(!groups.has(r.day))groups.set(r.day,{day:r.day,items:[],bytes:0,local_bytes:0,unknown:0,photos:0,videos:0,photo_bytes:0,video_bytes:0});
  const g=groups.get(r.day);g.items.push(r);g.bytes+=r.bytes||0;g.local_bytes+=r.local_bytes||0;g.unknown+=r.bytes===null?1:0;g[r.kind==='video'?'videos':'photos']++;g[r.kind==='video'?'video_bytes':'photo_bytes']+=r.bytes||0;
 }
 const q=el('activitySearch').value.trim().toLowerCase();
 return [...groups.values()].filter(g=>(el('activityDensity').value==='all'||g.items.length>=10||g.videos>=3||g.bytes>=1e9)&&(!q||(g.day+' '+(activityNames[g.day]||'')).toLowerCase().includes(q))).sort((a,b)=>el('activitySort').value==='size'?b.bytes-a.bytes:el('activitySort').value==='count'?b.items.length-a.items.length:b.day.localeCompare(a.day));
}
function activityText(tag,text,cls){const n=document.createElement(tag);n.textContent=text;if(cls)n.className=cls;return n}
function activityImage(r){const image=document.createElement('img');image.alt=r.kind==='video'?'视频封面':'照片封面';image.loading='lazy';image.decoding='async';if(r.thumbnail)image.src=r.thumbnail;else image.alt='暂无封面';return image}
function activityFilteredItems(){
 const group=activityGroups().find(g=>g.day===activityDay),type=el('activityMediaType').value;
 return group?group.items.filter(r=>type==='all'||r.kind===type):[];
}
function activityProtectionText(r){return r.favorite?'已收藏，不可勾选':r.hidden?'已隐藏，不可勾选':'受图库保护，不可勾选'}
function refreshActivitySelection(){
 const items=activityFilteredItems(),selectable=items.filter(r=>canSelect(mediaById.get(r.uuid)||r)),chosen=items.filter(r=>selected.has(r.uuid)).length;
 el('activitySelectGroup').disabled=deletionBusy||!selectable.some(r=>!selected.has(r.uuid));
 el('activityClearGroup').disabled=deletionBusy||chosen===0;
 el('activityDeleteSelected').disabled=!apiToken||deletionBusy||selected.size===0;
 el('activityDeleteSelected').textContent=`删除全部已勾选${selected.size?'（'+selected.size+' 项）':''}`;
 el('activitySelectionSummary').textContent=activityDay?`当前分组筛选共 ${items.length} 项，已勾选 ${chosen} 项。勾选本组包含尚未加载的项目。${selected.size>chosen?'另有 '+(selected.size-chosen)+' 项在其他分组或筛选中被勾选。':''}`:'';
 for(const card of el('activityGallery').querySelectorAll('.card[data-photo-id]')){
  const r=mediaById.get(card.dataset.photoId);if(!r)continue;
  const check=card.querySelector('input[type="checkbox"]');check.checked=selected.has(r.uuid);check.disabled=deletionBusy||removed.has(r.uuid)||!canSelect(r);card.classList.toggle('selected',check.checked);
  const note=card.querySelector('.activity-protection-note');note.hidden=canSelect(r);note.textContent=canSelect(r)?'':activityProtectionText(r);
 }
 const current=mediaById.get(activityPreviewId),select=el('activityMediaSelect');
 select.disabled=deletionBusy||!current||removed.has(activityPreviewId)||!canSelect(current);
 select.textContent=current&&!canSelect(current)?activityProtectionText(current):selected.has(activityPreviewId)?'取消勾选此项':'勾选此项';
 select.setAttribute('aria-pressed',String(selected.has(activityPreviewId)));
}
function setActivitySelection(id,value){
 const r=mediaById.get(id);if(deletionBusy||!r||removed.has(id)||!canSelect(r)){refreshActivitySelection();return}
 value?selected.add(id):selected.delete(id);save();refreshSelection();
}
function openActivityDay(day){activityDay=day;activityLimit=60;renderActivities();el('activityMediaScroll').scrollTop=0}
function filterActivityOverview(){activityDay='';renderActivities();el('activityOverview').scrollTop=0}
function renderActivities(){
 const groups=activityGroups(),container=el('activityCards');
 const summary=`${groups.length} 个日期分组 · ${groups.reduce((n,g)=>n+g.photos,0)} 张照片 · ${groups.reduce((n,g)=>n+g.videos,0)} 个视频 · 原始文件 ${activityBytes(groups.reduce((n,g)=>n+g.bytes,0))}`;
 if(el('activitySummary').textContent!==summary)el('activitySummary').textContent=summary;
 el('activityOverview').hidden=!!activityDay;el('activityDetail').hidden=!activityDay;
 if(activityDay){renderActivityDetail(groups);return}
 const signature=JSON.stringify(groups.map(g=>[g.day,activityNames[g.day]||'',g.bytes,g.items.map(r=>r.uuid)]));
 if(container.dataset.signature===signature){refreshActivitySelection();return}
 container.dataset.signature=signature;container.replaceChildren();
 if(!groups.length){container.append(activityText('p','没有符合条件的日期。试试“全部日期”，或调整搜索条件。','empty'));refreshActivitySelection();return}
 const fragment=document.createDocumentFragment();
 for(const g of groups){
  const card=document.createElement('article');card.className='activity-card';
  const cover=button('',()=>openActivityDay(g.day),'activity-cover');cover.setAttribute('aria-label','查看 '+(activityNames[g.day]||g.day)+' 的照片与视频');
  const examples=[...g.items.filter(r=>r.kind==='video'),...g.items.filter(r=>r.kind!=='video')].filter(r=>r.thumbnail);
  for(const r of examples.slice(0,3))cover.append(activityImage(r));
  if(!examples.length)cover.append(activityText('span','暂无本地预览','cover-empty'));
  const body=document.createElement('div');body.className='activity-card-body';
  const date=activityText('time',g.day,'activity-date');date.dateTime=g.day;
  body.append(date,activityText('h3',activityNames[g.day]||'这一天的拍摄记录'));
  const stats=document.createElement('div');stats.className='activity-card-stats';
  const size=document.createElement('div');size.append(activityText('strong',activityBytes(g.bytes),'activity-size'),activityText('span','原始文件体积','activity-size-label'));
  const counts=document.createElement('div');counts.className='activity-counts';counts.append(activityText('span',`${g.photos} 张照片`),activityText('span',`${g.videos} 个视频`));stats.append(size,counts);body.append(stats);
  body.append(activityText('p',`照片 ${activityBytes(g.photo_bytes)} · 视频 ${activityBytes(g.video_bytes)}`,'activity-breakdown'),activityText('p',`${g.items[0].date.slice(11,16)} — ${g.items.at(-1).date.slice(11,16)}${g.unknown?' · '+g.unknown+' 项体积未知':''}`,'activity-time'));
  body.append(button('查看这一天 →',()=>openActivityDay(g.day),'activity-open'));card.append(cover,body);fragment.append(card);
 }
 container.append(fragment);refreshActivitySelection();
}
function renderActivityDetail(groups){
 const g=groups.find(g=>g.day===activityDay),gallery=el('activityGallery'),name=el('activityName');
 if(!g){el('activityDetailTitle').textContent='当前条件下没有此分组';el('activityDetailSummary').textContent='返回日期分组，或调整筛选条件。';el('activityMore').hidden=true;el('activityDetailCount').textContent='';gallery.replaceChildren();delete gallery.dataset.signature;refreshActivitySelection();return}
 el('activityDetailTitle').textContent=activityNames[g.day]||g.day+' 的拍摄记录';
 const draft=activityDrafts.has(g.day)?activityDrafts.get(g.day):(activityNames[g.day]||'');
 // Keep the existing input and caret while background recognition refreshes the page.
 if(name.dataset.day!==g.day){name.dataset.day=g.day;name.value=draft;el('activityNameStatus').textContent=activityDrafts.has(g.day)?'名称尚未保存。':''}
 else if(document.activeElement!==name&&name.value!==draft)name.value=draft;
 el('activityDetailSummary').textContent=`${g.day} · ${g.photos} 张照片 / ${activityBytes(g.photo_bytes)} · ${g.videos} 个视频 / ${activityBytes(g.video_bytes)} · 原始文件 ${activityBytes(g.bytes)} · 已在本机 ${activityBytes(g.local_bytes)}${g.unknown?' · '+g.unknown+' 项体积未知':''}`;
 const type=el('activityMediaType').value,items=g.items.filter(r=>type==='all'||r.kind===type),visible=items.slice(0,activityLimit);
 el('activityMore').hidden=items.length<=activityLimit;
 el('activityDetailCount').textContent=`显示 ${visible.length} / ${items.length} 项 · 点击查看大图或播放视频`;
 const signature=JSON.stringify([g.day,type,visible.map(r=>r.uuid)]);
 if(gallery.dataset.signature===signature){refreshActivitySelection();return}
 gallery.dataset.signature=signature;gallery.replaceChildren();
 if(!items.length){gallery.append(activityText('p',type==='video'?'这一天没有符合条件的视频。':'这一天没有符合条件的照片。','empty'));refreshActivitySelection();return}
 const fragment=document.createDocumentFragment();
 for(const r of visible){
  const card=document.createElement('article');card.className='card';card.dataset.photoId=r.uuid;
  const pick=document.createElement('label');pick.className='card-top';const check=document.createElement('input');check.type='checkbox';check.setAttribute('aria-label','勾选'+(r.kind==='video'?'视频 ':'照片 ')+r.filename);check.onchange=()=>setActivitySelection(r.uuid,check.checked);pick.append(check,activityText('span',r.kind==='video'?'勾选视频':'勾选照片'));
  const open=button('',()=>openActivityMedia(r),'image-button');open.append(activityImage(r));open.setAttribute('aria-label',(r.kind==='video'?'播放视频 ':'查看照片 ')+r.filename);
  const body=document.createElement('div');body.className='card-body';body.append(activityText('strong',(r.kind==='video'?'视频':'照片')+' · '+(r.bytes===null?'体积未知':activityBytes(r.bytes)),'activity-media-kind'),activityText('p',r.date.slice(11,19),'muted'),activityText('p',r.filename,'activity-filename'));
  if(!r.available)body.append(activityText('p',r.kind==='video'?'原视频不在本机，暂不能播放':'原图不在本机，使用预览','muted activity-media-unavailable'));
  body.append(activityText('p','','muted activity-protection-note'));card.append(pick,open,body);fragment.append(card);
 }
 gallery.append(fragment);refreshActivitySelection();
}
function openActivityMedia(r){
 activityPreviewId=r.uuid;
 el('activityMediaTitle').textContent=(r.kind==='video'?'视频':'照片')+' · '+r.filename;el('activityPlayer').replaceChildren();
 if(r.kind==='video'&&r.available){const video=document.createElement('video');video.controls=true;video.playsInline=true;video.preload='metadata';if(r.thumbnail)video.poster=r.thumbnail;video.src='/api/activity-media/'+r.uuid;let triedCompatible=false;video.onloadedmetadata=()=>{el('activityPlayerError').textContent=triedCompatible?'正在播放兼容预览，原视频保持不变。':''};video.onerror=()=>{if(!triedCompatible){triedCompatible=true;el('activityPlayerError').textContent='正在本机准备兼容视频预览，首次打开可能需要稍候……';video.src='/api/activity-preview/'+r.uuid}else el('activityPlayerError').textContent='浏览器无法播放此视频格式，可在 Mac 照片应用中观看。'};el('activityPlayer').append(video)}
 else if(r.kind==='photo'&&r.thumbnail)el('activityPlayer').append(activityImage(r));
 el('activityPlayerError').textContent=r.kind==='video'&&!r.available?'原视频尚未下载到本机，此处只显示本地封面。':'';
 if(r.kind==='video'&&!r.available&&r.thumbnail)el('activityPlayer').append(activityImage(r));
 refreshActivitySelection();el('activityMediaDialog').showModal();
}
el('activityMediaDialog').addEventListener('close',()=>{activityPreviewId='';el('activityPlayer').replaceChildren()});
el('activityMediaClose').onclick=()=>el('activityMediaDialog').close();
el('activityMediaSelect').onclick=()=>setActivitySelection(activityPreviewId,!selected.has(activityPreviewId));
el('activitySelectGroup').onclick=()=>{if(deletionBusy)return;for(const r of activityFilteredItems())if(canSelect(mediaById.get(r.uuid)||r))selected.add(r.uuid);save();refreshSelection()};
el('activityClearGroup').onclick=()=>{if(deletionBusy)return;for(const r of activityFilteredItems())selected.delete(r.uuid);save();refreshSelection()};
el('activityDeleteSelected').onclick=()=>showDeletePreview();
el('activityTab').onclick=()=>{el('libraryView').hidden=true;el('activityView').hidden=false;el('activityTab').setAttribute('aria-pressed','true');el('libraryTab').setAttribute('aria-pressed','false');renderActivities()};
el('libraryTab').onclick=()=>{el('libraryView').hidden=false;el('activityView').hidden=true;el('activityTab').setAttribute('aria-pressed','false');el('libraryTab').setAttribute('aria-pressed','true')};
for(const id of ['activitySort','activityDensity','activityScreens'])el(id).onchange=filterActivityOverview;
el('activitySearch').oninput=filterActivityOverview;
el('activityBack').onclick=()=>{activityDay='';renderActivities()};
el('activityMore').onclick=()=>{activityLimit+=60;renderActivities()};
el('activityMediaType').onchange=()=>{activityLimit=60;renderActivities();el('activityMediaScroll').scrollTop=0};
el('activityName').oninput=()=>{if(!activityDay)return;activityDrafts.set(activityDay,el('activityName').value);el('activityNameStatus').textContent='名称尚未保存。'};
el('activitySaveName').onclick=()=>{if(!activityDay)return;const value=el('activityName').value.trim().slice(0,60);if(value)activityNames[activityDay]=value;else delete activityNames[activityDay];activityDrafts.delete(activityDay);el('activityName').value=value;try{localStorage.setItem('photo-activity-names-v1',JSON.stringify(activityNames));el('activityNameStatus').textContent='已保存名称，仅保存在当前浏览器。'}catch{el('activityNameStatus').textContent='浏览器无法保存名称，本次打开期间仍可查看。'}renderActivities()};
