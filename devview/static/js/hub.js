// 코덱스 허브 — devview 모든 보기 좌하단(대화 보기 제외)의 Codex 세션판
//   행 = 세션(기본 MAIN · 2ND + 추가 등록) · 닉네임 | effort | 맥락 | 지금 작업 · 행 테두리 = 상태(작업 중 노랑 빙글 · 턴 끝 녹색 점멸 · 오류 빨강 점멸)
//   행 클릭 = 선택(확인 → 점멸 꺼짐) → 누적창(허브 바로 위) + 행 오른쪽 아이콘 트레이(문서 = 직접 입력 · 마법봉 = 역할 magic)
//   입력창(허브 바로 위 · Enter 줄바꿈 · ✕ 취소 · ✈ 전송 · Esc 로 안 닫힘) · Esc = 행 선택 해제 · 작은 접기 단추
//   − 단추 = 최소화(세션 이름 칩만 · 화면 좌하단 · 왼쪽 = css --dv-hub-min-left) · + = 최소화 · 접힘 둘 다 풀고 가장 펼친 상태
//   행 목록 · 칩 줄을 끌면 옮김(drag.js · 상태별 위치 저장) · 더블클릭 = 기본 자리
//   서버: GET api/hub · api/hub/log · POST api/hub/queue · api/hub/magic
import { api } from './api.js';
import { $, h, esc, on, emit, store, toast } from './util.js';
import { makeMovable } from './drag.js';

// 선 아이콘(Lucide · ISC) — devview 우상단 단추와 같은 굵기 2
const ICONS = {
  doc: '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/><path d="M10 9H8"/><path d="M16 13H8"/><path d="M16 17H8"/>',
  wand: '<path d="m21.64 3.64-1.28-1.28a1.21 1.21 0 0 0-1.72 0L2.36 18.64a1.21 1.21 0 0 0 0 1.72l1.28 1.28a1.2 1.2 0 0 0 1.72 0L21.64 5.36a1.2 1.2 0 0 0 0-1.72"/><path d="m14 7 3 3"/><path d="M5 6v4"/><path d="M19 14v4"/><path d="M10 2v2"/><path d="M7 8H3"/><path d="M21 16h-4"/><path d="M11 3H9"/>',
  send: '<path d="M14.536 21.686a.5.5 0 0 0 .937-.024l6.5-19a.496.496 0 0 0-.635-.635l-19 6.5a.5.5 0 0 0-.024.937l7.93 3.18a2 2 0 0 1 1.112 1.11z"/><path d="m21.854 2.147-10.94 10.939"/>',
  x: '<path d="M18 6 6 18"/><path d="m6 6 12 12"/>',
  down: '<path d="m6 9 6 6 6-6"/>',
  up: '<path d="m18 15-6-6-6 6"/>',
  minus: '<path d="M5 12h14"/>',
  plus: '<path d="M5 12h14"/><path d="M12 5v14"/>',
};
// 아이콘 svg 글
// name: ICONS 키
const ic = (name) => `<svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[name]}</svg>`;
// effort 기호 — 사용량 위젯(claude_usage_widget EFFORT_SYMBOL) 규칙 그대로 · max 는 허브에서 안 씀
export const EFFORT = { low: '○', medium: '◐', high: '●', xhigh: '◎' };
// 행 높이(px) — 5행이 허브 높이 150 을 채움
const ROW_H = 30;
// 목록 갱신 간격(ms)
const POLL_MS = 1500;

