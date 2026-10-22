// Synthetic-only regression checks. No photo data, HTTP server, or deletion API is used.
// The browser's DOM drawing is stubbed; the actual persistence, filtering, selection
// handlers, and model-update code are evaluated from the application source.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');

const app = fs.readFileSync(__dirname + '/review_app.js', 'utf8');
function sourceBetween(start, end) {
  const from = app.indexOf(start);
  const to = app.indexOf(end, from + start.length);
  assert.ok(from >= 0 && to > from, `Application source boundary is missing: ${start}`);
  return app.slice(from, to);
}

const data = {
  items: [
    {uuid: 'manual', number: 1, filename: 'manual.jpg', date: '2026-01-01', tags: ['游戏', '冒险岛', '待复核'], hidden: false, deletable: true},
    {uuid: 'keep', number: 2, filename: 'keep.jpg', date: '2026-01-02', tags: ['自然风景', '自然风景', '待复核', '平台待确认', '本地模型待确认', '含重要资料'], hidden: false, deletable: true},
    {uuid: 'locked', number: 3, filename: 'locked.jpg', date: '2026-01-03', tags: ['购物', '订单详情', '待复核'], favorite: true, hidden: false, deletable: false},
    {uuid: 'game', number: 4, filename: 'game.jpg', date: '2026-01-04', tags: ['游戏', '王者荣耀', '二维码', '待复核'], search_text: '样例文字', hidden: false, deletable: true},
    {uuid: 'hidden', number: 5, filename: 'hidden.jpg', date: '2026-01-05', tags: ['生活记录', '待复核'], hidden: true, deletable: false},
    {uuid: 'unclassified', number: 6, filename: 'unclassified.jpg', date: '2026-01-06', tags: ['类型待确认', '主题待确认', '内容待确认'], hidden: false, deletable: true},
  ],
  dimensions: [
    {key: 'type', title: '类型', values: ['照片', '类型待确认']},
    {key: 'topic', title: '主题', values: ['游戏', '购物', '自然风景', '生活记录', '主题待确认', '自然风景']},
    {key: 'platform', title: '平台', values: ['冒险岛', '王者荣耀', '平台待确认']},
    {key: 'content', title: '内容', values: ['二维码', '订单详情', '订单详情', '内容待确认']},
    {key: 'quality', title: '整理提示', values: ['含重要资料']},
    {key: 'source', title: '识别方式', values: ['本地模型待确认', '本地视觉模型']},
    {key: 'review', title: '复核', values: ['待复核', '已确认可删', '保留', '无法识别']},
  ],
  fullVisual: {qwen: 1, unresolved_topics: 0},
  cautionTags: ['订单详情'],
};
const saved = {
  selected: ['manual', 'keep', 'locked', 'game', 'missing'],
  edits: {manual: ['自定义行程', '冒险岛', '已确认可删']},
  reviews: {manual: '已确认可删', keep: '保留'},
};
const storage = new Map([['photo-label-review-oct19', JSON.stringify(saved)]]);
const nodes = new Map();
function element(id) {
  if (!nodes.has(id)) nodes.set(id, {
    value: '', checked: false, hidden: false, open: false, disabled: false,
    textContent: '', dataset: {}, style: {}, setAttribute() {}, close() { this.open = false; },
  });
  return nodes.get(id);
}
element('mode').value = 'grouped';
element('reviewScope').value = 'all';

