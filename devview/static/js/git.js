// Git 탭 — 커밋 목록(브랜치 그래프 · 가상 스크롤) · 검색 · 커밋 상세 · 바뀐 파일 · diff(Monaco) · 파일 이력 · 커밋 안 한 변경
// 읽기 전용. 커밋 · 스테이징은 터미널(Codex) 몫
import { api } from './api.js';
import { $, esc, on, emit, store, debounce, toast, copyText, icon, fileBadge, baseName, dirName, relDate, fmtDate } from './util.js';
import { newGraph, place, rowSvg, graphWidth } from './graph.js';
import { langOf } from './theme.js';
import { openFile, openRev } from './editor.js';
import { contextMenu } from './popup.js';

const ROW = 26;
const PAGE = 400;
let monaco = null;
let repo = false;
let ready = false;
let commits = [];
let rows = [];                    // 그래프 줄(commits 와 같은 순서)
let graph = newGraph();
let more = false;
let loading = false;
let ref = store.get('git.ref', 'all');
let pathFilter = null;            // 파일 이력 모드(저장소 기준 경로)
let status = null;                // git/status 결과
let refs = [];
let refMap = new Map();           // 커밋 해시 → ref 목록
let head = null;
let branch = null;
let items = [];                   // 화면 줄: { local:true } | { i: commits 인덱스 }
let sel = -1;
let search = '';
let hits = [];
let hitAt = -1;
let filterOnly = false;
let detail = null;                // { kind:'commit'|'local', ... files }
let fileSel = -1;
let diffEd = null;
let diffModels = null;
let diffSeq = 0;
let commitSeq = 0;
let prefix = '';                  // 작업 폴더가 저장소 하위 폴더일 때 그 경로
let side = store.get('git.side', true);
let onlyChanged = store.get('git.only', true);
let ignoreWs = store.get('git.ws', false);
let pending = null;               // 목록을 불러온 뒤 고를 커밋 { h, path }