// main.js 가 넘긴 것 — view() · codeSel() · markCode() · clearMark() · gitSel() · ftSel()
let deps = {};
let queueOpen = null;   // 큐를 펼친 세션 닉네임
// 서버 행 목록 · queue 준비 상태
let rows = [];
let queueInfo = { ok: true, reason: null };
// 고른 행 닉네임 · 열린 창(null · 'acc' · 'input') · 입력창 문맥 {nick, kind: queue|magic, snap}
let picked = null;
let mode = null;
let inputCtx = null;
// 접힘 여부 · 확인 기록(thread → 마지막으로 확인한 턴 id) · 쓰던 글(닉네임:종류 → 글)
//   저장값은 initHub 에서 읽음 — 모듈을 불러오는 순간에는 작업 폴더별 저장 이름(setStoreNs)이 아직 안 정해짐
let folded = false;
// 최소화 여부(접힘과 따로 저장 — + 로 풀면 접힘도 풀림)
let minimized = false;
// 끌어 옮기기(drag.js) — 위치는 상태별 따로(hub.pos · hub.pos.min)
let mover = null;
let seen = {};
const drafts = {};
// 허브 상자 · 화면 부품
let box = null;
let el = {};
// 누적창에 그린 줄 수(바뀔 때만 다시 그림)
let accCount = -1;

// 화면 이름
// nick: 닉네임
const labelOf = (nick) => rows.find((r) => r.nick === nick)?.label || nick;

// 맥락 글 — «154k/258k (60%)»
// c: {used, window, pct}
export function ctxText(c) {
  if (!c || c.used == null || !c.window) return '—';
  // k 단위
  const k = (n) => (n >= 1000 ? `${Math.round(n / 1000)}k` : String(n));
  return `${k(c.used)}/${k(c.window)} (${Math.round(c.pct ?? (c.used / c.window) * 100)}%)`;
}

// 행 상태 — 'spin' 작업 중 · 'err' 확인 안 한 오류 · 'blink' 확인 안 한 턴 끝 · '' 테두리 없음
// r: 서버 행
export function rowState(r) {
  if (!r || !r.registered) return '';
  if (r.state === 'working' || r.state === 'survey' || r.state === 'approval') return 'spin';
  const d = r.done;
  if (!d || !d.id || !r.thread || seen[r.thread] === d.id) return '';
  return d.error ? 'err' : 'blink';
}

// 확인 — 그 세션의 마지막 턴을 «봤음» 으로(점멸 꺼짐)
// r: 서버 행
export function markSeen(r) {
  if (!r?.thread || !r.done?.id || seen[r.thread] === r.done.id) return;
  seen = { ...seen, [r.thread]: r.done.id };
  store.set('hub.seen', seen);
  paint();
  emit('hub-rows', rows);
}

// 지금 행 목록(대화 보기가 씀)
export const hubRows = () => rows;

