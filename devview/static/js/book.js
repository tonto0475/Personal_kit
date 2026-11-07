// Book 보기 — 북키트 책을 devview 안에서 연다(Alt+B)
//   왼쪽 = 책 목록(GET api/books — 만든 책의 판 하나가 한 줄 · 최신이 위 · 그룹 없음) — 설문 탭 왼쪽 목록과 같은 모양
//     줄 = «<책 제목> · v<N> · <판 이름>» + 회색 부가 줄(시각 · 블록 · 새로) · 책마다 마지막 판은 파랑 · 앞 판은 회색 · 고른 줄은 테두리
//   오른쪽 = 페이지 서버(포트 +100)의 그 html 을 iframe 으로 — 스티커 · 🪄 스티커 마법봉이 페이지 서버 같은 출처라 그대로 동작
//   목록은 탭을 열 때 · «새로고침» 단추로만 다시 읽는다(폴링 없음)
import { api } from './api.js';
import { $, esc, on, emit, store } from './util.js';
import { pageUrl } from './editor.js';

// 화면 부품 · 마지막 목록 · 고른 책(작업 폴더 기준 경로)
let el = {};
let list = { books: [] };
let cur = null;
// 책 안에서 마지막으로 누른 스티커 id(책 iframe 의 {book:'pick'}) — 지시 붙은 마법봉(Alt+E · Alt+R)의 대상
let pickNote = null;
// 여는 방식 — 'url' = 같은 주소 /pg/ 로 iframe 이동(기본) · 'doc' = 책 글을 받아 srcdoc 에 넣음(주소 이동이 막힌 브라우저 보험)
let mode = 'url';

// Book 보기 준비
// info: 서버 info
export function initBook(info) {
  const view = $('#bookView');
  if (!view) return;
  cur = store.get('book.cur', null);
  mode = store.get('book.mode', 'url') === 'doc' ? 'doc' : 'url';
  view.innerHTML = `
    <div class="dv-book">
      <aside class="dv-book-side">
        <div class="dv-book-head"><span>책 <span class="dv-book-count"></span></span>
          <button class="dv-ib" type="button" data-act="reload" title="목록 새로고침"><svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a9 9 0 1 1-3-6.7L21 8"/><path d="M21 3v5h-5"/></svg></button>
        </div>
        <div class="dv-book-list"></div>
      </aside>
      <section class="dv-book-main">
        <div class="dv-book-bar"><span class="dv-book-path"></span>
          <button class="dv-book-open dv-book-mode" type="button" data-act="mode"></button>
          <button class="dv-book-open" type="button" data-act="newtab" title="새 탭으로 열기">새 탭으로 열기</button>
        </div>
        <div class="dv-book-empty" hidden></div>
        <iframe class="dv-book-frame" title="책"></iframe>
      </section>
    </div>`;
  el = { list: $('.dv-book-list', view), path: $('.dv-book-path', view), frame: $('.dv-book-frame', view),
    empty: $('.dv-book-empty', view), open: $('.dv-book-open[data-act="newtab"]', view), count: $('.dv-book-count', view),
    mode: $('.dv-book-mode', view) };
  view.addEventListener('click', (e) => {
    const a = e.target.closest('[data-act]')?.dataset.act;
    if (a === 'reload') load();
    else if (a === 'newtab' && cur) window.open(pageUrl(cur), '_blank');
    else if (a === 'mode') { mode = mode === 'doc' ? 'url' : 'doc'; store.set('book.mode', mode); el.frame.dataset.url = ''; show(); }
    const b = e.target.closest('[data-book]');
    if (b) pick(b.dataset.book);
  });
  on('view', (v) => { if (v === 'book') load(); });
  // 책 안 «노트 목록» 단추 → {book:'toggle-list'} — 왼쪽 목록을 자리째 숨김 ↔ 보임(상태 기억)
  //   다른 출처(페이지 서버 = 포트 +100)라 보낸 창이 이 iframe 인지 · 메시지 모양 · 포트만 본다
  const box = $('.dv-book', view);
  box.classList.toggle('no-side', store.get('book.side', '1') === '0');
  // 책 안 Alt+Q · W · B → {book:'key', code} — 다른 출처라 iframe 안 키를 main.js 가 직접 못 받는다
  window.addEventListener('message', (e) => {
    if (e.source !== el.frame.contentWindow || !['toggle-list', 'key', 'pick'].includes(e.data?.book)) return;
    if (e.origin !== location.origin) return;   // 책은 같은 주소의 /pg/ 아래(2026-11-05 — 다른 포트는 대회 브라우저에서 막힘)
    if (e.data.book === 'key') { emit('hot-key', String(e.data.code)); return; }
    if (e.data.book === 'pick') { pickNote = e.data.id ? { note: String(e.data.id), doc: cur } : null; return; }
    const hide = !box.classList.contains('no-side');
    box.classList.toggle('no-side', hide);
    store.set('book.side', hide ? '0' : '1');
  });
}