export function initGit(m, info) {
  monaco = m;
  repo = !!info.git?.repo;
  head = info.git?.head || null;
  branch = info.git?.branch || null;
  prefix = info.git?.prefix || '';
  setRefs(info.git?.refs || []);
  const view = $('#gitView');
  if (!repo) {
    view.innerHTML = `<div class="dv-placeholder">${icon('branch')}<p>git 저장소 아님${info.git?.error ? ` — ${esc(info.git.error.split('\n')[0])}` : ''}</p></div>`;
    return;
  }
  view.innerHTML = `
    <div class="dv-git-top" id="gTop">
      <div class="dv-git-bar">
        <select id="gRef" title="보여 줄 브랜치"></select>
        <div class="dv-git-search">${icon('search')}<input id="gSearch" placeholder="메시지 · 해시 · 작성자 (Ctrl+F)" spellcheck="false" autocomplete="off">
          <span id="gHits" class="dv-dim"></span>
          <button class="dv-ib" data-g="prevHit" title="이전 일치 (Shift+Enter)">${icon('up')}</button>
          <button class="dv-ib" data-g="nextHit" title="다음 일치 (Enter)">${icon('down')}</button>
          <button class="dv-tog" data-g="filter" title="일치하는 커밋만 보기">일치만</button></div>
        <span class="dv-git-path" id="gPath" hidden></span>
        <span class="dv-sp"></span>
        <span id="gCount" class="dv-dim"></span>
        <button class="dv-ib" data-g="refresh" title="새로고침">${icon('refresh')}</button>
      </div>
      <div class="dv-git-mid">
        <div class="dv-git-log" id="gLog" tabindex="0"><div class="dv-git-log-inner" id="gLogInner"></div></div>
        <div class="dv-split is-v" data-split="gdetail"></div>
        <div class="dv-git-detail" id="gDetail"><div class="dv-placeholder">${icon('commit')}<p>커밋을 고르면 바뀐 파일</p></div></div>
      </div>
    </div>
    <div class="dv-split is-h" data-split="gdiff"></div>
    <div class="dv-git-diff" id="gDiff">
      <div class="dv-gd-bar" id="gDiffBar"></div>
      <div class="dv-gd-host" id="gDiffHost"></div>
      <div class="dv-placeholder" id="gDiffEmpty">${icon('cols')}<p>파일을 고르면 변경 내용</p></div>
    </div>`;
  paintRefSelect();
  $('#gLog').addEventListener('scroll', () => { paintRows(); if (nearEnd()) loadMore(); });
  $('#gLog').addEventListener('click', onLogClick);
  $('#gLog').addEventListener('contextmenu', onLogMenu);
  $('#gLog').addEventListener('keydown', onLogKey);
  $('#gDetail').addEventListener('click', onDetailClick);
  $('#gDetail').addEventListener('dblclick', (e) => { const f = e.target.closest('[data-f]'); if (f) openWorking(Number(f.dataset.f)); });
  $('#gDetail').addEventListener('keydown', onFilesKey);
  $('#gDiffBar').addEventListener('click', onDiffBar);
  $('#gDiffBar').addEventListener('dblclick', (e) => { if (!e.target.closest('button')) toggleMax(); });
  $('#gRef').addEventListener('change', () => { ref = $('#gRef').value; store.set('git.ref', ref); loadLog(); });
  const input = $('#gSearch');
  input.addEventListener('input', debounce(() => { search = input.value.trim(); applySearch(true); }, 120));
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') { e.preventDefault(); jumpHit(e.shiftKey ? -1 : 1); }
    if (e.key === 'Escape') { input.value = ''; search = ''; applySearch(); $('#gLog').focus(); }
    if (e.key === 'ArrowDown') { e.preventDefault(); $('#gLog').focus(); }
  });
  view.addEventListener('click', (e) => {
    const g = e.target.closest('[data-g]')?.dataset.g;
    if (g === 'refresh') { reload(); }
    else if (g === 'prevHit') jumpHit(-1);
    else if (g === 'nextHit') jumpHit(1);
    else if (g === 'filter') { filterOnly = !filterOnly; e.target.closest('[data-g]').classList.toggle('is-on', filterOnly); applySearch(); }
    else if (g === 'clearPath') { setPath(null); }
  });
  view.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'f' && !e.target.closest('.monaco-editor')) {
      e.preventDefault();
      input.focus();
      input.select();
    }
    if (e.key === 'F7' && diffEd) { e.preventDefault(); diffEd.goToDiff(e.shiftKey ? 'previous' : 'next'); }
  });
  on('git-st', (st) => { status = st.raw; if (ready) { rebuildItems(true); if (detail?.kind === 'local') refreshLocalDetail(); } });
  on('git-changed', () => { if (ready) reloadSoon(); });
  on('git-show', ({ h: hash, path }) => showFromOutside(hash, path));
  on('git-file-history', (p) => { emit('show-view', 'git'); setPath(p); });
  on('view', (v) => { if (v === 'git') activateView(); });
}

function activateView() {
  if (!repo) return;
  if (!ready) { ready = true; loadLog(); }
  setTimeout(() => { paintRows(); diffEd?.layout(); }, 0);
  if (!document.activeElement?.closest?.('#gitView')) $('#gLog')?.focus({ preventScroll: true });
}

function setRefs(list) {
  refs = list;
  refMap = new Map();
  for (const r of list) {
    if (!refMap.has(r.hash)) refMap.set(r.hash, []);
    refMap.get(r.hash).push(r);
  }
}

function paintRefSelect() {
  const s = $('#gRef');
  if (!s) return;
  const opt = (v, label) => `<option value="${esc(v)}"${v === ref ? ' selected' : ''}>${esc(label)}</option>`;
  const group = (t, kind) => {
    const list = refs.filter((r) => r.type === kind);
    return list.length ? `<optgroup label="${t}">${list.map((r) => opt(r.short, r.short)).join('')}</optgroup>` : '';
  };
  s.innerHTML = opt('all', '모든 브랜치') + opt('head', 'HEAD') + group('로컬 브랜치', 'branch') + group('원격', 'remote') + group('태그', 'tag');
  if (![...s.options].some((o) => o.value === ref)) { ref = 'all'; s.value = 'all'; }
}

