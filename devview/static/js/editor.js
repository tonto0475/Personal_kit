// 코드 탭 편집 영역 — 탭 · Monaco(코드) · md 편집기 · 그림/표 보기 · 충돌 띠 · 상태 표시줄 · 이동 기록 · PyCharm 키맵
import { api, rawUrl } from './api.js';
import { $, $$, h, esc, on, emit, store, debounce, toast, copyText, icon, fileBadge, baseName, dirName, extOf, clamp } from './util.js';
import { LANG_LABEL } from './theme.js';
import { initDocs, openDoc, openRevDoc, getDoc, closeDoc, save, isDirty, statusOf, textOf, takeDisk, keepMine,
  mdEdited } from './docs.js';
import { initChanges, attachDoc, detachDoc, gotoChange, hunkCount, hidePopup,
  bindEditor as bindChanges, useEditor as useChanges } from './changes.js';
import { initBlame, toggleBlame, isOn as blameOn, applyFor as applyBlame,
  bindEditor as bindBlame, useEditor as useBlame } from './blame.js';
import { pickList, contextMenu, openModal } from './popup.js';

let monaco = null;
// 아래 넷은 «지금 칸»(cur) 것 — 칸을 옮길 때 usePane() 이 바꿔 끼운다
let ed = null;
let tabs = [];                   // 열린 탭(경로) 순서
let active = null;
let views = new Map();           // 경로 → Monaco 보기 상태
// 칸 — [0] = index.html 의 왼쪽(id 있는 것) · [1] = 그것을 복제한 칸. 파일 하나는 한 칸에만 열림
const panes = [];
let cur = null;
let restoreRight = new Set();    // 다시 열 때 오른쪽 칸으로 갈 경로(저장값 split)
let restoreSplit = null;
let gitMap = new Map();          // 경로 → 상태 글자(M A U D R ! C)
let gitRepo = false;
let branch = '';
let fontSize = clamp(store.get('font', 13), 9, 28);
let mdFont = clamp(store.get('mdfont', 15), 11, 26);
let wrap = !!store.get('wrap', false);
const tableView = new Set();     // 표로 보는 CSV 경로
const navBack = [];
const navFwd = [];
let lastFocus = 'none';          // 'monaco' · 'md' · 'tree'

const STATUS_LABEL = { saved: '저장됨', dirty: '저장 안 됨', saving: '저장 중…', failed: '저장 실패', conflict: '외부 변경 충돌',
  deleted: '디스크에서 삭제됨' };
const ENC_LABEL = { 'utf-8': 'UTF-8', 'utf-8-sig': 'UTF-8 BOM', cp949: 'CP949', binary: '바이너리' };
export const GIT_COLOR = { M: 'is-mod', A: 'is-add', U: 'is-new', R: 'is-ren', D: 'is-del', '!': 'is-ign', C: 'is-conf' };

const lineHeightOf = (fs) => Math.round(fs * 1.54);
const EDITOR_OPTS = () => ({
  theme: 'pycharm-dark', fontFamily: '"JetBrains Mono", D2Coding, Consolas, "Malgun Gothic", monospace', fontSize,
  lineHeight: lineHeightOf(fontSize), fontLigatures: false, minimap: { enabled: false }, automaticLayout: true,
  scrollBeyondLastLine: true, padding: { top: 6 }, fixedOverflowWidgets: true, wordWrap: wrap ? 'on' : 'off',
  unicodeHighlight: { ambiguousCharacters: false, invisibleCharacters: false },   // 한글 · 전각 문자 상자 표시 끔
  renderLineHighlight: 'all', tabSize: 4, insertSpaces: true, detectIndentation: true, autoIndent: 'full',
  rulers: [120], guides: { indentation: true, highlightActiveIndentation: true, bracketPairs: false },
  bracketPairColorization: { enabled: false }, matchBrackets: 'always', occurrencesHighlight: 'singleFile',
  renderWhitespace: 'selection', folding: true, showFoldingControls: 'mouseover', lineDecorationsWidth: 12,
  stickyScroll: { enabled: true, defaultModel: 'indentationModel', maxLineCount: 4 }, links: false,
  wordBasedSuggestions: 'allDocuments', smoothScrolling: false, cursorSmoothCaretAnimation: 'off',
  mouseWheelZoom: false, contextmenu: true, model: null, ariaLabel: '코드 편집기',
});

// ======= 시작 =======
export function initEditor(m, info) {
  monaco = m;
  gitRepo = !!info.git?.repo;
  branch = info.git?.branch || '';
  // 오른쪽 칸 = 왼쪽 칸 복제(아직 비어 있을 때) — id 를 지워 시험 · 다른 모듈이 보는 #tabs 등은 왼쪽 그대로
  const left = $('#paneL');
  const right = left.cloneNode(true);
  right.removeAttribute('id');
  right.classList.remove('is-cur');
  right.querySelectorAll('[id]').forEach((el) => el.removeAttribute('id'));
  right.hidden = true;
  const bar = h('<div class="dv-psplit" title="끌어서 폭 조절 · 두 번 클릭: 반반" hidden></div>');
  left.after(bar, right);
  left.style.order = '0';
  right.style.order = '2';
  panes.push(makePane(left), makePane(right));
  panes.splitter = bar;
  initSplitter(bar);
  initDrag();
  const sp = store.get('split', null);
  if (sp && Array.isArray(sp.right)) { restoreSplit = sp; restoreRight = new Set(sp.right); }

  ed = createEditor(panes[0]);
  initDocs(monaco, makeMd);
  initChanges(monaco, ed, gitRepo);
  initBlame(monaco, ed);
  installKeymap();
  addActions(ed);
  usePane(panes[0]);
  document.documentElement.style.setProperty('--dv-md-size', `${mdFont}px`);

  on('doc-status', (doc) => {
    const p = paneOf(doc.path);
    if (p) paintTabs();
    if (p && p.active === doc.path) { paintBanner(p); if (p === cur) paintStatus(); }
  });
  on('doc-reloaded', (doc) => {
    const p = paneOf(doc.path);
    if (!p || p.active !== doc.path) return;
    if (doc.kind === 'image') showOther(doc, p);
    if (tableView.has(doc.path)) renderTable(doc, p);
  });
  on('doc-edit', (doc) => { const p = paneOf(doc.path); if (p && p.active === doc.path && tableView.has(doc.path)) tableSoon(doc, p); });
  on('git-status', (map) => { gitMap = map; paintTabs(); });
  on('git-branch', (b) => { branch = b || ''; paintStatus(); });
  on('blame', () => paintStatus());
  on('hunks', (doc) => { if (doc.path === active) paintStatus(); });

  for (const p of panes) bindPane(p);
  $('#status').addEventListener('click', onStatusClick);
  window.addEventListener('beforeunload', (e) => {
    const dirty = panes.flatMap((p) => p.tabs).map(getDoc).filter((d) => d && isDirty(d) && d.status !== 'conflict');
    if (!dirty.length) return;
    // 페이지를 떠나는 순간에도 저장 요청은 끝까지 전송(keepalive)
    for (const d of dirty) {
      fetch('api/save', { method: 'POST', keepalive: true, headers: { 'Content-Type': 'application/json', 'X-Devview': '1' },
        body: JSON.stringify({ path: d.path, content: textOf(d), base: d.hash, encoding: d.encoding, eol: d.eol }) });
    }
    e.preventDefault();
    e.returnValue = '';
  });
  paintAll();
  return ed;
}

