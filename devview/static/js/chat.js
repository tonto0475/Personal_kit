// 대화 보기 — 터미널 대신 · 허브에 붙은 Codex 세션의 대화(rollout 의 유저 메시지 · 최종 답변 · 혼잣말 · 오류 — 모델에게 시키지 않음)
//   위 = 세션 탭 스위치(테두리 규칙 = 허브 행과 같음 · 그 탭을 열면 점멸 꺼짐) · 가운데 = 대화(🚹 줄 전체 강조 · 🔁 다른 세션이 보낸 글(연녹색 · 이름 칩) · 🪄 마법봉 칩 · 🤖 · 혼잣말은 흐린 줄 · 보낸 직후는 «대기» 줄) · 아래 = 입력
//   입력: Enter 줄바꿈 · 보내기 = Ctrl+Enter · Alt+←→ 세션 탭(main.js 가 chat-tab 으로 알림) · Alt+A · S · D · F · G = 1~5번 탭(chat-pick · 어느 보기에서든) · PageUp/PageDown 이력
//   서버: GET api/hub/chat?nick=&after=N · POST api/hub/queue
import { api } from './api.js';
import { $, esc, on, store, toast } from './util.js';
import { hubRows, rowState, markSeen, ctxText, EFFORT } from './hub.js';
import { makeMovable } from './drag.js';

// 대화 갱신 간격(ms)
const POLL_MS = 500;
// 세션끼리 보낸 글 머리 «@이름 »(hub.py send · 설문 알림 — 이름 모양은 hub.py 닉네임과 같음)
const RELAY_RE = /^@([0-9A-Za-z가-힣_-]{1,24}) /;

// main.js 가 넘긴 것 — view()
let deps = {};
// 지금 세션 닉네임(저장값은 initChat 에서 — 모듈을 불러올 때는 작업 폴더별 저장 이름이 아직 없음) · 닉네임 → 받은 항목 목록
let cur = null;
const items = {};
// 진행 중 본문은 rollout 번호와 분리한다. 완성 기록이 오면 서버가 제외한다.
const live = {};
// 보냈지만 기록에 아직 안 들어온 글 — 닉네임 → [{text, at}](세션이 작업 중이면 queue 가 그 턴이 끝날 때까지 기다림)
const pending = {};
// 화면 부품 · 갱신 타이머 · 받는 중 여부
let el = {};
let timer = null;
let loading = false;