// ======= 불러오기 =======
const reloadSoon = debounce(() => reload(), 300);
async function reload() {
  try {
    const info = await api('git/info');
    head = info.head;
    branch = info.branch;
    setRefs(info.refs || []);
    paintRefSelect();
    emit('git-branch', branch);
  } catch { /* 목록만이라도 */ }
  await loadLog();
}

async function loadLog() {
  if (loading) return;
  loading = true;
  const keep = currentKey();
  try {
    let r;
    if (pathFilter) r = await api('git/file-log', { query: { gpath: pathFilter, limit: 1000 } });
    else r = await api('git/log', { query: { ref, limit: PAGE } });
    commits = r.commits;
    more = !!r.more && !pathFilter;
    graph = newGraph();
    rows = pathFilter ? commits.map(() => null) : place(graph, commits);
    if (r.head !== undefined) head = r.head;
  } catch (e) {
    toast(`git 이력 읽기 실패: ${e.message}`, 'bad');
    commits = [];
    rows = [];
  } finally {
    loading = false;
  }
  rebuildItems(false);
  if (pending) {
    const p = pending;
    pending = null;
    selectHash(p.h, p.path);
  } else if (keep) {
    const i = items.findIndex((it) => keyOf(it) === keep);
    if (i >= 0) { sel = i; paintRows(); } else if (items.length) select(0);
  } else if (items.length) {
    select(0);
  }
  applySearch();
}

async function loadMore() {
  if (!more || loading || pathFilter) return;
  loading = true;
  try {
    const r = await api('git/log', { query: { ref, limit: PAGE, skip: commits.length } });
    const add = r.commits.filter((c) => !commits.some((x) => x.h === c.h));
    commits.push(...add);
    rows.push(...place(graph, add));
    more = !!r.more;
  } catch (e) {
    more = false;
  } finally {
    loading = false;
  }
  rebuildItems(true);
  applySearch();
}

const nearEnd = () => { const l = $('#gLog'); return l && l.scrollTop + l.clientHeight > l.scrollHeight - ROW * 30; };

const keyOf = (it) => (!it ? null : it.local ? 'local' : commits[it.i]?.h);
const currentKey = () => keyOf(items[sel]);

function localChanges() {
  return status?.changes?.length && !pathFilter ? status.changes.length : 0;
}

function rebuildItems(keepSel) {
  const keep = keepSel ? currentKey() : null;
  items = [];
  if (localChanges()) items.push({ local: true });
  const showHits = filterOnly && search;
  commits.forEach((c, i) => { if (!showHits || matches(c)) items.push({ i }); });
  if (keep) { const k = items.findIndex((it) => keyOf(it) === keep); sel = k >= 0 ? k : Math.min(sel, items.length - 1); }
  const inner = $('#gLogInner');
  if (inner) inner.style.height = `${items.length * ROW}px`;
  $('#gCount').textContent = pathFilter ? `커밋 ${commits.length}개` : `커밋 ${commits.length}${more ? '+' : ''}개`;
  paintRows();
}

// ======= 목록 그리기(보이는 줄만) =======
function refBadges(hash) {
  const list = refMap.get(hash) || [];
  let out = '';
  if (hash === head) {
    out += `<span class="dv-ref is-head" title="HEAD">${branch ? `HEAD → ${esc(branch)}` : 'HEAD'}</span>`;
  }
  for (const r of list) {
    if (r.type === 'branch' && r.short === branch && hash === head) continue;
    out += `<span class="dv-ref is-${r.type}" title="${esc(r.name)}">${r.type === 'tag' ? icon('tag') : ''}${esc(r.short)}</span>`;
  }
  return out;
}

