// 파일 트리 — 폴더 펼침 · 이름 걸러 내기 · git 상태 색(PyCharm 과 같은 색) · 키보드 이동 · 오른쪽 클릭 메뉴
import { api } from './api.js';
import { $, esc, on, emit, store, toast, copyText, icon, fileBadge, baseName, dirName } from './util.js';
import { contextMenu, promptText } from './popup.js';

const entries = new Map();       // 경로 → { p, d, s, m, lazy, loaded }
const children = new Map();      // 폴더 경로('' = 루트) → 자식 경로 배열
let expanded = new Set(store.get('expanded', []));
let selected = null;
let filter = '';
let gitFiles = new Map();        // 경로 → 상태 글자
let gitDirs = new Map();         // 폴더 → 대표 상태 글자
let ignoredDirs = [];            // 무시된 폴더 접두어
let rootName = '';
let openFileFn = null;
let activePath = null;
let truncated = false;
const GIT_CLS = { M: 'is-mod', A: 'is-add', U: 'is-new', R: 'is-ren', D: 'is-del', '!': 'is-ign', C: 'is-conf' };

export function initTree({ name, openFile }) {
  rootName = name;
  openFileFn = openFile;
  const box = $('#tree');
  box.innerHTML = `<div class="dv-tree-head"><span class="dv-tree-title" title="${esc(name)}">${icon('folder')}${esc(name)}</span>
    <button class="dv-ib" data-t="newFile" title="새 파일">${icon('plus')}</button>
    <button class="dv-ib" data-t="locate" title="열린 파일 위치 (Alt+F1)">${icon('locate')}</button>
    <button class="dv-ib" data-t="collapse" title="모두 접기">${icon('collapse')}</button>
    <button class="dv-ib" data-t="refresh" title="새로고침">${icon('refresh')}</button></div>
    <div class="dv-tree-filter">${icon('search')}<input id="treeFilter" placeholder="이름 걸러 내기" spellcheck="false" autocomplete="off">
    <button class="dv-ib" data-t="clear" title="지우기" hidden>${icon('x')}</button></div>
    <div class="dv-tree-rows" id="treeRows" tabindex="0" role="tree"></div>`;
  const rows = $('#treeRows');
  const input = $('#treeFilter');
  box.addEventListener('click', onClick);
  box.addEventListener('dblclick', (e) => {
    const r = e.target.closest('[data-p]');
    if (r && !entries.get(r.dataset.p)?.d) openFileFn(r.dataset.p);
  });
  rows.addEventListener('contextmenu', onMenu);
  rows.addEventListener('keydown', onKey);
  input.addEventListener('input', () => { filter = input.value.trim(); $('[data-t="clear"]', box).hidden = !filter; render(); });
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') { input.value = ''; filter = ''; $('[data-t="clear"]', box).hidden = true; render(); rows.focus(); }
    if (e.key === 'ArrowDown') { e.preventDefault(); rows.focus(); move(1); }
    if (e.key === 'Enter') { e.preventDefault(); const first = visible()[0]; if (first) { select(first.p); openSel(); } }
  });
  on('git-st', (st) => { gitFiles = st.files; gitDirs = st.dirs; ignoredDirs = st.ignored; render(); });
  on('active-doc', (doc) => { activePath = doc && !doc.readonly ? doc.path : null; render(); });
  on('reveal', (p) => reveal(p));
  return load();
}

// ======= 목록 =======
function add(e) {
  const old = entries.get(e.p);
  entries.set(e.p, { ...e, loaded: old?.loaded || false });
  const parent = dirName(e.p);
  if (!children.has(parent)) children.set(parent, []);
  const list = children.get(parent);
  if (!list.includes(e.p)) list.push(e.p);
}

export async function load() {
  let r;
  try { r = await api('tree'); } catch (e) { toast(`트리 읽기 실패: ${e.message}`, 'bad'); return; }
  const lazyLoaded = [...entries.values()].filter((e) => e.lazy && e.loaded && expanded.has(e.p)).map((e) => e.p);
  entries.clear();
  children.clear();
  for (const e of r.entries) add(e);
  truncated = r.truncated;
  for (const d of lazyLoaded) if (entries.has(d)) await loadDir(d, false);
  for (const p of [...expanded]) if (!entries.has(p)) expanded.delete(p);
  sortAll();
  render();
}

async function loadDir(dir, paint = true) {
  let r;
  try { r = await api('tree', { query: { dir } }); } catch (e) { toast(`폴더 읽기 실패: ${e.message}`, 'bad'); return; }
  children.set(dir, []);
  for (const e of r.entries) add(e);
  const d = entries.get(dir);
  if (d) d.loaded = true;
  sortAll();
  if (paint) render();
}

