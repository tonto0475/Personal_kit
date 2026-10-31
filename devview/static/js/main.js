// devview 시작 — 화면 배치 · 보기 전환(코드/Git) · 폴링(파일 · git 변화) · 전역 단축키 · 나눔 막대
import { api } from './api.js';
import { $, $$, on, emit, store, setStoreNs, hydrateStore, toast, icon, dirName, clamp } from './util.js';
import { setupMonaco } from './theme.js';
import { initEditor, openFile, activePath, nextTab, navigate, editor } from './editor.js';
import { checkExternal, watchedPaths, saveAll } from './docs.js';
import { initTree, load as loadTree, reveal } from './tree.js';
import { initSearch, quickOpen, recentFiles, findInFiles, structure, showHelp } from './search.js';
import { initGit } from './git.js';
import { popupOpen } from './popup.js';

// Monaco 0.52 내부 비동기 경쟁 두 가지 — 다음 그리기에서 저절로 맞춰지는 무해한 거부라 이 둘만 조용히 처리
//   1. 같은 단어 강조(occurrencesHighlight): 모델 교체 때 대기 작업 취소 → «Canceled»(VS Code 도 취소 오류는 무시)
//   2. 고정 스크롤(sticky scroll): 외부 변경으로 줄 수가 줄면 진행 중이던 계산이 옛 줄 번호 사용 → «Illegal value for lineNumber»
window.addEventListener('unhandledrejection', (e) => {
  const r = e.reason;
  if (!r) return;
  if (r.name === 'Canceled' || r.message === 'Canceled') e.preventDefault();
  else if (r.message === 'Illegal value for lineNumber' && /StickyScroll/.test(r.stack || '')) e.preventDefault();
});

let view = 'code';
let survey = false;   // 설문 도구 연결 여부(서버 info.survey)
let repo = false;
let lastHead;
let branch = null;

// ======= Monaco 불러오기(한국어 메시지 먼저) =======
function loadMonaco() {
  return new Promise((resolve, reject) => {
    const req = window.require;
    req.config({ paths: { vs: new URL('static/monaco/vs', document.baseURI).href } });
    const main = () => req(['vs/editor/editor.main'], () => resolve(window.monaco), reject);
    req(['vs/nls.messages.ko'], main, main);
  });
}

async function getInfo() {
  for (let i = 0; ; i++) {
    try { return await api('info'); } catch (e) {
      if (i === 0) setConn(false);
      await new Promise((r) => setTimeout(r, Math.min(5000, 500 * (i + 1))));
    }
  }
}

async function boot() {
  const info = await getInfo();
  survey = !!info.survey;
  if (survey) initSurvey();
  setStoreNs(info.root);
  await hydrateStore();          // 빈 저장소로 새로 열렸으면(Browser 도구 복귀) 서버에 남긴 보던 상태로
  repo = !!info.git?.repo;
  branch = info.git?.branch || null;
  document.title = `${info.name} — devview`;
  $('#rootName').textContent = info.name;
  $('#rootName').title = info.root;
  paintBranch();
  const monaco = await loadMonaco();
  setupMonaco(monaco);
  initEditor(monaco, info);
  initSearch();
  initGit(monaco, info);
  initLayout();
  initKeys();
  initApp();
  initPalette();
  await initTree({ name: info.name, openFile });
  if (repo) await loadStatus();
  await restoreTabs();
  // 첫 화면 = 마지막 보기 · 설문으로는 열지 않는다(설문 주소 ?sv 로 열어도) — Browser 도구가 다른 도구에서
  // 돌아올 때마다 페이지를 새로 열어 그때마다 설문으로 튀었다(2026-10-30 유저 지정 · 패키지만 · 설문은 Alt+S)
  const last = store.get('view', 'code');
  showView(last === 'survey' ? 'code' : last);
  setConn(true);
  poll();
  document.documentElement.dataset.ready = '1';
  // 시험 · 디버깅용
  window.devview = { openFile, activePath, editor, monaco, showView, info };
}