// 허브 준비 — info.hub 가 없으면 안 띄움
// info: 서버 info / d: main.js 가 넘긴 것
export function initHub(info, d) {
  deps = d;
  box = $('#hub');
  if (!info.hub || !box) return false;
  folded = !!store.get('hub.folded', false);
  minimized = !!store.get('hub.min', false);
  seen = store.get('hub.seen', {}) || {};
  box.innerHTML = `
    <div class="dv-hub-rows" role="list"></div>
    <button class="dv-hub-fold" type="button" title="접기 · 펼치기">${ic('down')}</button>
    <button class="dv-hub-min" type="button" title="최소화">${ic('minus')}</button>
    <div class="dv-hub-acc" hidden><div class="dv-hub-acc-body"></div></div>
    <div class="dv-hub-queue" hidden></div>
    <div class="dv-hub-input" hidden><div class="dv-hub-input-head"></div><textarea spellcheck="false"></textarea></div>
    <div class="dv-hub-acts" hidden>
      <button class="dv-hub-btn" type="button" data-act="cancel" title="취소 — 쓴 글을 지우고 닫기">${ic('x')}<span>취소</span></button>
      <button class="dv-hub-btn is-send" type="button" data-act="send" title="전송 — codex queue">${ic('send')}<span>전송</span></button>
    </div>
    <div class="dv-hub-tray" hidden>
      <button class="dv-hub-tic" type="button" data-act="doc" title="직접 입력 — 그 세션에 codex queue">${ic('doc')}</button>
      <button class="dv-hub-tic" type="button" data-act="wand" title="마법봉 — 그 세션의 magic">${ic('wand')}</button>
    </div>`;
  el = { rows: $('.dv-hub-rows', box), fold: $('.dv-hub-fold', box), min: $('.dv-hub-min', box), acc: $('.dv-hub-acc', box), accBody: $('.dv-hub-acc-body', box), queue: $('.dv-hub-queue', box),
    input: $('.dv-hub-input', box), head: $('.dv-hub-input-head', box), ta: $('.dv-hub-input textarea', box),
    acts: $('.dv-hub-acts', box), tray: $('.dv-hub-tray', box) };
  // 지연 없는 툴팁 — 브라우저 기본 title 은 1초쯤 늦어서 직접 그림
  el.tip = h('<div class="dv-hub-tip" hidden></div>');
  document.body.append(el.tip);
  // 눌러도 편집기 포커스 · 선택을 빼앗지 않게(기호 팔레트와 같은 mousedown 막기) — 누적창 글 고르기 · 입력칸은 그대로
  box.addEventListener('mousedown', (e) => {
    if (!e.target.closest('textarea, .dv-hub-acc')) e.preventDefault();
  });
  el.rows.addEventListener('click', (e) => {
    // 큐 배지 — 펼치기 · 닫기(행은 안 고름)
    const qb = e.target.closest('[data-q]');
    if (qb) { queueOpen = queueOpen === qb.dataset.q ? null : qb.dataset.q; paintQueue(); return; }
    // 누른 행
    const row = e.target.closest('.dv-hub-row');
    if (row) pick(row.dataset.nick === picked ? null : row.dataset.nick);
  });
  el.rows.addEventListener('scroll', placeTray);
  el.fold.addEventListener('click', () => setFolded(!folded));
  // − = 최소화 · + = 최소화 · 접힘 둘 다 풀기(가장 펼친 상태)
  el.min.addEventListener('click', () => {
    if (minimized) { setMin(false); setFolded(false); } else setMin(true);
  });
  el.tray.addEventListener('click', (e) => {
    // 누른 아이콘
    const a = e.target.closest('[data-act]')?.dataset.act;
    if (a === 'doc') openInput(picked, 'queue');
    else if (a === 'wand') wand(picked);
  });
  el.acts.addEventListener('click', (e) => {
    // 누른 단추
    const a = e.target.closest('[data-act]')?.dataset.act;
    if (a === 'cancel') closeInput(true);
    else if (a === 'send') sendInput();
  });
  el.ta.addEventListener('input', () => { if (inputCtx) drafts[`${inputCtx.nick}:${inputCtx.kind}`] = el.ta.value; });
  box.addEventListener('mousemove', onTip);
  box.addEventListener('mouseleave', () => { el.tip.hidden = true; });
  // Esc — 행 선택 해제(입력창이 열려 있으면 아무것도 안 함 — 그래프 노드 선택 해제와 겹쳐서)
  on('escape', () => { if (mode !== 'input' && picked) pick(null); });
  on('view', () => syncView());
  // 끌기 손잡이 = 행 목록 · 칩 줄(단추 · 입력창 · 누적창은 손잡이 밖) · 펼친 상태는 위로 뜨는 누적창(160) · 오른쪽 전송 단추(180)까지 화면에 남김
  mover = makeMovable(box, el.rows, () => (minimized ? 'hub.pos.min' : 'hub.pos'),
    { keep: () => (minimized ? {} : { top: 160, right: 180 }) });
  setFolded(folded, false);
  setMin(minimized, false);
  syncView();
  poll();
  return true;
}

// 보기에 맞춰 보이기 — 대화 · Book 보기에서는 숨김(Book 은 왼쪽 책 목록을 가려서)
function syncView() {
  if (!box) return;
  box.hidden = ['chat', 'book'].includes(deps.view?.()) && !(mode === 'input' && inputCtx?.kind === 'note');
  if (box.hidden) el.tip.hidden = true;
  else mover?.apply();
}

// 접기 · 펼치기 — 접으면 한 줄(세션 이름 + 상태 테두리)
// v: 접힘 여부 / save: 저장 여부
function setFolded(v, save = true) {
  folded = v;
  box.classList.toggle('is-folded', folded);
  el.fold.innerHTML = ic(folded ? 'up' : 'down');
  el.fold.title = folded ? '펼치기' : '접기';
  if (save) store.set('hub.folded', folded);
  paint();
}

