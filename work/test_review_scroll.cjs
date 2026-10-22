// Evaluate the production query handlers with a synthetic DOM and observer.
// No server, media files, browser storage, or deletion API is accessed.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(__dirname+'/review_app.js','utf8');
function between(start,end){const from=source.indexOf(start),to=source.indexOf(end,from+start.length);assert.ok(from>=0&&to>from);return source.slice(from,to)}
const nodes=new Map(),timers=new Map(),observers=[],renders=[];let timerId=0,dialogOpen=false;
const el=id=>{if(!nodes.has(id))nodes.set(id,{scrollTop:0,hidden:false,checked:false,value:'',events:{},addEventListener(type,callback){this.events[type]=callback}});return nodes.get(id)};
class IntersectionObserver{constructor(callback,options){this.callback=callback;this.options=options;observers.push(this)}observe(target){this.target=target}}
const context=vm.createContext({el,IntersectionObserver,document:{querySelector:()=>dialogOpen?{}:null},stepPreview(){},togglePreview(){},renderPreview(){},setTimeout(callback){timers.set(++timerId,callback);return timerId},clearTimeout(id){timers.delete(id)},render(appendOnly){renders.push({appendOnly,page:vm.runInContext('page',context)})}});
vm.runInContext("let page=7,similarGroup='',facetsDirty=false,searchComposing=false,searchTimer;const active=new Set()",context);
vm.runInContext(between('function renderLibraryFromStart(){','// Facet counts'),context);
vm.runInContext(between("el('reviewScope').onchange=","el('selectVisible').onclick="),context);
assert.equal(observers.length,1);
const observer=observers[0];assert.equal(observer.options.root,el('libraryScroll'),'infinite loading uses the photo panel, not the document');assert.equal(observer.options.rootMargin,'500px');assert.equal(observer.target,el('loadSentinel'));
for(const id of ['reviewScope','includeHidden','mode','onlySelected']){el('libraryScroll').scrollTop=650;vm.runInContext('page=7',context);el(id).onchange();assert.equal(el('libraryScroll').scrollTop,0,id+' starts at the top');assert.equal(renders.at(-1).page,1)}
el('libraryScroll').scrollTop=650;el('reset').onclick();assert.equal(el('libraryScroll').scrollTop,0,'reset starts at the top');
el('libraryScroll').scrollTop=650;el('search').oninput();assert.equal(el('libraryScroll').scrollTop,650,'debounced typing does not jump until the query is applied');for(const callback of timers.values())callback();timers.clear();assert.equal(el('libraryScroll').scrollTop,0,'applied search starts at the top');
el('libraryScroll').scrollTop=650;el('search').events.compositionstart();el('search').oninput();assert.equal(timers.size,0,'IME composition does not apply a partial query');assert.equal(el('libraryScroll').scrollTop,650);el('search').events.compositionend();assert.equal(el('libraryScroll').scrollTop,0,'completed IME query starts at the top');
el('libraryScroll').scrollTop=920;el('loadMore').onclick();assert.equal(el('libraryScroll').scrollTop,920,'manual loading retains position');assert.equal(renders.at(-1).appendOnly,true);
let count=renders.length;observer.callback([{isIntersecting:true}]);assert.equal(renders.length,count+1);assert.equal(el('libraryScroll').scrollTop,920,'observer loading retains position');assert.equal(renders.at(-1).appendOnly,true);
for(const blocked of ['hidden-view','complete','dialog','outside']){el('libraryView').hidden=blocked==='hidden-view';el('loadMore').hidden=blocked==='complete';dialogOpen=blocked==='dialog';count=renders.length;observer.callback([{isIntersecting:blocked!=='outside'}]);assert.equal(renders.length,count,blocked+' prevents observer loading')}
console.log('PASS: panel-rooted infinite loading, search/IME/filter resets, append position retention and hidden/dialog guards');