async function restoreTabs() {
  const saved = store.get('tabs', []);
  for (const p of saved) await openFile(p, { nav: false, focus: false });
  const act = store.get('active', null);
  if (act && saved.includes(act)) await openFile(act, { nav: false, focus: false });
  if (!saved.length) {
    // 처음 열 때는 README 부터(공식 IDE 와 같은 시작)
    try {
      const r = await api('tree', {});
      const readme = r.entries.find((e) => !e.d && /^readme\.md$/i.test(e.p));
      if (readme) await openFile(readme.p, { nav: false, focus: false });
    } catch { /* 없음 */ }
  }
}

// ======= 설문 보기 — survey.py 화면(/sv/)을 iframe 으로 담음 =======
// 화면이 2초마다 보내는 소식: state(대기 개수 → 배지) · focus(새 설문 도착 → 알림만 · 보던 화면은 그대로)
function initSurvey() {
  const sp = new URLSearchParams(location.search);
  const q = new URLSearchParams();
  for (const k of ['s', 'p', 'id']) if (sp.get(k)) q.set(k, sp.get(k));
  const f = document.createElement('iframe');
  f.title = '설문';
  f.src = 'sv/' + (q.toString() ? '?' + q : '');
  $('#svView').appendChild(f);
  $('#svTab').hidden = false;
  // 설문 화면 안 입력 칸도 기호 팔레트가 넣을 수 있게(같은 주소라 안을 볼 수 있음) · 설문을 옮길 때마다 다시
  f.addEventListener('load', () => { try { watchFocus(f.contentDocument); } catch { /* 다른 주소 */ } });
  window.addEventListener('message', (e) => {
    if (e.source !== f.contentWindow || !e.data) return;
    if (e.data.sv === 'state') {
      const b = $('#svBadge');
      b.hidden = !e.data.pending;
      b.textContent = e.data.pending;
    } else if (e.data.sv === 'focus' && view !== 'survey') toast('새 설문 — Alt+S', '', 6000);
  });
  // 새로고침 때 같은 설문으로 다시 가지 않게 주소의 설문 값은 지움
  if (sp.has('sv')) history.replaceState(null, '', location.pathname);
}

// ======= 화면 캡처 — 지금 화면(코드 · Git · 설문 · 팝업)을 PNG 로 그려 서버가 docs/captures/ 에 저장 =======
// html2canvas 가 DOM 을 다시 그림(1.5~3초). 설문 보기는 iframe 안 화면을 따로 그려 그 자리에 겹침. 알림 띠는 뺌
let capturing = false;
async function capture() {
  if (capturing) return;
  if (typeof window.html2canvas !== 'function') { toast('캡처 도구 없음(static/html2canvas.min.js)', 'error'); return; }
  capturing = true;
  const btn = $('[data-act="capture"]');
  btn?.classList.add('is-busy');
  try {
    const opt = { backgroundColor: '#1e1f22', logging: false, scale: 1,
      ignoreElements: (el) => el.id === 'toasts' };
    // 팝업 · 창은 transform(translate -50%)으로 가운데 잡는데 html2canvas 가 이걸 잘라 그릴 때 틀림
    // → 복제본에서만 지금 보이는 좌표로 바꿔 둠(원래 화면은 그대로)
    const SEL = '.dv-pop, .dv-modal';
    const rects = [...document.querySelectorAll(SEL)].map((el) => el.getBoundingClientRect());
    const fixPops = (doc) => doc.querySelectorAll(SEL).forEach((el, i) => {
      const r = rects[i];
      if (!r) return;
      Object.assign(el.style, { position: 'fixed', transform: 'none', left: `${r.left}px`, top: `${r.top}px`,
        width: `${r.width}px`, height: `${r.height}px`, margin: '0' });
    });
    const c = await window.html2canvas(document.body, { ...opt, width: innerWidth, height: innerHeight,
      windowWidth: innerWidth, windowHeight: innerHeight, onclone: fixPops });
    const fr = view === 'survey' ? $('#svView iframe') : null;
    const d = fr?.contentDocument;
    if (d?.body) {
      const r = fr.getBoundingClientRect();
      const de = d.documentElement;
      const c2 = await window.html2canvas(de, { ...opt, width: r.width, height: r.height,
        windowWidth: r.width, windowHeight: r.height, x: de.scrollLeft, y: de.scrollTop });
      c.getContext('2d').drawImage(c2, r.left, r.top);
    }
    const png = c.toDataURL('image/png').split(',', 2)[1];
    const res = await api('capture', { body: { view, png } });
    toast(`캡처 저장 — ${res.path}`, '', 4000);
  } catch (e) {
    toast(`캡처 실패 — ${e.message || e}`, 'error', 4000);
  } finally {
    capturing = false;
    btn?.classList.remove('is-busy');
  }
}

