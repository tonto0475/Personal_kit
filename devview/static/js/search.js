// 찾기 — 파일 찾기(Shift 두 번 · Ctrl+P) · 최근 파일(Ctrl+E) · 파일 내용 검색(Ctrl+Shift+F) · 구조(Ctrl+F12) · 단축키 도움말
import { api } from './api.js';
import { h, esc, on, store, toast, icon, fileBadge, baseName, dirName, debounce } from './util.js';
import { pickList, overlay, openModal } from './popup.js';
import { allFiles } from './tree.js';
import { openFile, activeDoc, openTabs } from './editor.js';
import { getDoc, textOf } from './docs.js';

export function initSearch() {
  on('find-usages', (word) => findInFiles({ q: word, word: true, case: true }));
  on('structure', () => structure());
  on('find-file', ({ name, heading, open }) => {
    const hit = allFiles().find((p) => baseName(p).toLowerCase() === name);
    if (!hit) { toast(`문서 없음: ${name}`); return; }
    (open || openFile)(hit).then(() => { if (heading) getDoc(hit)?.md?.jumpHeading(heading); });
  });
}

// ======= 이름 일치 점수 =======
// 순서대로 들어 있으면 일치. 연속 · 단어 첫 글자 · 파일 이름 쪽 일치에 가산점
function subseq(q, s) {
  let j = 0, score = 0, prev = -2;
  const pos = [];
  for (let i = 0; i < s.length && j < q.length; i++) {
    if (s[i] !== q[j]) continue;
    let add = 1;
    if (prev === i - 1) add += 5;
    if (i === 0 || '/_-. '.includes(s[i - 1])) add += 8;
    score += add;
    pos.push(i);
    prev = i;
    j++;
  }
  return j === q.length ? { score, pos } : null;
}
export function fuzzy(qRaw, path) {
  const q = qRaw.toLowerCase().replace(/\s+/g, '');
  if (!q) return { score: 0, pos: [], base: true };
  const name = baseName(path).toLowerCase();
  const low = path.toLowerCase();
  if (!q.includes('/')) {
    const i = name.indexOf(q);
    if (i >= 0) return { score: 1000 + (i === 0 ? 300 : 0) - name.length, pos: [...Array(q.length)].map((_, k) => i + k), base: true };
    const m = subseq(q, name);
    if (m) return { score: 500 + m.score - name.length * 0.5, pos: m.pos, base: true };
  }
  const i = low.indexOf(q);
  if (i >= 0) return { score: 300 - low.length * 0.2, pos: [...Array(q.length)].map((_, k) => i + k), base: false };
  const m = subseq(q, low);
  return m ? { score: 100 + m.score - low.length * 0.3, pos: m.pos, base: false } : null;
}
function marked(text, pos) {
  if (!pos?.length) return esc(text);
  const set = new Set(pos);
  let out = '';
  for (let i = 0; i < text.length; i++) out += set.has(i) ? `<mark>${esc(text[i])}</mark>` : esc(text[i]);
  return out;
}

// ======= 파일 찾기 =======
export function quickOpen(initial = '') {
  const recent = store.get('recent', []);
  pickList({
    title: '파일 찾기', hint: 'Shift 두 번 · Ctrl+P · «이름:줄» 로 줄까지', placeholder: '파일 이름 (순서만 맞으면 됨)', value: initial,
    items: (raw) => {
      const [q, line] = raw.split(':');
      const files = allFiles();
      if (!q.trim()) {
        const known = new Set(files);
        return recent.filter((p) => known.has(p)).slice(0, 30).map((p) => ({ p, pos: [], base: true, line: Number(line) || null }));
      }
      const out = [];
      for (const p of files) {
        const m = fuzzy(q, p);
        if (m) out.push({ p, ...m, line: Number(line) || null, score: m.score + (recent.includes(p) ? 40 : 0) });
      }
      out.sort((a, b) => b.score - a.score || a.p.length - b.p.length);
      return out.slice(0, 80);
    },
    render: (x) => {
      const name = baseName(x.p);
      const dir = dirName(x.p);
      const off = x.p.length - name.length;
      const namePos = x.base ? x.pos : x.pos.filter((k) => k >= off).map((k) => k - off);
      const dirPos = x.base ? [] : x.pos.filter((k) => k < off);
      return `${fileBadge(name)}<span class="dv-pi-main">${marked(name, namePos)}${x.line ? `<span class="dv-dim">:${x.line}</span>` : ''}</span>`
        + `<span class="dv-pi-sub">${marked(dir, dirPos)}</span>`;
    },
    onPick: (x) => openFile(x.p, x.line ? { line: x.line } : {}),
    empty: '최근 연 파일 없음 — 이름을 입력',
  });
}