function sortAll() {
  for (const list of children.values()) {
    list.sort((a, b) => {
      const A = entries.get(a), B = entries.get(b);
      if (!!A?.d !== !!B?.d) return A?.d ? -1 : 1;
      return baseName(a).localeCompare(baseName(b), undefined, { sensitivity: 'base', numeric: true });
    });
  }
}

function gitOf(p, isDir) {
  if (isDir) {
    if (ignoredDirs.some((d) => p === d || p.startsWith(d + '/'))) return '!';
    return gitDirs.get(p) || '';
  }
  const g = gitFiles.get(p);
  if (g) return g;
  if (ignoredDirs.some((d) => p.startsWith(d + '/'))) return '!';
  return '';
}

function visible() {
  if (filter) {
    const q = filter.toLowerCase();
    const out = [];
    for (const e of entries.values()) {
      if (baseName(e.p).toLowerCase().includes(q) || (q.includes('/') && e.p.toLowerCase().includes(q))) {
        out.push({ p: e.p, depth: 0, flat: true });
        if (out.length >= 500) break;
      }
    }
    out.sort((a, b) => a.p.length - b.p.length || a.p.localeCompare(b.p));
    return out;
  }
  const out = [];
  const walk = (dir, depth) => {
    for (const p of children.get(dir) || []) {
      out.push({ p, depth });
      if (entries.get(p)?.d && expanded.has(p)) walk(p, depth + 1);
    }
  };
  walk('', 0);
  return out;
}

function highlight(name) {
  if (!filter) return esc(name);
  const i = name.toLowerCase().indexOf(filter.toLowerCase());
  if (i < 0) return esc(name);
  return `${esc(name.slice(0, i))}<mark>${esc(name.slice(i, i + filter.length))}</mark>${esc(name.slice(i + filter.length))}`;
}

export function render() {
  const rows = $('#treeRows');
  if (!rows) return;
  const vis = visible();
  if (!vis.length) {
    rows.innerHTML = `<div class="dv-tree-empty">${filter ? '일치 없음' : '빈 폴더'}</div>`;
    return;
  }
  rows.innerHTML = vis.map(({ p, depth, flat }) => {
    const e = entries.get(p);
    const g = gitOf(p, e.d);
    const name = baseName(p);
    const open = e.d && expanded.has(p);
    const lead = e.d ? `<span class="dv-chev">${icon(open ? 'chevD' : 'chevR')}</span>${icon('folder', 'dv-folder')}`
      : `<span class="dv-chev"></span>${fileBadge(name)}`;
    const sub = flat && dirName(p) ? `<span class="dv-tr-sub">${esc(dirName(p))}</span>` : '';
    return `<div class="dv-tr${p === selected ? ' is-sel' : ''}${p === activePath ? ' is-open' : ''} ${GIT_CLS[g] || ''}" data-p="${esc(p)}"`
      + ` style="--d:${depth}" role="treeitem" title="${esc(p)}">${lead}<span class="dv-tr-name">${highlight(name)}</span>${sub}`
      + `${e.link ? '<span class="dv-tr-sub">↪</span>' : ''}</div>`;
  }).join('') + (truncated && !filter ? '<div class="dv-tree-empty">항목이 많아 일부만 표시</div>' : '');
}

// ======= 조작 =======
async function toggle(p, openIt) {
  const e = entries.get(p);
  if (!e?.d) return;
  const want = openIt ?? !expanded.has(p);
  if (want) {
    expanded.add(p);
    if (e.lazy && !e.loaded) await loadDir(p, false);
  } else {
    expanded.delete(p);
  }
  store.set('expanded', [...expanded]);
  render();
}

function select(p) {
  selected = p;
  render();
  $('#treeRows .is-sel')?.scrollIntoView({ block: 'nearest' });
}

function openSel() {
  if (!selected) return;
  const e = entries.get(selected);
  if (e?.d) toggle(selected);
  else openFileFn(selected);
}

function move(d) {
  const vis = visible();
  if (!vis.length) return;
  let i = vis.findIndex((v) => v.p === selected);
  i = i < 0 ? 0 : Math.min(Math.max(0, i + d), vis.length - 1);
  select(vis[i].p);
}