export const editor = () => ed;
export const activePath = () => active;
export const activeDoc = () => getDoc(active);
export const openTabs = () => [...tabs];
export const focusedEditor = () => lastFocus;

// ======= 칸(나눠 보기) =======
function makePane(root) {
  const q = (s) => root.querySelector(s);
  return { root, tabs: [], active: null, views: new Map(), ed: null,
    el: { tabs: q('.dv-tabs'), crumbs: q('.dv-crumbs'), banner: q('.dv-banner'), body: q('.dv-body'),
      monaco: q('.dv-monaco'), md: q('.dv-mdhosts'), other: q('.dv-other'), empty: q('.dv-empty') } };
}

// 칸의 Monaco — 오른쪽은 처음 나눌 때 만든다. 커서 · 포커스 · Ctrl+클릭 · 변경 막대 · 주석을 편집기마다 붙임
function createEditor(p) {
  const e = monaco.editor.create(p.el.monaco, EDITOR_OPTS());
  p.ed = e;
  e.onDidChangeCursorPosition(() => { if (e === ed) paintCursor(); });
  e.onDidChangeCursorSelection(() => { if (e === ed) paintCursor(); });
  e.onDidFocusEditorText(() => { usePane(p); lastFocus = 'monaco'; });
  e.onMouseDown((ev) => {
    // Ctrl+클릭 = 정의로 이동(PyCharm)
    if (ev.target.type === monaco.editor.MouseTargetType.CONTENT_TEXT && (ev.event.ctrlKey || ev.event.metaKey)
      && !ev.event.altKey && !ev.event.shiftKey) {
      usePane(p);
      setTimeout(() => gotoDefinition(ev.target.position), 0);
    }
  });
  if (panes[1] === p) { bindChanges(e); bindBlame(e); addActions(e); }
  return e;
}

// 칸 하나의 탭 줄 · 경로 줄 · 띠 · Ctrl+휠 — 처리 전에 그 칸을 «지금 칸» 으로
function bindPane(p) {
  const t = p.el.tabs;
  p.root.addEventListener('pointerdown', () => usePane(p), true);
  t.addEventListener('click', (e) => { usePane(p); onTabClick(e); });
  t.addEventListener('auxclick', (e) => {
    const x = e.target.closest('[data-tab]');
    if (x && e.button === 1) { e.preventDefault(); closeTab(x.dataset.tab); }
  });
  t.addEventListener('contextmenu', (e) => { usePane(p); onTabMenu(e); });
  t.addEventListener('wheel', (e) => {
    if (e.ctrlKey) return;
    t.scrollLeft += e.deltaY || e.deltaX;
  }, { passive: true });
  p.el.banner.addEventListener('click', (e) => { usePane(p); onBannerClick(e); });
  p.el.crumbs.addEventListener('click', (e) => { usePane(p); onCrumbClick(e); });
  // Ctrl+휠 = 글자 크기(편집기 · md 각각)
  p.el.body.addEventListener('wheel', (e) => {
    if (!e.ctrlKey) return;
    e.preventDefault();
    usePane(p);
    const d = e.deltaY < 0 ? 1 : -1;
    if (getDoc(active)?.kind === 'md') {
      mdFont = clamp(mdFont + d, 11, 26);
      store.set('mdfont', mdFont);
      document.documentElement.style.setProperty('--dv-md-size', `${mdFont}px`);
    } else {
      fontSize = clamp(fontSize + d, 9, 28);
      store.set('font', fontSize);
      for (const q of panes) q.ed?.updateOptions({ fontSize, lineHeight: lineHeightOf(fontSize) });
    }
    toast(`글자 크기 ${getDoc(active)?.kind === 'md' ? mdFont : fontSize}`, '', 900);
  }, { passive: false });
}

// «지금 칸» 바꾸기 — 모듈 변수 · 변경 막대 · 주석 · 상태 표시줄이 이 칸 기준이 된다
function usePane(p) {
  if (!p || p === cur) return;
  cur = p;
  ed = p.ed;
  tabs = p.tabs;
  active = p.active;
  views = p.views;
  if (ed) { useChanges(ed); useBlame(ed); }
  for (const q of panes) q.root.classList.toggle('is-cur', q === p);
  paintStatus();
  paintCrumbs();
  if (active) emit('active-doc', getDoc(active) || null);
}

const paneOf = (path) => panes.find((p) => p.tabs.includes(path)) || null;
const otherPane = (p) => panes.find((q) => q !== p);
const visiblePanes = () => panes.filter((p) => !p.root.hidden).sort((a, b) => a.root.style.order - b.root.style.order);
const isSplit = () => visiblePanes().length > 1;

// side: 'right' | 'left' — 숨은 칸을 그쪽에 보이게
function showPane(p, side = 'right') {
  if (!p.root.hidden) return p;
  const o = otherPane(p);
  p.root.style.order = side === 'left' ? '0' : '2';
  o.root.style.order = side === 'left' ? '2' : '0';
  p.root.style.flex = '';
  o.root.style.flex = '';
  p.root.hidden = false;
  panes.splitter.hidden = false;
  $('#panes').classList.add('is-split');
  if (!p.ed) createEditor(p);
  return p;
}

// 빈 칸은 접는다 — 남은 칸이 화면을 다 씀
function hideEmpty() {
  for (const p of panes) {
    if (p.root.hidden || p.tabs.length || !isSplit()) continue;
    p.root.hidden = true;
    p.active = null;
    p.ed?.setModel(null);
    panes.splitter.hidden = true;
    $('#panes').classList.remove('is-split');
    for (const q of panes) q.root.style.flex = '';
    if (cur === p) { cur = null; usePane(otherPane(p)); }
  }
}

// 보던 탭 · 칸 저장 — tabs 는 두 칸 전부(main.js 가 이것으로 다시 열고), split 은 오른쪽 칸 몫
function saveTabs() {
  const keep = (a) => a.filter((p) => !p.startsWith('rev:'));
  const vis = visiblePanes();
  const real = (p) => (p && !p.startsWith('rev:') ? p : null);
  store.set('tabs', keep(vis.flatMap((p) => p.tabs)));
  store.set('active', real(active));
  store.set('split', vis.length > 1 ? { right: keep(vis[1].tabs), ar: real(vis[1].active), al: real(vis[0].active) } : null);
}

