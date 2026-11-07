// 알림 종 — 모든 보기 좌하단(끌어서 옮김 · drag.js) · 우상단 배지 = 안 읽은 개수 · 누르면 목록 창
//   목록 한 줄 누름 = 그 위치로 이동 + 읽음 · «모두 읽음» 단추 · Esc · 바깥 누름 = 닫기
//   이동: graph = 그래프 보기 → flowtree iframe 에 {ft:'focus', node, screen?} · book = Book 보기 → 책 주소#note=<id>[&t=<꼬리>]
//         survey = 설문 보기 → 그 설문 · chat = 대화 보기 → 그 세션 탭 · code = 그 파일(줄) · 그 밖 view = 그 보기
//   서버: GET api/notify(2초마다 · 숨은 탭 5초) · POST api/notify/read — 저장은 <키트>/.codex-hub/notify.jsonl(notify.py)
import { api } from './api.js';
import { $, h, esc, on, emit, toast } from './util.js';
import { makeMovable } from './drag.js';
import { flowPost } from './flow.js';
import { bookOpen } from './book.js';
import { hubRows } from './hub.js';

// 종 · 목록 아이콘(Lucide · ISC)
const BELL = '<svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M10.268 21a2 2 0 0 0 3.464 0"/><path d="M3.262 15.326A1 1 0 0 0 4 17h16a1 1 0 0 0 .74-1.673C19.41 13.956 18 12.499 18 8A6 6 0 0 0 6 8c0 4.499-1.411 5.956-2.738 7.326"/></svg>';
// 종류 → 이름(notify.py KINDS 와 같게)
const KINDS = { done: '완료', block: '이상', hold: '보류', pass: '정상', fail: '비정상', answer: '답변', note: '책 답',
  survey: '설문', 'survey-ack': '설문 반영', 'route-fail': '전달 실패', hub: '세션 대기', decide: '결정 필요',
  magic: '마법봉', 'queue-fail': '큐 전달 실패', report: '서브 보고', book: '책 새 판', info: '알림' };
// 출처 → 이름
const SRC = { script: '스크립트', tree: '그래프', notes: '책', survey: '설문', hub: '허브' };
// 그래프 노드 종류(notify.py 자동 수집의 node 칸) → 색 이름 — 색 값은 app.css .dv-notify-item.c-*(flowtree meta.js 노드 색과 같게)
const NODE_TONE = { task: 'task', verify: 'verify', question: 'question', survey: 'survey' };
// 북키트(책 · 스티커 답 · 책 새 판) 종류
const BOOK_KINDS = new Set(['note', 'book']);
const POLL_MS = 2000;

let deps = {};
let el = {};
let data = { items: [], unread: 0 };
let open = false;
let painted = '';
let mover = null;