function onKey(e) {
  if (e.altKey || e.ctrlKey || e.metaKey) return;
  const cur = entries.get(selected);
  if (e.key === 'ArrowDown') { e.preventDefault(); move(1); }
  else if (e.key === 'ArrowUp') { e.preventDefault(); move(-1); }
  else if (e.key === 'PageDown') { e.preventDefault(); move(15); }
  else if (e.key === 'PageUp') { e.preventDefault(); move(-15); }
  else if (e.key === 'ArrowRight' && cur?.d) {
    e.preventDefault();
    if (!expanded.has(selected)) toggle(selected, true); else { const c = children.get(selected); if (c?.length) select(c[0]); }
  } else if (e.key === 'ArrowLeft') {
    e.preventDefault();
    if (cur?.d && expanded.has(selected)) toggle(selected, false);
    else if (dirName(selected || '')) select(dirName(selected));
  } else if (e.key === 'Enter') { e.preventDefault(); openSel(); }
  else if (e.key === 'Escape') { e.preventDefault(); emit('focus-editor'); }
  else if (e.key.length === 1 && !/\s/.test(e.key)) {
    // 글자를 치면 걸러 내기 칸으로(PyCharm 의 speed search 대신)
    const input = $('#treeFilter');
    input.focus();
    input.value += e.key;
    input.dispatchEvent(new Event('input'));
    e.preventDefault();
  }
}

function onClick(e) {
  const t = e.target.closest('[data-t]')?.dataset.t;
  if (t === 'refresh') { load(); return; }
  if (t === 'collapse') { expanded.clear(); store.set('expanded', []); render(); return; }
  if (t === 'locate') { if (activePath) reveal(activePath); return; }
  if (t === 'newFile') { newItem(selectedDir(), false); return; }
  if (t === 'clear') { const i = $('#treeFilter'); i.value = ''; filter = ''; e.target.closest('[data-t]').hidden = true; render(); return; }
  const r = e.target.closest('[data-p]');
  if (!r) return;
  const p = r.dataset.p;
  selected = p;
  const ent = entries.get(p);
  if (ent?.d) toggle(p);
  else { render(); openFileFn(p); }
  $('#treeRows').focus({ preventScroll: true });
}

function selectedDir() {
  if (!selected) return '';
  return entries.get(selected)?.d ? selected : dirName(selected);
}

async function newItem(dir, isDir) {
  const pre = dir ? `${dir}/` : '';
  const name = await promptText({ title: isDir ? '새 폴더' : '새 파일', value: pre, hint: '작업 폴더 기준 경로 · / 로 하위 폴더까지',
    select: [pre.length, pre.length] });
  if (!name) return;
  try {
    const r = await api('create', { body: { path: name, dir: isDir } });
    await load();
    reveal(r.path);
    if (!isDir) openFileFn(r.path);
  } catch (e) {
    toast(`만들기 실패: ${e.message}`, 'bad');
  }
}

function onMenu(e) {
  const r = e.target.closest('[data-p]');
  e.preventDefault();
  const p = r?.dataset.p || '';
  if (p) { selected = p; render(); }
  const ent = entries.get(p);
  const dir = ent?.d ? p : dirName(p);
  const items = [];
  if (p && !ent?.d) items.push({ label: '열기', key: 'Enter', icon: 'file', act: () => openFileFn(p) }, '-');
  items.push(
    { label: '새 파일', icon: 'plus', act: () => newItem(dir, false) },
    { label: '새 폴더', icon: 'folderPlus', act: () => newItem(dir, true) },
    '-',
  );
  if (p) {
    items.push({ label: '경로 복사', icon: 'copy', act: () => copyText(p, '경로 복사') });
    if (!ent?.d) items.push({ label: 'Git 이력', icon: 'history', act: () => emit('git-file-history', p) });
    items.push('-');
  }
  items.push({ label: '모두 접기', icon: 'collapse', act: () => { expanded.clear(); store.set('expanded', []); render(); } },
    { label: '새로고침', icon: 'refresh', act: () => load() });
  contextMenu(e.clientX, e.clientY, items);
}

export async function reveal(p) {
  if (!p) return;
  emit('show-tree');
  const parts = p.split('/');
  for (let i = 1; i < parts.length; i++) {
    const d = parts.slice(0, i).join('/');
    const e = entries.get(d);
    if (e?.d) {
      expanded.add(d);
      if (e.lazy && !e.loaded) await loadDir(d, false);
    }
  }
  store.set('expanded', [...expanded]);
  if (filter) { filter = ''; $('#treeFilter').value = ''; }
  select(entries.has(p) ? p : dirName(p));
}

export const allFiles = () => [...entries.values()].filter((e) => !e.d).map((e) => e.p);
export const rootLabel = () => rootName;
