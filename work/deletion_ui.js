let apiToken='', photoAuthorization='unknown', deletionBusy=false, pendingDeletion=[];
const removed=new Set();
function deletionStatus(message){el('deletionStatus').textContent=message}
function updateDeleteButton(){el('clearAllSelected').disabled=!selected.size||deletionBusy;el('deleteSelected').disabled=!apiToken||deletionBusy||!selected.size;el('authorizePhotos').hidden=photoAuthorization==='authorized';el('authorizePhotos').disabled=!apiToken||deletionBusy;if(typeof refreshActivitySelection==='function')refreshActivitySelection()}
async function loadDeletionStatus(){
 try{const res=await fetch('/api/status',{cache:'no-store'});const data=await res.json();if(!data.ok)throw Error(data.error||'删除服务不可用');apiToken=data.token;photoAuthorization=data.authorization;for(const id of data.deleted||[]){removed.add(id);selected.delete(id)}save();if(typeof invalidateLibrary==='function')invalidateLibrary();render();deletionStatus(photoAuthorization==='authorized'?'图库已连接':'首次使用：请点击“授权照片访问”，在系统提示中允许完整访问。')}
 catch(e){deletionStatus('删除服务未连接：'+e.message+'。请通过本地服务地址打开页面。')}
 updateDeleteButton();
}
async function apiPost(path,data){const res=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json','X-Review-Token':apiToken},body:JSON.stringify(data)});const result=await res.json();if(!result.ok)throw Error(result.error||'操作未完成');return result}
function showDeletePreview(){
 const targets=[...selected].map(id=>mediaById.get(id)).filter(r=>r&&!removed.has(r.uuid)&&canSelect(r));
 pendingDeletion=targets.map(r=>r.uuid);
 if(!pendingDeletion.length){deletionStatus('当前勾选中没有可删除的项目，请检查是否已删除或受到保护。');return;}
 const selectedTotal=pendingDeletion.length;
 const scope=typeof activityFilteredItems==='function'&&!el('activityView').hidden?activityFilteredItems():filtered();
 const visibleIds=new Set(scope.map(r=>r.uuid));
 const hiddenCount=pendingDeletion.filter(id=>!visibleIds.has(id)).length;
 const videos=targets.filter(r=>r.kind==='video').length,photos=selectedTotal-videos;
 const counts=[photos?`${photos} 张照片`:'',videos?`${videos} 个视频`:''].filter(Boolean).join('、');
 el('deleteSummary').textContent=`本次将把全部 ${selectedTotal} 项（${counts}）移到“最近删除”。若中途失败，未完成项目会保留勾选。`+(hiddenCount?`其中 ${hiddenCount} 项不在当前筛选结果中。`:'');
 el('deleteItems').replaceChildren();
 for(const r of targets.slice(0,100)){const li=document.createElement('li');li.textContent=`${r.kind==='video'?'视频':'照片'} · ${r.filename||'#'+r.number} · ${r.date.slice(0,10)}`;el('deleteItems').append(li)}
 if(targets.length>100){const li=document.createElement('li');li.textContent=`另有 ${targets.length-100} 项已勾选，将一并处理。`;el('deleteItems').append(li)}
 el('deleteError').textContent=photoAuthorization==='authorized'?'':'请先关闭此窗口，点击页面上方的“授权照片访问”。';el('confirmDeletion').checked=false;el('confirmDelete').disabled=true;el('deleteDialog').showModal();
}
el('deleteSelected').onclick=showDeletePreview;
el('authorizePhotos').onclick=async()=>{deletionBusy=true;updateDeleteButton();deletionStatus('请处理系统的照片访问授权提示……');try{const result=await apiPost('/api/authorize',{});photoAuthorization=result.authorization;deletionStatus(photoAuthorization==='authorized'?'已授权。勾选照片后点击“删除已勾选”。':photoAuthorization==='notDetermined'?'系统尚未弹出授权请求，请重新点击“授权照片访问”；无需先到系统设置中查找。':photoAuthorization==='limited'?'目前只有部分照片权限，请在系统设置 → 隐私与安全性 → 照片中为“截图清理助手”选择完整访问。':'照片访问被拒绝或受限制，请在系统设置 → 隐私与安全性 → 照片中检查“截图清理助手”。')}catch(e){deletionStatus(e.message)}finally{deletionBusy=false;updateDeleteButton()}};
el('confirmDeletion').onchange=()=>{el('confirmDelete').disabled=!el('confirmDeletion').checked||deletionBusy||photoAuthorization!=='authorized'};
el('cancelDelete').onclick=()=>{if(!deletionBusy)el('deleteDialog').close()};
el('deleteDialog').addEventListener('cancel',e=>{if(deletionBusy)e.preventDefault()});
el('confirmDelete').onclick=async()=>{
 if(photoAuthorization!=='authorized'||deletionBusy||!el('confirmDeletion').checked||!pendingDeletion.length)return;
 deletionBusy=true;updateDeleteButton();el('confirmDelete').disabled=true;el('cancelDelete').disabled=true;el('confirmDeletion').disabled=true;el('deleteError').textContent='正在等待系统处理，请留意可能出现的照片删除确认框……';
 const targets=[...pendingDeletion];let completed=0;
 try{
  for(let offset=0;offset<targets.length;offset+=120){
   const batch=targets.slice(offset,offset+120);
   el('deleteError').textContent=`正在删除：已完成 ${completed}/${targets.length} 项。正在处理第 ${Math.floor(offset/120)+1}/${Math.ceil(targets.length/120)} 批，请留意系统确认框。`;
   const result=await apiPost('/api/trash',{requestId:(crypto.randomUUID?crypto.randomUUID():'10000000-1000-4000-8000-100000000000'.replace(/[018]/g,c=>(Number(c)^crypto.getRandomValues(new Uint8Array(1))[0]&15>>Number(c)/4).toString(16))),uuids:batch,confirmed:true});
   if(!Array.isArray(result.deleted)||result.deleted.some(id=>!batch.includes(id)))throw Error('删除回执异常，已停止后续批次，请核对照片图库。');
   for(const id of result.deleted){removed.add(id);selected.delete(id)}
   completed+=result.deleted.length;save();if(typeof invalidateLibrary==='function')invalidateLibrary();render();
   if(new Set(result.deleted).size!==batch.length)throw Error('本批未全部完成，已停止后续批次。');
  }
  el('deleteDialog').close();deletionStatus(`已将全部 ${completed} 项移到“最近删除”。如需恢复，请打开照片应用。`);
 }
 catch(e){el('deleteError').textContent=`已完成 ${completed}/${targets.length} 项，已停止。${e.message} 未完成的项目保留勾选，请检查后再试。`;el('confirmDeletion').checked=false;pendingDeletion=targets.filter(id=>!removed.has(id))}

 finally{deletionBusy=false;el('cancelDelete').disabled=false;el('confirmDeletion').disabled=false;updateDeleteButton()}
};
loadDeletionStatus();
