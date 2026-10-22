// Exercise the shipped motion module using synthetic DOM nodes only.
// No browser, Photos, network, or user media is accessed by this test.
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
class EventTarget {
 constructor(){this.listeners=new Map()}
 addEventListener(type,fn){if(!this.listeners.has(type))this.listeners.set(type,[]);this.listeners.get(type).push(fn)}
 emit(type,event={}){event.type=type;event.target??=this;for(const fn of this.listeners.get(type)||[])fn(event)}
}
const animations=[];
class Element extends EventTarget {
 constructor(tag='div'){super();this.tagName=tag.toUpperCase();this.children=[];this.dataset={};this.style={};this.attributes={};this.id='';this.className='';this.hidden=false;this.textContent='';this.opacity='1';this.offsetLeft=0;this.offsetTop=0;this.offsetWidth=100;this.offsetHeight=36;this.clientWidth=320;this.clientHeight=44;this.classList={toggle:cls=>{const set=new Set(this.className.split(' ').filter(Boolean)),add=!set.has(cls);add?set.add(cls):set.delete(cls);this.className=[...set].join(' ');return add}}}
 append(node){this.children.push(node);node.parent=this}
 setAttribute(name,value){this.attributes[name]=String(value)}
 getAttribute(name){return this.attributes[name]??null}
 matches(selector){return selector.split(',').some(part=>{part=part.trim();return part[0]==='.'?this.className.split(' ').includes(part.slice(1)):part[0]==='#'?this.id===part.slice(1):this.tagName===part.toUpperCase()})}
 closest(selector){return this.matches(selector)?this:this.parent?.closest(selector)||null}
 animate(frames,options){const animation={node:this,frames,options,cancelled:false,cancel(){this.cancelled=true;this.oncancel?.()},finish(){this.onfinish?.()}};animations.push(animation);return animation}
}
const document=new EventTarget();document.body=new Element('body');document.documentElement=new Element('html');document.createElement=tag=>new Element(tag);
const controls={},el=id=>controls[id]||(controls[id]=Object.assign(new Element(),{id}));
const tabs=new Element();tabs.className='view-tabs';
const modelDetail=new Element(),filterPanel=new Element();filterPanel.className='filter-panel';
document.querySelector=selector=>({'.view-tabs':tabs,'.model-detail':modelDetail,'.filter-panel':filterPanel})[selector]||null;
const tabIds=['libraryTab','activityTab','duplicateTab'],viewIds=['libraryView','activityView','duplicateView'];
tabIds.forEach((id,i)=>{const button=el(id);button.tagName='BUTTON';button.textContent=['图库','活动','相似照片'][i];button.offsetLeft=4+i*104;button.offsetTop=4;button.setAttribute('aria-pressed',String(i===0));tabs.append(button);el(viewIds[i]).hidden=i!==0;button.onclick=()=>{tabIds.forEach((other,j)=>{el(other).setAttribute('aria-pressed',String(i===j));el(viewIds[j]).hidden=i!==j})}});
const reduced=new EventTarget();reduced.matches=false;
const frames=new Map(),observers=[];let nextFrame=1,renderCount=0;
class ResizeObserver {constructor(callback){this.callback=callback;this.nodes=[];observers.push(this)}observe(node){this.nodes.push(node)}}
const context=vm.createContext({document,window:{matchMedia:()=>reduced},el,selected:new Set(),console,Map,ResizeObserver,render:()=>{renderCount++},getComputedStyle:node=>({opacity:node.opacity,fontSize:'14px',getPropertyValue:name=>name==='--duration-view'?'250ms':name==='--ease-out'?'cubic-bezier(.23, 1, .32, 1)':''}),requestAnimationFrame:callback=>{const id=nextFrame++;frames.set(id,callback);return id},cancelAnimationFrame:id=>frames.delete(id)});
const source=fs.readFileSync(path.join(__dirname,'review_motion.js'),'utf8');
vm.runInContext(source,context,{filename:'review_motion.js'});
const run=code=>vm.runInContext(code,context);
const click=(target,{pointer=true,detail=1}={})=>{if(pointer)document.emit('pointerdown',{target});const event={target,detail};target.onclick?.(event);target.emit('click',event);document.emit('click',event)};
const latest=()=>animations.at(-1);

const highlight=tabs.children.at(-1);
assert.equal(highlight.className,'view-tabs-highlight');assert.equal(highlight.getAttribute('aria-hidden'),'true','decorative nav copy is hidden from assistive technology');
assert.equal(highlight.children.length,3);assert.deepEqual(highlight.children.map(child=>child.textContent),['图库','活动','相似照片']);
for(const label of highlight.children){assert.equal(label.tagName,'SPAN');assert.equal(label.id,'','copies introduce no duplicate IDs');assert.equal(label.getAttribute('tabindex'),null);assert.equal(label.onclick,undefined);assert.equal(label.listeners.size,0,'copied labels are not interactive')}
assert.equal(highlight.style.clipPath,'inset(4px 216px 4px 4px round 9px)');assert.equal(highlight.children[1].style.left,'108px');assert.equal(highlight.children[1].style.width,'100px');assert.equal(animations.length,0,'initial load does not animate the entire library');