// 탭을 다른 칸(to)으로 옮기기 — 같은 칸이면 순서만. 문서는 닫지 않고(저장 · 변경 막대 그대로) 화면만 옮김
export function moveTab(path, to, index = null) {
  const from = paneOf(path);
  if (!from || !to) return;
  const doc = getDoc(path);
  if (from === to) {
    const i = from.tabs.indexOf(path);
    from.tabs.splice(i, 1);
    from.tabs.splice(index === null ? from.tabs.length : Math.min(index > i ? index - 1 : index, from.tabs.length), 0, path);
    paintTabs();
    saveTabs();
    return;
  }
  showPane(to);
  if (from.active === path && doc?.kind === 'code' && from.ed?.getModel() === doc.model) from.views.set(path, from.ed.saveViewState());
  const v = from.views.get(path);
  from.views.delete(path);
  if (v) to.views.set(path, v);
  const i = from.tabs.indexOf(path);
  from.tabs.splice(i, 1);
  if (doc?.md) to.el.md.append(doc.md.box);
  if (from.active === path) {
    usePane(from);
    activate(from.tabs[i] || from.tabs[i - 1] || null, { focus: false });
  }
  to.tabs.splice(index === null ? to.tabs.length : Math.min(index, to.tabs.length), 0, path);
  usePane(to);
  activate(path);
  hideEmpty();
  paintTabs();
  saveTabs();
}

// 나눠 띄우기 — 칸이 하나일 때 탭을 숨은 칸에 그쪽(side)으로
export function splitTab(path, side = 'right') {
  const from = paneOf(path);
  if (!from) return;
  if (isSplit()) { moveTab(path, otherPane(from)); return; }
  if (from.tabs.length < 2) { toast('탭이 하나뿐이라 나눌 수 없음', '', 1500); return; }
  const to = otherPane(from);
  showPane(to, side);
  moveTab(path, to);
}

// 칸막이 끌기 — 왼쪽 칸 폭(%)만 정함. 두 번 클릭 = 반반
function initSplitter(bar) {
  bar.addEventListener('dblclick', () => { for (const p of panes) p.root.style.flex = ''; });
  bar.addEventListener('pointerdown', (e) => {
    e.preventDefault();
    const box = $('#panes').getBoundingClientRect();
    const [l, r] = visiblePanes();
    if (!r) return;
    bar.setPointerCapture(e.pointerId);
    bar.classList.add('is-drag');
    const move = (ev) => {
      const pct = clamp(((ev.clientX - box.left) / box.width) * 100, 15, 85);
      l.root.style.flex = `0 0 calc(${pct}% - 2px)`;
      r.root.style.flex = '1 1 0';
    };
    const up = () => { bar.classList.remove('is-drag'); bar.removeEventListener('pointermove', move); bar.removeEventListener('pointerup', up); };
    bar.addEventListener('pointermove', move);
    bar.addEventListener('pointerup', up);
  });
}

// ======= 탭 끌어 놓기 =======
// 탭 줄 위 → 그 자리로(같은 칸이면 순서, 다른 칸이면 옮김) · 편집 영역 위 → 칸이 하나면 좌 · 우 반쪽에 나눠 띄움,
// 둘이면 다른 칸으로 옮김. 놓일 곳은 파란 상자(반쪽 · 칸 전체) 또는 세로 막대(탭 사이)로 보여 줌
let dragPath = null;
let dropAt = null;
function initDrag() {
  const box = $('#panes');
  const mark = h('<div class="dv-drop" hidden></div>');
  box.append(mark);
  const show = (r, bar = false) => {
    const b = box.getBoundingClientRect();
    mark.hidden = false;
    mark.classList.toggle('is-bar', bar);
    Object.assign(mark.style, { left: `${r.left - b.left}px`, top: `${r.top - b.top}px`, width: `${r.width}px`, height: `${r.height}px` });
  };
  const clear = () => { mark.hidden = true; dropAt = null; };
  box.addEventListener('dragstart', (e) => {
    const t = e.target.closest?.('[data-tab]');
    if (!t) return;
    dragPath = t.dataset.tab;
    e.dataTransfer.effectAllowed = 'move';
    // 🔴 text/plain 로 실으면 Monaco · md 편집기가 놓인 자리에 경로 글자를 넣고 저장한다(시험에서 실측) → 전용 형식만
    e.dataTransfer.setData('application/x-devview-tab', dragPath);
  });
  box.addEventListener('dragend', () => { dragPath = null; clear(); });
  box.addEventListener('dragleave', (e) => { if (!box.contains(e.relatedTarget)) clear(); });
  // 탭을 끄는 동안은 칸 상자가 먼저(캡처) 받아 편집기까지 안 내려보냄 — 편집기의 놓기 커서 · 글자 넣기 차단
  box.addEventListener('dragenter', (e) => { if (dragPath) { e.preventDefault(); e.stopPropagation(); } }, true);
  box.addEventListener('dragover', (e) => {
    if (!dragPath) return;
    e.stopPropagation();
    const from = paneOf(dragPath);
    const pr = e.target.closest?.('.dv-pane');
    const p = panes.find((q) => q.root === pr);
    if (!from || !p) { clear(); return; }
    let at = null;
    const strip = e.target.closest('.dv-tabs');
    if (strip) {
      // 탭 사이 — 마우스가 놓인 탭의 앞 · 뒤
      const items = [...strip.querySelectorAll('[data-tab]')];
      let idx = items.length;
      for (let i = 0; i < items.length; i++) {
        const r = items[i].getBoundingClientRect();
        if (e.clientX < r.left + r.width / 2) { idx = i; break; }
      }
      const sr = strip.getBoundingClientRect();
      const ref = items[idx] ? items[idx].getBoundingClientRect().left : (items.length ? items[items.length - 1].getBoundingClientRect().right : sr.left);
      at = { kind: 'tabs', pane: p, index: idx };
      show({ left: ref - 1, top: sr.top + 4, width: 3, height: sr.height - 8 }, true);
    } else {
      const r = p.el.body.getBoundingClientRect();
      if (!isSplit()) {
        if (from.tabs.length < 2) { clear(); return; }
        const right = e.clientX > r.left + r.width / 2;
        at = { kind: 'split', side: right ? 'right' : 'left' };
        show({ left: right ? r.left + r.width / 2 : r.left, top: r.top, width: r.width / 2, height: r.height });
      } else if (p !== from) {
        at = { kind: 'move', pane: p };
        show(r);
      } else { clear(); return; }
    }
    dropAt = at;
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
  }, true);
  box.addEventListener('drop', (e) => {
    if (!dragPath) return;
    e.preventDefault();
    e.stopPropagation();
    if (!dropAt) { dragPath = null; clear(); return; }
    const path = dragPath;
    const at = dropAt;
    dragPath = null;
    clear();
    if (at.kind === 'tabs') moveTab(path, at.pane, at.index);
    else if (at.kind === 'move') moveTab(path, at.pane);
    else splitTab(path, at.side);
  }, true);
}