// ======= 앱 화면 — 과제 앱 서버(기본 3000)를 devview 안 iframe 으로 =======
// Browser 도구 칸을 포트마다 바꿔 오가지 않으려고. 주소는 지금 devview 주소에서 포트만 바꿔 만든다
//   E2B 같은 «포트-샌드박스주소» 이름(8701-xxx.e2b.app) → 3000-xxx.e2b.app · 그 밖(localhost 등) → 호스트:3000
export function appUrl(port, loc = location) {
  const m = loc.hostname.match(/^(\d+)-(.+)$/);
  return m ? `${loc.protocol}//${port}-${m[2]}/` : `${loc.protocol}//${loc.hostname}:${port}/`;
}
function initApp() {
  const inp = $('#appPort');
  inp.value = store.get('appPort', '3000');
  const load = () => {
    const p = inp.value.trim();
    if (!/^\d{2,5}$/.test(p)) { toast('포트는 숫자', 'error'); return; }
    store.set('appPort', p);
    const url = appUrl(p);
    $('#appUrl').textContent = url;
    // 같은 주소여도 다시 받게(서버를 다시 띄운 뒤 새로고침)
    $('#appFrame').src = 'about:blank';
    setTimeout(() => { $('#appFrame').src = url; }, 30);
  };
  inp.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); load(); } });
  $('#appReload').addEventListener('click', load);
  on('view', (v) => { if (v === 'app' && !$('#appFrame').getAttribute('src')) load(); });
}

// ======= 기호 팔레트 — 브라우저 전체화면에서 Win+. · 개인 단축키가 막혀서, 화면 단추로 커서 자리에 넣음 =======
// 마지막으로 커서가 있던 입력 칸(코드 · md 편집기 · Git 검색 · 설문 메모 · 대화창)을 기억해 두고 그 자리에 넣는다
// 넣을 곳이 없으면 클립보드로 복사 → Ctrl+V(터미널은 Ctrl+Shift+V)
const SYMS = ['🚹', '❇️', '🔎', '💭', '📌', '❓', '🤖', '🔴', '🟠', '🟢', '⭐', '✅', '❌',
  '→', '←', '↑', '↓', '●', '○', '△', '·', '«', '»', '—', '※'];
// 기호 단축키 — 유저 PC 의 개인 단축키(AHK)와 같은 조합. 키 자리(e.code)로 봐서 한글 입력 중에도 같게
//   Ctrl+` 🚹 · Alt+` ❇️ · Alt+1 🔎 · Alt+2 💭 · Alt+3 📌 · Ctrl+Q ❓ · Ctrl+1 · 2 · 3 🔴 🟠 🟢 · Ctrl+. → · Ctrl+, ←
const SYM_KEYS = { 'c:Backquote': '🚹', 'a:Backquote': '❇️', 'a:Digit1': '🔎', 'a:Digit2': '💭', 'a:Digit3': '📌', 'c:KeyQ': '❓',
  'c:Digit1': '🔴', 'c:Digit2': '🟠', 'c:Digit3': '🟢', 'c:Period': '→', 'c:Comma': '←' };