export function recentFiles() {
  const known = new Set(allFiles());
  const list = store.get('recent', []).filter((p) => known.has(p) || openTabs().includes(p));
  pickList({
    title: '최근 파일', hint: 'Ctrl+E', placeholder: '걸러 내기',
    items: (q) => list.filter((p) => !q || fuzzy(q, p)).slice(0, 40),
    render: (p) => `${fileBadge(baseName(p))}<span class="dv-pi-main">${esc(baseName(p))}</span><span class="dv-pi-sub">${esc(dirName(p))}</span>`,
    onPick: (p) => openFile(p),
    empty: '최근 연 파일 없음',
  });
}

// ======= 파일 구조 =======
function outline(doc) {
  const text = textOf(doc);
  const lines = text.split('\n');
  const out = [];
  if (doc.kind === 'md') {
    let fence = false;
    lines.forEach((l, i) => {
      if (/^\s*(```|~~~)/.test(l)) fence = !fence;
      const m = !fence && /^(#{1,6})\s+(.*?)\s*#*$/.exec(l);
      if (m) out.push({ name: m[2], kind: `H${m[1].length}`, depth: m[1].length - 1, line: i + 1 });
    });
    return out;
  }
  const lang = doc.model.getLanguageId();
  lines.forEach((l, i) => {
    let m;
    if (lang === 'python-pc') {
      if ((m = /^(\s*)(?:async\s+)?def\s+([A-Za-z_]\w*)/.exec(l))) out.push({ name: `${m[2]}()`, kind: 'def', depth: m[1].length / 4, line: i + 1 });
      else if ((m = /^(\s*)class\s+([A-Za-z_]\w*)/.exec(l))) out.push({ name: m[2], kind: 'class', depth: m[1].length / 4, line: i + 1 });
      else if ((m = /^([A-Z][A-Z0-9_]+)\s*(?::[^=]+)?=(?!=)/.exec(l))) out.push({ name: m[1], kind: '상수', depth: 0, line: i + 1 });
    } else if (/javascript|typescript/.test(lang)) {
      if ((m = /^(\s*)(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s*\*?\s*([A-Za-z_$][\w$]*)/.exec(l))) out.push({ name: `${m[2]}()`, kind: 'function', depth: m[1].length / 2, line: i + 1 });
      else if ((m = /^(\s*)(?:export\s+)?(?:default\s+)?class\s+([A-Za-z_$][\w$]*)/.exec(l))) out.push({ name: m[2], kind: 'class', depth: m[1].length / 2, line: i + 1 });
      else if ((m = /^(\s*)(?:export\s+)?(?:const|let)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>/.exec(l))) out.push({ name: `${m[2]}()`, kind: 'const', depth: m[1].length / 2, line: i + 1 });
      else if ((m = /^(\s+)(?:static\s+|async\s+|get\s+|set\s+)*([A-Za-z_$][\w$]*)\s*\([^)]*\)\s*\{/.exec(l)) && !/^(if|for|while|switch|catch|return)$/.test(m[2])) out.push({ name: `${m[2]}()`, kind: 'method', depth: m[1].length / 2, line: i + 1 });
    } else if (lang === 'shell') {
      if ((m = /^\s*(?:function\s+)?([A-Za-z_][\w-]*)\s*\(\)\s*\{?/.exec(l))) out.push({ name: `${m[1]}()`, kind: 'function', depth: 0, line: i + 1 });
    } else if (lang === 'yaml') {
      if ((m = /^(\s*)([^\s#:][^:]*):(\s|$)/.exec(l)) && m[1].length <= 4) out.push({ name: m[2], kind: 'key', depth: m[1].length / 2, line: i + 1 });
    }
  });
  return out;
}

export function structure() {
  const doc = activeDoc();
  if (!doc || (doc.kind !== 'code' && doc.kind !== 'md')) { toast('구조를 볼 파일이 없음'); return; }
  const items = outline(doc);
  if (!items.length) { toast('정의 · 제목 없음'); return; }
  pickList({
    title: '파일 구조', hint: `Ctrl+F12 · ${items.length}개`, placeholder: '이름 걸러 내기',
    items: (q) => items.filter((x) => !q || fuzzy(q, x.name)),
    render: (x) => `<span class="dv-pi-tag">${esc(x.kind)}</span><span class="dv-pi-main" style="padding-left:${Math.min(6, Math.floor(x.depth)) * 14}px">${esc(x.name)}</span><span class="dv-pi-sub">${x.line}</span>`,
    onPick: (x) => openFile(doc.readonly ? doc.path : doc.path, { line: x.line }),
  });
}

// ======= 파일 내용 검색 =======
const opts = { case: false, word: false, regex: false, glob: '' };
export function findInFiles(init = {}) {
  Object.assign(opts, { case: !!init.case, word: !!init.word, regex: false }, init.glob !== undefined ? { glob: init.glob } : {});
  const { wrap, close } = overlay();
  const box = h(`<div class="dv-pop dv-find" role="dialog">
    <div class="dv-pop-head"><span class="dv-pop-title">파일 내용 검색</span><span class="dv-pop-hint" data-f="count"></span></div>
    <div class="dv-find-row"><input class="dv-pop-input" data-f="q" spellcheck="false" autocomplete="off" placeholder="찾을 내용">
      <button class="dv-tog" data-o="case" title="대소문자 구분">Aa</button><button class="dv-tog" data-o="word" title="단어 단위">W</button>
      <button class="dv-tog" data-o="regex" title="정규식">.*</button></div>
    <div class="dv-find-row"><input class="dv-pop-input dv-find-glob" data-f="glob" spellcheck="false" autocomplete="off" placeholder="파일 이름 조건 (예: *.py, !tests/*)"></div>
    <div class="dv-pop-list dv-find-list" data-f="list"></div></div>`);
  wrap.append(box);
  const q = box.querySelector('[data-f="q"]');
  const glob = box.querySelector('[data-f="glob"]');
  const list = box.querySelector('[data-f="list"]');
  const count = box.querySelector('[data-f="count"]');
  q.value = init.q || store.get('lastFind', '');
  glob.value = opts.glob;
  let hits = [];
  let sel = 0;
  let seq = 0;
  const paintToggles = () => box.querySelectorAll('[data-o]').forEach((b) => b.classList.toggle('is-on', !!opts[b.dataset.o]));
  function paint() {
    if (!hits.length) { list.innerHTML = `<div class="dv-pop-empty">${q.value ? '일치 없음' : '찾을 내용을 입력'}</div>`; return; }
    let last = '';
    let html = '';
    hits.forEach((x, i) => {
      if (x.p !== last) {
        last = x.p;
        html += `<div class="dv-find-file">${fileBadge(baseName(x.p))}<span>${esc(baseName(x.p))}</span><span class="dv-pi-sub">${esc(dirName(x.p))}</span></div>`;
      }
      const t = x.t;
      const s = Math.max(0, x.c - 60);
      const pre = (s > 0 ? '…' : '') + t.slice(s, x.c).replace(/^\s+/, '');
      html += `<div class="dv-pop-item dv-find-hit${i === sel ? ' is-sel' : ''}" data-i="${i}"><span class="dv-find-n">${x.n}</span>`
        + `<span class="dv-find-t">${esc(pre)}<mark>${esc(t.slice(x.c, x.e))}</mark>${esc(t.slice(x.e, x.e + 200))}</span></div>`;
    });
    list.innerHTML = html;
    list.querySelector('.is-sel')?.scrollIntoView({ block: 'nearest' });
  }
  let ranFor = null;               // 마지막으로 결과를 받은 조건
  const key = () => `${q.value}\n${glob.value}\n${opts.case}${opts.word}${opts.regex}`;
  const runNow = async () => {
    const my = ++seq;
    const query = q.value;
    ranFor = key();
    store.set('lastFind', query);
    opts.glob = glob.value;
    if (!query) { hits = []; count.textContent = ''; paint(); return; }
    count.textContent = '찾는 중…';
    let r;
    try {
      r = await api('search', { query: { q: query, case: opts.case ? 1 : 0, word: opts.word ? 1 : 0, regex: opts.regex ? 1 : 0, glob: opts.glob } });
    } catch (e) {
      if (my !== seq) return;
      count.textContent = e.message;
      hits = [];
      paint();
      return;
    }
    if (my !== seq) return;
    hits = r.hits;
    sel = 0;
    count.textContent = `${r.hits.length}${r.truncated ? '+' : ''}건 · 파일 ${r.files}개`;
    paint();
  };
  const run = debounce(runNow, 220);
  const pick = (i) => {
    const x = hits[i];
    if (!x) return;
    close(false);
    openFile(x.p, { line: x.n, col: x.c + 1 });
  };
  box.addEventListener('click', (e) => {
    const o = e.target.closest('[data-o]')?.dataset.o;
    if (o) { opts[o] = !opts[o]; paintToggles(); run(); q.focus(); return; }
    const it = e.target.closest('[data-i]');
    if (it) pick(Number(it.dataset.i));
  });
  for (const el of [q, glob]) {
    el.addEventListener('input', run);
    el.addEventListener('keydown', (e) => {
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault();
        if (hits.length) sel = (sel + (e.key === 'ArrowDown' ? 1 : -1) + hits.length) % hits.length;
        paint();
      } else if (e.key === 'Enter') {
        e.preventDefault();
        // 치자마자 Enter — 지금 조건으로 먼저 검색한 뒤 고름
        if (ranFor !== key()) { run.cancel(); runNow().then(() => pick(sel)); } else pick(sel);
      }
      else if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); close(); }
      else if (e.altKey && /^[cwr]$/i.test(e.key)) {
        e.preventDefault();
        const k = { c: 'case', w: 'word', r: 'regex' }[e.key.toLowerCase()];
        opts[k] = !opts[k];
        paintToggles();
        run();
      }
    });
  }
  paintToggles();
  q.focus();
  q.select();
  if (q.value) run(); else paint();
}

// ======= 단축키 도움말 =======
const KEYS = [
  ['파일', [['Shift 두 번 · Ctrl+P', '파일 찾기 («이름:줄» 로 줄까지)'], ['Ctrl+E', '최근 파일'], ['Ctrl+Shift+F', '파일 내용 검색'],
    ['Alt+Shift+1', '파일 트리 보이기/숨기기'], ['Alt+F1', '열린 파일을 트리에서 찾기'], ['Alt+← / Alt+→', '이전/다음 탭'], ['가운데 클릭', '탭 닫기']]],
  ['편집 (PyCharm 키맵)', [['Ctrl+/', '줄 주석 켜기/끄기'], ['Ctrl+Shift+/', '블록 주석'], ['Tab · Shift+Tab', '들여쓰기 · 내어쓰기'],
    ['Enter', '«:» 뒤 자동 들여쓰기 · return/pass 뒤 내어쓰기'], ['Ctrl+D', '줄 복제'], ['Ctrl+Shift+D', '줄 삭제'],
    ['Alt+Shift+↑↓', '줄 옮기기'], ['Shift+Enter', '아래에 새 줄'], ['Ctrl+Shift+J', '줄 합치기'], ['Ctrl+Shift+U', '대소문자 바꾸기'],
    ['Alt+J · Ctrl+Alt+Shift+J', '같은 단어 다중 선택'], ['Ctrl+Y · Ctrl+Shift+Z', '다시 실행'], ['Ctrl+Alt+L', '코드 정리 (JSON · JS · HTML · CSS)'],
    ['Ctrl+S', '바로 저장 (평소엔 1초 뒤 자동)']]],
  ['이동 · 찾기', [['Ctrl+B · F12 · Ctrl+클릭', '정의로 이동'], ['Alt+F7', '사용처 찾기'], ['Ctrl+F12', '파일 구조'], ['Ctrl+G', '줄로 이동'],
    ['Ctrl+F · Ctrl+R', '찾기 · 바꾸기'], ['Ctrl+Alt+← / →', '이전/다음 위치'], ['Ctrl+Alt+Shift+↑↓', '이전/다음 변경'],
    ['Ctrl+Alt+Shift+C', '«경로:줄» 복사'], ['Ctrl+Shift+A · F1(편집기)', '명령 목록'], ['Ctrl+휠', '글자 크기']]],
  ['Git 탭', [['Alt+9', 'Git 탭 · 코드 탭 오가기'], ['↑ ↓', '커밋 이동'], ['Enter · →', '바뀐 파일 목록으로'], ['F7 · Shift+F7', '다음/이전 변경 부분'],
    ['Ctrl+F', '커밋 검색 (메시지 · 해시 · 작성자)']]],
  ['그래프', [['Alt+` · Alt+1~8 · Alt+0', '그래프 Main · 섹션1~8 · 섹션0 화면으로 (어느 보기에서든 · 입력 칸 · 책 안에서도)'], ['Alt+Q', 'MAIN 마법봉 — 그래프에서 고른 노드로 (어느 보기에서든 · 그래프 · 편집기 · 책 안에서도)'],
    ['Alt+W', '2ND 마법봉 — 지금 화면의 선택으로 (그래프 · 코드 · Git · 설문 · 앱 · 책은 고른 메모)'],
    ['Alt+E · Alt+R', '지시 붙은 마법봉 MAIN · 2ND — 대상은 Alt+Q · W 와 같고 허브 입력창에 지시를 써서 ✈ (노드 없어도 · 어느 보기에서든)'],
    ['` (입력 칸 밖)', '고른 노드의 연결 내용 — 파일 · 문서는 오른쪽 절반에 열고 앵커 줄로 · 모듈은 모듈 설명'], ['` · Esc · ×', '연결 내용 닫기']]],
  ['Book', [['Alt+B', 'Book 탭(북키트 책 목록 · 보기) ↔ 코드 탭']]],
  ['설문 · 캡처', [['Ctrl+Alt+P', '화면 캡처 → docs/captures/ (팝업이 떠 있어도)']]],
  ['문서 바로 가기 (예비 키도 같이 켜 둠)', [['Ctrl+Alt+1', '결정 · 인수인계 문서 docs/hand_off.md'],
    ['Ctrl+Alt+2', '설문 탭'], ['Ctrl+Alt+3', '데이터 지도 docs/ONTOLOGY.md'],
    ['Ctrl+Space · Ctrl+Shift+Space · Ctrl+Alt+4', '앱 탭 ↔ 직전 보기']]],
  ['대화', [['Alt+A · S · D · F · G', '대화 보기 1~5번 세션 탭 (어느 보기에서든 · 한글 자판도 같음)'], ['Alt+← / →', '대화 보기 안에서 옆 세션 탭'],
    ['Ctrl+Enter', '보내기 (Enter 는 줄바꿈)'], ['🤖 · 접힘 줄 클릭', '답변 하나 접기 · 펴기'], ['Ctrl+Shift+, · Ctrl+Shift+.', '답변 전부 접기 · 전부 펴기']]],
  ['앱 화면 · 기호', [['Ctrl+Space', '앱 탭 ↔ 직전 보기 — 과제 앱 서버(PORT 칸 · 기본 3000)를 이 안에서(코드 편집기 자동 완성 대신)'], ['Alt+.', '기호 팔레트 — 마지막 입력 칸의 커서 자리에 넣음(코드 · md · Git · 설문)'], ['Esc', '기호 팔레트 닫기'],
    ['Ctrl+` · Alt+Z', '🚹 · ❇️ (입력 칸에 커서가 있을 때 — 아래도 같음)'], ['Alt+X · Alt+C · Alt+V', '🔎 · 💭 · 📌'],
    ['Ctrl+Q', '❓'], ['Ctrl+1 · 2 · 3', '🔴 · 🟠 · 🟢'], ['Ctrl+. · Ctrl+,', '→ · ←']]],
];
export function showHelp() {
  const body = h(`<div class="dv-help">${KEYS.map(([t, rows]) => `<section><h3>${esc(t)}</h3><table>${rows.map(([k, d]) =>
    `<tr><td><kbd>${esc(k)}</kbd></td><td>${esc(d)}</td></tr>`).join('')}</table></section>`).join('')}
    <p class="dv-help-warn">${icon('alert')}브라우저가 먼저 가져가는 키: Ctrl+W(탭 닫힘) · Ctrl+N · Ctrl+T · Ctrl+Shift+N/W/T · Ctrl+Tab. PyCharm 의 Ctrl+W(선택 넓히기) 대신 Alt+Shift+→</p></div>`);
  openModal({ title: '단축키', body, wide: true });
}