let nextUpdate = {items: []};
const requests = [];
async function mockFetch(url) {
  requests.push(url);
  assert.ok(url.startsWith('/api/local-model-'), 'Unexpected network operation');
  return {json: async () => url.includes('progress')
    ? {phase: 'running', processed: 2, total: 5}
    : structuredClone(nextUpdate)};
}
const context = vm.createContext({
  document: {getElementById: element, querySelectorAll: () => []},
  localStorage: {getItem: key => storage.get(key) || null, setItem: (key, value) => storage.set(key, value)},
  fetch: mockFetch,
});
const run = code => vm.runInContext(code, context);
const ids = () => Array.from(run('filtered().map(r => r.uuid)'));
const stateBoundary = app.indexOf("el('reviewScope').onchange=");
assert.ok(stateBoundary > 0, 'Application setup boundary is missing');
run(app.slice(0, stateBoundary).replace('/*__DATA__*/', JSON.stringify(data)).replace('/*__ACTIVITY_DATA__*/', JSON.stringify({items:[]})));
run(`
  const removed = new Set();
  let deletionBusy = false, pendingDeletion = [], renderCount = 0;
  function updateDeleteButton() {}
  function deletionStatus(message) { el('deletionStatus').textContent = message; }
  function updateLibrarySummary() {}
  render = () => { renderCount++; };
  renderPreview = () => {};
  let localModelUpdateAt = 0, localModelPollBusy = false;
`);
// Exercise the actual selection event handlers after restoring legacy browser state.
run(sourceBetween("el('selectVisible').onclick=", "el('density').onclick="));
run(sourceBetween('async function pollLocalModel(){', '/*__ACTIVITY_UI__*/'));
run(sourceBetween("el('editForm').onsubmit=", "el('search').addEventListener"));

function cleanLabelVocabulary() {
  const forbidden = ['待复核', '已确认可删', '保留', '无法识别', '类型待确认', '主题待确认', '平台待确认', '内容待确认', '本地模型待确认', '含重要资料'];
  const dimensions = JSON.parse(run('JSON.stringify(payload.dimensions)'));
  for (const d of dimensions) {
    assert.equal(new Set(d.values).size, d.values.length, 'Facet values must be deduplicated');
    assert.ok(d.values.every(t => !forbidden.includes(t)), 'Workflow labels must not remain in facets');
  }
  const values = Array.from(run('rows.flatMap(r => tags(r))'));
  assert.ok(values.every(t => !forbidden.includes(t)), 'Workflow labels must not remain in photo tags');
  assert.equal(run("tags(rowById.get('locked')).filter(t => t === '订单详情').length"), 1, 'Concrete content labels must survive cleanup');
}

function selectionProtection() {
  cleanLabelVocabulary();
  assert.deepEqual(Array.from(run('[...selected]')).sort(), ['game', 'keep', 'manual']);
  assert.equal(run("canSelect(rowById.get('keep'))"), true, 'A legacy keep review must not block a new selection');
  assert.equal(run("payload.dimensions.some(d => d.key === 'review')"), false, 'Legacy review facets must be removed');
  assert.equal(run("[...tagDimension.keys()].some(t => ['待复核','已确认可删','保留','无法识别'].includes(t))"), false, 'Legacy review vocabulary must not be searchable as a facet');
  assert.deepEqual(Array.from(run("tags(rowById.get('manual'))")), ['自定义行程', '冒险岛'], 'Manual content tags survive without legacy review status');
  assert.deepEqual(Array.from(run("tags(rowById.get('keep'))")), ['自然风景'], 'Rows must not acquire a default review status and repeated tags must collapse');
  assert.deepEqual(Array.from(run("tags(rowById.get('unclassified'))")), [], 'Unknown labels are hidden rather than creating another review task');
  assert.equal(run("canSelect(rowById.get('locked'))"), false, 'Favorite protection from the backend must remain');
  assert.equal(ids().includes('hidden'), false);
  element('includeHidden').checked = true;
  assert.equal(ids().includes('hidden'), true);
  assert.equal(run("canSelect(rowById.get('hidden'))"), false);
  element('includeHidden').checked = false;
}

function searchAndFacets() {
  for (const [query, expected] of [
    ['冒险岛', ['manual']], ['自定义行程', ['manual']],
    ['王者二维码', ['game']], ['样例文字', ['game']],
    ['待复核', []], ['已确认可删', []], ['保留', []], ['无法识别', []],
    ['待确认', []], ['含重要资料', []], ['订单详情', ['locked']],
  ]) {
    element('search').value = query;
    assert.deepEqual(ids(), expected, `Search: ${query}`);
  }
  element('search').value = '';
  run("active.add('游戏'); active.add('王者荣耀'); active.add('冒险岛');");
  assert.deepEqual(ids(), ['game'], 'Same-dimension OR must compose with cross-dimension AND');
  element('mode').value = 'any';
  assert.deepEqual(ids(), ['manual', 'game']);
  element('mode').value = 'all';
  assert.deepEqual(ids(), []);
  element('mode').value = 'grouped';
  run('active.clear();');
}