function symKey(e) {
  if (e.shiftKey || e.metaKey || e.ctrlKey === e.altKey) return null;
  return SYM_KEYS[(e.ctrlKey ? 'c:' : 'a:') + e.code] || null;
}
let lastEdit = null;
function editable(el) {
  return !!el && (el.isContentEditable || el.tagName === 'TEXTAREA'
    || (el.tagName === 'INPUT' && /^(text|search|)$/.test(el.type || '')));
}
function watchFocus(doc) {
  if (!doc || doc.__dvWatch) return;
  doc.__dvWatch = true;
  doc.addEventListener('focusin', (e) => { if (editable(e.target)) lastEdit = e.target; });
  // Esc 로 닫기 · 기호 단축키 — 편집기(Monaco)가 먼저 먹지 않게 잡는 단계(capture)에서
  doc.defaultView?.addEventListener('keydown', (e) => {
    if (e.isComposing) return;   // 한글 조합 중 키는 입력기 몫 — 가로채면 마지막 글자가 끊기거나 두 번 들어감
    if (e.key === 'Escape' && !$('#palette').hidden) { e.preventDefault(); e.stopPropagation(); togglePalette(false); return; }
    // 문서 바로 가기 · 앱 탭 — 브라우저 · OS 가 먼저 가져가는 키가 있을 수 있어 예비 키를 같이 켜 둔다(키 자리 e.code 라 한글 입력 중에도 같음)
    //   ADR: Alt+A · Alt+Shift+A · Ctrl+Alt+1 / 설문: Alt+S · Alt+Shift+S · Ctrl+Alt+2 / ONTOLOGY: Alt+D · Alt+Shift+D · Ctrl+Alt+3
    //   앱 ↔ 직전 보기: Ctrl+Space · Ctrl+Shift+Space · Ctrl+Alt+4
    const nav = navKey(e);
    if (nav && nav !== 'app') { e.preventDefault(); e.stopPropagation(); goDoc(nav); return; }
    if (nav === 'app') {
      e.preventDefault(); e.stopPropagation();
      showView(view === 'app' ? prevView : 'app');
      return;
    }
    // 입력 칸에 커서가 있을 때만 — 밖에서는 원래 단축키(Alt+1 = 파일 트리 등) 그대로
    const sym = symKey(e);
    if (sym && editable(doc.activeElement)) {
      e.preventDefault(); e.stopPropagation();
      lastEdit = doc.activeElement;
      insertSym(sym);
    }
  }, true);
  // 설문 화면 안에서도 Alt+. (팔레트) · Alt+8 · 9 (보기 전환) — iframe 안 키는 devview 로 안 올라와서 여기서 받음
  if (doc !== document) doc.addEventListener('keydown', (e) => {
    if (!e.altKey || e.ctrlKey || e.metaKey) return;
    const to = { 8: 'survey', 9: 'git' }[e.key];
    if (e.key === '.') { e.preventDefault(); togglePalette(); }
    else if (to) { e.preventDefault(); showView(view === to ? 'code' : to); }
  });
}
// 바로 가기 키 → 갈 곳(ADR.md · survey · ONTOLOGY.md · app) 또는 null
function navKey(e) {
  if (e.metaKey) return null;
  const doc3 = { KeyA: 'ADR.md', KeyS: 'survey', KeyD: 'ONTOLOGY.md' };
  if (e.altKey && !e.ctrlKey && doc3[e.code]) return doc3[e.code];             // Alt+A · S · D (Shift 붙여도)
  if (e.ctrlKey && e.altKey && !e.shiftKey) {
    return { Digit1: 'ADR.md', Digit2: 'survey', Digit3: 'ONTOLOGY.md', Digit4: 'app' }[e.code] || null;
  }
  if (e.ctrlKey && !e.altKey && e.code === 'Space') return 'app';               // Ctrl+Space · Ctrl+Shift+Space
  return null;
}
// 문서 바로 가기 — 작업 폴더의 docs/이름 만 연다(kit/docs 는 원본 양식이라 열지 않는다 · ready-start 1-1 이 루트 docs/ 로 복사)
async function goDoc(name) {
  if (name === 'survey') {
    if (survey) showView('survey'); else toast('설문 도구 없음', 'error');
    return;
  }
  let hit = false;
  try {
    const r = await api('tree', {});
    hit = r.entries.some((x) => !x.d && x.p === `docs/${name}`);
  } catch { /* 아래 알림 */ }
  if (!hit) { toast(`docs/${name} 없음`, 'error'); return; }
  showView('code');
  await openFile(`docs/${name}`);
}
// 지금 화면에 보이는 칸인가 — 다른 보기(숨은 탭)나 숨은 설문 화면 속 칸에는 넣지 않는다
function shown(el) {
  const fe = el.ownerDocument.defaultView?.frameElement;
  if (fe && !fe.getClientRects().length) return false;
  return el.getClientRects().length > 0;
}
function insertSym(text) {
  const el = lastEdit;
  if (el && el.isConnected && shown(el)) {
    // Monaco 편집기 안이면 그 편집기 명령으로 — 실행 취소 · 자동 저장 흐름이 그대로
    const ed = el.closest('.monaco-editor') && window.monaco?.editor.getEditors()
      .find((x) => x.getContainerDomNode().contains(el));
    if (ed) { ed.focus(); ed.trigger('palette', 'type', { text }); return; }
    el.focus();
    // contenteditable(md 편집기) · textarea · input 공통 — 입력 사건이 나서 저장 · 초안 흐름이 그대로
    if (el.ownerDocument.execCommand('insertText', false, text)) return;
    if (typeof el.setRangeText === 'function') {
      el.setRangeText(text, el.selectionStart, el.selectionEnd, 'end');
      el.dispatchEvent(new Event('input', { bubbles: true }));
      return;
    }
  }
  // 클립보드 — 포커스가 iframe(설문 · 앱)에 있으면 브라우저가 클립보드 쓰기를 거절해서 임시 칸을 만들어 복사
  const ok = () => toast(`${text} 복사됨 — Ctrl+V (터미널은 Ctrl+Shift+V)`, '', 2500);
  const ta = document.createElement('textarea');
  ta.value = text;
  ta.style.cssText = 'position:fixed;opacity:0;left:-9999px';
  document.body.appendChild(ta);
  ta.select();
  const copied = document.execCommand('copy');
  ta.remove();
  if (copied) { ok(); return; }
  navigator.clipboard?.writeText(text).then(ok, () => toast('넣을 곳 없음 — 입력 칸을 먼저 누르고 다시', 'error'));
}
function togglePalette(force) {
  const p = $('#palette');
  p.hidden = force === undefined ? !p.hidden : !force;
}
function initPalette() {
  const p = $('#palette');
  p.innerHTML = SYMS.map((s) => `<button type="button" title="${s}">${s}</button>`).join('');
  // 눌러도 입력 칸의 커서를 빼앗지 않게(mousedown 기본 동작 막음)
  p.addEventListener('mousedown', (e) => e.preventDefault());
  $('[data-act="palette"]').addEventListener('mousedown', (e) => e.preventDefault());
  p.addEventListener('click', (e) => { const b = e.target.closest('button'); if (b) insertSym(b.textContent); });
  document.addEventListener('mousedown', (e) => {
    if (!p.hidden && !p.contains(e.target) && !e.target.closest('[data-act="palette"]')) togglePalette(false);
  });
  watchFocus(document);
}