// 최소화 · 풀기 — 최소화하면 세션 이름 칩만(좌하단) · 고른 행 · 누적창 · 입력창은 닫음(쓰던 글은 남김)
// v: 최소화 여부 / save: 저장 여부
function setMin(v, save = true) {
  minimized = v;
  if (minimized) {
    picked = null;
    if (mode === 'input') closeInput(false);
    closeAcc();
  }
  box.classList.toggle('is-min', minimized);
  el.min.innerHTML = ic(minimized ? 'plus' : 'minus');
  el.min.title = minimized ? '펼치기' : '최소화';
  if (save) store.set('hub.min', minimized);
  paint();
}

// 목록 받기 — 1.5초마다(숨은 탭은 4초)
async function poll() {
  try {
    // 서버 응답
    const r = await api('hub');
    rows = r.rows || [];
    queueInfo = r.queue || { ok: true };
    paint();
    emit('hub-rows', rows);
    if (mode === 'acc') loadAcc();
  } catch { /* 서버 끊김 — 다음에 */ }
  setTimeout(poll, document.hidden ? 4000 : POLL_MS);
}

// 마지막으로 그린 내용 표시(같으면 다시 안 그림 — 1.5초마다 DOM 을 갈아엎지 않게)
let painted = '';

// 행 그리기
function paint() {
  if (!el.rows) return;
  // 그릴 내용 표시
  const sig = JSON.stringify([rows, picked, folded, minimized, seen]);
  if (sig === painted) { placeTray(); return; }
  painted = sig;
  el.rows.innerHTML = rows.map((r) => {
    // 테두리 상태 · effort 기호 · 미연결 여부
    const st = rowState(r);
    const eff = EFFORT[r.effort] || '?';
    const off = !r.registered;
    return `<div class="dv-hub-row${r.nick === picked ? ' is-sel' : ''}${off ? ' is-off' : ''}${st ? ` m-${st}` : ''}" role="listitem" data-nick="${esc(r.nick)}">`
      + `<span class="dv-hub-nick">${esc(r.label)}</span>`
      + `<span class="dv-hub-eff" data-tip="${esc(`effort ${r.effort || '?'} · ${r.effort_src || '?'}`)}">${esc(eff)}</span>`
      + `<span class="dv-hub-ctx" data-tip="${esc(r.context ? `맥락 ${(r.context.used || 0).toLocaleString()} / ${(r.context.window || 0).toLocaleString()} 토큰${r.model ? ` · ${r.model}` : ''}` : '맥락 모름')}">${esc(off ? '' : ctxText(r.context))}</span>`
      + `<span class="dv-hub-st" data-tip-auto="1">${r.queue?.length ? `<button class="dv-hub-q" type="button" data-q="${esc(r.nick)}" title="턴이 끝나면 들어갈 글 — 눌러서 펼치기">큐 ${r.queue.length}</button>` : ''}${esc(off ? '미연결' : r.status || (r.done?.error ? `오류: ${r.done.error}` : ''))}</span>`
      + '</div>';
  }).join('');
  // 접은 한 줄 · 최소화 — 세션 이름 칩(상태 테두리 같은 규칙)
  if (folded || minimized) {
    el.rows.innerHTML = `<div class="dv-hub-chips" title="끌어서 옮기기 · 더블클릭 = 기본 자리">${rows.filter((r) => r.registered).map((r) => {
      const st = rowState(r);
      return `<span class="dv-hub-chip${st ? ` m-${st}` : ''}">${esc(r.label)}${r.queue?.length ? ` · 큐 ${r.queue.length}` : ''}</span>`;
    }).join('') || '<span class="dv-hub-chip is-off">허브</span>'}</div>`;
  }
  paintQueue();
  // 크기 · 상태가 바뀌었을 수 있음 — 그 상태의 저장 자리로 다시 놓고 화면 안으로
  mover?.apply();
  placeTray();
}

