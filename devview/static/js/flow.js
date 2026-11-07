// 그래프 보기 — flowtree 화면(/ft/)을 iframe 으로 담고, 노드의 연결 문서를 오른쪽 절반에 기존 보기(편집기 · md · PDF · 엑셀)로 연다
//   flowtree → devview: {ft:'open', path, line, anchor} 오른쪽 절반에 열기 · {ft:'close'} 닫기
//   devview → flowtree: {ft:'closed'} 이쪽(× · Esc · ` · 다른 보기로 감)에서 닫았음 — flowtree 가 자기 패널을 되살림
import { $, kitPath } from './util.js';

// 그래프 iframe — 그래프 보기를 처음 열 때 만듦(코드로 시작하면 flowtree 화면을 안 읽음)
let frame = null;
// 그래프에서 고른 노드 {view: feature · adr · code, nodes: [{id, kind, graph, title}]} — flowtree 가 바뀔 때마다 알림(허브 마법봉 대상)
let ftSel = { view: '', nodes: [] };
// flowtree 를 찾았는지(서버 info.flowtree.ok)
let available = false;
// 열린 연결 문서 {path, line} — 없으면 null
let split = null;
// main.js 가 넘긴 것 — openFile · editor · watchFocus · view(지금 보기 이름)
let deps = {};

// 그래프 화면이 있는지
export const flowReady = () => available;
// 오른쪽 절반에 연결 문서가 열려 있는지
export const flowSplit = () => !!split;

// 입력 중인 칸인가 — 편집기(Monaco · md) · 입력칸 안의 ` · Esc 는 그 칸 몫
// el: 포커스 요소
function typingIn(el) {
  if (!el) return false;
  return /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName) || el.isContentEditable || !!el.closest?.('.monaco-editor');
}

// 그래프 보기 준비 — flowtree 가 없으면 한 줄 안내만(false 반환)
// info: 서버 info / d: {openFile, editor, watchFocus, view}
export function initFlow(info, d) {
  deps = d;
  if (!info.flowtree?.ok) {
    $('#ftView').innerHTML = '<div class="dv-ft-none">flowtree 없음</div>';
    return false;
  }
  available = true;
  window.addEventListener('message', (e) => {
    if (!frame || e.source !== frame.contentWindow || !e.data?.ft) return;
    if (e.data.ft === 'open') openSplit(e.data);
    else if (e.data.ft === 'close') closeSplit(false);
    else if (e.data.ft === 'selection') ftSel = { view: String(e.data.view || ''), nodes: Array.isArray(e.data.nodes) ? e.data.nodes : [] };
    else if (e.data.ft === 'flushed') { const f = flushWait.get(e.data.id); if (f) { flushWait.delete(e.data.id); f(); } }
  });
  $('#ftClose').addEventListener('click', () => closeSplit(true));
  // 오른쪽 칸 쪽에 포커스가 있을 때의 ` · Esc — 입력 칸 · 편집기 안에서는 그 칸 몫
  window.addEventListener('keydown', (e) => {
    if (!split || e.isComposing || e.ctrlKey || e.altKey || e.metaKey || e.shiftKey) return;
    if (e.key !== 'Escape' && e.code !== 'Backquote') return;
    if (typingIn(document.activeElement)) return;
    e.preventDefault();
    e.stopPropagation();
    closeSplit(true);
  }, true);
  return true;
}

// 그래프 iframe 만들기(한 번만)
function ensureFrame() {
  if (frame || !available) return;
  frame = document.createElement('iframe');
  frame.title = '그래프';
  frame.src = 'ft/';
  $('#ftView').appendChild(frame);
  // 같은 주소라 안 문서에 키 처리기(마법봉 Alt+Q · W · 기호 · 팔레트)를 붙일 수 있음 — 새로 읽을 때마다 다시
  frame.addEventListener('load', () => {
    try { deps.watchFocus(frame.contentDocument); } catch { /* 다른 주소 */ }
    loaded = true;
    // 읽기 전에 미뤄 둔 메시지(알림 종 focus 등)
    for (const m of queued.splice(0)) frame.contentWindow?.postMessage(m, '*');
    // 읽기 전에 미뤄 둔 포커스 — 그사이 유저가 다른 곳을 눌렀으면 건드리지 않음
    if (wantFocus && deps.view() === 'graph' && [document.body, frame].includes(document.activeElement)) focusNow();
    wantFocus = false;
  });
}

// 그래프 문서가 다 읽혔는지(키 처리기를 붙인 뒤) · 읽기 전 포커스 요청이 있었는지
let loaded = false;
let wantFocus = false;

// 지금 그래프 iframe 에 포커스
function focusNow() {
  frame.focus();
  frame.contentWindow?.focus();
}

