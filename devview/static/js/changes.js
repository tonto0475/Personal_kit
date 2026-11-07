// 줄 변경 표시 — HEAD 판 대비 추가(초록) · 수정(파랑) · 삭제(회색 삼각). PyCharm 의 왼쪽 변경 막대
// 막대 클릭 → 옛 내용 팝업 · 되돌리기(되돌리기도 Ctrl+Z 로 취소 가능) · 이전/다음 변경
// 기준: HEAD 의 같은 경로 파일. 새 파일(HEAD 에 없음)은 표시 안 함 · git 저장소가 아니면 표시 안 함
import { api } from './api.js';
import { lineDiff } from './diffutil.js';
import { h, esc, on, emit, icon, toast } from './util.js';
import { getDoc } from './docs.js';

let monaco = null;
let editor = null;
const base = new Map();          // 경로 → { text | null, loading }
let gitRepo = false;
let popup = null;

export function initChanges(m, ed, isRepo) {
  monaco = m;
  editor = ed;
  gitRepo = isRepo;
  on('doc-edit', (doc) => { if (doc.kind === 'code') soon(doc); });
  on('doc-reloaded', (doc) => { if (doc.kind === 'code') soon(doc); });
  on('git-head', () => { base.clear(); for (const p of opened) { const d = getDoc(p); if (d) load(d); } });
  bindEditor(ed);
}

// 나눠 보기 — 칸마다 편집기가 따로라 막대 클릭은 편집기마다 붙이고, 이동 · 팝업은 «지금 칸» 편집기 기준
export function bindEditor(ed) {
  ed.onMouseDown((e) => {
    if (e.target.type !== monaco.editor.MouseTargetType.GUTTER_LINE_DECORATIONS) return;
    editor = ed;
    const line = e.target.position?.lineNumber;
    const doc = currentDoc();
    if (!line || !doc) return;
    const i = (doc.hunks || []).findIndex((hk) => hunkHas(hk, line));
    if (i >= 0) showPopup(doc, i);
  });
  ed.onDidChangeModel(() => { if (editor === ed) hidePopup(); });
}
export function useEditor(ed) {
  if (editor !== ed) hidePopup();
  editor = ed;
}

const opened = new Set();
const currentDoc = () => {
  const m = editor.getModel();
  if (!m) return null;
  for (const p of opened) { const d = getDoc(p); if (d && d.model === m) return d; }
  return null;
};

export function attachDoc(doc) {
  if (doc.kind !== 'code' || doc.readonly || !gitRepo) return;
  opened.add(doc.path);
  if (!base.has(doc.path)) load(doc); else compute(doc);
}
export function detachDoc(doc) {
  opened.delete(doc.path);
  base.delete(doc.path);
}

async function load(doc) {
  base.set(doc.path, { text: null, loading: true });
  try {
    const r = await api('git/blob', { query: { rev: 'HEAD', path: doc.path } });
    base.set(doc.path, { text: r.missing || r.binary || r.too_large ? null : r.content, loading: false });
  } catch {
    base.set(doc.path, { text: null, loading: false });
  }
  compute(doc);
}

const timers = new Map();
function soon(doc) {
  if (!opened.has(doc.path)) return;
  clearTimeout(timers.get(doc.path));
  timers.set(doc.path, setTimeout(() => compute(doc), 250));
}

function hunkHas(hk, line) {
  // line 은 1 기준. 삭제 hunk 는 표시된 줄(삭제 위치 바로 아래 줄, 끝이면 마지막 줄)
  if (hk.nl === 0) return line === anchorLine(hk);
  return line >= hk.n + 1 && line <= hk.n + hk.nl;
}
function anchorLine(hk) {
  return Math.max(1, Math.min(hk.n + 1, hk.lines || hk.n + 1));
}

function compute(doc) {
  if (!doc.model || doc.model.isDisposed()) return;
  const b = base.get(doc.path);
  let hunks = [];
  if (b && b.text !== null) {
    const cur = doc.model.getValue(monaco.editor.EndOfLinePreference.LF);
    if (doc.model.getLineCount() <= 30000) hunks = lineDiff(b.text, cur);
  }
  const total = doc.model.getLineCount();
  for (const hk of hunks) hk.lines = total;
  doc.hunks = hunks;
  const decos = [];
  for (const hk of hunks) {
    if (hk.nl === 0) {
      const ln = anchorLine(hk);
      const atEnd = hk.n + 1 > total;
      decos.push({ range: new monaco.Range(ln, 1, ln, 1), options: {
        linesDecorationsClassName: `dv-chg dv-chg-del${atEnd ? ' is-end' : ''}`,
        overviewRuler: { color: '#868a91', position: monaco.editor.OverviewRulerLane.Left } } });
    } else {
      const cls = hk.ol === 0 ? 'dv-chg-add' : 'dv-chg-mod';
      decos.push({ range: new monaco.Range(hk.n + 1, 1, hk.n + hk.nl, 1), options: { isWholeLine: true,
        linesDecorationsClassName: `dv-chg ${cls}`,
        overviewRuler: { color: hk.ol === 0 ? '#549159' : '#375fad', position: monaco.editor.OverviewRulerLane.Left } } });
    }
  }
  doc.chgIds = doc.model.deltaDecorations(doc.chgIds || [], decos);
  emit('hunks', doc);
  if (popup && popup.doc === doc) {
    if (!hunks.length) hidePopup();
    else showPopup(doc, Math.min(popup.index, hunks.length - 1));
  }
}