function clearAcrossFilters() {
  element('search').value = '王者';
  run("pageRows = [rowById.get('game')];");
  element('clearVisible').onclick();
  assert.deepEqual(Array.from(run('[...selected]')).sort(), ['keep', 'manual'], 'Loaded-only clear must retain the filtered-out selection');
  element('onlySelected').checked = true;
  run("pendingDeletion = ['manual'];");
  element('clearAllSelected').onclick();
  assert.equal(run('selected.size'), 0);
  assert.equal(run('pendingDeletion.length'), 0);
  assert.deepEqual(ids(), []);
  const persisted = JSON.parse(storage.get('photo-label-review-oct19'));
  assert.deepEqual(persisted.selected, []);
  assert.deepEqual(persisted.edits, saved.edits);
  assert.deepEqual(persisted.reviews, saved.reviews);
  assert.ok(run('renderCount') > 0, 'Visible selected-only results must refresh after deselection');
  element('search').value = '';
  element('onlySelected').checked = false;
  run("pageRows = ['keep', 'locked', 'hidden'].map(id => rowById.get(id));");
  element('selectVisible').onclick();
  assert.deepEqual(Array.from(run('[...selected]')), ['keep'], 'Bulk selection ignores old reviews while keeping backend protections');
  element('clearAllSelected').onclick();
}

async function modelUpdates() {
  run(`
    function testCard() {
      const details = {open: false};
      return {querySelector: selector => selector === 'details' ? details : null};
    }
    createPhotoCard = () => {
      const card = testCard();
      card.contentDimension = tagDimension.get('新增场景');
      return card;
    };
    const initialManualCard = testCard(), initialGameCard = testCard();
    initialManualCard.querySelector('details').open = true;
    cardCache.set('manual', initialManualCard);
    cardCache.set('game', initialGameCard);
    selected.add('manual'); selected.add('game');
  `);
  nextUpdate = {updated_at: 10, items: structuredClone(data.items), dimensions: structuredClone(data.dimensions), fullVisual: data.fullVisual};
  await run('pollLocalModel()');
  assert.equal(run("cardCache.get('manual') === initialManualCard"), true, 'Unchanged model rows must preserve existing cards');
  assert.equal(run("cardCache.get('game') === initialGameCard"), true);

  const dimensions = structuredClone(data.dimensions);
  dimensions.find(d => d.key === 'content').values.push('新增场景');
  nextUpdate = {
    updated_at: 20,
    items: [
      {uuid: 'manual', tags: ['购物', '新增场景', '待复核'], vlm: {status: 'complete', model: 'Qwen3.5-test', reason: '合成结果'}},
      {uuid: 'keep', tags: ['游戏', '游戏', '待复核', '主题待确认', '含重要资料']},
      structuredClone(data.items.find(r => r.uuid === 'game')),
    ],
    dimensions, fullVisual: {qwen: 3, unresolved_topics: 0},
  };
  await run('pollLocalModel()');
  cleanLabelVocabulary();
  assert.deepEqual(Array.from(run("tags(rowById.get('manual'))")), ['自定义行程', '冒险岛']);
  assert.deepEqual(Array.from(run("tags(rowById.get('keep'))")), ['游戏']);
  assert.equal(run("payload.dimensions.some(d => d.key === 'review')"), false, 'Live model updates must not restore review facets');
  assert.equal(run("[...tagDimension.keys()].some(t => ['待复核','已确认可删','保留','无法识别'].includes(t))"), false);
  assert.equal(run("canSelect(rowById.get('keep'))"), true);
  assert.deepEqual(JSON.parse(storage.get('photo-label-review-oct19')).reviews, saved.reviews, 'Compatibility state must stay intact without controlling selection');
  assert.deepEqual(Array.from(run('[...selected]')).sort(), ['game', 'manual']);
  assert.equal(run("cardCache.get('manual') === initialManualCard"), false, 'Changed model data must refresh its cached card');
  assert.equal(run("cardCache.get('manual').querySelector('details').open"), true, 'Open recognition details must survive a model update');
  assert.equal(run("cardCache.get('manual').contentDimension"), 'content', 'New vocabulary must be installed before rebuilding cards');
  assert.equal(run("rows.find(r => r.uuid === 'manual') === rowById.get('manual')"), true, 'Preview and group row references must remain valid');
  run("const settledManualCard = cardCache.get('manual'), settledGameCard = cardCache.get('game');");
  nextUpdate.updated_at = 30;
  await run('pollLocalModel()');
  assert.equal(run("cardCache.get('manual') === settledManualCard"), true, 'Repeated snapshots must not recreate cards');
  assert.equal(run("cardCache.get('game') === settledGameCard"), true);
  assert.ok(requests.every(url => !url.includes('/trash')));
}