// 큐 펼침 — 턴이 끝나면 들어갈 글 목록(비면 닫힘)
function paintQueue() {
  const q = rows.find((r) => r.nick === queueOpen)?.queue || [];
  el.queue.hidden = !q.length;
  el.queue.innerHTML = q.length ? `<div class="dv-hub-qbody"><div class="dv-hub-qhead">${esc(labelOf(queueOpen))} 큐 ${q.length} — 턴이 끝나면 차례로 들어감</div>`
    + q.map((x, i) => `<div class="dv-hub-qrow"><b>${i + 1}</b> <span>${esc(x.at)}</span> ${esc(x.text)}</div>`).join('') + '</div>' : '';
}

// 행 고르기 · 풀기 — 고르면 확인(점멸 꺼짐) · 누적창 · 트레이
// nick: 닉네임(null = 해제)
function pick(nick) {
  if (mode === 'input' && nick !== picked) closeInput(false);
  picked = nick;
  if (nick) {
    // 고른 행
    const r = rows.find((x) => x.nick === nick);
    markSeen(r);
    openAcc();
  } else {
    closeAcc();
  }
  paint();
}

// 트레이 자리 — 고른 행 오른쪽(허브 밖) · 행이 안 보이면 숨김
function placeTray() {
  if (!el.tray) return;
  // 고른 행 칸
  const row = picked && !folded && !minimized ? el.rows.querySelector(`.dv-hub-row[data-nick="${CSS.escape(picked)}"]`) : null;
  if (!row) { el.tray.hidden = true; return; }
  // 목록 칸 안 위치
  const top = row.offsetTop - el.rows.scrollTop;
  if (top < -4 || top > el.rows.clientHeight - ROW_H + 4) { el.tray.hidden = true; return; }
  // 고른 행
  const r = rows.find((x) => x.nick === picked);
  el.tray.hidden = false;
  el.tray.style.top = `${top}px`;
  $('[data-act="wand"]', el.tray).hidden = !r?.role;
  el.tray.classList.toggle('is-noqueue', !queueInfo.ok);
  el.tray.title = queueInfo.ok ? '' : `queue 불가 — ${queueInfo.reason || '원인 모름'}`;
}

// ======= 누적창 =======
function openAcc() {
  if (mode === 'input') return;
  mode = 'acc';
  accCount = -1;
  el.acc.hidden = false;
  el.accBody.innerHTML = '<div class="dv-hub-empty">불러오는 중</div>';
  loadAcc(true);
}

function closeAcc() {
  if (mode === 'acc') mode = null;
  el.acc.hidden = true;
}

// 누적 받기 — 바뀌었을 때만 다시 그림 · 열 때는 맨 아래(최신)로
// first: 처음 열 때
async function loadAcc(first = false) {
  // 그릴 행
  const r = rows.find((x) => x.nick === picked);
  if (!r) return;
  if (!r.registered) {
    el.accBody.innerHTML = `<div class="dv-hub-empty">${esc(r.label)} 미연결 — 그 세션이 $codex-hub 로 등록하면 보임</div>`;
    return;
  }
  let res;
  try { res = await api('hub/log', { query: { nick: r.nick } }); } catch (e) {
    el.accBody.innerHTML = `<div class="dv-hub-empty">누적 읽기 실패 — ${esc(e.message)}</div>`;
    return;
  }
  if (picked !== r.nick || mode !== 'acc') return;
  // 줄 목록
  const lines = res.lines || [];
  if (!first && lines.length === accCount) return;
  // 맨 아래였는지(새 줄이 오면 따라감)
  const atEnd = el.accBody.scrollTop + el.accBody.clientHeight >= el.accBody.scrollHeight - 4;
  accCount = lines.length;
  el.accBody.innerHTML = lines.length ? lines.map((x) => `<div class="dv-hub-line"><i class="dv-hub-dot"></i>`
    + `<span class="dv-hub-at">${esc(String(x.at).slice(5, 16))}</span><span class="dv-hub-tx">${esc(x.text)}</span></div>`).join('')
    : `<div class="dv-hub-empty">${esc(r.label)} 누적 없음 — 큰 단위가 끝나면 세션이 hub.py log 로 한 줄씩</div>`;
  if (first || atEnd) el.accBody.scrollTop = el.accBody.scrollHeight;
}