// ======= 보기 전환 =======
let prevView = 'code';   // 앱 탭에서 Ctrl+Space 로 돌아갈 보기
export function showView(v) {
  if (view !== 'app') prevView = view;
  view = ['git', 'app'].includes(v) ? v : (v === 'survey' && survey ? 'survey' : 'code');
  store.set('view', view);
  $('#codeView').hidden = view !== 'code';
  $('#gitView').hidden = view !== 'git';
  $('#svView').hidden = view !== 'survey';
  $('#appView').hidden = view !== 'app';
  $$('.dv-view').forEach((b) => b.classList.toggle('is-on', b.dataset.view === view));
  emit('view', view);
  if (view === 'code') setTimeout(() => editor()?.layout(), 0);
}
on('show-view', (v) => showView(v));

// ======= 폴링 — 파일 지문 · 열린 파일 · git 지문 =======
let sig = null;
async function poll() {
  try {
    const r = await api('poll', { query: { paths: watchedPaths().join('\n') } });
    setConn(true);
    if (sig) {
      if (r.tree !== sig.tree) { loadTree(); statusSoon(); }
      if (r.git !== sig.git) { emit('git-changed'); statusSoon(); }
    }
    sig = r;
    await checkExternal(r.files);
  } catch (e) {
    setConn(false);
  }
  setTimeout(poll, document.hidden ? 5000 : 1500);
}