// 알림 종 준비 — 서버에 notify.py 가 없으면 안 띄움
// info: 서버 info / d: {showView, openFile, view}
export function initNotify(info, d) {
  deps = d;
  if (!info.notify) return false;
  const main = $('.dv-main');
  el.bell = h(`<div class="dv-bell" id="bell"><div class="dv-bell-btn" role="button" tabindex="0" title="알림">${BELL}<span class="dv-bell-badge" hidden></span></div></div>`);
  el.btn = $('.dv-bell-btn', el.bell);
  el.badge = $('.dv-bell-badge', el.bell);
  el.panel = h(`<div class="dv-notify" id="notifyPanel" hidden>
    <div class="dv-notify-head"><span class="dv-notify-title">알림 <b class="dv-notify-count"></b></span>
      <button class="dv-notify-all" type="button" data-act="all" title="안 읽은 알림 전부 읽음 처리">모두 읽음</button></div>
    <div class="dv-notify-list" role="list"></div></div>`);
  el.list = $('.dv-notify-list', el.panel);
  el.count = $('.dv-notify-count', el.panel);
  el.all = $('.dv-notify-all', el.panel);
  main.append(el.bell);
  // 허브(펼침 · 접힘 · 최소화) 기본 자리는 종 오른쪽으로(종 왼쪽 12 + 폭 36 + 여백 12) — 끌어서 저장한 자리는 drag.js 가 그대로
  document.documentElement.style.setProperty('--dv-hub-min-left', '60px');
  document.documentElement.style.setProperty('--dv-hub-left', '60px');
  document.body.append(el.panel);
  // 끌어서 옮기기 — 종 전체가 손잡이(drag.js 는 <button> 위에서 끌기를 시작하지 않아 종은 div role=button)
  mover = makeMovable(el.bell, el.bell, 'bell.pos', { onMove: () => { if (open) place(); } });
  el.btn.addEventListener('click', () => toggle());
  el.btn.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggle(); } });
  el.panel.addEventListener('click', (e) => {
    if (e.target.closest('[data-act="all"]')) { readAll(); return; }
    const row = e.target.closest('[data-id]');
    if (row) go(row.dataset.id);
  });
  document.addEventListener('mousedown', (e) => {
    if (open && !el.panel.contains(e.target) && !el.bell.contains(e.target)) toggle(false);
  }, true);
  on('escape', () => { if (open) toggle(false); });
  window.addEventListener('keydown', (e) => { if (open && e.key === 'Escape') toggle(false); });
  window.addEventListener('resize', () => { if (open) place(); });
  poll();
  return true;
}

// 목록 받기
async function poll() {
  await load();
  setTimeout(poll, document.hidden ? 5000 : POLL_MS);
}
async function load() {
  try { data = await api('notify'); } catch { return; }
  paint();
}

// 배지 · 목록 그리기(바뀐 것이 있을 때만)
function paint() {
  const n = data.unread || 0;
  el.badge.hidden = !n;
  el.badge.textContent = n > 99 ? '99+' : String(n);
  el.bell.classList.toggle('has-unread', n > 0);
  el.btn.title = n ? `알림 — 안 읽음 ${n}` : '알림';
  el.count.textContent = n ? String(n) : '';
  el.all.disabled = !n;
  const sig = JSON.stringify(data.items.map((r) => [r.id, r.read]));
  if (sig === painted) return;
  painted = sig;
  el.list.innerHTML = data.items.length ? data.items.map(row).join('') : '<div class="dv-notify-none">알림 없음</div>';
}

// 색 이름 — 그래프 자동 수집(src tree + node) = 노드 종류 색 · 설문 도구 = 설문 · 북키트 = book · 나머지(스크립트 등록 · 허브 · node 없는 옛 기록) = 회색
// r: 알림
export function tone(r) {
  if (r.src === 'tree') return NODE_TONE[r.node] || 'etc';
  if (r.src === 'survey') return 'survey';
  if (r.src === 'notes' || BOOK_KINDS.has(r.kind)) return 'book';
  return 'etc';
}

// 한 줄
// r: 알림
function row(r) {
  const kind = KINDS[r.kind] || r.kind;
  const where = toLabel(r.to || {});
  return `<button type="button" class="dv-notify-item c-${tone(r)}${r.read ? ' is-read' : ''}${r.level === 'bad' ? ' is-bad' : ''}" role="listitem" data-id="${esc(r.id)}" title="${esc(where)}">`
    + `<span class="dv-notify-kind k-${esc(r.kind)}">${r.level === 'bad' ? '🔴 ' : ''}${esc(kind)}</span>`
    + `<span class="dv-notify-text"><span class="dv-notify-t">${esc(r.title)}</span>`
    + (r.body ? `<span class="dv-notify-b">${esc(r.body)}</span>` : '')
    + `<span class="dv-notify-meta">${esc(String(r.at || '').slice(5, 16))} · ${esc(SRC[r.src] || r.src || '')}${where ? ` · ${esc(where)}` : ''}</span></span>`
    + '</button>';
}

