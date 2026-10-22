// Motion belongs to deliberate pointer actions, never background recognition or arrow-key review.
const reducedMotion=window.matchMedia('(prefers-reduced-motion: reduce)');
const motionTokens=getComputedStyle(document.documentElement);
const motionDuration=parseFloat(motionTokens.getPropertyValue('--duration-view'))||250;
const motionEase=motionTokens.getPropertyValue('--ease-out').trim();
const motionAnimations=new Map();
function stopContentMotion(){for(const animation of motionAnimations.values())animation.cancel();motionAnimations.clear()}
function revealContent(node,direction='up',feedback=false){
 if(!node||node.hidden||document.body.dataset.input==='keyboard'||typeof node.animate!=='function')return;
 const previous=motionAnimations.get(node),opacity=previous?getComputedStyle(node).opacity:(feedback ? .55 : 0);
 if(previous)previous.cancel();
 const offset=direction==='forward'?'translateX(24px)':direction==='back'?'translateX(-24px)':'translateY(12px)';
 const frames=reducedMotion.matches||feedback?[{opacity},{opacity:1}]:[{opacity,transform:offset},{opacity:1,transform:'translate(0, 0)'}];
 const animation=node.animate(frames,{duration:reducedMotion.matches?125:feedback?160:motionDuration,easing:motionEase});
 motionAnimations.set(node,animation);
 const cleanup=()=>{if(motionAnimations.get(node)===animation)motionAnimations.delete(node)};
 animation.onfinish=cleanup;animation.oncancel=cleanup;
}
document.addEventListener('keydown',()=>{document.body.dataset.input='keyboard';stopContentMotion()},true);
document.addEventListener('pointerdown',()=>{document.body.dataset.input='pointer'},true);

// The clipped copy moves the active background and label together. Its contents are decorative only.
const viewTabs=document.querySelector('.view-tabs');
const viewButtons=[el('libraryTab'),el('activityTab'),el('duplicateTab')];
const viewHighlight=document.createElement('div');viewHighlight.className='view-tabs-highlight';viewHighlight.setAttribute('aria-hidden','true');
for(const button of viewButtons){const label=document.createElement('span');label.textContent=button.textContent;viewHighlight.append(label)}
viewTabs.append(viewHighlight);
function syncViewHighlight(){
 const active=viewButtons.find(button=>button.getAttribute('aria-pressed')==='true');if(!active)return;
 for(let i=0;i<viewButtons.length;i++){
  const button=viewButtons[i],label=viewHighlight.children[i];
  Object.assign(label.style,{left:button.offsetLeft+'px',top:button.offsetTop+'px',width:button.offsetWidth+'px',height:button.offsetHeight+'px',fontSize:getComputedStyle(button).fontSize});
 }
 viewHighlight.style.clipPath=`inset(${active.offsetTop}px ${Math.max(0,viewTabs.clientWidth-active.offsetLeft-active.offsetWidth)}px ${Math.max(0,viewTabs.clientHeight-active.offsetTop-active.offsetHeight)}px ${active.offsetLeft}px round 9px)`;
 viewTabs.dataset.motionReady='true';
}
syncViewHighlight();
let resizeFrame;
const tabsResize=new ResizeObserver(()=>{
 viewTabs.dataset.resizing='true';syncViewHighlight();cancelAnimationFrame(resizeFrame);
 resizeFrame=requestAnimationFrame(()=>{delete viewTabs.dataset.resizing});
});
tabsResize.observe(viewTabs);
for(const button of viewButtons)tabsResize.observe(button);
let activeView='libraryView';
for(const [tab,view]of [['libraryTab','libraryView'],['activityTab','activityView'],['duplicateTab','duplicateView']]){
 el(tab).addEventListener('click',event=>{
  const changed=view!==activeView;activeView=view;
  if(view==='libraryView')render();
  syncViewHighlight();
  if(changed){stopContentMotion();if(event.detail)revealContent(el(view))}
 });
}

// Delegation runs after the existing actions; render/poll functions stay animation-free.
let lastSelectionCount=selected.size;
document.addEventListener('click',event=>{
 if(!event.detail||document.body.dataset.input==='keyboard')return;
 const target=event.target.closest('button, input, summary');if(!target)return;
 if(target.matches('.activity-cover, .activity-open')){stopContentMotion();revealContent(el('activityDetail'),'forward')}
 else if(target.id==='activityBack'){stopContentMotion();revealContent(el('activityOverview'),'back')}
 else if(target.matches('.filter, .active-chip, #reset, #density'))revealContent(el('grid'),'up',true);
 if(selected.size!==lastSelectionCount){
  if(lastSelectionCount&&selected.size)revealContent(el('selectionCount'),'up',true);
  lastSelectionCount=selected.size;
 }
});
document.addEventListener('change',event=>{
 if(document.body.dataset.input==='keyboard')return;
 const id=event.target.id;
 if(['reviewScope','mode','includeHidden','onlySelected'].includes(id))revealContent(el('grid'),'up',true);
 else if(id==='activityMediaType')revealContent(el('activityGallery'),'up',true);
 else if(['activitySort','activityDensity','activityScreens'].includes(id))revealContent(el('activityCards'),'up',true);
 else if(['duplicateKind','duplicateSort'].includes(id))revealContent(el('duplicateCards'),'up',true);
});
el('modelDetails').addEventListener('toggle',()=>{if(el('modelDetails').open)revealContent(document.querySelector('.model-detail'),'up',true)});
el('toggleFilters').onclick=()=>{
 const opened=document.querySelector('.filter-panel').classList.toggle('is-open');el('toggleFilters').setAttribute('aria-expanded',String(opened));
 if(opened)revealContent(el('filterContent'),'up',true);
};
reducedMotion.addEventListener('change',stopContentMotion);