let statusTimer = null;
function statusSoon() {
  clearTimeout(statusTimer);
  statusTimer = setTimeout(loadStatus, 300);
}

// git 상태 → 트리 · 탭 색 · Git 탭 «커밋하지 않은 변경»
async function loadStatus() {
  if (!repo) return;
  let st;
  try { st = await api('git/status'); } catch { return; }
  const files = new Map();
  const dirs = new Map();
  const ignored = [];
  for (const it of st.items) {
    if (!it.local && it.local !== '') continue;
    const xy = it.x + it.y;
    const local = it.local.replace(/\/$/, '');
    if (xy === '!!') {
      if (it.path.endsWith('/')) ignored.push(local); else files.set(local, '!');
      continue;
    }
    let g;
    if (xy === '??') g = 'U';
    else if (/U/.test(xy) || xy === 'AA' || xy === 'DD') g = 'C';
    else if (it.x === 'A') g = 'A';
    else if (it.x === 'R' || it.y === 'R') g = 'R';
    else if (it.x === 'D' || it.y === 'D') g = 'D';
    else g = 'M';
    files.set(local, g);
    let d = dirName(local);
    while (d) { if (!dirs.has(d)) dirs.set(d, 'M'); d = dirName(d); }
  }
  emit('git-st', { files, dirs, ignored, raw: st });
  emit('git-status', files);
  const n = st.changes?.length || 0;
  const badge = $('#gitBadge');
  badge.hidden = !n;
  badge.textContent = n > 99 ? '99+' : String(n);
  if (st.head !== lastHead) {
    if (lastHead !== undefined) emit('git-head', st.head);
    lastHead = st.head;
  }
  if (st.branch !== branch) { branch = st.branch; emit('git-branch', branch); paintBranch(); }
}

function paintBranch() {
  const el = $('#branchName');
  el.innerHTML = repo ? `${icon('branch')}${branch || 'HEAD 분리'}` : '';
  el.hidden = !repo;
}

// ======= 연결 표시등 =======
let online = null;
function setConn(ok) {
  if (ok === online) return;
  const back = ok && online === false;
  online = ok;
  const el = $('#conn');
  el.className = `dv-conn ${ok ? 'is-on' : 'is-off'}`;
  el.title = ok ? '서버 연결됨' : '서버 응답 없음 — 저장 · 갱신 중지';
  if (!ok) toast('서버 응답 없음 — devview 서버가 꺼졌는지 확인', 'bad', 4000);
  if (back) {
    // 끊긴 사이 저장 못 한 문서 다시 저장 · 목록 갱신
    toast('서버 다시 연결됨');
    saveAll();
    loadTree();
    statusSoon();
  }
}
on('online', (ok) => setConn(ok));