// 목록 읽기 → 그리기 · 고른 책이 없거나 사라졌으면 맨 위 책
async function load() {
  try {
    list = await api('books');
  } catch (e) {
    el.list.innerHTML = `<div class="dv-book-none">목록 읽기 실패 — ${esc(e.message || e)}</div>`;
    return;
  }
  if (!list.books.some((b) => b.path === cur)) cur = list.books[0]?.path || null;
  paint();
  show();
}

// 목록 한 줄 — 설문 목록(a.sv)과 같은 모양 · 마지막 판 = 파랑(pend) · 앞 판 = 회색(done)
// b: 판 항목
function row(b) {
  const cls = `dv-book-item ${b.latest ? 'pend' : 'done'}${b.path === cur ? ' is-on' : ''}`;
  return `<button type="button" class="${cls}" data-book="${esc(b.path)}" title="${esc(b.path)}">`
    + `<span class="dv-book-name">${esc(b.title)}</span><small class="dv-book-sub">${esc(b.sub || '')}</small></button>`;
}

function paint() {
  el.count.textContent = list.books.length ? String(list.books.length) : '';
  el.list.innerHTML = list.books.length ? list.books.map(row).join('')
    : '<div class="dv-book-none">만든 책 없음 — $ontology 로 1차판을 만들면 여기에</div>';
}

// 오른쪽 — 고른 책을 같은 주소 /pg/ 로(또는 글을 받아 srcdoc 으로)
// hash: «#note=<id>&t=<꼬리>» — 열린 뒤 그 스티커 · 질문 줄로
function show(hash = '') {
  el.empty.hidden = !!cur;
  el.frame.hidden = !el.empty.hidden;
  el.open.disabled = !cur;
  el.mode.textContent = mode === 'doc' ? '주소로 열기' : '다른 방식으로 열기';
  el.mode.title = mode === 'doc' ? '같은 주소 /pg/ 로 이동해 연다(기본)' : '주소 이동 없이 책 글을 받아 넣는다(책이 흰 화면이면)';
  if (!cur) { el.empty.textContent = '고른 책 없음'; el.path.textContent = ''; el.frame.removeAttribute('src'); el.frame.removeAttribute('srcdoc'); return; }
  const url = pageUrl(cur);
  el.path.textContent = cur;
  el.path.title = url;
  if (mode === 'doc') { if (el.frame.dataset.url !== 'doc:' + url || hash) openDoc(url, hash); return; }
  if (el.frame.dataset.url !== url || hash) { el.frame.removeAttribute('srcdoc'); el.frame.dataset.url = url; el.frame.src = url + hash; }
}

// srcdoc 으로 열기 — 책 글을 같은 주소에서 받아 <base>(책 폴더 /pg/…/)를 넣어 api/notes 등 상대 경로가 그대로 가게
// srcdoc 문서는 주소 꼬리가 없어 #note= 는 열린 뒤 그 문서의 hash 를 바꿔 넘긴다(책 엔진이 hashchange 를 받음)
// url: 책 /pg/ 주소 / hash: «#note=…» 또는 ''
async function openDoc(url, hash) {
  el.frame.dataset.url = 'doc:' + url;
  let html;
  try {
    const r = await fetch(url, { cache: 'no-store' });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    html = await r.text();
  } catch (e) {
    el.frame.dataset.url = '';
    el.empty.hidden = false;
    el.frame.hidden = true;
    el.empty.textContent = `책 읽기 실패 — ${e.message || e}`;
    return;
  }
  const base = `<base href="${url.slice(0, url.lastIndexOf('/') + 1)}">`;
  html = /<head[^>]*>/i.test(html) ? html.replace(/<head[^>]*>/i, (h) => h + base) : base + html;
  if (hash) el.frame.addEventListener('load', () => { try { el.frame.contentWindow.location.hash = hash; } catch { /* 넘기지 못함 */ } }, { once: true });
  el.frame.removeAttribute('src');
  el.frame.srcdoc = html;
}

// 책 고르기
// path: 작업 폴더 기준 경로
function pick(path) {
  if (!path) return;
  cur = path;
  store.set('book.cur', cur);
  paint();
  show();
}

// 책 열기 + 주소 꼬리(#note=…) — 알림 종이 부름. 책 폴더 이름이면 그 책 마지막 판, 없으면 경로 그대로
// t: {book, path} / hash: «#note=<id>&t=<꼬리>» / 반환: 열었는지
export async function bookOpen(t, hash = '') {
  await load();
  const hit = list.books.find((b) => b.book === t.book && b.latest) || list.books.find((b) => b.path === t.path);
  if (!hit) return false;
  cur = hit.path;
  store.set('book.cur', cur);
  paint();
  show(hash);
  return true;
}

// 2ND 마법봉 단축키 — 책 안에서 고른 메모의 🪄 를 누르게 함
export function bookWand() {
  el.frame?.contentWindow?.postMessage({ book: 'wand' }, '*');
}

// 지시 붙은 마법봉 대상 — 지금 책에서 고른 스티커 {note, doc} 또는 {}
export function bookSel() {
  return pickNote && pickNote.doc === cur ? { ...pickNote } : {};
}

// 시험 · 디버깅용
export function bookDebug() {
  return { cur, list, url: el.frame?.dataset.url || null };
}