// ======= md 편집기 =======
function makeMd(doc, text, readOnly = false) {
  const box = h('<div class="dv-md" hidden></div>');
  cur.el.md.append(box);           // 여는 칸(openFile 이 먼저 그 칸으로 바꿔 둠)
  const handle = window.DevMd.create(box, {
    text,
    readOnly,
    onChange: () => mdEdited(doc),
    onSave: (reason) => { if (!doc.readonly) save(doc, { manual: reason === 'key' }); },
    onLink: (href, wiki) => openMdLink(doc, href, wiki),
    onCursor: () => { if (doc.path === active) paintCursor(); },
    onFocus: (f) => { if (f) { usePane(paneOf(doc.path)); lastFocus = 'md'; } },
  });
  const destroy = handle.destroy;
  handle.destroy = () => { destroy(); box.remove(); };
  handle.box = box;
  return handle;
}

function openMdLink(doc, href, wiki) {
  const here = doc.realPath || doc.path;
  if (wiki !== undefined) {
    const [d, hd] = wiki.split('#');
    if (!d) { doc.md.jumpHeading(hd || ''); return; }
    emit('find-file', { name: d.toLowerCase().replace(/\.md$/, '') + '.md', heading: hd });
    return;
  }
  if (!href) return;
  if (href.startsWith('#')) { doc.md.jumpHeading(decodeURIComponent(href.slice(1))); return; }
  if (/^[a-z]+:/i.test(href)) {
    // 대회 환경은 외부 브라우저 접근 금지 — 열지 않고 주소만 복사
    copyText(href, '외부 링크는 열지 않고 복사함');
    return;
  }
  const [p, hd] = href.split('#');
  const parts = (dirName(here) ? dirName(here) + '/' : '').concat(decodeURIComponent(p)).split('/');
  const out = [];
  for (const s of parts) { if (s === '..') out.pop(); else if (s && s !== '.') out.push(s); }
  openFile(out.join('/')).then(() => { if (hd) getDoc(out.join('/'))?.md?.jumpHeading(decodeURIComponent(hd)); });
}

// ======= 열기 · 닫기 =======
export async function openFile(path, { line = null, col = 1, nav = true, focus = true } = {}) {
  if (!path) return null;
  if (nav && active && (active !== path || line)) pushNav();
  // 칸 고르기 — 이미 열린 칸 · 다시 열 때 오른쪽이던 것 · 아니면 지금 칸
  const right = !paneOf(path) && restoreRight.delete(path);
  usePane(paneOf(path) || (right ? showPane(panes[1]) : cur));
  let doc;
  try {
    doc = await openDoc(path);
  } catch (e) {
    toast(`열기 실패: ${path} (${e.message})`, 'bad');
    hideEmpty();                   // 다시 열기로 펼친 오른쪽 칸이 빈 채 남지 않게
    return null;
  }
  if (!tabs.includes(path)) {
    const i = tabs.indexOf(active);
    tabs.splice(i >= 0 ? i + 1 : tabs.length, 0, path);
    attachDoc(doc);
  }
  activate(path, { focus });
  if (line) reveal(doc, line, col);
  remember(path);
  if (right && !restoreRight.size) finishRestore();
  return doc;
}

// 다시 열기 끝 — 칸마다 보던 탭으로(오른쪽 → 왼쪽 순, 마지막 포커스는 main.js 가 active 로 정함)
function finishRestore() {
  const sp = restoreSplit;
  restoreSplit = null;
  if (!sp) return;
  if (sp.ar && panes[1].tabs.includes(sp.ar)) { usePane(panes[1]); activate(sp.ar, { focus: false }); }
  if (sp.al && panes[0].tabs.includes(sp.al)) { usePane(panes[0]); activate(sp.al, { focus: false }); }
}

export async function openRev(rev, path, gpath, label) {
  const key = `rev:${rev}:${path || gpath}`;
  if (!getDoc(key)) {
    let r;
    try {
      r = await api('git/blob', { query: { rev, gpath: gpath || undefined, path: gpath ? undefined : path } });
    } catch (e) { toast(`열기 실패: ${e.message}`, 'bad'); return; }
    if (r.missing) { toast('그 판에는 이 파일이 없음'); return; }
    if (r.binary || r.too_large) { toast('바이너리 · 큰 파일은 열지 않음'); return; }
    openRevDoc(key, path || gpath, r.content, label || rev.slice(0, 8));
  }
  if (!tabs.includes(key)) {
    const i = tabs.indexOf(active);
    tabs.splice(i >= 0 ? i + 1 : tabs.length, 0, key);
  }
  emit('show-view', 'code');
  activate(key);
}

function reveal(doc, line, col = 1) {
  if (doc.kind === 'code') {
    ed.revealLineInCenter(line);
    ed.setPosition({ lineNumber: line, column: col || 1 });
    ed.focus();
  } else if (doc.kind === 'md') {
    doc.md.gotoLine(line, col);
  }
}

export function activate(path, { focus = true } = {}) {
  const prev = getDoc(active);
  if (prev?.kind === 'code' && ed.getModel() === prev.model) views.set(active, ed.saveViewState());
  hidePopup();
  active = cur.active = path;
  const doc = getDoc(path);
  $$('.dv-md', cur.el.md).forEach((b) => { b.hidden = true; });
  cur.el.other.hidden = true;
  cur.el.monaco.hidden = true;
  cur.el.empty.hidden = !!doc;
  if (doc?.kind === 'code' && !tableView.has(path)) {
    cur.el.monaco.hidden = false;
    ed.setModel(doc.model);
    ed.updateOptions({ readOnly: !!doc.readonly });
    const v = views.get(path);
    if (v) ed.restoreViewState(v);
    if (focus) ed.focus();
  } else {
    ed.setModel(null);
    if (doc?.kind === 'md') {
      doc.md.box.hidden = false;
      if (focus && !doc.readonly) setTimeout(() => doc.md.focus(), 0);
    } else if (doc) {
      showOther(doc);
    }
  }
  applyBlame(doc);
  paintAll();
  saveTabs();
  emit('active-doc', doc || null);
}

export async function closeTab(path) {
  usePane(paneOf(path));
  const doc = getDoc(path);
  if (doc && doc.status === 'conflict') { toast('저장 충돌을 먼저 해결해야 닫힘', 'bad'); activate(path); return false; }
  if (doc && isDirty(doc) && doc.status !== 'deleted') {
    await save(doc, { manual: true });
    if (isDirty(doc)) { toast('저장 실패 — 탭을 닫지 않음', 'bad'); activate(path); return false; }
  }
  const i = tabs.indexOf(path);
  if (i < 0) return true;
  tabs.splice(i, 1);
  views.delete(path);
  tableView.delete(path);
  if (doc) { detachDoc(doc); closeDoc(doc); }
  if (active === path) activate(tabs[i] || tabs[i - 1] || null, { focus: false });
  else paintTabs();
  hideEmpty();
  saveTabs();
  return true;
}

