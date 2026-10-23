/* The setup controller is isolated from gallery selection and background label merging. */
(function (root) {
 'use strict';
 const ACTIVE = new Set(['running', 'stopping']);
 const number = value => Math.max(0, Number(value) || 0);
 const count = value => number(value).toLocaleString('zh-CN');
 function bytes(value) {
  value = number(value);
  if (value >= 1e9) return (value / 1e9).toFixed(2) + ' GB';
  if (value >= 1e6) return (value / 1e6).toFixed(1) + ' MB';
  return Math.ceil(value / 1e3) + ' KB';
 }
 function message(value, fallback) {
  const text = String(value || '').trim();
  // API messages are text, never HTML. Internal tracebacks and paths stay out of the UI.
  if (!text || text.length > 240 || /Traceback|stack trace|File ["']|\/(?:Users|home)\/|\.py", line|\bat \w+.*\(.*:\d+:\d+\)/i.test(text)) return fallback;
  return text;
 }
 function busy(state) { return ACTIVE.has(state?.job?.state); }
 function downloading(state) { return (state?.models || []).some(model => model.state === 'downloading'); }
 function modelView(model, state) {
  const ready = model.state === 'ready';
  const downloadingModel = model.state === 'downloading';
  const total = number(model.total_bytes || model.size_bytes);
  const downloaded = Math.min(number(model.downloaded_bytes), total || Infinity);
  const states = {not_installed: '尚未下载', downloading: '下载中', paused: '已暂停', ready: model.selected ? '正在使用' : '已下载', failed: '下载未完成'};
  return {
   ready, downloading: downloadingModel, total, downloaded,
   state: states[model.state] || '尚未下载',
   downloadLabel: model.state === 'paused' ? '继续下载' : model.state === 'failed' ? '重试下载' : '下载模型',
   progressVisible: downloadingModel || model.state === 'paused' || (model.state === 'failed' && downloaded > 0),
   canRecognize: ready && !!model.selected && !!state?.platform?.model_supported && !!state?.library?.has_scan && number(state?.library?.photos) > 0 && !busy(state),
   sizeLabel: downloadingModel || model.state === 'paused' || (model.state === 'failed' && downloaded > 0) ? `${bytes(downloaded)} / ${total ? bytes(total) : '正在计算'}` : `${ready ? '已安装' : '下载约'} ${bytes(total)}`,
  };
 }
 function createClient(fetcher) {
  let state = null, loading = null, acting = false;
  async function load() {
   if (loading) return loading;
   loading = (async () => {
    const response = await fetcher('/api/setup', {cache: 'no-store', credentials: 'same-origin'});
    const result = await response.json();
    if (!response.ok || !result.ok) throw new Error(message(result.error, '暂时无法连接本机程序，请重试。'));
    state = result;
    return state;
   })();
   try { return await loading; } finally { loading = null; }
  }
  async function act(path, body = {}) {
   if (acting) throw new Error('正在处理，请稍候。');
   acting = true;
   try {
    if (!state?.token) await load();
    if (!state?.token) throw new Error('页面连接尚未准备好，请重试连接。');
    const response = await fetcher(path, {
     method: 'POST', credentials: 'same-origin',
     headers: {'Content-Type': 'application/json', 'X-Review-Token': state.token},
     body: JSON.stringify(body),
    });
    const result = await response.json();
    if (!response.ok || !result.ok) {
     // Renew a stale session for the next explicit user action. Never replay a mutation.
     if (response.status === 403) { await load(); throw new Error('页面连接已更新，请再试一次。'); }
     throw new Error(message(result.error, '操作没有完成，请稍后重试。'));
    }
    return result;
   } finally { acting = false; }
  }
  return {load, act, get state() { return state; }};
 }
 function mount(document, environment = root) {
  const get = id => document.getElementById(id);
  if (!get('setupDialog') || !get('openSetup')) return null;
  const dialog = get('setupDialog'), cards = new Map();
  const client = createClient(environment.fetch.bind(environment));
  let state = null, timer = null, pending = false, initialRevision, initialEmpty = false, stopped = false;
  const text = (id, value) => { get(id).textContent = value; };
  const hide = (id, value) => { get(id).hidden = !!value; };
  const enable = (id, value) => { get(id).disabled = !value; };
  const schedule = () => {
   if (timer !== null) environment.clearTimeout(timer);
   timer = null;
   if (!stopped && document.visibilityState !== 'hidden' && (dialog.open || busy(state) || downloading(state))) timer = environment.setTimeout(refresh, 2000);
  };
  const welcome = get('setupWelcome');
  get('libraryScroll')?.prepend(welcome);
  function createModelCard(model) {
   const node = document.createElement('article'); node.className = 'setup-model-card';
   const create = (tag, className, parent) => { const item = document.createElement(tag); item.className = className; parent.append(item); return item; };
   const heading = create('div', 'setup-model-heading', node);
   const title = create('h4', '', heading), status = create('span', 'setup-model-state', heading);
   const description = create('p', 'setup-model-description', node);
   const progress = create('progress', '', node); progress.max = 100; progress.setAttribute('aria-label', '模型下载进度');
   const footer = create('div', 'setup-model-footer', node), size = create('p', 'setup-model-size', footer), actions = create('div', 'setup-model-actions', footer);
   const buttons = {};
   for (const [key, label, path] of [
    ['download', '下载模型', '/api/models/download'], ['pause', '暂停下载', '/api/models/pause'],
    ['select', '选用此模型', '/api/models/select'], ['recognize', '开始识别', '/api/recognition/start'],
   ]) {
    const button = create('button', key === 'recognize' ? 'primary' : '', actions); button.textContent = label;
    button.addEventListener('click', () => action(path, {id: model.id})); buttons[key] = button;
   }
   const error = create('p', 'setup-model-error', node); error.setAttribute('role', 'status');
   const card = {node, title, status, description, progress, size, buttons, error};
   cards.set(model.id, card); get('setupModels').append(node); return card;
  }
  function render() {
   if (!state) return;
   const platform = state.platform || {}, library = state.library || {}, job = state.job || {}, models = state.models || [];
   const running = busy(state), available = !pending && !stopped;
   const hasLibrary = !!library.has_scan;
   const changed = initialRevision !== undefined && state.library_revision !== initialRevision;
   const resultsReady = changed && !(job.kind === 'scan' && running);
   welcome.hidden = !initialEmpty;
   for (const id of ['grid', 'loadSentinel']) if (get(id)) get(id).hidden = initialEmpty;
   text('setupWelcomeTitle', resultsReady ? '图库已整理好' : running ? '正在整理你的图库' : platform.folder_mode ? '从照片文件夹开始' : '从这台 Mac 的照片开始');
   text('setupWelcomeOpen', resultsReady ? '查看整理结果' : running ? '查看整理进度' : '开始整理图库');
   text('setupLibrarySummary', hasLibrary ? `${count(library.photos)} 张照片 · ${count(library.videos)} 个视频` : '首次使用，从读取图库开始');
   text('setupScan', hasLibrary ? '重新扫描图库' : '开始整理图库');
   enable('setupScan', !!platform.supported && available && !running && (!platform.folder_mode || !!library.folder));
   if (get('setupFolderControls')) {
    hide('setupFolderControls', !platform.folder_mode);
    text('setupIntro', platform.folder_mode ? '选择本机照片文件夹，在这台电脑完成整理。' : '读取系统照片，在这台电脑完成整理。');
    enable('setupFolder', available && !running);
    text('setupFolderPath', library.folder || '尚未选择文件夹');
    text('setupLibraryHelp', platform.folder_mode ? '选择本机照片目录或已下载的 iCloud 照片文件夹。基础 OCR 使用系统已有语言包；仅在云端的文件会跳过。' : '首次使用时，请按系统提示允许照片访问。基础识别不需要下载模型。');
    if (platform.folder_mode && library.skipped) text('setupLibrarySummary', `${count(library.photos)} 张照片 · ${count(library.videos)} 个视频 · ${count(library.skipped)} 项未下载或不可访问`);
   }
   hide('setupPlatform', !platform.message);
   text('setupPlatform', message(platform.message, '当前设备暂不支持此功能。'));
   hide('setupJob', !job.kind || job.state === 'idle');
   const kind = job.kind === 'recognize' ? '增强识别' : '图库扫描';
   const label = {running: '进行中', stopping: '正在停止', completed: '已完成', failed: '未完成', paused: '已暂停'}[job.state] || '';
   text('setupJobTitle', kind + (label ? ' · ' + label : ''));
   text('setupJobMessage', message(job.message, job.state === 'failed' ? '任务没有完成，可以重试。已完成的结果会保留。' : '处理结果会保存在本机。'));
   const progress = job.progress || {}, total = number(progress.total), processed = Math.min(number(progress.processed), total || Infinity);
   get('setupJobProgress').hidden = !running && !total;
   if (total) get('setupJobProgress').value = Math.min(100, processed / total * 100);
   else get('setupJobProgress').removeAttribute('value');
   text('setupJobCount', total ? `${count(processed)} / ${count(total)}` : running ? '正在准备…' : '');
   hide('setupStop', !running); enable('setupStop', available && job.state !== 'stopping');
   text('setupStop', job.state === 'stopping' ? '正在暂停…' : '暂停任务');
   hide('setupJobRetry', !['failed', 'paused'].includes(job.state));
   text('setupJobRetry', job.state === 'paused' ? '继续' + kind : '重试' + kind);
   const selected = models.find(model => model.selected);
   enable('setupJobRetry', available && (job.kind === 'scan' ? !!platform.supported : !!selected && modelView(selected, state).canRecognize));
   hide('setupResults', !resultsReady);
   get('openSetup').dataset.busy = String(running || downloading(state) || changed);
   get('openSetup').title = changed ? '图库已更新，查看整理结果' : running || downloading(state) ? '查看后台任务进度' : '图库与模型';
   const seen = new Set();
   for (const model of models) {
    if (!model.id || seen.has(model.id)) continue;
    seen.add(model.id);
    const card = cards.get(model.id) || createModelCard(model), view = modelView(model, state);
    card.title.textContent = model.name || model.id; card.status.textContent = view.state;
    card.description.textContent = message(model.description, '在本机增强照片标签识别。');
    card.size.textContent = view.sizeLabel;
    card.progress.hidden = !view.progressVisible;
    if (view.total) card.progress.value = view.downloaded / view.total * 100; else card.progress.removeAttribute('value');
    card.buttons.download.textContent = view.downloadLabel;
    card.buttons.download.hidden = view.ready || view.downloading;
    card.buttons.download.disabled = !platform.model_supported || !available;
    card.buttons.pause.hidden = !view.downloading;
    card.buttons.pause.disabled = !available;
    card.buttons.select.hidden = !view.ready || !!model.selected;
    card.buttons.select.disabled = !available || running;
    card.buttons.recognize.hidden = !view.ready || !model.selected;
    card.buttons.recognize.disabled = !available || !view.canRecognize;
    card.buttons.recognize.textContent = job.kind === 'recognize' && job.state === 'paused' ? '继续识别' : '开始识别';
    card.buttons.recognize.title = !hasLibrary ? '请先完成图库基础扫描' : !number(library.photos) ? '图库中没有可识别的照片' : '';
    card.error.hidden = !model.error;
    card.error.textContent = message(model.error, '下载没有完成。请检查网络后重试，已下载的部分会保留。');
   }
   for (const [id, card] of cards) if (!seen.has(id)) { card.node.remove(); cards.delete(id); }
   hide('setupModelsEmpty', !!models.length);
   hide('setupQuit', !state.packaged);
   enable('setupQuit', available); enable('setupQuitAccept', available);
   enable('setupWelcomeOpen', !stopped);
  }
  async function refresh() {
   if (stopped) return;
   try {
    state = await client.load();
    if (initialRevision === undefined) {
     initialRevision = state.library_revision;
     initialEmpty = !state.library?.has_scan && !number(state.library?.photos) && !number(state.library?.videos);
    }
    hide('setupConnectionError', true); render();
   } catch (error) {
    text('setupConnectionMessage', message(error.message, '暂时无法连接本机程序，请重新打开程序后重试。'));
    hide('setupConnectionError', false);
   } finally { schedule(); }
  }
  async function action(path, body = {}) {
   if (pending || stopped) return;
   pending = true; hide('setupActionError', true); hide('setupActionNotice', true); render();
   try {
    await client.act(path, body);
    if (path === '/api/app/quit') {
     stopped = true; hide('setupQuitConfirm', true);
     text('setupActionNotice', '正在保存进度并退出。下次双击程序即可重新打开。'); hide('setupActionNotice', false);
    } else await refresh();
   } catch (error) {
    text('setupActionError', message(error.message, '操作没有完成，请稍后重试。')); hide('setupActionError', false);
   } finally { pending = false; render(); schedule(); }
  }
  function open(event) {
   // Native dialog handles focus containment, Escape, and return to its invoker.
   if (!event?.detail) document.body.dataset.input = 'keyboard';
   if (!dialog.open) dialog.showModal();
   refresh();
  }
  get('openSetup').addEventListener('click', open);
  get('setupWelcomeOpen').addEventListener('click', event => {
   if (state && state.library_revision !== initialRevision && !(state.job?.kind === 'scan' && busy(state))) environment.location.reload();
   else open(event);
  });
  get('setupClose').addEventListener('click', () => dialog.close());
  dialog.addEventListener('close', () => { hide('setupQuitConfirm', true); schedule(); });
  get('setupRetry').addEventListener('click', refresh);
  get('setupScan').addEventListener('click', () => action('/api/library/scan'));
  get('setupStop').addEventListener('click', () => action('/api/tasks/stop'));
  get('setupJobRetry').addEventListener('click', () => {
   if (state?.job?.kind === 'recognize') {
    const selected = state.models?.find(model => model.selected);
    if (selected) action('/api/recognition/start', {id: selected.id});
   } else action('/api/library/scan');
  });
  get('setupViewResults').addEventListener('click', () => environment.location.reload());
  get('setupFolder')?.addEventListener('click', () => action('/api/library/folder'));
  get('setupQuit').addEventListener('click', () => { hide('setupQuitConfirm', false); get('setupQuitCancel').focus(); });
  get('setupQuitCancel').addEventListener('click', () => { hide('setupQuitConfirm', true); get('setupQuit').focus(); });
  get('setupQuitAccept').addEventListener('click', () => action('/api/app/quit'));
  document.addEventListener('visibilitychange', () => {
   if (document.visibilityState !== 'hidden' && (dialog.open || busy(state) || downloading(state))) refresh();
   else schedule();
  });
  refresh(); // Read status once. Scan and model download always require a user action.
  return {refresh, action, open, client, get state() { return state; }, get cards() { return cards; }};
 }
 const api = {bytes, message, busy, downloading, modelView, createClient, mount};
 if (typeof module === 'object' && module.exports) module.exports = api;
 else if (root.document) mount(root.document);
})(typeof window === 'object' ? window : globalThis);