function emptyManualTags() {
  run("editing = rowById.get('unclassified');");
  element('tagInput').value = '';
  let prevented = false;
  element('editForm').onsubmit({preventDefault() { prevented = true; }});
  assert.ok(prevented);
  assert.deepEqual(Array.from(run("tags(rowById.get('unclassified'))")), ['未分类'], 'Empty manual labels must stay usable without asking for confirmation');
  assert.deepEqual(JSON.parse(storage.get('photo-label-review-oct19')).reviews, saved.reviews);
}

(async () => {
  selectionProtection();
  searchAndFacets();
  clearAcrossFilters();
  await modelUpdates();
  emptyManualTags();
  console.log('PASS: 隐藏历史复核与待确认标签、空标签回退、收藏隐藏保护、标签/别名/多维搜索、跨筛选清空、手动标签与兼容数据保留、增量卡片缓存与展开状态；仅使用合成数据');
})().catch(error => { console.error(error); process.exitCode = 1; });

// Activity-only items and videos share restored selections without entering photo facets.
{
 const activity={items:[
  {uuid:'extra-photo',kind:'photo',favorite:false,hidden:false},
  {uuid:'video',kind:'video',favorite:false,hidden:false,available:false},
  {uuid:'protected-video',kind:'video',favorite:true},
  {uuid:'game',kind:'photo',favorite:true},
 ]};
 const savedActivity={selected:['extra-photo','video','protected-video','game','manual','missing'],edits:{manual:['自己的标签']}};
 const activityStorage=new Map([['photo-label-review-oct19',JSON.stringify(savedActivity)]]);
 const activityContext=vm.createContext({document:{getElementById:element},localStorage:{getItem:key=>activityStorage.get(key)||null,setItem:(key,value)=>activityStorage.set(key,value)}});
 vm.runInContext(app.slice(0,stateBoundary).replace('/*__DATA__*/',JSON.stringify(data)).replace('/*__ACTIVITY_DATA__*/',JSON.stringify(activity)),activityContext);
 const check=code=>vm.runInContext(code,activityContext);
 assert.deepEqual(Array.from(check('[...selected]')).sort(),['extra-photo','manual','video']);
 assert.equal(check('rows.length'),data.items.length,'Activity videos must not enter photo search/facets');
 assert.equal(check("mediaById.get('manual')===rowById.get('manual')"),true,'All views must share canonical photo rows');
 assert.equal(check("canSelect(mediaById.get('game'))"),false,'Activity protection overrides an unprotected label record');
 assert.deepEqual(Array.from(check("tags(mediaById.get('video'))")),[]);
 check('save()');
 assert.deepEqual(JSON.parse(activityStorage.get('photo-label-review-oct19')).selected.sort(),['extra-photo','manual','video']);
 console.log('PASS: 活动照片/视频勾选恢复、跨来源保护、云端原件选择、图库搜索隔离');
}