// 대화 보기 준비 — info.hub 가 없으면 탭을 안 보임
// info: 서버 info / d: {view}
export function initChat(info, d) {
  deps = d;
  const view = $('#chatView');
  if (!info.hub || !view) return false;
  cur = store.get('chat.nick', null);
  folded = new Set(store.get('chat.folded', []));
  $('#chatTab').hidden = false;
  view.innerHTML = `
    <div class="dv-chat">
      <div class="dv-chat-tabs" role="tablist"></div>
      <div class="dv-chat-mid">
        <div class="dv-chat-list" tabindex="0"></div>
        <div class="dv-subs" hidden>
          <div class="dv-subs-head"><span class="dv-subs-sum"></span><button type="button" class="dv-subs-fold"></button></div>
          <div class="dv-subs-list"></div>
        </div>
      </div>
      <div class="dv-chat-foot">
        <textarea class="dv-chat-input" spellcheck="false" placeholder="보낼 글 — Enter 줄바꿈 · 보내기 Ctrl+Enter"></textarea>
        <div class="dv-chat-meta"></div>
      </div>
    </div>`;
  el = { tabs: $('.dv-chat-tabs', view), list: $('.dv-chat-list', view), ta: $('.dv-chat-input', view), meta: $('.dv-chat-meta', view),
    subs: $('.dv-subs', view), subSum: $('.dv-subs-sum', view), subFold: $('.dv-subs-fold', view), subList: $('.dv-subs-list', view) };
  subsFolded = store.get('chat.subsFolded', false);
  // 머리줄을 끌어 옮김(대화 글을 가리면 비키게) · 머리줄 더블클릭 = 기본 자리
  subsMove = makeMovable(el.subs, $('.dv-subs-head', view), 'chat.subsPos');
  el.subFold.addEventListener('mousedown', (e) => e.preventDefault());
  el.subFold.addEventListener('click', () => {
    subsFolded = !subsFolded;
    store.set('chat.subsFolded', subsFolded);
    paintSubFold();
  });
  paintSubFold();
  el.tabs.addEventListener('mousedown', (e) => e.preventDefault());
  el.tabs.addEventListener('click', (e) => {
    // 누른 탭
    const t = e.target.closest('[data-nick]');
    if (t) select(t.dataset.nick);
  });
  el.ta.addEventListener('keydown', onKey);
  // 답 접기 · 펴기 — 🤖 · 접힘 줄 클릭(글을 고르는 중이면 무시)
  el.list.addEventListener('click', (e) => {
    const f = e.target.closest('[data-fold]');
    if (f && !String(getSelection?.() || '')) toggleFold(f.dataset.fold);
  });
  // 이력 — PageUp/PageDown 은 입력칸에 있어도 대화를 넘김
  view.addEventListener('keydown', (e) => {
    // 전부 접기 · 펴기 — Ctrl+Shift+, · Ctrl+Shift+. (키 자리로 — 한글 입력 중에도 같음)
    if (e.ctrlKey && e.shiftKey && !e.altKey && (e.code === 'Comma' || e.code === 'Period')) {
      e.preventDefault();
      foldAll(e.code === 'Comma');
      return;
    }
    if ((e.key === 'PageUp' || e.key === 'PageDown') && !e.altKey && !e.ctrlKey) {
      e.preventDefault();
      el.list.scrollBy({ top: (e.key === 'PageUp' ? -1 : 1) * el.list.clientHeight * 0.9 });
    }
  });
  on('hub-rows', () => { paintTabs(); paintMeta(); ackIfVisible(); });
  on('view', (v) => {
    if (v === 'chat') { start(); setTimeout(() => el.ta.focus(), 0); } else stop();
  });
  on('chat-tab', (dir) => step(dir));
  on('chat-pick', (n) => pick(n));
  return true;
}

// 탭으로 보일 세션 — 등록된 것(thread 있음)
const sessions = () => hubRows().filter((r) => r.registered && r.thread);

// 세션 탭 그리기 — 테두리 = 허브 행과 같은 규칙
function paintTabs() {
  if (!el.tabs) return;
  // 탭 세션 목록
  const list = sessions();
  if (!cur || !list.some((r) => r.nick === cur)) cur = list[0]?.nick || null;
  el.tabs.innerHTML = list.length ? list.map((r) => {
    const st = rowState(r);
    return `<button type="button" role="tab" class="dv-chat-tab${r.nick === cur ? ' is-on' : ''}${st ? ` m-${st}` : ''}" data-nick="${esc(r.nick)}">`
      + `${esc(r.label)}<span class="dv-chat-eff">${esc(EFFORT[r.effort] || '?')}</span></button>`;
  }).join('') : '<span class="dv-chat-none">연결된 세션 없음 — 세션이 $codex-hub 로 등록하면 탭이 생김</span>';
}

// 입력창 아래 — 맥락 · 모델 · effort
function paintMeta() {
  if (!el.meta) return;
  // 지금 세션 행
  const r = hubRows().find((x) => x.nick === cur);
  el.meta.innerHTML = r ? `<span>맥락 ${esc(ctxText(r.context))}</span><span>모델 ${esc(r.model || '?')}</span>`
    + `<span>effort <b class="dv-chat-effb">${esc(EFFORT[r.effort] || '?')}</b> ${esc(r.effort || '?')}${r.effort_src === '기본값' ? '(기본)' : ''}</span>` : '';
}