// ======= 변경 사이 이동 · 되돌리기 =======
export function gotoChange(dir) {
  const doc = currentDoc();
  if (!doc?.hunks?.length) { toast('바뀐 곳 없음'); return; }
  const line = editor.getPosition()?.lineNumber || 1;
  const starts = doc.hunks.map((hk) => (hk.nl === 0 ? anchorLine(hk) : hk.n + 1));
  let i;
  if (dir > 0) { i = starts.findIndex((s) => s > line); if (i < 0) i = 0; }
  else { i = starts.map((s, k) => [s, k]).filter(([s]) => s < line).pop()?.[1]; if (i === undefined) i = starts.length - 1; }
  editor.revealLineInCenter(starts[i]);
  editor.setPosition({ lineNumber: starts[i], column: 1 });
  showPopup(doc, i);
}

function rollback(doc, hk) {
  const m = doc.model;
  const total = m.getLineCount();
  const oldText = hk.old.join('\n');
  let range, text;
  if (hk.nl === 0) {
    // 지워진 줄 되살리기 — hk.n 줄(0 기준) 앞에 삽입
    if (hk.n >= total) { range = new monaco.Range(total, m.getLineMaxColumn(total), total, m.getLineMaxColumn(total)); text = '\n' + oldText; }
    else { range = new monaco.Range(hk.n + 1, 1, hk.n + 1, 1); text = oldText + '\n'; }
  } else if (hk.ol === 0) {
    // 추가된 줄 지우기
    const s = hk.n + 1, e = hk.n + hk.nl;
    if (e < total) range = new monaco.Range(s, 1, e + 1, 1);
    else if (s > 1) range = new monaco.Range(s - 1, m.getLineMaxColumn(s - 1), e, m.getLineMaxColumn(e));
    else range = new monaco.Range(1, 1, e, m.getLineMaxColumn(e));
    text = '';
  } else {
    const s = hk.n + 1, e = hk.n + hk.nl;
    range = new monaco.Range(s, 1, e, m.getLineMaxColumn(e));
    text = oldText;
  }
  m.pushStackElement();
  m.pushEditOperations([], [{ range, text }], () => null);
  m.pushStackElement();
  editor.focus();
}

// ======= 팝업 =======
function showPopup(doc, index) {
  const hk = doc.hunks[index];
  if (!hk) return;
  hidePopup();
  const host = editor.getDomNode();
  const kind = hk.ol === 0 ? '추가' : hk.nl === 0 ? '삭제' : '수정';
  const range = hk.nl === 0 ? `${anchorLine(hk)}줄 위` : `${hk.n + 1}${hk.nl > 1 ? '–' + (hk.n + hk.nl) : ''}줄`;
  const el = h(`<div class="dv-hunk">
    <div class="dv-hunk-head"><span>${kind} · ${range} · ${index + 1}/${doc.hunks.length}</span>
      <button data-a="prev" title="이전 변경 (Ctrl+Alt+Shift+↑)">${icon('up')}</button>
      <button data-a="next" title="다음 변경 (Ctrl+Alt+Shift+↓)">${icon('down')}</button>
      <button data-a="undo" title="이 부분을 HEAD 내용으로 되돌리기">${icon('undo')}되돌리기</button>
      <button data-a="close" title="닫기 (Esc)">${icon('x')}</button></div>
    ${hk.ol ? `<pre class="dv-hunk-old">${esc(hk.old.join('\n'))}</pre>` : '<div class="dv-hunk-none">HEAD 에 없던 줄</div>'}
  </div>`);
  const top = editor.getTopForLineNumber(hk.nl === 0 ? anchorLine(hk) : hk.n + hk.nl + 1) - editor.getScrollTop();
  el.style.top = `${Math.max(4, Math.min(top + 2, host.clientHeight - 80))}px`;
  el.style.left = `${editor.getLayoutInfo().contentLeft}px`;
  el.addEventListener('mousedown', (e) => e.stopPropagation());
  el.addEventListener('click', (e) => {
    const a = e.target.closest('[data-a]')?.dataset.a;
    if (a === 'close') hidePopup();
    else if (a === 'undo') { rollback(doc, hk); hidePopup(); }
    else if (a === 'prev' || a === 'next') {
      const n = doc.hunks.length;
      const j = (index + (a === 'next' ? 1 : -1) + n) % n;
      const t = doc.hunks[j];
      const ln = t.nl === 0 ? anchorLine(t) : t.n + 1;
      editor.revealLineInCenter(ln);
      showPopup(doc, j);
    }
  });
  host.append(el);
  popup = { el, doc, index };
}

export function hidePopup() {
  if (popup) { popup.el.remove(); popup = null; }
}
on('escape', () => hidePopup());

export const hunkCount = (doc) => doc?.hunks?.length || 0;