function paintRows() {
  const log = $('#gLog');
  const inner = $('#gLogInner');
  if (!log || !inner || !log.clientHeight) return;
  const first = Math.max(0, Math.floor(log.scrollTop / ROW) - 10);
  const last = Math.min(items.length, Math.ceil((log.scrollTop + log.clientHeight) / ROW) + 10);
  const gw = pathFilter || (filterOnly && search) ? 0 : graphWidth(graph.max);
  const hitSet = new Set(hits);
  let html = '';
  for (let k = first; k < last; k++) {
    const it = items[k];
    const cls = `dv-gr${k === sel ? ' is-sel' : ''}${hitSet.has(k) ? ' is-hit' : ''}${k === hits[hitAt] ? ' is-cur' : ''}`;
    if (it.local) {
      html += `<div class="${cls} is-local" style="top:${k * ROW}px" data-k="${k}"><span class="dv-gr-graph" style="width:${gw}px">`
        + `${gw ? `<svg width="${gw}" height="${ROW}"><circle cx="10" cy="${ROW / 2}" r="4" fill="none" stroke="#868a91" stroke-width="1.6" stroke-dasharray="2 2"/></svg>` : ''}</span>`
        + `<span class="dv-gr-msg">커밋하지 않은 변경 <b>${localChanges()}</b></span><span class="dv-gr-author"></span><span class="dv-gr-date"></span></div>`;
      continue;
    }
    const c = commits[it.i];
    html += `<div class="${cls}" style="top:${k * ROW}px" data-k="${k}" title="${esc(c.h.slice(0, 10))} · ${esc(c.an)} · ${esc(fmtDate(c.at))}">`
      + `<span class="dv-gr-graph" style="width:${gw}px">${gw ? rowSvg(rows[it.i], ROW, gw, c.h === head) : ''}</span>`
      + `<span class="dv-gr-msg">${refBadges(c.h)}<span class="dv-gr-s">${esc(c.s)}</span></span>`
      + `<span class="dv-gr-author">${esc(c.an)}</span><span class="dv-gr-date">${esc(relDate(c.at))}</span></div>`;
  }
  inner.innerHTML = html;
}

// ======= 검색 =======
function matches(c) {
  const q = search.toLowerCase();
  return c.s.toLowerCase().includes(q) || c.h.startsWith(q) || c.an.toLowerCase().includes(q) || (c.ae || '').toLowerCase().includes(q);
}
function applySearch(jump = false) {
  if (filterOnly) rebuildItems(true);
  hits = [];
  if (search) items.forEach((it, k) => { if (!it.local && matches(commits[it.i])) hits.push(k); });
  hitAt = hits.length ? Math.max(0, hits.findIndex((k) => k >= sel)) : -1;
  const el = $('#gHits');
  if (el) el.textContent = search ? (hits.length ? `${hitAt + 1}/${hits.length}` : '0건') : '';
  if (jump && hits.length) select(hits[hitAt]);
  else paintRows();
}
function jumpHit(d) {
  if (!hits.length) return;
  hitAt = (hitAt + d + hits.length) % hits.length;
  $('#gHits').textContent = `${hitAt + 1}/${hits.length}`;
  select(hits[hitAt]);
}

// ======= 고르기 =======
function select(k, { file = null } = {}) {
  if (k < 0 || k >= items.length) return;
  sel = k;
  const log = $('#gLog');
  const top = k * ROW;
  if (top < log.scrollTop) log.scrollTop = top;
  else if (top + ROW > log.scrollTop + log.clientHeight) log.scrollTop = top + ROW - log.clientHeight;
  paintRows();
  const it = items[k];
  if (it.local) showLocal();
  else showCommit(commits[it.i].h, { file: file ?? (pathFilter ? commits[it.i].fpath || pathFilter : null) });
}

async function selectHash(hash, path) {
  const k = items.findIndex((it) => !it.local && commits[it.i].h.startsWith(hash));
  if (k >= 0) { select(k, { file: path ? gitPathOf(path) : null }); return; }
  // 목록 밖(오래된 커밋) — 상세만
  showCommit(hash, { file: path ? gitPathOf(path) : null });
}

function gitPathOf(local) {
  return prefix ? `${prefix}/${local}` : local;
}

function showFromOutside(hash, path) {
  emit('show-view', 'git');
  if (!ready) { ready = true; pending = { h: hash, path }; loadLog(); return; }
  if (pathFilter) setPath(null);
  selectHash(hash, path);
}

function setPath(local, gpath = null) {
  pathFilter = gpath || (local ? gitPathOf(local) : null);
  const el = $('#gPath');
  if (el) {
    el.hidden = !pathFilter;
    el.innerHTML = pathFilter ? `${icon('history')}파일 이력: <b>${esc(local || pathFilter)}</b><button class="dv-ib" data-g="clearPath" title="전체 이력으로">${icon('x')}</button>` : '';
  }
  ready = true;
  sel = -1;
  loadLog();
}