export async function closeOthers(keep) {
  for (const p of [...tabs]) if (p !== keep) await closeTab(p);
}

export function nextTab(dir) {
  if (!tabs.length) return;
  const i = tabs.indexOf(active);
  activate(tabs[(i + dir + tabs.length) % tabs.length]);
}

// ======= 이동 기록(Ctrl+Alt+← →) =======
function here() {
  const doc = getDoc(active);
  if (!doc) return null;
  if (doc.kind === 'code' && ed.getModel() === doc.model) {
    const p = ed.getPosition();
    return { path: active, line: p?.lineNumber || 1, col: p?.column || 1 };
  }
  if (doc.kind === 'md') { const c = doc.md.cursor(); return { path: active, line: c.line, col: c.col }; }
  return { path: active, line: 1, col: 1 };
}
function pushNav() {
  const h0 = here();
  if (!h0) return;
  const top = navBack[navBack.length - 1];
  if (top && top.path === h0.path && Math.abs(top.line - h0.line) < 3) return;
  navBack.push(h0);
  if (navBack.length > 60) navBack.shift();
  navFwd.length = 0;
}
export async function navigate(dir) {
  const from = dir < 0 ? navBack : navFwd;
  const to = dir < 0 ? navFwd : navBack;
  const cur = here();
  while (from.length) {
    const t = from.pop();
    if (!tabs.includes(t.path) && t.path.startsWith('rev:')) continue;
    if (cur) to.push(cur);
    await openFile(t.path, { line: t.line, col: t.col, nav: false });
    return;
  }
  toast(dir < 0 ? '이전 위치 없음' : '다음 위치 없음', '', 1200);
}

function remember(path) {
  if (path.startsWith('rev:')) return;
  const r = store.get('recent', []).filter((p) => p !== path);
  r.unshift(path);
  store.set('recent', r.slice(0, 40));
}

// ======= 그리기 =======
function paintAll() {
  paintTabs();
  paintCrumbs();
  paintBanner();
  paintStatus();
}

function tabLabel(path) {
  const doc = getDoc(path);
  if (doc?.readonly) return `${baseName(doc.realPath)} <i>@${esc(doc.label)}</i>`;
  return esc(baseName(path));
}

// 탭 줄 — 칸마다. 탭은 끌어서 순서 · 칸을 바꾼다(initDrag)
export function paintTabs() {
  for (const pn of panes) paintTabsOf(pn);
}
function paintTabsOf(pn) {
  const box = pn.el.tabs;
  box.innerHTML = pn.tabs.map((p) => {
    const doc = getDoc(p);
    const st = doc ? statusOf(doc) : 'saved';
    const g = GIT_COLOR[gitMap.get(p)] || '';
    const name = doc?.readonly ? doc.realPath : p;
    return `<div class="dv-tab${p === pn.active ? ' is-active' : ''}${doc?.readonly ? ' is-ro' : ''} ${g}" data-tab="${esc(p)}" title="${esc(name)}" draggable="true">`
      + `${fileBadge(baseName(name))}<span class="dv-tab-name">${tabLabel(p)}</span>`
      + `${st === 'conflict' || st === 'deleted' || st === 'failed' ? `<span class="dv-tab-warn" title="${esc(STATUS_LABEL[st])}">${icon('alert')}</span>` : ''}`
      + `<span class="dv-tab-x${st === 'dirty' || st === 'saving' ? ' is-dirty' : ''}" data-close="${esc(p)}" title="닫기 (가운데 클릭)">${icon('x')}</span></div>`;
  }).join('');
  box.querySelector('.is-active')?.scrollIntoView({ block: 'nearest', inline: 'nearest' });
}

function paintCrumbs(pn = cur) {
  const doc = getDoc(pn.active);
  const box = pn.el.crumbs;
  if (!doc) { box.innerHTML = ''; box.hidden = true; return; }
  box.hidden = false;
  const path = doc.readonly ? doc.realPath : doc.path;
  const segs = path.split('/');
  const crumbs = segs.map((s, i) => `<span class="dv-crumb" data-crumb="${esc(segs.slice(0, i + 1).join('/'))}">${esc(s)}</span>`)
    .join(`<span class="dv-crumb-sep">${icon('chevR')}</span>`);
  const btn = (act, ic, label, title, on2 = false) =>
    `<button class="dv-cb${on2 ? ' is-on' : ''}" data-cb="${act}" title="${esc(title)}">${icon(ic)}<span>${esc(label)}</span></button>`;
  let acts = '';
  if (doc.readonly) {
    acts += btn('openCurrent', 'open', '현재 파일', '작업 폴더의 지금 파일 열기');
  } else {
    const ext = extOf(path);
    if (doc.kind === 'code' && (ext === 'csv' || ext === 'tsv')) acts += btn('table', 'table', tableView.has(path) ? '원문 보기' : '표로 보기', 'CSV 를 표로 보기', tableView.has(path));
    if (gitRepo && (doc.kind === 'code' || doc.kind === 'md')) {
      acts += btn('compare', 'cols', 'HEAD 비교', '마지막 커밋과 지금 내용 비교 (이 창에서 고쳐도 됨)');
      acts += btn('history', 'history', '이력', 'Git 에서 이 파일의 변경 이력');
      if (doc.kind === 'code') acts += btn('blame', 'user', '주석', '줄마다 마지막으로 고친 커밋 · 작성자 (Git blame)', blameOn(doc));
    }
  }
  box.innerHTML = `<div class="dv-crumbs-path">${crumbs}</div><div class="dv-crumbs-acts">${acts}</div>`;
}

function paintBanner(pn = cur) {
  const doc = getDoc(pn.active);
  const box = pn.el.banner;
  const st = doc ? statusOf(doc) : null;
  let html = '';
  if (doc?.readonly) {
    html = `${icon('eye')}<span>읽기 전용 — ${esc(doc.label)} 판의 ${esc(doc.realPath)}</span>`;
  } else if (st === 'conflict') {
    html = `${icon('alert')}<span><b>외부 변경 충돌</b> 다른 곳(Codex · 공식 IDE)에서 이 파일이 바뀜. 내 변경은 아직 저장 안 함</span>`
      + '<button data-b="diff">차이 보기</button><button data-b="disk">디스크 내용 불러오기</button><button data-b="mine">내 내용으로 저장</button>';
  } else if (st === 'deleted') {
    html = `${icon('alert')}<span><b>디스크에서 삭제됨</b> 터미널 · AI 가 이 파일을 지웠을 수 있음</span>`
      + '<button data-b="recreate">지금 내용으로 다시 만들기</button><button data-b="drop">탭 닫기</button>';
  } else if (st === 'failed') {
    html = `${icon('alert')}<span><b>저장 실패</b> ${esc(doc.note || '')}</span><button data-b="retry">다시 저장</button>`
      + (/CP949|저장할 수 없는 글자/.test(doc.note || '') ? '<button data-b="utf8">UTF-8 로 저장</button>' : '');
  }
  box.innerHTML = html;
  box.hidden = !html;
  box.className = `dv-banner${doc?.readonly ? ' is-info' : ''}`;
}

