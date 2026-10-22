const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert/strict');
const script=fs.readFileSync(__dirname+'/deletion_ui.js','utf8');
async function test(failAt=0,mixed=false){
 const nodes={},selected=new Set(Array.from({length:214},(_,i)=>'id'+i));const media=[...selected].map((uuid,i)=>({uuid,number:uuid,filename:uuid+(mixed&&i>=123?'.mov':'.jpg'),kind:mixed&&i>=123?'video':'photo',date:'2026-10-21'}));const rows=media.filter(r=>r.kind==='photo');const mediaById=new Map(media.map(r=>[r.uuid,r]));let calls=[];
 const el=id=>nodes[id]??=( {textContent:'',checked:false,disabled:false,hidden:false,replaceChildren(){},append(){},showModal(){this.open=true},close(){this.open=false},addEventListener(){}});
 const ctx=vm.createContext({Set,Array,Math,Error,crypto:require('node:crypto').webcrypto,selected,rows,mediaById,activityFilteredItems:()=>media,canSelect:()=>true,filtered:()=>rows,tags:()=>['订单详情'],payload:{cautionTags:['订单详情']},el,save(){},render(){},document:{createElement:()=>({})},fetch:async()=>({json:async()=>({ok:true,token:'test',authorization:'authorized'})})});
 vm.runInContext(script,ctx);await new Promise(r=>setImmediate(r));
 ctx.mockPost=async(path,data)=>{calls.push(data.uuids);if(calls.length===failAt)throw Error('模拟中途失败');return {deleted:data.uuids}};
 vm.runInContext('apiPost=mockPost;showDeletePreview()',ctx);assert.equal(vm.runInContext('pendingDeletion.length',ctx),214);if(mixed)assert.match(el('deleteSummary').textContent,/123 张照片、91 个视频/);assert.doesNotMatch(el('deleteSummary').textContent,/保留提醒|待确认|复核/,'Delete confirmation must not introduce a review workflow');el('confirmDeletion').checked=true;await el('confirmDelete').onclick();
 assert.deepEqual(calls.map(x=>x.length),[120,94]);assert.equal(selected.size,failAt?94:0);
 if(failAt)assert.match(el('deleteError').textContent,/120\/214/);else assert.match(el('deletionStatus').textContent,/全部 214/);
}
(async()=>{await test();await test(2);await test(0,true);await test(2,true);console.log('PASS: 确认弹窗无保留提醒计数；214项照片/视频自动分两批；中途失败保留94张；无真实删除调用')})().catch(e=>{console.error(e);process.exit(1)});