// ======= 커밋 상세 =======
async function showCommit(hash, { parent = 0, file = null } = {}) {
  const my = ++commitSeq;
  let r;
  try {
    r = await api('git/commit', { query: { h: hash, parent } });
  } catch (e) {
    toast(`커밋 읽기 실패: ${e.message}`, 'bad');
    return;
  }
  if (my !== commitSeq) return;
  detail = { kind: 'commit', ...r };
  fileSel = r.files.length ? 0 : -1;
  if (file) {
    const i = r.files.findIndex((f) => f.path === file || f.old === file);
    if (i >= 0) fileSel = i;
  }
  paintDetail();
  showDiff();
}

function showLocal() {
  ++commitSeq;
  detail = { kind: 'local', files: status?.changes || [] };
  fileSel = detail.files.length ? Math.min(Math.max(0, fileSel), detail.files.length - 1) : -1;
  paintDetail();
  showDiff();
}

function refreshLocalDetail() {
  const keep = detail.files[fileSel]?.path;
  detail = { kind: 'local', files: status?.changes || [] };
  const i = detail.files.findIndex((f) => f.path === keep);
  fileSel = i >= 0 ? i : detail.files.length ? 0 : -1;
  paintDetail();
  showDiff();
}

const ST_LABEL = { M: '수정', A: '추가', D: '삭제', R: '이름 변경', C: '복사', T: '종류 변경', U: '새 파일' };
const ST_CLS = { M: 'is-mod', A: 'is-add', D: 'is-del', R: 'is-ren', C: 'is-add', T: 'is-mod', U: 'is-new' };

function paintDetail() {
  const box = $('#gDetail');
  const d = detail;
  if (!d) return;
  const files = d.files || [];
  const plus = files.reduce((s, f) => s + (f.add || 0), 0);
  const minus = files.reduce((s, f) => s + (f.dele || 0), 0);
  let head1 = '';
  if (d.kind === 'commit') {
    const lines = d.msg.split('\n');
    const subject = lines[0];
    const body = lines.slice(1).join('\n').trim();
    const parents = d.p.map((p, i) => `<a class="dv-hash${i === d.parent ? ' is-on' : ''}" data-parent="${i}" title="${d.p.length > 1 ? '이 부모 기준으로 비교' : '부모 커밋'}">${esc(p.slice(0, 8))}</a>`).join(' ');
    head1 = `<div class="dv-cd-msg"><div class="dv-cd-subject">${esc(subject)}</div>${body ? `<pre class="dv-cd-body">${esc(body)}</pre>` : ''}</div>
      <div class="dv-cd-meta">
        <div><span class="dv-dim">커밋</span><a class="dv-hash" data-copy="${esc(d.h)}" title="해시 복사">${esc(d.h.slice(0, 10))}${icon('copy')}</a>${refBadges(d.h)}</div>
        <div><span class="dv-dim">작성</span>${esc(d.an)} <span class="dv-dim">&lt;${esc(d.ae)}&gt;</span></div>
        <div><span class="dv-dim">날짜</span>${esc(fmtDate(d.at))} <span class="dv-dim">(${esc(relDate(d.at))})</span></div>
        ${d.cn !== d.an || Math.abs(d.ct - d.at) > 60 ? `<div><span class="dv-dim">커밋한 이</span>${esc(d.cn)} · ${esc(fmtDate(d.ct))}</div>` : ''}
        ${d.p.length ? `<div><span class="dv-dim">부모</span>${parents}${d.p.length > 1 ? '<span class="dv-dim"> 병합 — 고른 부모 기준</span>' : ''}</div>` : '<div><span class="dv-dim">부모</span>없음 (첫 커밋)</div>'}
      </div>`;
  } else {
    head1 = `<div class="dv-cd-msg"><div class="dv-cd-subject">커밋하지 않은 변경</div>
      <div class="dv-dim">HEAD${status?.branch ? ` (${esc(status.branch)})` : ''} 와 작업 폴더 비교 · 스테이징 포함</div></div>`;
  }
  const rowsHtml = files.map((f, i) => {
    const name = baseName(f.path);
    const dir = dirName(f.path);
    const ren = f.old ? `<span class="dv-dim"> ← ${esc(f.old)}</span>` : '';
    const nums = f.binary ? '<span class="dv-dim">바이너리</span>'
      : `${f.add ? `<span class="dv-plus">+${f.add}</span>` : ''}${f.dele ? `<span class="dv-minus">−${f.dele}</span>` : ''}`;
    return `<div class="dv-cf${i === fileSel ? ' is-sel' : ''} ${ST_CLS[f.st] || ''}" data-f="${i}" title="${esc(ST_LABEL[f.st] || f.st)} · ${esc(f.path)}">`
      + `<span class="dv-cf-st">${esc(f.st)}</span>${fileBadge(name)}<span class="dv-cf-name">${esc(name)}</span>`
      + `<span class="dv-cf-dir">${esc(dir)}${ren}</span><span class="dv-cf-num">${nums}</span></div>`;
  }).join('');
  box.innerHTML = `${head1}<div class="dv-cd-files-head">바뀐 파일 <b>${files.length}</b>${plus ? ` <span class="dv-plus">+${plus}</span>` : ''}${minus ? ` <span class="dv-minus">−${minus}</span>` : ''}</div>`
    + `<div class="dv-cd-files" tabindex="0">${rowsHtml || '<div class="dv-placeholder"><p>바뀐 파일 없음</p></div>'}</div>`;
}