// 지금 탭이 보이는 동안 새 답은 바로 «확인»
function ackIfVisible() {
  if (deps.view?.() !== 'chat' || !cur) return;
  // 지금 세션 행
  const r = hubRows().find((x) => x.nick === cur);
  if (r && rowState(r) !== 'spin') markSeen(r);
}

// 세션 고르기 — 그 탭을 열면 점멸 꺼짐
// nick: 닉네임
function select(nick) {
  if (!nick) return;
  cur = nick;
  store.set('chat.nick', nick);
  paintTabs();
  paintMeta();
  ackIfVisible();
  render(true);
  load();
  paintSubs([]);
  loadSubs();
}

// Alt+←→ — 옆 세션 탭으로
// dir: -1 · +1
function step(dir) {
  // 탭 세션 목록 · 지금 번호
  const list = sessions();
  if (!list.length) return;
  const i = Math.max(0, list.findIndex((r) => r.nick === cur));
  select(list[(i + dir + list.length) % list.length].nick);
}

// Alt+A · S · D · F · G — n번째 세션 탭으로(main.js 가 chat-pick 으로 알림)
// n: 0 부터
function pick(n) {
  // 그 번호 세션
  const r = sessions()[n];
  if (r) select(r.nick); else toast(`${n + 1}번 세션 없음`, 'bad', 1500);
  setTimeout(() => el.ta?.focus(), 0);
}

// 갱신 시작 · 멈춤(대화 보기에 있을 때만)
function start() {
  paintTabs();
  paintMeta();
  ackIfVisible();
  render(true);
  clearTimeout(timer);
  const loop = async () => {
    await load();
    await loadSubs();
    timer = setTimeout(loop, document.hidden ? 4000 : POLL_MS);
  };
  loop();
}
function stop() {
  clearTimeout(timer);
  timer = null;
}

// 새 항목 받기 — 받은 개수 뒤만
async function load() {
  if (!cur || loading) return;
  loading = true;
  // 받는 세션
  const nick = cur;
  try {
    // 받은 목록
    const have = items[nick] || [];
    const r = await api('hub/chat', { query: { nick, after: r0(have) } });
    if (r.reset) items[nick] = [];
    const before = (items[nick] || []).length;
    const previous = live[nick] || [];
    const previousLive = JSON.stringify(previous);
    live[nick] = r.live || [];
    items[nick] = [...(items[nick] || []), ...(r.items || [])];
    // 진행 중 접은 답이 정본으로 바뀌어도 접힘을 이어간다.
    for (const it of r.items || []) {
      const prior = previous.find((x) => x.role === 'assistant' && it.role === 'assistant' && x.turn === it.turn);
      if (prior && folded.has(`${nick}:${prior.i}`)) { folded.add(`${nick}:${it.i}`); saveFold(); }
    }
    // 기록에 들어온 글은 «대기» 줄에서 뺌(앞에서부터 같은 글 하나씩)
    for (const it of r.items || []) {
      if (it.role !== 'user') continue;
      const k = (pending[nick] || []).findIndex((x) => x.text.trim() === String(it.text).trim());
      if (k >= 0) pending[nick].splice(k, 1);
    }
    if (nick === cur) {
      if (r.reset || items[nick].length !== before) render(false);
      else if (JSON.stringify(live[nick]) !== previousLive) paintStream();
    }
  } catch (e) {
    if (nick === cur && !(items[nick] || []).length) el.list.innerHTML = `<div class="dv-chat-empty">${esc(e.message)}</div>`;
  } finally {
    loading = false;
  }
}

// 다음 받을 번호(마지막 항목 i + 1)
// have: 받은 목록
const r0 = (have) => (have.length ? have[have.length - 1].i + 1 : 0);

// ======= 서브 상태 패널 — 대화 오른쪽 아래 · 고른 세션의 서브만 · 보기 전용 =======
// 접힘 여부 · 지금 그려진 내용(같으면 다시 안 그림 — 패널 스크롤 · 툴팁 유지)
let subsFolded = false;
// 패널 끌어 옮기기
let subsMove = null;
let subsKey = '';