// ======= 입력창 =======
// 열기 — 문서 아이콘(queue) · 2ND 마법봉(magic, 질문 전용) · 지시 붙은 마법봉(note — Alt+E MAIN · Alt+R 2ND)
// nick: 닉네임 / kind: queue · magic · note / snap: 누른 순간의 선택 스냅샷
function openInput(nick, kind, snap = null) {
  if (!nick) return;
  closeAcc();
  mode = 'input';
  inputCtx = { nick, kind, snap };
  // 허브가 숨는 보기(Book · 대화)에서도 지시 입력 동안은 보임 — 닫으면 syncView 가 되돌림
  if (box.hidden) box.hidden = false;
  el.input.hidden = false;
  el.acts.hidden = false;
  // 머리 줄 — 보낼 곳 · 대상
  const head = kind === 'magic' ? `질문 → ${labelOf(nick)} · 대상: ${snap?.label || '없음(섬 질문)'}`
    : kind === 'note' ? `지시 → ${labelOf(nick)} 마법봉 · 대상: ${snap?.label || '대상 없음'}` : `→ ${labelOf(nick)} 직접 입력 (codex queue)`;
  el.head.textContent = queueInfo.ok ? head : `${head} — 🔴 queue 불가: ${queueInfo.reason || '원인 모름'}`;
  el.head.classList.toggle('is-bad', !queueInfo.ok);
  el.input.classList.toggle('is-magic', kind !== 'queue');
  el.ta.value = drafts[`${nick}:${kind}`] || '';
  el.ta.placeholder = kind === 'magic' ? '질문 — Enter 는 줄바꿈 · 전송은 ✈' : kind === 'note' ? '지시 — Enter 는 줄바꿈 · 전송은 ✈'
    : '보낼 글 — Enter 는 줄바꿈 · 전송은 ✈';
  setTimeout(() => el.ta.focus(), 0);
}

// 닫기 — clear 면 쓴 글도 지움(✕) · 고른 범위 덧칠도 지움 · 누적창으로 돌아감
// clear: 글 지우기
function closeInput(clear) {
  if (inputCtx && clear) delete drafts[`${inputCtx.nick}:${inputCtx.kind}`];
  if (inputCtx && inputCtx.kind !== 'queue') deps.clearMark?.();
  inputCtx = null;
  mode = null;
  el.input.hidden = true;
  el.acts.hidden = true;
  el.ta.blur();
  syncView();
  if (picked) openAcc();
}

// 보내기 — 성공하면 닫힘 · 실패하면 글을 남겨 둠
async function sendInput() {
  if (!inputCtx) return;
  // 글 · 문맥
  const text = el.ta.value;
  const c = inputCtx;
  if (!text.trim()) { toast('보낼 글 없음', 'bad'); return; }
  const btn = $('[data-act="send"]', el.acts);
  btn.disabled = true;
  try {
    if (c.kind === 'magic') {
      // 2ND 질문 — 누른 순간의 보기 · 선택
      const res = await api('hub/magic', { body: { nick: c.nick, view: c.snap?.view || deps.view(), selection: c.snap?.selection || {}, question: text } });
      toast(res.msg || '보냄');
    } else if (c.kind === 'note') {
      // 지시 붙은 마법봉 — 누른 순간의 대상 + 지시 글(답 자리 · 분배는 서버 · 세션 몫)
      const res = await api('hub/magic', { body: { nick: c.nick, view: c.snap?.view || deps.view(), selection: c.snap?.selection || {}, instruction: text } });
      if ((res.skipped || []).length) toast(`${res.skip_note || '뺌'} — 뺌 · 나머지 보냄`, 'bad', 5000);
      else toast(res.msg || '보냄');
    } else {
      const res = await api('hub/queue', { body: { nick: c.nick, text } });
      toast(`${labelOf(c.nick)} 에 보냄 · ${String(res.out || '').split(' · ')[0]}`);
    }
    closeInput(true);
  } catch (e) {
    toast(`보내기 실패 — ${e.message}`, 'bad', 6000);
  } finally {
    btn.disabled = false;
  }
}