function onDetailClick(e) {
  const c = e.target.closest('[data-copy]');
  if (c) { copyText(c.dataset.copy, '해시 복사'); return; }
  const p = e.target.closest('[data-parent]');
  if (p && detail?.kind === 'commit') {
    const i = Number(p.dataset.parent);
    if (detail.p.length > 1 && i !== detail.parent) showCommit(detail.h, { parent: i });
    else selectHash(detail.p[i]);
    return;
  }
  const f = e.target.closest('[data-f]');
  if (f) { fileSel = Number(f.dataset.f); paintDetail(); showDiff(); $('#gDetail .dv-cd-files')?.focus({ preventScroll: true }); }
}

function onFilesKey(e) {
  if (!detail?.files?.length) return;
  if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
    e.preventDefault();
    fileSel = Math.min(Math.max(0, fileSel + (e.key === 'ArrowDown' ? 1 : -1)), detail.files.length - 1);
    paintDetail();
    $('#gDetail .dv-cd-files')?.focus({ preventScroll: true });
    $('#gDetail .dv-cf.is-sel')?.scrollIntoView({ block: 'nearest' });
    showDiff();
  } else if (e.key === 'Enter') { e.preventDefault(); openWorking(fileSel); }
  else if (e.key === 'ArrowLeft' || e.key === 'Escape') { e.preventDefault(); $('#gLog').focus(); }
}

// ======= diff =======
function ensureDiff() {
  if (diffEd) return diffEd;
  const fs = store.get('font', 13);
  diffEd = monaco.editor.createDiffEditor($('#gDiffHost'), {
    theme: 'pycharm-dark', automaticLayout: true, readOnly: true, originalEditable: false, renderSideBySide: side,
    useInlineViewWhenSpaceIsLimited: true, renderSideBySideInlineBreakpoint: 700, ignoreTrimWhitespace: ignoreWs,
    hideUnchangedRegions: { enabled: onlyChanged, contextLineCount: 3, minimumLineCount: 3, revealLineCount: 20 },
    fontFamily: '"JetBrains Mono", D2Coding, Consolas, "Malgun Gothic", monospace', fontSize: fs, lineHeight: Math.round(fs * 1.54),
    minimap: { enabled: false }, scrollBeyondLastLine: false, renderOverviewRuler: true, renderMarginRevertIcon: false,
    unicodeHighlight: { ambiguousCharacters: false, invisibleCharacters: false }, links: false, stickyScroll: { enabled: false },
  });
  return diffEd;
}

async function fetchSide(spec) {
  // spec: { rev, gpath } | { local } | { empty:true }
  if (spec.empty) return { content: '' };
  if (spec.local) return api('file', { query: { path: spec.local } });
  return api('git/blob', { query: { rev: spec.rev, gpath: spec.gpath } });
}