function paintCursor() {
  const el = $('#status [data-st="cursor"]');
  if (!el) return;
  const doc = getDoc(active);
  if (doc?.kind === 'code' && ed.getModel() === doc.model) {
    const p = ed.getPosition();
    const sel = ed.getSelection();
    const n = sel && !sel.isEmpty() ? doc.model.getValueInRange(sel).length : 0;
    el.textContent = p ? `${p.lineNumber}:${p.column}${n ? ` (${n}자)` : ''}` : '';
  } else if (doc?.kind === 'md') {
    const c = doc.md.cursor();
    el.textContent = `${c.line}:${c.col}`;
  } else {
    el.textContent = '';
  }
}

export function paintStatus() {
  const doc = getDoc(active);
  const box = $('#status');
  const path = doc ? (doc.readonly ? doc.realPath : doc.path) : '';
  const st = doc ? statusOf(doc) : '';
  const lang = doc ? (doc.kind === 'md' ? 'Markdown' : doc.kind === 'code' ? (LANG_LABEL[doc.model.getLanguageId()] || doc.model.getLanguageId()) : '') : '';
  let indent = '';
  if (doc?.kind === 'code') {
    const o = doc.model.getOptions();
    indent = o.insertSpaces ? `공백 ${o.indentSize || o.tabSize}` : `탭 ${o.tabSize}`;
  }
  const chg = doc?.kind === 'code' ? hunkCount(doc) : 0;
  box.innerHTML = `<span class="dv-st-path" data-st="path" title="클릭: 경로 복사">${esc(path)}</span><span class="dv-st-sp"></span>`
    + (chg ? `<button class="dv-st-btn" data-st="change" title="다음 변경으로 (Ctrl+Alt+Shift+↓)">변경 ${chg}</button>` : '')
    + `<span data-st="cursor"></span>`
    + (lang ? `<span>${esc(lang)}</span>` : '')
    + (indent ? `<span>${esc(indent)}</span>` : '')
    + (doc?.eol && !doc.readonly ? `<span title="줄바꿈 — 원래 파일 그대로 저장">${doc.eol}</span>` : '')
    + (doc?.encoding && !doc.readonly ? `<span title="인코딩 — 원래 파일 그대로 저장">${ENC_LABEL[doc.encoding] || doc.encoding}</span>` : '')
    + (branch ? `<span class="dv-st-branch" title="현재 브랜치">${icon('branch')}${esc(branch)}</span>` : '')
    + (doc && !doc.readonly && (doc.kind === 'code' || doc.kind === 'md') ? `<span class="dv-st-save is-${st}" data-st="save" title="${st === 'failed' ? '클릭: 다시 저장' : '자동 저장'}">${STATUS_LABEL[st] || ''}</span>` : '')
    + (doc?.kind === 'code' ? `<button class="dv-st-btn${wrap ? ' is-on' : ''}" data-st="wrap" title="긴 줄 접어 보기 (Alt+Z)">줄바꿈</button>` : '');
  paintCursor();
}

function showOther(doc, pn = cur) {
  const box = pn.el.other;
  box.hidden = false;
  if (doc.kind === 'image') {
    box.innerHTML = `<div class="dv-img"><img alt="" src="${esc(rawUrl(doc.path))}&v=${encodeURIComponent(doc.sig || '')}"><div class="dv-img-info"></div></div>`;
    const img = box.querySelector('img');
    img.onload = () => { box.querySelector('.dv-img-info').textContent = `${img.naturalWidth} × ${img.naturalHeight} · ${(doc.size || 0).toLocaleString()}B`; };
  } else if (doc.kind === 'code' && tableView.has(doc.path)) {
    renderTable(doc, pn);
  } else {
    box.innerHTML = `<div class="dv-placeholder">${icon('file')}<p>${esc(doc.note || '표시하지 않는 파일')}</p></div>`;
  }
}

// ======= CSV 표 =======
function parseCsv(text, delim) {
  const rows = [];
  let row = [], f = '', q = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (q) {
      if (c === '"') { if (text[i + 1] === '"') { f += '"'; i++; } else q = false; } else f += c;
    } else if (c === '"' && f === '') q = true;
    else if (c === delim) { row.push(f); f = ''; }
    else if (c === '\n') { row.push(f); rows.push(row); row = []; f = ''; if (rows.length > 5000) break; }
    else if (c !== '\r') f += c;
  }
  if (f || row.length) { row.push(f); rows.push(row); }
  return rows;
}
function renderTable(doc, pn = cur) {
  const box = pn.el.other;
  const rows = parseCsv(textOf(doc), extOf(doc.path) === 'tsv' ? '\t' : ',');
  const head = rows[0] || [];
  const body = rows.slice(1, 2001);
  const num = (s) => /^\s*-?[\d,]*\.?\d+(?:[eE][+-]?\d+)?\s*$/.test(s);
  box.innerHTML = `<div class="dv-table-wrap"><table class="dv-table"><thead><tr><th>#</th>${head.map((x) => `<th>${esc(x)}</th>`).join('')}</tr></thead>`
    + `<tbody>${body.map((r, i) => `<tr><td class="is-n">${i + 1}</td>${r.map((x) => `<td${num(x) ? ' class="is-num"' : ''}>${esc(x)}</td>`).join('')}</tr>`).join('')}</tbody></table>`
    + `<div class="dv-table-info">행 ${Math.max(0, rows.length - 1).toLocaleString()}${rows.length > 2001 ? ' (앞 2,000행만 표시)' : ''} · 열 ${head.length}</div></div>`;
}
const tableSoon = debounce((doc, pn) => renderTable(doc, pn), 300);

// ======= 클릭 처리 =======
function onTabClick(e) {
  const x = e.target.closest('[data-close]');
  if (x) { e.stopPropagation(); closeTab(x.dataset.close); return; }
  const t = e.target.closest('[data-tab]');
  if (t) activate(t.dataset.tab);
}