// ======= 마법봉 =======
// main = 그래프에서 고른 노드(작업 · 검증 · 질문 · 답한 설문)로 바로 · 2nd = 누른 순간의 선택을 스냅샷 → 질문 입력창
//   2nd 그래프: 고른 질문 노드(질문 = 제목) · 메모 있는 설문 노드(질문 = 메모)는 입력창 없이 바로 — 서버가 need_input 이면 입력창
// nick: 닉네임
async function wand(nick) {
  // 고른 행
  const r = rows.find((x) => x.nick === nick);
  if (!r?.role) return;
  // 그래프 안 열린 입력 칸(메모 · 제목)을 먼저 저장 — 칸을 벗어나지 않고 눌러도 친 글로 보냄
  if (deps.view?.() === 'graph') await deps.flush?.();
  if (r.role === '2nd') {
    // 누른 순간의 선택 — 입력창으로 포커스가 옮겨 가도 이 범위로
    const snap = snapshot();
    if (snap.view === 'graph' && (snap.selection.nodes || []).length) {
      try {
        // 질문 글 없이 먼저 — 답 자리 노드(질문 · 설문)는 서버가 트리로 판정
        const res = await api('hub/magic', { body: { nick, view: 'graph', selection: snap.selection } });
        if (!res.need_input) { toast(res.msg || '보냄'); return; }
      } catch (e) {
        toast(`마법봉 실패 — ${e.message}`, 'bad', 6000);
        return;
      }
    }
    if (snap.mark) deps.markCode?.(snap.mark);
    openInput(nick, 'magic', snap);
    return;
  }
  // MAIN 은 그래프 보기에서만 — 다른 보기에서 마지막 그래프 선택을 보내지 않음
  if (deps.view?.() !== 'graph') {
    toast('MAIN 마법봉(Alt+Q)은 그래프 보기에서 — 그래프에서 노드를 고른 뒤 · 지시와 함께면 Alt+E', 'bad', 4500);
    return;
  }
  // 그래프 선택
  const fs = deps.ftSel?.() || { nodes: [] };
  // 보낼 노드 — 종류별 분배는 MAIN 몫(서버 · 스크립트가 트리 종류로 나눔)
  const nodes = fs.nodes || [];
  if (!nodes.length) {
    toast('노드를 고르지 않음 — 그래프에서 노드를 고르기(Ctrl+클릭 여럿)', 'bad', 4000);
    return;
  }
  try {
    // 서버 응답
    const res = await api('hub/magic', { body: { nick, view: 'graph', selection: { nodes, graph_view: fs.view || '' } } });
    // 답 없는 · 보류 · 이미 반영한 설문은 서버가 빼고 보냄 — 뺀 것을 알림
    if ((res.skipped || []).length) toast(`${res.skip_note || '뺌'} — 뺌 · 나머지 보냄`, 'bad', 5000);
    else toast(res.msg || '보냄');
  } catch (e) {
    toast(`마법봉 실패 — ${e.message}`, 'bad', 6000);
  }
}

// 단축키 마법봉 — 그 역할 행의 마법봉 단추와 같은 동작(main.js 가 부름)
// role: main · 2nd
export function hubWand(role) {
  // 그 역할의 행
  const r = rows.find((x) => x.role === role);
  if (!r) { toast(`${role.toUpperCase()} 세션 없음`, 'bad'); return; }
  if (role === '2nd' && box.hidden) { toast('이 보기에서는 2ND 마법봉을 쓸 수 없음', 'bad'); return; }
  if (mode === 'input' && inputCtx?.kind === 'magic' && inputCtx.nick === r.nick) { el.ta.focus(); return; }
  if (minimized) setMin(false);
  wand(r.nick);
}