async function showDiff() {
  paintDiffBar();
  const f = detail?.files?.[fileSel];
  const my = ++diffSeq;
  if (!f) { setDiffEmpty('파일을 고르면 변경 내용'); return; }
  let left, right;
  if (detail.kind === 'commit') {
    left = f.st === 'A' || !detail.base ? { empty: true } : { rev: detail.base, gpath: f.old || f.path };
    right = f.st === 'D' ? { empty: true } : { rev: detail.h, gpath: f.path };
  } else {
    // 새 파일(U · A)은 HEAD 에 없음 → 빈 왼쪽. 없는 경로는 서버가 missing 으로 답해 빈 내용 처리
    left = f.st === 'U' || !status?.head ? { empty: true } : { rev: 'HEAD', gpath: f.old || f.path };
    right = f.st === 'D' ? { empty: true } : f.local ? { local: f.local } : { empty: true };
  }
  let a, b;
  try {
    [a, b] = await Promise.all([fetchSide(left), fetchSide(right)]);
  } catch (e) {
    if (my === diffSeq) setDiffEmpty(`읽기 실패: ${e.message}`);
    return;
  }
  if (my !== diffSeq) return;
  if (a.binary || b.binary) { setDiffEmpty('바이너리 파일 — 내용 비교 안 함'); return; }
  if (a.too_large || b.too_large) { setDiffEmpty('5MB 넘는 파일 — 내용 비교 안 함'); return; }
  const lang = langOf(f.path);
  const ed = ensureDiff();
  $('#gDiffEmpty').hidden = true;
  $('#gDiffHost').hidden = false;
  const old = diffModels;
  diffModels = { original: monaco.editor.createModel(a.missing ? '' : a.content ?? '', lang), modified: monaco.editor.createModel(b.missing ? '' : b.content ?? '', lang) };
  ed.setModel(diffModels);
  if (old) { old.original.dispose(); old.modified.dispose(); }
  // 첫 변경 위치로
  const once = ed.onDidUpdateDiff(() => {
    once.dispose();
    const ch = ed.getLineChanges?.() || [];
    if (ch.length) ed.getModifiedEditor().revealLineNearTop(Math.max(1, ch[0].modifiedStartLineNumber || ch[0].originalStartLineNumber));
  });
}

function setDiffEmpty(msg) {
  $('#gDiffHost').hidden = true;
  const e = $('#gDiffEmpty');
  e.hidden = false;
  e.querySelector('p').textContent = msg;
}

function paintDiffBar() {
  const bar = $('#gDiffBar');
  const f = detail?.files?.[fileSel];
  const tog = (k, on2, label, title) => `<button class="dv-tog${on2 ? ' is-on' : ''}" data-d="${k}" title="${esc(title)}">${esc(label)}</button>`;
  const btn = (k, ic, label, title, dis = false) => `<button class="dv-cb" data-d="${k}" title="${esc(title)}"${dis ? ' disabled' : ''}>${icon(ic)}<span>${esc(label)}</span></button>`;
  const where = !f ? '' : detail.kind === 'commit'
    ? `<span class="dv-dim">${detail.base ? esc(detail.base.slice(0, 7)) : '빈 판'} → ${esc(detail.h.slice(0, 7))}</span>`
    : '<span class="dv-dim">HEAD → 작업 폴더</span>';
  bar.innerHTML = `<span class="dv-gd-title">${f ? `${fileBadge(baseName(f.path))}<b>${esc(f.path)}</b>${f.old ? `<span class="dv-dim"> ← ${esc(f.old)}</span>` : ''} ${where}` : '<span class="dv-dim">변경 내용</span>'}</span>`
    + '<span class="dv-sp"></span>'
    + `<button class="dv-ib" data-d="prev" title="이전 변경 (Shift+F7)">${icon('up')}</button><button class="dv-ib" data-d="next" title="다음 변경 (F7)">${icon('down')}</button>`
    + tog('side', side, '나란히', '나란히 / 한 줄로 보기')
    + tog('only', onlyChanged, '바뀐 부분만', '바뀌지 않은 부분 접기')
    + tog('ws', ignoreWs, '공백 무시', '줄 앞뒤 공백 차이 무시')
    + btn('open', 'open', '열기', '작업 폴더의 지금 파일 열기 (Enter)', !f?.local || f.st === 'D')
    + (detail?.kind === 'commit' ? btn('rev', 'eye', '이 판', '이 커밋 시점의 파일 보기', !f || f.st === 'D') : '')
    + btn('hist', 'history', '이력', '이 파일의 이력만 보기', !f)
    + `<button class="dv-ib" data-d="max" title="크게 / 원래대로 (막대 더블클릭)">${icon('fold')}</button>`;
}

