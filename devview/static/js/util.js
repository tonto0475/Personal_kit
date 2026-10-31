// 공용 도구 — DOM · 이벤트 · 저장소 · 시간 표시 · 알림 · 아이콘

export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

export function h(html) {
  const t = document.createElement('template');
  t.innerHTML = html.trim();
  return t.content.firstElementChild;
}

const ESC = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
export const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ESC[c]);

export function debounce(fn, ms) {
  let t = null;
  const f = (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
  f.cancel = () => clearTimeout(t);
  return f;
}

export const clamp = (v, a, b) => Math.min(Math.max(v, a), b);
export const baseName = (p) => (p || '').split('/').pop();
export const dirName = (p) => ((p || '').includes('/') ? p.slice(0, p.lastIndexOf('/')) : '');
export const extOf = (p) => { const n = baseName(p).toLowerCase(); return n.includes('.') ? n.split('.').pop() : ''; };

// ======= 이벤트 =======
const bus = new Map();
export function on(name, fn) {
  if (!bus.has(name)) bus.set(name, new Set());
  bus.get(name).add(fn);
  return () => bus.get(name).delete(fn);
}
export function emit(name, data) {
  for (const fn of bus.get(name) || []) {
    try { fn(data); } catch (e) { console.error(`[devview] ${name}`, e); }
  }
}

// ======= 저장소 — 작업 폴더별 이름 공간. 사생활 창 · 차단 환경에서는 조용히 기본값 =======
let ns = 'dv:';
export function setStoreNs(root) { ns = `dv:${root}:`; }
export const store = {
  get(k, d) {
    try {
      const v = localStorage.getItem(ns + k);
      return v === null ? d : JSON.parse(v);
    } catch { return d; }
  },
  set(k, v) {
    try { localStorage.setItem(ns + k, JSON.stringify(v)); } catch { /* 저장 불가 환경 */ }
    syncSoon();
  },
};

// ======= 보던 상태를 서버에도 — 대회 Browser 도구는 돌아올 때 빈 저장소로 페이지를 새로 연다 =======
// 저장할 때마다(0.8초 묶음) 이 작업 폴더 몫(ns 접두어) 전부를 서버 ~/.devview/state.json 에 보낸다
// 열 때 브라우저 저장소에 이 몫이 하나도 없으면 서버 값으로 채운다(hydrateStore) → 탭 · 열린 파일 · 보기 복원
let syncTimer = null;
function mine() {
  const out = {};
  try {
    for (let i = 0; i < localStorage.length; i++) {
      const k = localStorage.key(i);
      if (k.startsWith(ns)) out[k.slice(ns.length)] = localStorage.getItem(k);
    }
  } catch { /* 저장 불가 환경 */ }
  return out;
}
function syncSoon() {
  if (ns === 'dv:') return;                              // 작업 폴더를 알기 전
  clearTimeout(syncTimer);
  syncTimer = setTimeout(() => {
    fetch('api/state', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Devview': '1' },
      body: JSON.stringify({ ns, data: mine() }), keepalive: true }).catch(() => { /* 서버 끊김 — 다음 저장 때 */ });
  }, 800);
}
export async function hydrateStore() {
  if (Object.keys(mine()).length) return false;          // 이미 있음(같은 브라우저) — 서버 값으로 덮지 않음
  try {
    // 1.5초 안에 답이 없으면 건너뜀 — 시작이 이 요청에 묶여 멈추지 않게(없으면 예전처럼 빈 시작)
    const r = await fetch('api/state?ns=' + encodeURIComponent(ns), { cache: 'no-store', signal: AbortSignal.timeout(1500) });
    const data = (await r.json()).data || {};
    for (const [k, v] of Object.entries(data)) localStorage.setItem(ns + k, v);
    return Object.keys(data).length > 0;
  } catch { return false; }
}