// 지시 붙은 마법봉 단축키(Alt+E = MAIN · Alt+R = 2ND) — 누른 순간의 선택 → 그 역할 행의 입력창(자동 전송 없음)
// role: main · 2nd
export async function hubWandNote(role) {
  // 그 역할의 행
  const r = rows.find((x) => x.role === role);
  if (!r) { toast(`${role.toUpperCase()} 세션 없음`, 'bad'); return; }
  if (mode === 'input' && inputCtx?.kind === 'note' && inputCtx.nick === r.nick) { el.ta.focus(); return; }
  if (minimized) setMin(false);
  // 그래프 안 열린 입력 칸을 먼저 저장 — 그 뒤 선택 스냅샷
  if (deps.view?.() === 'graph') await deps.flush?.();
  const snap = snapshot();
  if (snap.mark) deps.markCode?.(snap.mark);
  openInput(r.nick, 'note', snap);
}

// 지금 보기의 선택 스냅샷 — {view, selection, label, mark}
function snapshot() {
  // 지금 보기
  const v = deps.view?.() || 'code';
  if (v === 'graph') {
    const fs = deps.ftSel?.() || { nodes: [] };
    const nodes = fs.nodes || [];
    return { view: 'graph', selection: { nodes, graph_view: fs.view || '' },
      label: nodes.length ? nodes.map((n) => n.title || n.id).slice(0, 3).join(' · ') + (nodes.length > 3 ? ` 외 ${nodes.length - 3}` : '') : '' };
  }
  if (v === 'code') {
    const s = deps.codeSel?.();
    if (!s) return { view: 'app', selection: {}, label: '' };
    const lines = s.range ? (s.range.start_line === s.range.end_line ? `${s.range.start_line}줄` : `${s.range.start_line}–${s.range.end_line}줄`) : '';
    return { view: 'code', selection: { file: s.file, doc_kind: s.doc_kind, readonly: s.readonly, range: s.range, text: s.text, table: s.table },
      label: `${s.file}${lines ? ` ${lines}` : ''}${!s.range && s.text ? ' (고른 글자)' : ''}`, mark: s.range ? s : null };
  }
  if (v === 'book') {
    // 책 — 마지막으로 누른 스티커(책 iframe 이 알려 줌) · 책 html 경로
    const b = deps.bookSel?.() || {};
    return { view: 'book', selection: b.note ? { note: b.note, doc: b.doc } : {}, label: b.note ? `책 스티커 ${b.note}` : '' };
  }
  if (v === 'git') {
    const g = deps.gitSel?.() || {};
    return { view: 'git', selection: { commit: g.hash || '', subject: g.subject || '', git_file: g.file || '' },
      label: [g.hash ? g.hash.slice(0, 8) : '', g.file || ''].filter(Boolean).join(' · ') };
  }
  return { view: v, selection: {}, label: '' };
}

// ======= 지연 없는 툴팁 =======
// e: 마우스 이벤트
function onTip(e) {
  // 툴팁 대상 칸
  const t = e.target.closest('[data-tip], [data-tip-auto]');
  // 보일 글 — 넘친 «지금 작업» 칸은 전체 글
  const text = t ? (t.dataset.tip || (t.scrollWidth > t.clientWidth + 1 ? t.textContent : '')) : '';
  if (!text) { el.tip.hidden = true; return; }
  el.tip.textContent = text;
  el.tip.hidden = false;
  // 화면 밖으로 안 나가게
  const w = el.tip.offsetWidth;
  const ht = el.tip.offsetHeight;
  el.tip.style.left = `${Math.min(e.clientX + 12, innerWidth - w - 6)}px`;
  el.tip.style.top = `${Math.max(6, e.clientY - ht - 10)}px`;
}

// 시험 · 디버깅용
export const hubDebug = () => ({ picked, mode, folded, minimized, rows: rows.map((r) => ({ nick: r.nick, state: rowState(r) })), inputCtx });