// ======= 배치 · 나눔 막대 =======
function initLayout() {
  const root = document.documentElement;
  const sizes = { tree: store.get('w.tree', 250), gdetail: store.get('w.gdetail', 380), gdiff: store.get('w.gdiff', 0) };
  const apply = () => {
    root.style.setProperty('--dv-tree-w', `${sizes.tree}px`);
    root.style.setProperty('--dv-gdetail-w', `${sizes.gdetail}px`);
    if (sizes.gdiff) root.style.setProperty('--dv-gdiff-h', `${sizes.gdiff}px`);
  };
  apply();
  // 좁은 화면(대회 미리보기 칸)에서는 트리를 접은 채 시작
  if (store.get('tree.hidden', innerWidth < 720)) $('#codeView').classList.add('is-notree');
  document.addEventListener('pointerdown', (e) => {
    const bar = e.target.closest('[data-split]');
    if (!bar) return;
    e.preventDefault();
    const kind = bar.dataset.split;
    const start = { x: e.clientX, y: e.clientY, v: kind === 'gdiff' ? ($('#gDiff')?.getBoundingClientRect().height || 300) : sizes[kind] };
    bar.setPointerCapture(e.pointerId);
    bar.classList.add('is-drag');
    const move = (ev) => {
      if (kind === 'tree') sizes.tree = clamp(start.v + ev.clientX - start.x, 140, innerWidth * 0.6);
      else if (kind === 'gdetail') sizes.gdetail = clamp(start.v - (ev.clientX - start.x), 220, innerWidth * 0.7);
      else if (kind === 'gdiff') sizes.gdiff = clamp(start.v - (ev.clientY - start.y), 120, innerHeight - 140);
      apply();
    };
    const up = () => {
      bar.removeEventListener('pointermove', move);
      bar.removeEventListener('pointerup', up);
      bar.classList.remove('is-drag');
      store.set(`w.${kind}`, sizes[kind]);
      editor()?.layout();
    };
    bar.addEventListener('pointermove', move);
    bar.addEventListener('pointerup', up);
  });
  $('#views').addEventListener('click', (e) => {
    const b = e.target.closest('[data-view]');
    if (b) showView(b.dataset.view);
  });
  $('#topActs').addEventListener('click', (e) => {
    const a = e.target.closest('[data-act]')?.dataset.act;
    if (a === 'quickOpen') quickOpen();
    else if (a === 'find') findInFiles();
    else if (a === 'help') showHelp();
    else if (a === 'capture') capture();
    else if (a === 'palette') togglePalette();
    else if (a === 'tree') toggleTree();
  });
  on('show-tree', () => { if ($('#codeView').classList.contains('is-notree')) toggleTree(); if (view !== 'code') showView('code'); });
  on('focus-editor', () => editor()?.focus());
}

function toggleTree() {
  const c = $('#codeView');
  c.classList.toggle('is-notree');
  store.set('tree.hidden', c.classList.contains('is-notree'));
  if (!c.classList.contains('is-notree')) $('#treeRows')?.focus({ preventScroll: true });
  setTimeout(() => editor()?.layout(), 0);
}