function onTabMenu(e) {
  const t = e.target.closest('[data-tab]');
  if (!t) return;
  e.preventDefault();
  const p = t.dataset.tab;
  const doc = getDoc(p);
  const real = doc?.readonly ? doc.realPath : p;
  contextMenu(e.clientX, e.clientY, [
    { label: '닫기', key: '가운데 클릭', icon: 'x', act: () => closeTab(p) },
    { label: '다른 탭 모두 닫기', act: () => closeOthers(p) },
    { label: '모든 탭 닫기', act: () => closeOthers(null) },
    '-',
    isSplit()
      ? { label: '다른 칸으로 옮기기', icon: 'cols', act: () => moveTab(p, otherPane(paneOf(p))) }
      : { label: '오른쪽으로 나눠 보기', icon: 'cols', act: () => splitTab(p, 'right'), disabled: tabs.length < 2 },
    '-',
    { label: '경로 복사', icon: 'copy', act: () => copyText(real, '경로 복사') },
    { label: '트리에서 보기', icon: 'locate', act: () => emit('reveal', real), disabled: !!doc?.readonly },
    { label: 'Git 이력', icon: 'history', act: () => emit('git-file-history', real), disabled: !gitRepo },
  ]);
}

function onStatusClick(e) {
  const s = e.target.closest('[data-st]')?.dataset.st;
  const doc = getDoc(active);
  if (s === 'path' && doc) copyText(doc.readonly ? doc.realPath : doc.path, '경로 복사');
  else if (s === 'wrap') toggleWrap();
  else if (s === 'change') gotoChange(1);
  else if (s === 'save' && doc && (doc.status === 'failed' || isDirty(doc))) save(doc, { manual: true });
}

function onBannerClick(e) {
  const b = e.target.closest('[data-b]')?.dataset.b;
  const doc = getDoc(active);
  if (!b || !doc) return;
  if (b === 'disk') takeDisk(doc);
  else if (b === 'mine') keepMine(doc);
  else if (b === 'diff') showConflictDiff(doc);
  else if (b === 'recreate') save(doc, { force: true, manual: true });
  else if (b === 'drop') { if (doc.kind === 'code') doc.savedVersion = doc.model.getAlternativeVersionId(); else if (doc.kind === 'md') doc.savedDoc = doc.md.doc(); doc.status = 'saved'; closeTab(doc.path); }
  else if (b === 'retry') save(doc, { manual: true });
  else if (b === 'utf8') { doc.encoding = 'utf-8'; save(doc, { manual: true }); }
}

function onCrumbClick(e) {
  const c = e.target.closest('[data-crumb]');
  if (c) { emit('reveal', c.dataset.crumb); return; }
  const b = e.target.closest('[data-cb]')?.dataset.cb;
  const doc = getDoc(active);
  if (!b || !doc) return;
  if (b === 'table') { if (tableView.has(doc.path)) tableView.delete(doc.path); else tableView.add(doc.path); activate(doc.path); }
  else if (b === 'compare') compareWithHead(doc);
  else if (b === 'history') emit('git-file-history', doc.path);
  else if (b === 'blame') toggleBlame(doc).then(paintCrumbs);
  else if (b === 'openCurrent') openFile(doc.realPath);
}

export function toggleWrap() {
  wrap = !wrap;
  store.set('wrap', wrap);
  for (const p of panes) p.ed?.updateOptions({ wordWrap: wrap ? 'on' : 'off' });
  paintStatus();
}

// ======= 비교 창(Monaco diff) =======
// diff 편집기는 하나만 만들어 재사용 — Monaco 0.52 는 dispose 한 diff 편집기를 내부 목록에서 빼지 않아 열 때마다 쌓임
let modalDiff = null;
function diffModal(title, original, modified, lang, actions, readOnlyRight = false) {
  if (!modalDiff) {
    const host = h('<div class="dv-modal-diff"></div>');
    const de = monaco.editor.createDiffEditor(host, { theme: 'pycharm-dark', automaticLayout: true, originalEditable: false,
      renderSideBySide: true, useInlineViewWhenSpaceIsLimited: true, minimap: { enabled: false },
      fontFamily: '"JetBrains Mono", D2Coding, Consolas, "Malgun Gothic", monospace',
      hideUnchangedRegions: { enabled: true, contextLineCount: 3, minimumLineCount: 3, revealLineCount: 20 },
      unicodeHighlight: { ambiguousCharacters: false, invisibleCharacters: false }, scrollBeyondLastLine: false });
    modalDiff = { host, de };
  }
  const { host, de } = modalDiff;
  const om = monaco.editor.createModel(original, lang);
  const mm = typeof modified === 'string' ? monaco.editor.createModel(modified, lang) : modified;
  const dlg = openModal({ title, body: host, actions, onClose: () => {
    de.setModel(null);
    om.dispose();
    if (typeof modified === 'string') mm.dispose();
  } });
  de.updateOptions({ readOnly: readOnlyRight, fontSize, lineHeight: lineHeightOf(fontSize) });
  de.setModel({ original: om, modified: mm });
  setTimeout(() => de.layout(), 0);
  return dlg;
}

async function compareWithHead(doc) {
  let r;
  try { r = await api('git/blob', { query: { rev: 'HEAD', path: doc.path } }); } catch (e) { toast(e.message, 'bad'); return; }
  const base = r.missing ? '' : r.binary ? null : r.content;
  if (base === null) { toast('바이너리 파일'); return; }
  const lang = doc.kind === 'md' ? 'markdown' : doc.model.getLanguageId();
  const right = doc.kind === 'code' ? doc.model : textOf(doc);
  diffModal(`HEAD ↔ 지금 — ${doc.path}${r.missing ? ' (HEAD 에 없는 새 파일)' : ''}`, base, right, lang, [], doc.kind !== 'code');
}

function showConflictDiff(doc) {
  if (!doc.disk) return;
  const lang = doc.kind === 'md' ? 'markdown' : doc.model.getLanguageId();
  const right = doc.kind === 'code' ? doc.model : textOf(doc);
  diffModal(`디스크(왼쪽) ↔ 내 내용(오른쪽) — ${doc.path}`, doc.disk.content ?? '', right, lang, [
    { label: '디스크 내용 불러오기', run: () => takeDisk(doc) },
    { label: '내 내용으로 저장', primary: true, run: () => { keepMine(doc); } },
  ], doc.kind !== 'code');
}

// ======= 정의로 이동 · 사용처 =======
function wordAt(pos) {
  const doc = getDoc(active);
  if (doc?.kind !== 'code' || !pos) return null;
  return doc.model.getWordAtPosition(pos)?.word || null;
}