// 이동 대상 글(툴팁 · 회색 줄)
function toLabel(to) {
  if (to.view === 'graph') return `그래프 ${to.node || ''}`;
  if (to.view === 'book') return `책 ${to.book || ''}`;
  if (to.view === 'survey') return '설문';
  if (to.view === 'chat') return `대화 ${to.nick || ''}`;
  if (to.view === 'code') return `${to.path || ''}${to.line ? `:${to.line}` : ''}`;
  return to.view ? String(to.view) : '';
}

// 목록 창 열기 · 닫기
// v: 열기 여부(없으면 뒤집기)
function toggle(v) {
  open = v === undefined ? !open : !!v;
  el.panel.hidden = !open;
  el.bell.classList.toggle('is-open', open);
  if (open) { place(); load(); }
}

// 목록 창 자리 — 종 위(자리가 없으면 아래) · 화면 안으로
function place() {
  const b = el.bell.getBoundingClientRect();
  const p = el.panel;
  const w = p.offsetWidth;
  const ht = p.offsetHeight;
  const left = Math.max(6, Math.min(b.left, innerWidth - w - 6));
  const top = b.top - ht - 8 >= 6 ? b.top - ht - 8 : Math.min(b.bottom + 8, innerHeight - ht - 6);
  p.style.left = `${left}px`;
  p.style.top = `${Math.max(6, top)}px`;
}

// 읽음 처리
async function read(ids) {
  try { data = await api('notify/read', { body: { ids } }); paint(); } catch (e) { toast(`읽음 처리 실패 — ${e.message}`, 'bad'); }
}
async function readAll() {
  try { data = await api('notify/read', { body: { all: true } }); paint(); } catch (e) { toast(`읽음 처리 실패 — ${e.message}`, 'bad'); }
}

// 하나 고름 → 그 위치로 · 읽음
// id: 알림 id
async function go(id) {
  const r = data.items.find((x) => x.id === id);
  if (!r) return;
  toggle(false);
  if (!r.read) read([id]);
  await jump(r.to || {});
}

// 이동
// to: 이동 대상
export async function jump(to) {
  const v = to.view;
  if (v === 'graph') {
    deps.showView('graph');
    if (to.node) {
      const m = { ft: 'focus', node: String(to.node) };
      if (to.screen !== undefined && to.screen !== null) m.screen = to.screen;
      if (to.graph) m.graph = to.graph;
      flowPost(m);
    }
  } else if (v === 'book') {
    deps.showView('book');
    const hash = to.note ? `#note=${encodeURIComponent(to.note)}${to.t ? `&t=${encodeURIComponent(to.t)}` : ''}` : '';
    const ok = await bookOpen({ book: to.book, path: to.path }, hash);
    if (!ok) toast(`책 없음 — ${to.book || to.path || ''}`, 'bad');
  } else if (v === 'survey') {
    const f = $('#svView iframe');
    if (!f) { toast('설문 도구 없음', 'bad'); return; }
    deps.showView('survey');
    if (to.id) {
      const q = new URLSearchParams();
      for (const k of ['s', 'p', 'id']) if (to[k]) q.set(k, to[k]);
      f.src = `sv/?${q}`;
    }
  } else if (v === 'chat') {
    if ($('#chatTab')?.hidden) { toast('대화 보기 없음 — 허브가 꺼져 있음', 'bad'); return; }
    deps.showView('chat');
    const i = hubRows().filter((x) => x.registered && x.thread).findIndex((x) => x.nick === to.nick);
    if (i >= 0) emit('chat-pick', i);
  } else if (v === 'code' && to.path) {
    deps.showView('code');
    await deps.openFile(to.path, { line: to.line || null });
  } else if (v) {
    deps.showView(v);
  }
}

// 시험 · 디버깅용
export const notifyDebug = () => ({ open, unread: data.unread, items: data.items.length, pos: mover?.pos() || null });