// ======= 시간 =======
const pad = (n) => String(n).padStart(2, '0');
export function fmtDate(sec) {
  if (!sec) return '';
  const d = new Date(sec * 1000);
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
export function relDate(sec) {
  if (!sec) return '';
  const d = new Date(sec * 1000);
  const now = new Date();
  const diff = (now - d) / 1000;
  const hm = `${pad(d.getHours())}:${pad(d.getMinutes())}`;
  if (diff < 60 && diff > -60) return '방금';
  if (diff < 3600 && diff > 0) return `${Math.floor(diff / 60)}분 전`;
  const day = (x) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();
  const days = Math.round((day(now) - day(d)) / 86400000);
  if (days === 0) return `오늘 ${hm}`;
  if (days === 1) return `어제 ${hm}`;
  if (d.getFullYear() === now.getFullYear()) return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${hm}`;
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}
export function shortDate(sec) {
  if (!sec) return '';
  const d = new Date(sec * 1000);
  const now = new Date();
  if (d.getFullYear() === now.getFullYear()) return `${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  return `${String(d.getFullYear()).slice(2)}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

// ======= 알림 =======
export function toast(msg, kind = '', ms = 2600) {
  const box = document.getElementById('toasts');
  if (!box) return;
  const el = h(`<div class="dv-toast ${kind ? 'is-' + kind : ''}">${esc(msg)}</div>`);
  box.append(el);
  setTimeout(() => { el.classList.add('is-out'); setTimeout(() => el.remove(), 300); }, ms);
}

export async function copyText(text, label = '복사함') {
  let ok = false;
  try {
    await navigator.clipboard.writeText(text);
    ok = true;
  } catch {
    // iframe 에 clipboard-write 권한이 없을 때 — 옛 방식
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.style.cssText = 'position:fixed;left:-9999px;top:0';
    document.body.append(ta);
    ta.select();
    try { ok = document.execCommand('copy'); } catch { ok = false; }
    ta.remove();
  }
  toast(ok ? `${label}: ${text.length > 60 ? text.slice(0, 60) + '…' : text}` : '복사 실패', ok ? '' : 'bad');
  return ok;
}

// ======= 아이콘 (선 아이콘, 모양 출처: Lucide · ISC) =======
const P = {
  code: '<polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/>',
  branch: '<line x1="6" x2="6" y1="3" y2="15"/><circle cx="18" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><path d="M18 9a9 9 0 0 1-9 9"/>',
  commit: '<circle cx="12" cy="12" r="3"/><line x1="3" x2="9" y1="12" y2="12"/><line x1="15" x2="21" y1="12" y2="12"/>',
  chevR: '<path d="m9 18 6-6-6-6"/>',
  chevD: '<path d="m6 9 6 6 6-6"/>',
  chevL: '<path d="m15 18-6-6 6-6"/>',
  folder: '<path d="M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z"/>',
  file: '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/>',
  search: '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',
  searchText: '<path d="M21 6H3"/><path d="M10 12H3"/><path d="M10 18H3"/><circle cx="17" cy="15" r="3"/><path d="m21 19-1.9-1.9"/>',
  refresh: '<path d="M21 12a9 9 0 1 1-9-9c2.52 0 4.93 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/>',
  x: '<path d="M18 6 6 18"/><path d="m6 6 12 12"/>',
  plus: '<path d="M5 12h14"/><path d="M12 5v14"/>',
  folderPlus: '<path d="M12 10v6"/><path d="M9 13h6"/><path d="M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z"/>',
  copy: '<rect width="14" height="14" x="8" y="8" rx="2" ry="2"/><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/>',
  locate: '<circle cx="12" cy="12" r="7"/><circle cx="12" cy="12" r="2"/><line x1="12" x2="12" y1="1" y2="5"/><line x1="12" x2="12" y1="19" y2="23"/><line x1="1" x2="5" y1="12" y2="12"/><line x1="19" x2="23" y1="12" y2="12"/>',
  collapse: '<path d="m7 20 5-5 5 5"/><path d="m7 4 5 5 5-5"/>',
  help: '<circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><path d="M12 17h.01"/>',
  history: '<path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/><path d="M12 7v5l4 2"/>',
  cols: '<rect width="18" height="18" x="3" y="3" rx="2"/><path d="M12 3v18"/>',
  rows: '<rect width="18" height="18" x="3" y="3" rx="2"/><path d="M3 12h18"/>',
  up: '<path d="m5 12 7-7 7 7"/><path d="M12 19V5"/>',
  down: '<path d="M12 5v14"/><path d="m19 12-7 7-7-7"/>',
  open: '<path d="M15 3h6v6"/><path d="M10 14 21 3"/><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>',
  eye: '<path d="M2.06 12.35a1 1 0 0 1 0-.7 10.75 10.75 0 0 1 19.88 0 1 1 0 0 1 0 .7 10.75 10.75 0 0 1-19.88 0"/><circle cx="12" cy="12" r="3"/>',
  fold: '<path d="m7 15 5 5 5-5"/><path d="m7 9 5-5 5 5"/>',
  wrap: '<path d="M3 6h18"/><path d="M3 12h15a3 3 0 1 1 0 6h-4"/><polyline points="16 16 14 18 16 20"/><path d="M3 18h7"/>',
  user: '<path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>',
  tree: '<path d="M21 12h-8"/><path d="M21 6H8"/><path d="M21 18h-8"/><path d="M3 6v4c0 1.1.9 2 2 2h3"/><path d="M3 10v6c0 1.1.9 2 2 2h3"/>',
  save: '<path d="M15.2 3a2 2 0 0 1 1.4.6l3.8 3.8a2 2 0 0 1 .6 1.4V19a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z"/><path d="M17 21v-7a1 1 0 0 0-1-1H8a1 1 0 0 0-1 1v7"/><path d="M7 3v4a1 1 0 0 0 1 1h7"/>',
  alert: '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4"/><path d="M12 17h.01"/>',
  panel: '<rect width="18" height="18" x="3" y="3" rx="2"/><path d="M9 3v18"/>',
  table: '<path d="M12 3v18"/><rect width="18" height="18" x="3" y="3" rx="2"/><path d="M3 9h18"/><path d="M3 15h18"/>',
  undo: '<path d="M9 14 4 9l5-5"/><path d="M4 9h10.5a5.5 5.5 0 0 1 5.5 5.5a5.5 5.5 0 0 1-5.5 5.5H11"/>',
  filter: '<polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"/>',
  tag: '<path d="M12.59 2.59A2 2 0 0 0 11.17 2H4a2 2 0 0 0-2 2v7.17a2 2 0 0 0 .59 1.42l8.7 8.7a2.43 2.43 0 0 0 3.42 0l6.58-6.58a2.43 2.43 0 0 0 0-3.42z"/><circle cx="7.5" cy="7.5" r=".5" fill="currentColor"/>',
  dot: '<circle cx="12" cy="12" r="4" fill="currentColor"/>',
  image: '<rect width="18" height="18" x="3" y="3" rx="2" ry="2"/><circle cx="9" cy="9" r="2"/><path d="m21 15-3.09-3.09a2 2 0 0 0-2.82 0L6 21"/>',
  link: '<path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>',
};
export const icon = (name, cls = '') =>
  `<svg class="ic ${cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${P[name] || ''}</svg>`;

// ======= 파일 종류 표식 — 확장자별 글자 · 색(PyCharm 아이콘 색 계열) =======
const BADGE = {
  py: ['Py', '#5f9ad8'], pyi: ['Py', '#5f9ad8'], ipynb: ['Nb', '#e88f3c'],
  js: ['JS', '#d5b778'], mjs: ['JS', '#d5b778'], cjs: ['JS', '#d5b778'], jsx: ['JX', '#56c2d6'],
  ts: ['TS', '#548af7'], tsx: ['TX', '#56c2d6'], json: ['{}', '#d5b778'], md: ['M↓', '#6fa8dc'],
  html: ['<>', '#e3794b'], htm: ['<>', '#e3794b'], css: ['#', '#7aa6e0'], scss: ['#', '#c77dbb'],
  yml: ['Y', '#c77dbb'], yaml: ['Y', '#c77dbb'], toml: ['T', '#a1a3ab'], ini: ['≡', '#a1a3ab'], cfg: ['≡', '#a1a3ab'],
  sh: ['$', '#73bd79'], bash: ['$', '#73bd79'], txt: ['≡', '#a1a3ab'], log: ['≡', '#a1a3ab'],
  csv: ['▦', '#73bd79'], tsv: ['▦', '#73bd79'], sql: ['DB', '#d5b778'], xml: ['<>', '#e3794b'],
  svg: ['◩', '#e3a35f'], png: ['◩', '#c77dbb'], jpg: ['◩', '#c77dbb'], jpeg: ['◩', '#c77dbb'], gif: ['◩', '#c77dbb'],
  webp: ['◩', '#c77dbb'], env: ['⚙', '#a1a3ab'], lock: ['🔒', '#868a91'], dockerfile: ['🐳', '#548af7'],
};
export function fileBadge(name) {
  const n = (name || '').toLowerCase();
  let key = n.includes('.') ? n.split('.').pop() : n;
  if (n === 'dockerfile') key = 'dockerfile';
  if (n.startsWith('.env')) key = 'env';
  const [t, c] = BADGE[key] || ['', ''];
  if (!t) return `<span class="dv-fb">${icon('file')}</span>`;
  return `<span class="dv-fb dv-fb-t" style="color:${c}">${esc(t)}</span>`;
}
