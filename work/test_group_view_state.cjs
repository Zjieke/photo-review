// State regressions use synthetic records and a minimal in-memory DOM only.
// This test never opens Photos, calls deletion APIs, or reads user photo data.
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
class Element {
 constructor(tag='div'){this.tagName=tag.toUpperCase();this.children=[];this.dataset={};this.attributes={};this.value='';this.checked=false;this.hidden=false;this.textContent='';this.className='';this.replaceCount=0;this.scrollLeft=0;this.scrollTop=0;this.classList={toggle:(cls,on)=>{const set=new Set(this.className.split(' ').filter(Boolean));on?set.add(cls):set.delete(cls);this.className=[...set].join(' ')}}}
 append(...children){for(const node of children){if(node.tagName==='FRAGMENT')this.append(...node.children);else{this.children.push(node);node.parent=this}}}
 replaceChildren(...children){this.children=[];this.replaceCount++;this.append(...children)}
 setAttribute(k,v){this.attributes[k]=v}
 addEventListener(){}
 showModal(){this.open=true}
 close(){this.open=false}
 contains(el){return this===el||this.children.some(n=>n.contains&&n.contains(el))}
 querySelectorAll(sel){let out=[];for(const node of this.children){const match=sel==='[data-focus-key]'?!!node.dataset.focusKey:sel==='.card[data-photo-id]'?node.className.split(' ').includes('card')&&!!node.dataset.photoId:sel==='input[type="checkbox"]'?node.tagName==='INPUT'&&node.type==='checkbox':sel[0]==='.'?node.className.split(' ').includes(sel.slice(1)):false;if(match)out.push(node);out.push(...node.querySelectorAll(sel))}return out}
 querySelector(sel){return this.querySelectorAll(sel)[0]||null}
 focus(){document.activeElement=this}
}
const controls={},el=id=>controls[id]||(controls[id]=new Element());
const document={createElement:t=>new Element(t),createDocumentFragment:()=>new Element('fragment'),activeElement:null};
const data={items:Array.from({length:65},(_,i)=>({uuid:'p'+i,day:'2026-01-01',kind:'photo',bytes:100,local_bytes:100,date:'2026-01-01T12:01:02',filename:'photo'+i+'.jpg',thumbnail:'fixture.jpg',available:true,screenshot:i===64,deletable:i!==2,favorite:i===2}))};
data.items.push(...[0,1].map(i=>({uuid:'v'+i,day:'2026-01-01',kind:'video',bytes:500,local_bytes:i?0:500,date:'2026-01-01T13:01:02',filename:'video'+i+'.mov',thumbnail:'fixture.jpg',available:!i,deletable:true})));
const stored={},selected=new Set(),removed=new Set(),rows=data.items.filter(r=>r.kind==='photo').map(r=>({...r})),mediaById=new Map([...rows,...data.items.filter(r=>r.kind==='video')].map(r=>[r.uuid,r]));let saved=0,deletePreviews=0;
const c=vm.createContext({document,console,el,removed,rows,selected,activityData:data,mediaById,apiToken:'fixture',deletionBusy:false,localStorage:{getItem:()=>null,setItem:(k,v)=>{stored[k]=v}},canSelect:r=>r.deletable!==false,button:(txt,click,cls)=>{const b=new Element('button');b.textContent=txt;b.onclick=click;b.className=cls||'';return b},save:()=>{saved++},showDeletePreview:()=>{deletePreviews++},refreshSelection:()=>vm.runInContext('refreshActivitySelection();if(typeof refreshDuplicateSelection===\'function\')refreshDuplicateSelection()',c)});
el('activityDensity').value='all';el('activitySort').value='size';el('activityMediaType').value='all';el('duplicateKind').value='all';el('duplicateSort').value='size';
vm.runInContext(fs.readFileSync(path.join(__dirname,'activity_ui.js'),'utf8'),c);
vm.runInContext('renderActivities()',c);const renders=el('activityCards').replaceCount;vm.runInContext('renderActivities()',c);assert.equal(el('activityCards').replaceCount,renders,'unchanged overview DOM retained');
vm.runInContext("openActivityDay('2026-01-01')",c);const detailRenders=el('activityGallery').replaceCount;el('activityName').value='演唱会，正在输入';document.activeElement=el('activityName');el('activityName').oninput();vm.runInContext('renderActivities()',c);assert.equal(el('activityName').value,'演唱会，正在输入','background refresh preserves draft');assert.equal(el('activityGallery').replaceCount,detailRenders,'background refresh retains media DOM');
el('activityBack').onclick();vm.runInContext("openActivityDay('2026-01-01')",c);assert.equal(el('activityName').value,'演唱会，正在输入','return preserves draft');el('activitySaveName').onclick();assert.equal(JSON.parse(stored['photo-activity-names-v1'])['2026-01-01'],'演唱会，正在输入','existing names storage retained');
const activityChecks=el('activityGallery').querySelectorAll('input[type="checkbox"]'),activityRenders=el('activityGallery').replaceCount;
assert.equal(activityChecks.length,60,'activity initially limits rendered media to 60');assert.equal(activityChecks[2].disabled,true,'favorite cannot be selected');
activityChecks[0].checked=true;document.activeElement=activityChecks[0];activityChecks[0].onchange();assert.equal(selected.has('p0'),true,'activity checkbox shares global selection');assert.equal(el('activityGallery').replaceCount,activityRenders,'selection retains activity media nodes');assert.equal(document.activeElement,activityChecks[0],'selection keeps keyboard focus');assert.ok(saved>0,'selection is saved');
el('activitySelectGroup').onclick();assert.equal(selected.has('p63'),true,'group select includes unloaded photos');assert.equal(selected.has('v1'),true,'group select includes cloud-only video');assert.equal(selected.has('p2'),false,'group select excludes protected photo');assert.equal(selected.has('p64'),false,'group select respects screenshot filter');
selected.add('outside');vm.runInContext('refreshActivitySelection()',c);assert.match(el('activityDeleteSelected').textContent,/全部已勾选/);assert.match(el('activitySelectionSummary').textContent,/另有 1 项/,'global deletion exposes other selected items');el('activityDeleteSelected').onclick();assert.equal(deletePreviews,1,'activity deletion opens shared confirmation');
el('activityMediaType').value='video';el('activityMediaType').onchange();assert.equal(el('activityGallery').querySelectorAll('input[type="checkbox"]').length,2,'video filter renders video cards');el('activityClearGroup').onclick();assert.equal(selected.has('v0'),false,'clear group respects media filter');assert.equal(selected.has('p0'),true,'clear videos preserves selected photos');assert.equal(selected.has('outside'),true,'clear group preserves other selections');
vm.runInContext("openActivityMedia(activityData.items.find(r=>r.uuid==='v1'))",c);el('activityMediaSelect').onclick();assert.equal(selected.has('v1'),true,'preview can select cloud-only video');assert.equal(el('activityMediaSelect').textContent,'取消勾选此项');el('activityMediaSelect').onclick();assert.equal(selected.has('v1'),false,'preview can unselect video');
vm.runInContext("openActivityMedia(activityData.items.find(r=>r.uuid==='p2'))",c);assert.equal(el('activityMediaSelect').disabled,true,'preview respects favorite protection');el('activityMediaSelect').onclick();assert.equal(selected.has('p2'),false,'protected preview handler cannot bypass protection');
vm.runInContext('deletionBusy=true;refreshActivitySelection()',c);assert.equal(el('activitySelectGroup').disabled,true,'batch deletion disables group selection');const beforeBusy=selected.size;el('activitySelectGroup').onclick();assert.equal(selected.size,beforeBusy,'busy guard prevents group changes');vm.runInContext('deletionBusy=false',c);
el('activityMediaType').value='photo';el('activityScreens').checked=true;el('activityScreens').onchange();vm.runInContext("openActivityDay('2026-01-01')",c);el('activitySelectGroup').onclick();assert.equal(selected.has('p64'),true,'including screenshots expands group selection');selected.clear();vm.runInContext('refreshActivitySelection()',c);
const duplicates={groups:[{id:'similar-test',kind:'similar',suggested_keep:'p0',items:data.items.slice(0,3)}]};
vm.runInContext(fs.readFileSync(path.join(__dirname,'duplicate_ui.js'),'utf8').replace('/*__DUPLICATE_DATA__*/',JSON.stringify(duplicates)),c);vm.runInContext('renderDuplicates()',c);
const duplicateRenders=el('duplicateCards').replaceCount,gallery=el('duplicateCards').querySelector('.duplicate-gallery');gallery.scrollLeft=130;
const checks=el('duplicateCards').querySelectorAll('input[type="checkbox"]');checks[1].checked=true;document.activeElement=checks[1];checks[1].onchange();assert.equal(selected.has('p1'),true);assert.equal(el('duplicateCards').replaceCount,duplicateRenders,'select does not rebuild cards');assert.equal(gallery.scrollLeft,130,'horizontal position retained');assert.equal(document.activeElement,checks[1],'checkbox focus retained');
vm.runInContext('renderDuplicates()',c);assert.equal(el('duplicateCards').replaceCount,duplicateRenders,'model refresh does not rebuild unchanged groups');rows[1].favorite=true;rows[1].deletable=false;vm.runInContext('refreshDuplicateSelection()',c);assert.equal(checks[1].disabled,true,'backend favorite protection refreshes checkbox');assert.equal(el('duplicateCards').querySelectorAll('.duplicate-protection-note')[1].hidden,false,'changed protection refreshes explanation');
removed.add('p2');vm.runInContext('renderDuplicates()',c);assert.equal(el('duplicateCards').querySelector('.duplicate-gallery').scrollLeft,130,'data refresh retains horizontal position');assert.equal(document.activeElement.dataset.focusKey,'similar-test:check:p1','data refresh restores focused checkbox');
// Independent vertical panels retain position except when the user changes the query.
el('libraryScroll').scrollTop=410;el('activityOverview').scrollTop=720;el('activityMediaScroll').scrollTop=560;
vm.runInContext("openActivityDay('2026-01-01')",c);assert.equal(el('activityMediaScroll').scrollTop,0,'opening a day starts its media at the top');assert.equal(el('activityOverview').scrollTop,720,'opening detail retains the overview position');
el('activityMediaScroll').scrollTop=440;vm.runInContext('renderActivities()',c);assert.equal(el('activityMediaScroll').scrollTop,440,'background activity render retains media position');
el('activityMore').onclick();assert.equal(el('activityMediaScroll').scrollTop,440,'loading more media retains position');
el('activityBack').onclick();assert.equal(el('activityOverview').scrollTop,720,'return to overview retains its position');
el('activitySearch').oninput();assert.equal(el('activityOverview').scrollTop,0,'new overview search starts at the top');
el('activityOverview').scrollTop=620;el('activitySort').onchange();assert.equal(el('activityOverview').scrollTop,0,'new overview order starts at the top');
vm.runInContext("openActivityDay('2026-01-01')",c);el('activityMediaScroll').scrollTop=330;el('activityMediaType').onchange();assert.equal(el('activityMediaScroll').scrollTop,0,'media filtering starts at the top');
el('duplicateScroll').scrollTop=880;vm.runInContext('renderDuplicates()',c);assert.equal(el('duplicateScroll').scrollTop,880,'background duplicate render retains vertical position');
el('duplicateMore').onclick();assert.equal(el('duplicateScroll').scrollTop,880,'loading more groups retains position');
el('duplicateSearch').oninput();assert.equal(el('duplicateScroll').scrollTop,0,'new duplicate search starts at the top');
el('duplicateScroll').scrollTop=710;el('duplicateKind').onchange();assert.equal(el('duplicateScroll').scrollTop,0,'new duplicate kind starts at the top');
el('activityOverview').scrollTop=720;el('activityMediaScroll').scrollTop=440;el('duplicateScroll').scrollTop=880;
el('activityTab').onclick();el('duplicateTab').onclick();el('libraryTab').onclick();
assert.deepEqual(['libraryScroll','activityOverview','activityMediaScroll','duplicateScroll'].map(id=>el(id).scrollTop),[410,720,440,880],'top-level view changes retain each panel position');
console.log('PASS: activity selection, drafts/cache, duplicate selection/focus, independent panel scroll retention and user filter resets');