// ======= 전역 단축키 =======
// 캡처 단계에서 먼저 받음 — Monaco 안에서도 동작. 브라우저 동작(뒤로 가기 · 새로고침 · 페이지 저장)은 막음
function initKeys() {
  let lastShift = 0;
  let shiftClean = false;
  const inMonaco = () => !!document.activeElement?.closest?.('.monaco-editor');
  const inInput = () => /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement?.tagName || '') && !inMonaco();
  window.addEventListener('keydown', (e) => {
    const k = e.key;
    const ctrl = e.ctrlKey || e.metaKey;
    const low = k.length === 1 ? k.toLowerCase() : k;
    if (k === 'Shift') { shiftClean = !e.repeat && !ctrl && !e.altKey; return; }
    shiftClean = false;
    lastShift = 0;
    const stop = () => { e.preventDefault(); e.stopPropagation(); };
    // 화면 캡처 — 팝업이 떠 있어도 찍히게 팝업 검사보다 먼저
    if (ctrl && e.altKey && !e.shiftKey && low === 'p') { stop(); capture(); return; }
    if (popupOpen() && k !== 'Escape') return;
    if (k === 'Escape') { emit('escape'); return; }
    // 브라우저 새로고침 · 페이지 저장 · 뒤로 가기 차단
    if (k === 'F5' || (ctrl && low === 'r' && !inMonaco())) { stop(); toast('새로고침 키는 막아 둠 — 화면 새로고침은 버튼으로', '', 1500); return; }
    if (ctrl && !e.shiftKey && !e.altKey && low === 's') {
      // 편집기 안이면 각 편집기가 처리(Monaco 동작 · md 키맵). 밖이면 열린 문서 전부 저장
      if (!inMonaco() && !document.activeElement?.closest?.('.cm-editor')) { stop(); saveAll(); }
      return;
    }
    if (e.altKey && !ctrl && (k === 'ArrowLeft' || k === 'ArrowRight')) {
      stop();
      if (view === 'code') nextTab(k === 'ArrowLeft' ? -1 : 1);
      return;
    }
    if (ctrl && e.altKey && !e.shiftKey && (k === 'ArrowLeft' || k === 'ArrowRight')) { stop(); navigate(k === 'ArrowLeft' ? -1 : 1); return; }
    if (ctrl && !e.shiftKey && !e.altKey && low === 'p') { stop(); quickOpen(); return; }
    if (ctrl && !e.shiftKey && !e.altKey && low === 'e') { stop(); recentFiles(); return; }
    if (ctrl && e.shiftKey && !e.altKey && low === 'f') { stop(); findInFiles(selectionText()); return; }
    if (e.altKey && !ctrl && k === '1') { stop(); if (view !== 'code') showView('code'); toggleTree(); return; }
    if (e.altKey && !ctrl && k === '9') { stop(); showView(view === 'git' ? 'code' : 'git'); return; }
    if (e.altKey && !ctrl && k === '8' && survey) { stop(); showView(view === 'survey' ? 'code' : 'survey'); return; }
    if (e.altKey && !ctrl && !e.shiftKey && k === '.') { stop(); togglePalette(); return; }
    if (e.altKey && !ctrl && k === 'F1') { stop(); if (activePath()) reveal(activePath()); return; }
    if (ctrl && k === 'F12' && !inMonaco()) { stop(); structure(); return; }
    if (k === 'F1' && !inMonaco()) { stop(); showHelp(); return; }
    if (k === 'Backspace' && !inMonaco() && !inInput() && !document.activeElement?.isContentEditable) e.preventDefault();
  }, true);
  window.addEventListener('keyup', (e) => {
    if (e.key !== 'Shift' || !shiftClean) return;
    const now = performance.now();
    if (now - lastShift < 380) { lastShift = 0; if (!popupOpen()) quickOpen(); } else lastShift = now;
  }, true);
  // 마우스 뒤로/앞으로 버튼 = 이동 기록(브라우저 뒤로 가기 대신)
  for (const t of ['mousedown', 'mouseup']) {
    window.addEventListener(t, (e) => {
      if (e.button !== 3 && e.button !== 4) return;
      e.preventDefault();
      if (t === 'mouseup') navigate(e.button === 3 ? -1 : 1);
    }, true);
  }
  window.addEventListener('focus', () => statusSoon());
}

function selectionText() {
  const ed = editor();
  const sel = ed?.getSelection();
  if (ed?.hasTextFocus() && sel && !sel.isEmpty() && sel.startLineNumber === sel.endLineNumber) {
    return { q: ed.getModel().getValueInRange(sel) };
  }
  return {};
}

boot().catch((e) => {
  console.error(e);
  document.body.insertAdjacentHTML('beforeend', `<div class="dv-fatal">시작 실패: ${String(e?.message || e)}</div>`);
});