export async function gotoDefinition(pos) {
  const doc = getDoc(active);
  const word = wordAt(pos || ed.getPosition());
  if (!word) return;
  let r;
  try { r = await api('symbols', { query: { name: word } }); } catch (e) { toast(e.message, 'bad'); return; }
  const curLine = (pos || ed.getPosition())?.lineNumber;
  let hits = r.hits.filter((x) => !(x.p === doc.path && x.n === curLine));
  const best = hits.filter((x) => x.r === Math.min(...hits.map((y) => y.r)));
  if (!hits.length) {
    if (r.hits.length) { emit('find-usages', word); return; }       // 정의 위에서 누름 → 사용처
    toast(`«${word}» 정의 못 찾음 — 사용처 검색`, '', 1600);
    emit('find-usages', word);
    return;
  }
  if (best.length === 1) { openFile(best[0].p, { line: best[0].n, col: best[0].c + 1 }); return; }
  hits = [...best, ...hits.filter((x) => !best.includes(x))];
  const RANK = ['정의', '대입', 'import'];
  pickList({
    title: `«${word}» 정의 후보`, hint: `${hits.length}곳`, placeholder: '경로로 걸러 내기',
    items: (q) => hits.filter((x) => !q || x.p.toLowerCase().includes(q.toLowerCase())),
    render: (x) => `<span class="dv-pi-tag">${RANK[x.r] || ''}</span><span class="dv-pi-main">${esc(x.t)}</span><span class="dv-pi-sub">${esc(x.p)}:${x.n}</span>`,
    onPick: (x) => openFile(x.p, { line: x.n, col: x.c + 1 }),
  });
}

// ======= PyCharm 키맵 =======
function installKeymap() {
  const K = monaco.KeyCode;
  const M = monaco.KeyMod;
  const editW = 'editorTextFocus && !editorReadonly';
  monaco.editor.addKeybindingRules([
    { keybinding: M.CtrlCmd | K.KeyD, command: 'editor.action.copyLinesDownAction', when: editW },
    { keybinding: M.CtrlCmd | M.Shift | K.KeyD, command: 'editor.action.deleteLines', when: editW },      // 유저 키맵
    { keybinding: M.CtrlCmd | K.KeyY, command: 'redo', when: 'editorTextFocus' },                          // 유저 키맵
    { keybinding: M.Shift | M.Alt | K.Backspace, command: 'redo', when: 'editorTextFocus' },
    { keybinding: M.Alt | K.KeyJ, command: 'editor.action.addSelectionToNextFindMatch', when: 'editorFocus' },
    { keybinding: M.CtrlCmd | M.Alt | M.Shift | K.KeyJ, command: 'editor.action.selectHighlights', when: 'editorFocus' },
    { keybinding: M.Shift | M.Alt | K.UpArrow, command: 'editor.action.moveLinesUpAction', when: editW },
    { keybinding: M.Shift | M.Alt | K.DownArrow, command: 'editor.action.moveLinesDownAction', when: editW },
    { keybinding: M.CtrlCmd | M.Shift | K.UpArrow, command: 'editor.action.moveLinesUpAction', when: editW },
    { keybinding: M.CtrlCmd | M.Shift | K.DownArrow, command: 'editor.action.moveLinesDownAction', when: editW },
    { keybinding: M.Shift | K.Enter, command: 'editor.action.insertLineAfter', when: editW },
    { keybinding: M.CtrlCmd | M.Alt | K.Enter, command: 'editor.action.insertLineBefore', when: editW },
    { keybinding: M.CtrlCmd | M.Shift | K.KeyJ, command: 'editor.action.joinLines', when: editW },
    { keybinding: M.CtrlCmd | M.Shift | K.Slash, command: 'editor.action.blockComment', when: editW },
    { keybinding: M.CtrlCmd | K.KeyR, command: 'editor.action.startFindReplaceAction', when: 'editorFocus' },
    { keybinding: M.CtrlCmd | M.Alt | K.KeyI, command: 'editor.action.reindentselectedlines', when: editW },
    { keybinding: M.CtrlCmd | M.Shift | K.KeyA, command: 'editor.action.quickCommand', when: 'editorFocus' },
  ]);
}

// 편집기 동작(저장 · 정의로 이동 등) — 편집기마다 붙임(오른쪽 칸 편집기는 만들 때). 안에서 쓰는 ed · active 는 «지금 칸»
function addActions(e0) {
  const K = monaco.KeyCode;
  const M = monaco.KeyMod;
  const act = (id, label, keybindings, run, menu = null) => e0.addAction({ id, label, keybindings, run,
    ...(menu ? { contextMenuGroupId: menu[0], contextMenuOrder: menu[1] } : {}) });
  act('dv.save', '저장', [M.CtrlCmd | K.KeyS], () => { const d = getDoc(active); if (d) save(d, { manual: true }); });
  act('dv.wrap', '줄바꿈 켜기/끄기', [M.Alt | K.KeyZ], () => toggleWrap());
  act('dv.toggleCase', '대소문자 바꾸기', [M.CtrlCmd | M.Shift | K.KeyU], (e) => {
    const m = e.getModel();
    const edits = e.getSelections().filter((s) => !s.isEmpty()).map((s) => {
      const t = m.getValueInRange(s);
      return { range: s, text: t === t.toUpperCase() ? t.toLowerCase() : t.toUpperCase() };
    });
    if (edits.length) e.executeEdits('dv.toggleCase', edits);
  });
  act('dv.gotoDef', '정의로 이동', [M.CtrlCmd | K.KeyB, K.F12], () => gotoDefinition(), ['navigation', 1]);
  act('dv.usages', '사용처 찾기', [M.Alt | K.F7], () => { const w = wordAt(ed.getPosition()); if (w) emit('find-usages', w); }, ['navigation', 2]);
  act('dv.structure', '파일 구조', [M.CtrlCmd | K.F12], () => emit('structure'), ['navigation', 3]);
  act('dv.copyRef', '경로:줄 복사', [M.CtrlCmd | M.Alt | M.Shift | K.KeyC], () => {
    const p = ed.getPosition();
    copyText(`${getDoc(active)?.realPath || active}:${p.lineNumber}`, '경로:줄 복사');
  }, ['9_cutcopypaste', 9]);
  act('dv.nextChange', '다음 변경', [M.CtrlCmd | M.Alt | M.Shift | K.DownArrow], () => gotoChange(1));
  act('dv.prevChange', '이전 변경', [M.CtrlCmd | M.Alt | M.Shift | K.UpArrow], () => gotoChange(-1));
  act('dv.compare', 'HEAD 와 비교', [], () => { const d = getDoc(active); if (d && gitRepo) compareWithHead(d); }, ['z_git', 1]);
  act('dv.blame', 'Git 주석(blame) 켜기/끄기', [], () => { const d = getDoc(active); if (d && gitRepo) toggleBlame(d).then(paintCrumbs); }, ['z_git', 2]);
  act('dv.history', 'Git 파일 이력', [], () => emit('git-file-history', active), ['z_git', 3]);
  act('dv.reformat', '코드 정리', [M.CtrlCmd | M.Alt | K.KeyL], async (e) => {
    const a = e.getAction('editor.action.formatDocument');
    if (a && a.isSupported()) await a.run(); else toast('이 언어는 정리 기능 없음', '', 1500);
  });
}