// 보기에 맞춰 배치 — main.js showView 끝에서 부름. 그래프가 아닌 보기로 가면 연결 문서는 닫힘
// view: 지금 보기 이름
export function flowLayout(view) {
  if (view === 'graph') ensureFrame();
  if (split && view !== 'graph') closeSplit(true, false);
  // 그래프 + 연결 문서
  const on = !!split && view === 'graph';
  if (!on && !$('.dv-main').classList.contains('is-ftsplit')) return;   // 나눔이 없고 없던 채 — 손댈 것 없음(showView 가 이미 배치)
  $('.dv-main').classList.toggle('is-ftsplit', on);
  $('#ftBar').hidden = !on;
  $('#codeView').hidden = !(view === 'code' || on);
  if (on) document.documentElement.style.setProperty('--dv-ftbar-h', `${$('#ftBar').offsetHeight || 30}px`);
  setTimeout(() => deps.editor?.()?.layout(), 0);
}

// 연결 문서 열기 — 오른쪽 절반에 기존 보기로, 줄이 있으면 그 줄로. 포커스는 그래프로 되돌림(` · Esc 가 그래프 키 처리로)
// m: {path, line, anchor}
async function openSplit(m) {
  // flowtree 경로는 키트 기준(작업 공간 루트 = 키트) → 작업 폴더 기준으로
  const path = m.path ? kitPath(m.path) : null;
  if (!path) return;
  split = { path, line: m.line || null };
  $('#ftBarPath').textContent = `${path}${m.line ? `:${m.line}` : ''}${m.anchor ? `  (${m.anchor})` : ''}`;
  flowLayout(deps.view());
  // 연 문서(실패하면 null — openFile 이 알림)
  const doc = await deps.openFile(path, { line: m.line || null, focus: false });
  if (!doc) { closeSplit(true); return; }
  setTimeout(() => deps.editor?.()?.layout(), 0);
  setTimeout(() => { frame.focus(); frame.contentWindow?.focus(); }, 30);
}

// 연결 문서 닫기 — 그래프를 다시 전체 폭으로
// tell: flowtree 에 닫혔다고 알림(이쪽에서 닫을 때) / relayout: 배치 다시(flowLayout 안에서 부를 땐 false)
export function closeSplit(tell = true, relayout = true) {
  if (!split) return;
  split = null;
  if (tell) frame?.contentWindow?.postMessage({ ft: 'closed' }, '*');
  if (relayout) flowLayout(deps.view());
  if (relayout && deps.view() === 'graph') setTimeout(() => { frame?.focus(); frame?.contentWindow?.focus(); }, 0);
}

// 그래프 iframe 에 포커스 — 그래프 보기로 왔을 때 바로 노드 키(` · 1 · 2)가 먹게
//   다 읽히기 전이면 읽은 뒤로 미룸 — 읽는 중인 iframe 에 포커스를 주면 그사이 누른 키(Alt+D 등)가 어디에도 안 감
export function focusFlow() {
  if (!frame) return;
  if (!loaded) { wantFocus = true; return; }
  setTimeout(focusNow, 0);
}

// 그래프 iframe 에 메시지 — 아직 안 읽혔으면 읽은 뒤 보냄(알림 종 → {ft:'focus', node, screen?})
// m: 메시지 / 반환: 그래프 화면이 있는지
const queued = [];
// 마법봉 직전 «지금 칸 저장» — 그래프 안 열린 입력 칸(메모 · 제목)을 저장하고 끝나면 풀림(그래프가 없거나 답이 없으면 1.5초 뒤 그냥)
//   저장 뒤 선택 알림(ft:'selection')이 다시 올 시간을 한 틱 더 준다
export function flushFlow() {
  if (!available || !loaded || !frame?.contentWindow) return Promise.resolve();
  const id = `f${++flushSeq}`;
  return new Promise((res) => {
    const done = () => setTimeout(res, 30);
    flushWait.set(id, done);
    setTimeout(() => { if (flushWait.delete(id)) res(); }, 1500);
    frame.contentWindow.postMessage({ ft: 'flush', id }, '*');
  });
}
// 저장 기다리는 요청 id → 풀기 · 일련번호
const flushWait = new Map();
let flushSeq = 0;

export function flowPost(m) {
  if (!available) return false;
  ensureFrame();
  if (loaded) frame.contentWindow?.postMessage(m, '*'); else queued.push(m);
  return true;
}

// 시험 · 디버깅용 — 지금 연결 문서
export const flowState = () => ({ split: split && { ...split }, ready: !!frame });

// 그래프에서 고른 노드(허브 마법봉) — 그래프를 아직 안 열었으면 빈 목록
export const flowSelection = () => ({ view: ftSel.view, nodes: ftSel.nodes.map((n) => ({ ...n })) });