function onDiffBar(e) {
  const d = e.target.closest('[data-d]')?.dataset.d;
  if (!d) return;
  const f = detail?.files?.[fileSel];
  if (d === 'prev' || d === 'next') { diffEd?.goToDiff(d === 'next' ? 'next' : 'previous'); diffEd?.getModifiedEditor().focus(); }
  else if (d === 'side') { side = !side; store.set('git.side', side); diffEd?.updateOptions({ renderSideBySide: side }); paintDiffBar(); }
  else if (d === 'only') { onlyChanged = !onlyChanged; store.set('git.only', onlyChanged); diffEd?.updateOptions({ hideUnchangedRegions: { enabled: onlyChanged } }); paintDiffBar(); }
  else if (d === 'ws') { ignoreWs = !ignoreWs; store.set('git.ws', ignoreWs); diffEd?.updateOptions({ ignoreTrimWhitespace: ignoreWs }); paintDiffBar(); }
  else if (d === 'open') openWorking(fileSel);
  else if (d === 'rev' && f) openRev(detail.h, f.local, f.path, detail.h.slice(0, 8));
  else if (d === 'hist' && f) setPath(f.local, f.path);
  else if (d === 'max') toggleMax();
}

function toggleMax() {
  $('#gitView').classList.toggle('is-diffmax');
  diffEd?.layout();
}

function openWorking(i) {
  const f = detail?.files?.[i];
  if (!f?.local || f.st === 'D') { toast('작업 폴더에 없는 파일'); return; }
  let line = null;
  const ch = diffEd?.getLineChanges?.() || [];
  const cur = diffEd?.getModifiedEditor().getPosition();
  if (cur && cur.lineNumber > 1) line = cur.lineNumber;
  else if (ch.length) line = ch[0].modifiedStartLineNumber || null;
  emit('show-view', 'code');
  openFile(f.local, line ? { line } : {});
}

// ======= 목록 조작 =======
function onLogClick(e) {
  const r = e.target.closest('[data-k]');
  if (r) select(Number(r.dataset.k));
  $('#gLog').focus({ preventScroll: true });
}

function onLogKey(e) {
  if (e.altKey || e.ctrlKey || e.metaKey) return;
  if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
    e.preventDefault();
    select(Math.min(Math.max(0, sel + (e.key === 'ArrowDown' ? 1 : -1)), items.length - 1));
  } else if (e.key === 'PageDown' || e.key === 'PageUp') {
    e.preventDefault();
    const n = Math.max(1, Math.floor($('#gLog').clientHeight / ROW) - 1);
    select(Math.min(Math.max(0, sel + (e.key === 'PageDown' ? n : -n)), items.length - 1));
  } else if (e.key === 'Home') { e.preventDefault(); select(0); }
  else if (e.key === 'End') { e.preventDefault(); select(items.length - 1); }
  else if (e.key === 'Enter' || e.key === 'ArrowRight') { e.preventDefault(); $('#gDetail .dv-cd-files')?.focus(); }
}

function onLogMenu(e) {
  const r = e.target.closest('[data-k]');
  if (!r) return;
  e.preventDefault();
  const k = Number(r.dataset.k);
  const it = items[k];
  if (!it || it.local) return;
  const c = commits[it.i];
  contextMenu(e.clientX, e.clientY, [
    { label: '해시 복사', icon: 'copy', act: () => copyText(c.h, '해시 복사') },
    { label: '짧은 해시 복사', act: () => copyText(c.h.slice(0, 8), '해시 복사') },
    { label: '메시지 복사', act: () => copyText(c.s, '메시지 복사') },
    '-',
    { label: '이 커밋 고르기', act: () => select(k) },
  ]);
}