// 받아서 그리기 — 받는 사이 탭을 바꿨으면 버림 · 실패하면 패널을 숨김
async function loadSubs() {
  if (!cur) { paintSubs([]); return; }
  // 받는 세션
  const nick = cur;
  try {
    const r = await api('hub/subagents', { query: { nick } });
    if (nick === cur) paintSubs(r.subs || []);
  } catch {
    if (nick === cur) paintSubs([]);
  }
}

// 패널 그리기 — 서브가 없으면 숨김
// list: 서브 줄 목록
function paintSubs(list) {
  const key = JSON.stringify(list);
  if (key === subsKey) return;
  subsKey = key;
  el.subs.hidden = !list.length;
  if (list.length) subsMove.apply();
  el.subSum.textContent = `서브 ${list.length} · 일함 ${list.filter((s) => s.state === 'work').length}`;
  el.subList.innerHTML = list.map((s) => {
    // 표시 — 일함 · 쉼 · 중단
    const st = s.state === 'work' ? ['is-work', '일함'] : s.stopped ? ['is-stop', '중단'] : ['is-rest', '쉼'];
    const tip = [`${s.name}${s.nickname ? ` (${s.nickname})` : ''} · ${st[1]}${s.at ? ` · ${s.at}` : ''}`, s.text, s.why && s.why !== s.text ? s.why : ''].filter(Boolean).join('\n');
    return `<div class="dv-sub ${st[0]}" data-sub="${esc(s.id || '')}" title="${esc(tip)}"><span class="dv-sub-name">${esc(String(s.name).replace(/^\/root\//, ''))}</span>`
      + `<span class="dv-sub-mark">${st[1]}</span><span class="dv-sub-text">${esc(s.text)}</span></div>`;
  }).join('');
}

// 접기 단추 · 목록 보임 반영
function paintSubFold() {
  el.subs.classList.toggle('is-folded', subsFolded);
  el.subFold.textContent = subsFolded ? '▴' : '▾';
  el.subFold.title = subsFolded ? '펼치기' : '접기';
}

// ======= 답변 마크다운 — 대부분의 md 서식(제목 6단계 · 굵게(빨강 강조) · 기울임 · 취소선 · 코드 · 링크 · 인용 · 목록 · 할 일 · 표 · 구분선 · 코드 블록) =======
// 글을 먼저 이스케이프한 뒤 모양만 태그로 바꾼다(답변 속 HTML 은 글자 그대로 — 주입 없음)