click(el('activityTab'));assert.equal(latest().node,el('activityView'));assert.equal(latest().options.duration,250);assert.equal(latest().frames[0].transform,'translateY(12px)');assert.equal(highlight.style.clipPath,'inset(4px 112px 4px 108px round 9px)');
const tabAnimation=latest();document.emit('keydown',{key:'ArrowRight'});assert.equal(tabAnimation.cancelled,true,'keyboard input cancels an in-flight animation');assert.equal(run('motionAnimations.size'),0);
let count=animations.length;click(el('libraryTab'),{pointer:false,detail:0});assert.equal(animations.length,count,'keyboard tab activation remains instant');assert.equal(renderCount,1);

click(el('activityTab'));
const cover=new Element('button');cover.className='activity-cover';const coverImage=new Element('img');cover.append(coverImage);
click(coverImage);assert.equal(latest().node,el('activityDetail'));assert.equal(latest().frames[0].transform,'translateX(24px)','enter activity moves forward');
const entering=latest();el('activityBack').tagName='BUTTON';click(el('activityBack'));assert.equal(entering.cancelled,true);assert.equal(latest().node,el('activityOverview'));assert.equal(latest().frames[0].transform,'translateX(-24px)','return activity moves backward');
document.emit('keydown',{key:'Enter'});count=animations.length;click(cover,{pointer:false,detail:0});click(el('activityBack'),{pointer:false,detail:0});assert.equal(animations.length,count,'keyboard activity navigation has no scripted motion');

const filter=new Element('button');filter.className='filter';click(filter);const firstFilter=latest();assert.equal(firstFilter.node,el('grid'));assert.equal(firstFilter.options.duration,160);assert.equal(firstFilter.frames[0].opacity,.55);
el('grid').opacity='0.37';click(filter);const interruptedFilter=latest();assert.equal(firstFilter.cancelled,true,'repeat action cancels previous animation');assert.equal(interruptedFilter.frames[0].opacity,'0.37','interrupted animation resumes from current computed opacity');assert.equal(run('motionAnimations.size'),1,'only one animation remains registered per node');firstFilter.onfinish();assert.equal(run('motionAnimations.size'),1,'stale completion cannot clear newer animation');interruptedFilter.finish();assert.equal(run('motionAnimations.size'),0);

click(el('duplicateTab'));const beforeReduce=latest();reduced.matches=true;reduced.emit('change');assert.equal(beforeReduce.cancelled,true,'changing reduced-motion preference cancels current animation');click(el('activityTab'));assert.equal(latest().options.duration,125);assert.equal(latest().frames.length,2);for(const frame of latest().frames)assert.deepEqual(Object.keys(frame),['opacity'],'reduced motion is opacity only');
document.emit('keydown',{key:'Enter'});count=animations.length;click(el('duplicateTab'),{pointer:false,detail:0});assert.equal(animations.length,count,'reduced motion does not override instant keyboard activation');

assert.equal(observers.length,1);assert.deepEqual(observers[0].nodes,[tabs,...tabIds.map(el)]);
tabs.clientWidth=390;el('duplicateTab').offsetLeft=244;el('duplicateTab').offsetWidth=142;observers[0].callback();assert.equal(tabs.dataset.resizing,'true','resize disables the CSS transition immediately');assert.equal(highlight.style.clipPath,'inset(4px 4px 4px 244px round 9px)');assert.equal(highlight.children[2].style.width,'142px');
el('duplicateTab').offsetWidth=180;observers[0].callback();assert.equal(highlight.style.clipPath,'inset(4px 0px 4px 244px round 9px)','resize bounds cannot create negative clip insets');assert.equal(frames.size,1,'repeat resize coalesces frame cleanup');for(const callback of frames.values())callback();frames.clear();assert.equal(tabs.dataset.resizing,undefined);

count=animations.length;context.render();context.render();assert.equal(animations.length,count,'background renders do not cause reveal animations');
assert.deepEqual([...document.listeners.keys()].sort(),['change','click','keydown','pointerdown'],'motion is attached to user events, not background polling or DOM mutations');
assert.deepEqual([...el('modelDetails').listeners.keys()],['toggle']);assert.equal(typeof el('toggleFilters').onclick,'function');assert.equal(source.includes('MutationObserver'),false,'no mutation observer replays motion after recognition updates');
console.log('PASS: real motion module pointer/keyboard navigation, activity direction, cancellation, reduced motion, interruption continuity, decorative tab highlight and responsive bounds; background rendering stays still');
