// Git 주석(blame) — 줄 번호 칸에 «날짜 작성자» 표시. PyCharm 의 Annotate with Git Blame
// 줄마다 장식을 붙여 두고 그 장식으로 줄을 찾음 → 편집으로 줄이 밀려도 주석이 제 줄을 따라감
// 줄 번호 칸 색 = 커밋 나이(최근일수록 진한 파랑, PyCharm VCS_ANNOTATIONS_COLOR_1~5)
// 줄 번호 클릭 → Git 탭에서 그 커밋 · 그 파일 diff
import { api } from './api.js';
import { h, esc, emit, on, shortDate, fmtDate, toast } from './util.js';
import { getDoc } from './docs.js';

let monaco = null;
let editor = null;
const state = new Map();         // 경로 → { data, ids, idx: Map(장식 id → 줄 배열 위치) }
let tip = null;

export function initBlame(m, ed) {
  monaco = m;
  editor = ed;
  on('doc-saved', (doc) => { if (state.has(doc.path)) refreshSoon(doc); });
  on('git-head', () => { for (const p of state.keys()) { const d = getDoc(p); if (d) refreshSoon(d); } });
  bindEditor(ed);
}

// 나눠 보기 — 편집기마다 줄 번호 칸 클릭 · 툴팁을 붙임. 처리할 때는 그 편집기를 기준으로
export function bindEditor(ed) {
  ed.onMouseDown((e) => {
    if (e.target.type !== monaco.editor.MouseTargetType.GUTTER_LINE_NUMBERS) return;
    const info = infoAt(e.target.position?.lineNumber, ed);
    if (info && !info.uncommitted) emit('git-show', { h: info.h, path: info.path });
  });
  ed.onMouseMove((e) => {
    if (e.target.type !== monaco.editor.MouseTargetType.GUTTER_LINE_NUMBERS) { hideTip(); return; }
    const info = infoAt(e.target.position?.lineNumber, ed);
    if (!info) { hideTip(); return; }
    showTip(info, e.event.posx, e.event.posy);
  });
  ed.onMouseLeave(() => hideTip());
  ed.onDidChangeModel(() => { hideTip(); applyFor(currentDoc(ed), ed); });
}
export function useEditor(ed) { editor = ed; }

function currentDoc(ed = editor) {
  const m = ed.getModel();
  if (!m) return null;
  for (const p of state.keys()) { const d = getDoc(p); if (d?.model === m) return d; }
  return null;
}

export const isOn = (doc) => !!doc && state.has(doc.path);

export async function toggleBlame(doc) {
  if (!doc || doc.kind !== 'code' || doc.readonly) return;
  if (state.has(doc.path)) {
    const s = state.get(doc.path);
    doc.model.deltaDecorations(s.ids, []);
    state.delete(doc.path);
    applyFor(doc);
    emit('blame', doc);
    return;
  }
  state.set(doc.path, { data: null, ids: [], idx: new Map() });
  await refresh(doc);
  emit('blame', doc);
}

const timers = new Map();
function refreshSoon(doc) {
  clearTimeout(timers.get(doc.path));
  timers.set(doc.path, setTimeout(() => refresh(doc), 400));
}

async function refresh(doc) {
  const s = state.get(doc.path);
  if (!s) return;
  let r;
  try {
    r = await api('git/blame', { query: { path: doc.path } });
  } catch (e) {
    toast(`주석 실패: ${e.message}`, 'bad');
    return;
  }
  if (!state.has(doc.path)) return;
  if (r.untracked) { toast('git 이 모르는 파일 — 주석 없음'); state.delete(doc.path); applyFor(doc); emit('blame', doc); return; }
  if (r.too_large) { toast('파일이 커서 주석 생략'); state.delete(doc.path); applyFor(doc); emit('blame', doc); return; }
  // 커밋 나이 순위 → 5단계 색
  const times = [...new Set(Object.values(r.commits).map((c) => c.at || 0))].sort((a, b) => b - a);
  const rank = new Map(times.map((t, i) => [t, Math.min(5, 1 + Math.floor((i * 5) / Math.max(1, times.length)))]));
  const decos = r.lines.map((hash, i) => {
    const c = r.commits[hash] || {};
    const unc = /^0+$/.test(hash || '');
    return { range: new monaco.Range(i + 1, 1, i + 1, 1), options: {
      lineNumberClassName: unc ? 'dv-age-new' : `dv-age-${rank.get(c.at || 0) || 5}`,
      stickiness: monaco.editor.TrackedRangeStickiness.NeverGrowsWhenTypingAtEdges } };
  });
  s.ids = doc.model.deltaDecorations(s.ids, decos);
  s.idx = new Map(s.ids.map((id, i) => [id, i]));
  s.data = r;
  applyFor(doc);
}

function infoAt(line, ed = editor) {
  const doc = currentDoc(ed);
  const s = doc && state.get(doc.path);
  if (!s?.data || !line) return null;
  for (const d of doc.model.getLineDecorations(line)) {
    const i = s.idx.get(d.id);
    if (i === undefined) continue;
    const hash = s.data.lines[i];
    const c = s.data.commits[hash] || {};
    return { h: hash, path: doc.path, an: c.an || '', at: c.at || 0, s: c.s || '', uncommitted: /^0+$/.test(hash || '') };
  }
  return null;
}

function label(doc, line) {
  const s = state.get(doc.path);
  const num = String(line);
  if (!s?.data) return num;
  for (const d of doc.model.getLineDecorations(line)) {
    const i = s.idx.get(d.id);
    if (i === undefined) continue;
    const hash = s.data.lines[i];
    if (/^0+$/.test(hash || '')) return `${'커밋 전'.padEnd(17)} ${num.padStart(4)}`;
    const c = s.data.commits[hash] || {};
    const who = (c.an || '').slice(0, 9).padEnd(9);
    return `${shortDate(c.at)} ${who} ${num.padStart(4)}`;
  }
  return `${''.padEnd(17)} ${num.padStart(4)}`;
}

// 현재 편집기에 보이는 문서 기준으로 줄 번호 칸 설정
export function applyFor(doc, ed = editor) {
  if (doc && state.has(doc.path) && state.get(doc.path).data && ed.getModel() === doc.model) {
    ed.updateOptions({ lineNumbers: (n) => label(doc, n), lineNumbersMinChars: 24 });
  } else {
    ed.updateOptions({ lineNumbers: 'on', lineNumbersMinChars: 4 });
  }
}

function showTip(info, x, y) {
  if (!tip) {
    tip = h('<div class="dv-tip"></div>');
    document.body.append(tip);
  }
  tip.innerHTML = info.uncommitted ? '아직 커밋하지 않은 줄'
    : `<b>${esc(info.h.slice(0, 8))}</b> · ${esc(info.an)} · ${esc(fmtDate(info.at))}<br>${esc(info.s)}<br><span class="dv-dim">클릭 → Git 탭에서 이 커밋</span>`;
  tip.style.left = `${x + 14}px`;
  tip.style.top = `${y + 12}px`;
  tip.hidden = false;
}
function hideTip() {
  if (tip) tip.hidden = true;
}