// 링크 주소 — http(s) · file · 상대 경로만(javascript: 등 막음)
// u: 이스케이프된 주소
const mdHref = (u) => (/^(https?:|file:|\/|\.|#)/i.test(u) || !/^[a-z][a-z0-9+.-]*:/i.test(u) ? u : '#');

// 줄 안 꾸밈 — `코드` 먼저 떼어 두고 링크 · 굵게+기울임 · 굵게 · 기울임 · 취소선
// s: 이스케이프 전 한 줄
function mdInline(s) {
  // 떼어 둔 코드 조각
  const codes = [];
  let t = esc(s).replace(/`([^`]+)`/g, (_, c) => { codes.push(c); return `\u0000${codes.length - 1}\u0000`; });
  t = t.replace(/!\[([^\]]*)\]\(([^)\s]+)\)/g, (_, a, u) => `<a class="dv-cm-a" href="${mdHref(u)}" target="_blank" rel="noopener">🖼 ${a || u}</a>`)
    .replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (_, a, u) => `<a class="dv-cm-a" href="${mdHref(u)}" target="_blank" rel="noopener">${a}</a>`)
    .replace(/\*\*\*([^*]+?)\*\*\*/g, '<b class="dv-cm-b"><i>$1</i></b>')
    .replace(/\*\*([^*]+?)\*\*/g, '<b class="dv-cm-b">$1</b>')
    .replace(/(^|[^\w])__([^_]+?)__(?!\w)/g, '$1<b class="dv-cm-b">$2</b>')
    .replace(/(^|[^*])\*([^*\s][^*]*?)\*(?!\*)/g, '$1<i>$2</i>')
    .replace(/~~([^~]+?)~~/g, '<s>$1</s>');
  return t.replace(/\u0000(\d+)\u0000/g, (_, i) => `<code>${codes[+i]}</code>`);
}

// 표 한 줄 → 칸 목록(앞뒤 | 떼기)
// line: 표 줄
const mdCells = (line) => line.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map((c) => c.trim());
// 표 구분 줄(|---|:--:|) 여부
const mdSep = (line) => /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/.test(line);
// 목록 줄 모양 — 들여쓰기 · 기호 · 내용
const LI_RE = /^(\s*)([-*+]|\d+[.)])\s+(.*)$/;
// 블록 시작 줄 여부(문단을 끊는 줄)
// L: 줄 목록 / i: 위치
const mdBlockStart = (L, i) => /^\s*```/.test(L[i]) || /^#{1,6}\s/.test(L[i]) || LI_RE.test(L[i]) || /^\s*>/.test(L[i])
  || /^\s*(-{3,}|\*{3,}|_{3,})\s*$/.test(L[i]) || (L[i].includes('|') && i + 1 < L.length && mdSep(L[i + 1]));

// 목록 — 들여쓰기로 중첩 · 할 일 [ ] [x]
// L: 줄 목록 / i: 시작 위치 → [html, 다음 위치]
function mdList(L, i) {
  // 기준 들여쓰기 · 번호 목록 여부 · 첫 번호
  const m0 = L[i].match(LI_RE);
  const base = m0[1].length;
  const ordered = /\d/.test(m0[2]);
  const start = ordered ? parseInt(m0[2], 10) : 1;
  // 항목 html
  const lis = [];
  while (i < L.length) {
    const m = L[i].match(LI_RE);
    if (!m || m[1].length < base) break;
    if (m[1].length > base) {
      // 더 깊은 목록 → 앞 항목 안에 넣기
      const [inner, ni] = mdList(L, i);
      if (lis.length) lis[lis.length - 1] = lis[lis.length - 1].replace(/<\/li>$/, `${inner}</li>`);
      i = ni;
      continue;
    }
    if (/\d/.test(m[2]) !== ordered) break;
    // 할 일 칸
    const task = m[3].match(/^\[([ xX])\]\s+(.*)$/);
    lis.push(task ? `<li class="dv-cm-task"><span class="dv-cm-box${task[1] === ' ' ? '' : ' on'}">${task[1] === ' ' ? '' : '✓'}</span>${mdInline(task[2])}</li>`
      : `<li>${mdInline(m[3])}</li>`);
    i++;
    // 이어지는 줄(들여쓴 일반 글) → 같은 항목
    while (i < L.length && L[i].trim() && !LI_RE.test(L[i]) && /^\s{2,}/.test(L[i]) && !mdBlockStart(L, i)) {
      lis[lis.length - 1] = lis[lis.length - 1].replace(/<\/li>$/, `<br>${mdInline(L[i].trim())}</li>`);
      i++;
    }
  }
  const tag = ordered ? 'ol' : 'ul';
  return [`<${tag} class="dv-cm-l"${ordered && start !== 1 ? ` start="${start}"` : ''}>${lis.join('')}</${tag}>`, i];
}

// 블록 단위 변환
// text: 답변 원문
function mdLite(text) {
  // 줄 목록 · 결과 조각 · 위치
  const L = String(text || '').replace(/\r/g, '').split('\n');
  const out = [];
  let i = 0;
  while (i < L.length) {
    const ln = L[i];
    // 코드 블록(``` 언어)
    if (/^\s*```/.test(ln)) {
      const buf = [];
      i++;
      while (i < L.length && !/^\s*```/.test(L[i])) buf.push(L[i++]);
      i++;
      out.push(`<pre class="dv-cm-pre"><code>${esc(buf.join('\n'))}</code></pre>`);
      continue;
    }
    // 표 — 머리 줄 + 구분 줄(:--: 정렬)
    if (ln.includes('|') && i + 1 < L.length && mdSep(L[i + 1])) {
      const head = mdCells(ln);
      const align = mdCells(L[i + 1]).map((c) => (c.startsWith(':') && c.endsWith(':') ? 'center' : c.endsWith(':') ? 'right' : 'left'));
      const rows = [];
      i += 2;
      while (i < L.length && L[i].includes('|') && L[i].trim()) rows.push(mdCells(L[i++]));
      const st = (k) => (align[k] && align[k] !== 'left' ? ` style="text-align:${align[k]}"` : '');
      out.push(`<table class="dv-cm-tbl"><thead><tr>${head.map((c, k) => `<th${st(k)}>${mdInline(c)}</th>`).join('')}</tr></thead>`
        + `<tbody>${rows.map((r) => `<tr>${head.map((_, k) => `<td${st(k)}>${mdInline(r[k] ?? '')}</td>`).join('')}</tr>`).join('')}</tbody></table>`);
      continue;
    }
    // 제목(# ~ ######) — 단계마다 크기
    const hm = ln.match(/^(#{1,6})\s+(.*?)\s*#*\s*$/);
    if (hm) { out.push(`<div class="dv-cm-h dv-cm-h${hm[1].length}">${mdInline(hm[2])}</div>`); i++; continue; }
    // 구분선
    if (/^\s*(-{3,}|\*{3,}|_{3,})\s*$/.test(ln)) { out.push('<hr class="dv-cm-hr">'); i++; continue; }
    // 인용(>) — 안쪽을 다시 변환(중첩 가능)
    if (/^\s*>/.test(ln)) {
      const buf = [];
      while (i < L.length && /^\s*>/.test(L[i])) buf.push(L[i++].replace(/^\s*>\s?/, ''));
      out.push(`<blockquote class="dv-cm-q">${mdLite(buf.join('\n'))}</blockquote>`);
      continue;
    }
    // 목록
    if (LI_RE.test(ln)) {
      const [html, ni] = mdList(L, i);
      out.push(html);
      i = ni;
      continue;
    }
    // 빈 줄
    if (!ln.trim()) { i++; continue; }
    // 문단 — 빈 줄 · 다른 블록 전까지 이어 붙임(줄바꿈 유지)
    const buf = [];
    while (i < L.length && L[i].trim() && (!buf.length || !mdBlockStart(L, i))) buf.push(mdInline(L[i++]));
    out.push(`<p class="dv-cm-p">${buf.join('<br>')}</p>`);
  }
  return out.join('');
}

// ======= 답변 접기 · 펴기 — 🤖 · 접힘 줄을 누르거나 Ctrl+Shift+, (전부 접기) · Ctrl+Shift+. (전부 펴기) =======
// 접힌 답 열쇠(«닉:번호»)
// (initChat 에서 채움 — 저장소 이름표가 작업 폴더로 정해진 뒤)
let folded = new Set();
// 접힘 저장(최근 500개)
const saveFold = () => store.set('chat.folded', [...folded].slice(-500));
// 답 하나의 열쇠
// it: 항목
const foldKey = (it) => `${cur}:${it.i}`;
// 접힌 답의 한 줄 미리보기 — md 기호를 뺀 첫 글 줄
// text: 답변 원문
const firstLine = (text) => (String(text || '').split('\n').map((s) => s.replace(/^\s*(#{1,6}|>|[-*+]|\d+[.)]|\|)\s*/, '').replace(/\*\*|__|~~|`/g, '').replace(/\s*\|\s*/g, ' · ').trim()).filter((s) => !/^[-:\s·]+$/.test(s)).find(Boolean) || '').slice(0, 140);

// 하나 접기 · 펴기
// key: 열쇠
function toggleFold(key) {
  if (folded.has(key)) folded.delete(key); else folded.add(key);
  saveFold();
  render(false);
}

// 지금 세션의 답 전부 접기 · 펴기
// close: 접기 여부
function foldAll(close) {
  for (const it of [...(items[cur] || []), ...(live[cur] || [])]) {
    if (it.role !== 'assistant') continue;
    if (close) folded.add(foldKey(it)); else folded.delete(foldKey(it));
  }
  saveFold();
  render(false);
  toast(close ? '답변 전부 접음' : '답변 전부 펼침');
}

// 대화 그리기 — 맨 아래였으면 새 항목을 따라감
// jump: 무조건 맨 아래로
function render(jump) {
  if (!el.list) return;
  // 지금 세션 항목
  const list = [...(items[cur] || []), ...(live[cur] || [])];
  const wait = pending[cur] || [];
  const atEnd = el.list.scrollTop + el.list.clientHeight >= el.list.scrollHeight - 6;
  // 대기 줄 — 세션이 작업 중이면 «대기열», 아니면 «들어가는 중»
  const busy = rowState(hubRows().find((x) => x.nick === cur) || {}) === 'spin';
  const waitHtml = wait.map((w) => `<div class="dv-msg is-user is-pending"><span class="dv-msg-who">🚹</span><div class="dv-msg-txt">${esc(w.text)}</div>`
    + `<span class="dv-msg-at" title="${busy ? '세션이 작업 중 — 지금 턴이 끝나면 들어감' : '보냄 — 기록에 들어가는 중'}">${busy ? '대기열' : '보냄'}</span></div>`).join('');
  el.list.innerHTML = list.length || wait.length ? list.map((it) => {
    const streamAttr = it.live ? ` data-stream="${esc(it.id)}"` : '';
    // 혼잣말 — 흐린 한 덩어리(접기 · 마크다운 없음)
    if (it.role === 'note') {
      return `<div class="dv-msg is-note"${streamAttr}><span class="dv-msg-who">·</span><div class="dv-msg-txt">${esc(it.text)}</div>`
        + `<span class="dv-msg-at" title="${esc(it.at || '')}">${esc(String(it.at || '').slice(11, 16))}</span></div>`;
    }
    // 유저 글 중 세션끼리 보낸 글(«@이름 » — hub.py send · 설문 알림) · 마법봉 글(🪄 — 허브가 queue)
    const relay = it.role === 'user' ? RELAY_RE.exec(it.text || '') : null;
    const magic = it.role === 'user' && !relay && String(it.text || '').startsWith('🪄');
    if (relay || magic) {
      const chip = relay ? `<span class="dv-msg-chip">${esc(relay[1])}</span>` : '<span class="dv-msg-chip is-magic">🪄 마법봉</span>';
      const body = relay ? it.text.slice(relay[0].length) : it.text.replace(/^🪄\s*/, '');
      return `<div class="dv-msg is-user ${relay ? 'is-relay' : 'is-magic'}"><span class="dv-msg-who">${relay ? '🔁' : '🚹'}</span>`
        + `<div class="dv-msg-txt">${chip}${esc(body)}</div>`
        + `<span class="dv-msg-at" title="${esc(it.at || '')}${it.via === 'queue' ? ' · queue 로 들어옴' : ''}">${esc(String(it.at || '').slice(11, 16))}${it.via === 'queue' ? ' ⇢' : ''}</span></div>`;
    }
    // 표시 — 유저 🚹 · 답 🤖 · 오류 ■
    const who = it.role === 'user' ? '🚹' : it.role === 'assistant' ? '🤖' : '■';
    // 펼친 답의 접기 단추 — 시각 칸 아래(🤖 를 눌러도 접히지만 눈에 안 띔)
    const close = it.role === 'assistant' && !folded.has(foldKey(it))
      ? `<button type="button" class="dv-cm-close" data-fold="${esc(foldKey(it))}" title="이 답 접기 (전부: Ctrl+Shift+,)">▴ 접기</button>` : '';
    return `<div class="dv-msg is-${esc(it.role)}"${streamAttr}><span class="dv-msg-who"${it.role === 'assistant' ? ` data-fold="${esc(foldKey(it))}" title="접기 · 펴기 (전부: Ctrl+Shift+, · Ctrl+Shift+.)"` : ''}>${who}</span>`
      + (it.role !== 'assistant' ? `<div class="dv-msg-txt">${esc(it.text)}</div>`
        : folded.has(foldKey(it)) ? `<div class="dv-msg-txt dv-cm-fold" data-fold="${esc(foldKey(it))}" title="눌러서 펼치기">▸ ${esc(firstLine(it.text))} <span class="dv-cm-more">… 접힘</span></div>`
          : `<div class="dv-msg-txt dv-cmd">${mdLite(it.text)}</div>`)
      + `<span class="dv-msg-at" title="${esc(it.at || '')}${it.via === 'queue' ? ' · queue 로 들어옴' : ''}">${esc(String(it.at || '').slice(11, 16))}${it.via === 'queue' ? ' ⇢' : ''}${close}</span></div>`;
  }).join('') + waitHtml : `<div class="dv-chat-empty">${cur ? '대화 없음' : ''}</div>`;
  if (jump || atEnd || wait.length) el.list.scrollTop = el.list.scrollHeight;
}

// 같은 메시지는 본문만 갱신해 선택·접힘·위쪽 스크롤을 유지한다.
function paintStream() {
  if (!el.list) return;
  const messages = live[cur] || [];
  const nodes = [...el.list.querySelectorAll('[data-stream]')];
  if (nodes.length !== messages.length || nodes.some((node, i) => node.dataset.stream !== messages[i].id)) {
    render(false);
    return;
  }
  const atEnd = el.list.scrollTop + el.list.clientHeight >= el.list.scrollHeight - 6;
  nodes.forEach((node, i) => {
    const it = messages[i];
    if (it.role === 'assistant' && folded.has(foldKey(it))) return;
    node.querySelector('.dv-msg-txt').innerHTML = it.role === 'note' ? esc(it.text) : mdLite(it.text);
  });
  if (atEnd) el.list.scrollTop = el.list.scrollHeight;
}

// 입력 키 — Ctrl+Enter = 보내기 · Enter = 줄바꿈(그대로)
// e: 키 이벤트
function onKey(e) {
  if (e.key !== 'Enter' || e.isComposing || e.keyCode === 229) return;
  if ((e.ctrlKey || e.metaKey) && !e.altKey && !e.shiftKey) {
    e.preventDefault();
    send();
  }
}

// 보내기 — 성공하면 비우고 «대기» 줄로 바로 보임 · 실패하면 글을 남겨 둠
async function send() {
  // 글
  const text = el.ta.value;
  if (!text.trim()) return;
  if (!cur) { toast('보낼 세션 없음 — 세션이 $codex-hub 로 등록해야 함', 'bad'); return; }
  try {
    // 보낸 세션(응답 사이 탭을 바꿔도 그 세션에)
    const nick = cur;
    const sent = await api('hub/queue', { body: { nick, text } });
    el.ta.value = '';
    (pending[nick] ||= []).push({ text, at: Date.now() });
    if (nick === cur) render(true);
    toast(`${hubRows().find((r) => r.nick === nick)?.label || nick} 에 보냄 · ${String(sent?.out || '').split(' · ')[0]}`);
    setTimeout(load, 600);
  } catch (err) {
    toast(`보내기 실패 — ${err.message}`, 'bad', 6000);
  }
}

// 시험 · 디버깅용
export const chatDebug = () => ({ cur, count: (items[cur] || []).length });
