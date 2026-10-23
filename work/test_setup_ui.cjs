'use strict';
const assert = require('node:assert/strict');
const {createClient, mount, modelView, message} = require('./setup_ui.js');
const clone = value => JSON.parse(JSON.stringify(value));
const tick = () => new Promise(resolve => setImmediate(resolve));
const initial = () => ({
 ok: true, token: 'test-session', packaged: true,
 platform: {supported: true, model_supported: true, message: ''},
 library: {has_scan: false, photos: 0, videos: 0},
 job: {kind: null, state: 'idle', message: '', progress: {}},
 models: [{id: 'qwen-local', name: 'Qwen 本地模型', description: '测试模型', state: 'not_installed', size_bytes: 3e9, selected: false}],
 library_revision: 'empty',
});
function mockAPI(state = initial()) {
 const calls = []; let nextError = null;
 const fetch = async (path, options = {}) => {
  calls.push({path, options});
  if (options.method !== 'POST') return {ok: true, status: 200, json: async () => clone(state)};
  if (nextError) { const error = nextError; nextError = null; return {ok: false, status: error.status || 500, json: async () => ({ok: false, error: error.message})}; }
  assert.equal(options.headers['X-Review-Token'], state.token);
  assert.equal(options.credentials, 'same-origin');
  const body = JSON.parse(options.body);
  if (path.startsWith('/api/models/') || path === '/api/recognition/start') assert.equal(body.id, 'qwen-local');
  if (path === '/api/models/download') state.models[0].state = 'downloading';
  if (path === '/api/models/pause') state.models[0].state = 'paused';
  if (path === '/api/library/scan') state.job = {kind: 'scan', state: 'running', progress: {processed: 1, total: 10}};
  if (path === '/api/recognition/start') state.job = {kind: 'recognize', state: 'running', progress: {processed: 1, total: 10}};
  if (path === '/api/tasks/stop') state.job.state = 'paused';
  return {ok: true, status: 200, json: async () => ({ok: true})};
 };
 return {state, calls, fetch, fail: error => {nextError = error;}};
}
class Element {
 constructor(tag, id = '', document) { this.tagName = tag; this.id = id; this.document = document; this.children = []; this.hidden = false; this.disabled = false; this.dataset = {}; this.listeners = {}; this.attributes = {}; this.open = false; this.textContent = ''; }
 append(node) { node.parent = this; this.children.push(node); }
 prepend(node) { node.parent = this; this.children.unshift(node); }
 remove() { if (this.parent) this.parent.children = this.parent.children.filter(item => item !== this); }
 setAttribute(key, value) { this.attributes[key] = value; }
 removeAttribute(key) { delete this.attributes[key]; }
 addEventListener(name, listener) { (this.listeners[name] ||= []).push(listener); }
 emit(name, event = {}) { for (const listener of this.listeners[name] || []) listener({detail: 1, target: this, ...event}); }
 click(event) { if (!this.disabled) this.emit('click', event); }
 focus() { this.document.activeElement = this; }
 showModal() { this.open = true; this.document.activeElement = this; }
 close() { this.open = false; this.emit('close'); }
}
function mockDocument() {
 const document = {visibilityState: 'visible', listeners: {}, nodes: new Map()};
 document.createElement = tag => new Element(tag, '', document);
 document.getElementById = id => document.nodes.get(id) || null;
 document.addEventListener = (type, fn) => {(document.listeners[type] ||= []).push(fn);};
 document.emit = type => (document.listeners[type] || []).forEach(fn => fn());
 document.body = new Element('body', 'body', document); document.body.dataset.input = 'pointer';
 const fs = require('node:fs'), path = require('node:path');
 const html = fs.readFileSync(path.join(__dirname, 'setup_section.html'), 'utf8') + '<div id="openSetup"></div><div id="grid"></div><div id="loadSentinel"></div><div id="libraryScroll"></div>';
 for (const [, tag, id] of html.matchAll(/<(\w+)[^>]*id="([^"]+)"/g)) document.nodes.set(id, new Element(tag, id, document));
 return document;
}
(async () => {
 const api = mockAPI(), client = createClient(api.fetch);
 await client.act('/api/models/download', {id: 'qwen-local'});
 assert.deepEqual(api.calls.map(item => item.path), ['/api/setup', '/api/models/download'], 'first mutation fetches the session token');
 assert.equal(JSON.parse(api.calls[1].options.body).id, 'qwen-local');
 api.fail({status: 403, message: 'stale token'}); api.state.token = 'fresh-token';
 await assert.rejects(client.act('/api/models/pause', {id: 'qwen-local'}), /连接已更新/);
 assert.deepEqual(api.calls.slice(-2).map(item => item.path), ['/api/models/pause', '/api/setup'], '403 refreshes status without automatically replaying mutation');
 await client.act('/api/models/pause', {id: 'qwen-local'});
 assert.equal(api.calls.at(-1).options.headers['X-Review-Token'], 'fresh-token');
 api.fail({message: 'Traceback: internal module failed'});
 await assert.rejects(client.act('/api/library/scan'), /操作没有完成/);
 assert.equal(message('Traceback (most recent call last):', 'safe'), 'safe');
 assert.equal(message('请检查网络后重试。', 'safe'), '请检查网络后重试。');

 const document = mockDocument(), uiAPI = mockAPI(), timers = new Map(); let timerId = 0, reloads = 0;
 const environment = {fetch: uiAPI.fetch, setTimeout: callback => {timers.set(++timerId, callback); return timerId;}, clearTimeout: id => timers.delete(id), location: {reload: () => {reloads++;}}};
 const ui = mount(document, environment); const get = id => document.getElementById(id);
 await tick();
 assert.equal(uiAPI.calls.length, 1); assert.equal(uiAPI.calls[0].path, '/api/setup', 'opening page only reads state');
 assert.equal(timers.size, 0, 'closed idle dialog does not poll');
 assert.equal(get('setupWelcome').hidden, false); assert.equal(get('grid').hidden, true);
 assert.equal(get('libraryScroll').children[0], get('setupWelcome'), 'first-use card lives in the independently scrolling media area');
 assert.equal(get('setupScan').disabled, false);
 get('openSetup').click({detail: 0}); await tick();
 assert.equal(get('setupDialog').open, true); assert.equal(document.body.dataset.input, 'keyboard', 'keyboard open stays immediate');
 assert.equal(timers.size, 1);
 const card = ui.cards.get('qwen-local'), downloadButton = card.buttons.download;
 card.buttons.download.click(); await tick();
 assert.equal(card.buttons.pause.hidden, false); assert.equal(get('openSetup').dataset.busy, 'true');
 assert.equal(ui.cards.get('qwen-local'), card); assert.equal(ui.cards.get('qwen-local').buttons.download, downloadButton, 'polling patches existing nodes rather than replacing focused controls');
 uiAPI.state.models[0].downloaded_bytes = 500_000_000; uiAPI.state.models[0].total_bytes = 3e9;
 await ui.refresh(); assert.match(card.size.textContent, /500.0 MB \/ 3.00 GB/);
 card.buttons.pause.click(); await tick();
 assert.equal(card.buttons.download.textContent, '继续下载');
 get('setupClose').click(); assert.equal(timers.size, 0, 'pausing download and closing dialog stops polling');
 get('setupScan').click(); await tick();
 assert.equal(get('setupScan').disabled, true); assert.equal(timers.size, 1, 'active task polls even with dialog closed');
 assert.equal(get('setupJobCount').textContent, '1 / 10');
 const mutations = () => uiAPI.calls.filter(item => item.options.method === 'POST');
 const beforeDoubleClick = mutations().length;
 await Promise.all([ui.action('/api/tasks/stop'), ui.action('/api/tasks/stop')]);
 assert.equal(mutations().length, beforeDoubleClick + 1, 'double click cannot start duplicate mutation');
 assert.equal(get('setupJobRetry').textContent, '继续图库扫描');
 uiAPI.state.library = {has_scan: true, photos: 10, videos: 2}; uiAPI.state.job.state = 'completed'; uiAPI.state.library_revision = 'scan-1';
 await ui.refresh();
 assert.equal(reloads, 0, 'scan completion never automatically refreshes and discards active state');
 assert.equal(get('setupResults').hidden, false); assert.equal(get('setupWelcomeOpen').textContent, '查看整理结果');
 assert.equal(get('setupWelcome').hidden, false, 'empty page continues showing the results entry until explicit refresh');
 get('setupViewResults').click(); assert.equal(reloads, 1);
 uiAPI.state.models[0] = {...uiAPI.state.models[0], state: 'ready', selected: true}; await ui.refresh();
 assert.equal(card.buttons.recognize.disabled, false);
 card.buttons.recognize.click(); await tick();
 assert.equal(uiAPI.calls.filter(item => item.options.method === 'POST').at(-1).path, '/api/recognition/start');
 assert.equal(card.buttons.recognize.disabled, true);
 document.visibilityState = 'hidden'; document.emit('visibilitychange'); assert.equal(timers.size, 0, 'hidden tabs avoid background polling');
 document.visibilityState = 'visible'; document.emit('visibilitychange'); await tick(); assert.equal(timers.size, 1);
 uiAPI.state.platform.model_supported = false; uiAPI.state.job.state = 'paused'; await ui.refresh();
 assert.equal(card.buttons.recognize.disabled, true);
 assert.equal(modelView({state: 'ready', selected: true}, {platform: {model_supported: true}, library: {has_scan: false}, job: {state: 'idle'}}).canRecognize, false, 'recognition requires a completed scan');
 uiAPI.fail({message: 'network failure'}); await ui.action('/api/models/download', {id: 'qwen-local'});
 assert.equal(get('setupActionError').hidden, false); assert.equal(get('setupActionError').textContent, 'network failure');
 uiAPI.state.platform.model_supported = true; await ui.refresh();
 get('setupQuit').click(); assert.equal(get('setupQuitConfirm').hidden, false); assert.equal(document.activeElement, get('setupQuitCancel'));
 get('setupQuitCancel').click(); assert.equal(get('setupQuitConfirm').hidden, true); assert.equal(document.activeElement, get('setupQuit'));
 get('setupQuit').click(); get('setupQuitAccept').click(); await tick();
 assert.equal(timers.size, 0); assert.match(get('setupActionNotice').textContent, /保存进度并退出/);
 assert.equal(get('setupScan').disabled, true);
 console.log('PASS: setup uses authenticated explicit actions, preserves model card nodes, supports pause/resume/error/retry, polls only when needed, never autoscans/downloads or reloads results, and exits cleanly');
})().catch(error => {console.error(error); process.exitCode = 1;});
