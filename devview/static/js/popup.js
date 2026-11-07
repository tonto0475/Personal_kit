// 팝업 — 목록 고르기(파일 찾기 · 최근 파일 · 구조 · 정의 후보) · 이름 입력 · 오른쪽 클릭 메뉴 · 큰 창(모달)
import { h, esc, emit, icon } from './util.js';

let current = null;              // 열린 팝업 { el, close }

export function closePopups() {
  if (current) current.close();
}
export const popupOpen = () => !!current;

export function overlay(cls = '') {
  closePopups();
  const wrap = h(`<div class="dv-pop-wrap ${cls}"></div>`);
  document.body.append(wrap);
  const prevFocus = document.activeElement;
  const close = (restore = true) => {
    if (current?.el !== wrap) return;
    wrap.remove();
    current = null;
    emit('popup-closed');
    if (restore && prevFocus && document.contains(prevFocus)) prevFocus.focus?.();
  };
  wrap.addEventListener('mousedown', (e) => { if (e.target === wrap) close(); });
  current = { el: wrap, close };
  return { wrap, close };
}

// ======= 목록 고르기 =======
// opts: { title, placeholder, items(q) → 배열 | Promise, render(item, q) → html, onPick(item, ev), hint, value, debounce }
export function pickList(opts) {
  const { wrap, close } = overlay();
  const box = h(`<div class="dv-pop" role="dialog">
    <div class="dv-pop-head"><span class="dv-pop-title">${esc(opts.title || '')}</span><span class="dv-pop-hint">${esc(opts.hint || '')}</span></div>
    <input class="dv-pop-input" spellcheck="false" autocomplete="off" placeholder="${esc(opts.placeholder || '')}">
    <div class="dv-pop-list" role="listbox"></div></div>`);
  wrap.append(box);
  const input = box.querySelector('input');
  const list = box.querySelector('.dv-pop-list');
  let items = [];
  let sel = 0;
  let seq = 0;
  let timer = null;
  let stale = false;               // 입력은 바뀌었는데 목록은 아직 옛것

  function paint() {
    if (!items.length) {
      list.innerHTML = `<div class="dv-pop-empty">${esc(input.value ? '일치 없음' : (opts.empty || '항목 없음'))}</div>`;
      return;
    }
    list.innerHTML = items.map((it, i) => `<div class="dv-pop-item${i === sel ? ' is-sel' : ''}" data-i="${i}">${opts.render(it, input.value)}</div>`).join('');
    list.querySelector('.is-sel')?.scrollIntoView({ block: 'nearest' });
  }
  async function update() {
    const my = ++seq;
    stale = false;
    clearTimeout(timer);
    let r = opts.items(input.value);
    if (r && typeof r.then === 'function') {
      list.classList.add('is-busy');
      try { r = await r; } catch (e) { r = []; }
      list.classList.remove('is-busy');
    }
    if (my !== seq) return;
    items = r || [];
    sel = 0;
    paint();
  }
  function pick(i, ev) {
    const it = items[i];
    if (!it) return;
    close(false);
    opts.onPick(it, ev || {});
  }
  input.addEventListener('input', () => {
    stale = true;
    clearTimeout(timer);
    timer = setTimeout(update, opts.debounce ?? 0);
  });
  input.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp' || e.key === 'PageDown' || e.key === 'PageUp') {
      e.preventDefault();
      const step = e.key.startsWith('Page') ? 10 : 1;
      const d = e.key === 'ArrowDown' || e.key === 'PageDown' ? step : -step;
      if (items.length) sel = (sel + d + items.length) % items.length;
      paint();
    } else if (e.key === 'Enter') {
      e.preventDefault();
      // 빨리 치고 바로 Enter — 목록을 지금 입력 기준으로 먼저 갱신한 뒤 고름
      if (stale) update().then(() => pick(sel, e)); else pick(sel, e);
    } else if (e.key === 'Escape') {
      e.preventDefault();
      e.stopPropagation();
      close();
    }
  });
  list.addEventListener('mousedown', (e) => e.preventDefault());
  list.addEventListener('click', (e) => {
    const it = e.target.closest('[data-i]');
    if (it) pick(Number(it.dataset.i), e);
  });
  list.addEventListener('mousemove', (e) => {
    const it = e.target.closest('[data-i]');
    if (it && Number(it.dataset.i) !== sel) { sel = Number(it.dataset.i); paint(); }
  });
  input.value = opts.value || '';
  input.focus();
  input.select();
  update();
  return { close, refresh: update, input };
}

// ======= 이름 입력 =======
export function promptText({ title, value = '', placeholder = '', hint = '', select = null }) {
  return new Promise((resolve) => {
    const { wrap, close } = overlay();
    const box = h(`<div class="dv-pop dv-pop-small" role="dialog">
      <div class="dv-pop-head"><span class="dv-pop-title">${esc(title)}</span><span class="dv-pop-hint">${esc(hint)}</span></div>
      <input class="dv-pop-input" spellcheck="false" autocomplete="off" placeholder="${esc(placeholder)}"></div>`);
    wrap.append(box);
    const input = box.querySelector('input');
    input.value = value;
    let done = false;
    const finish = (v) => { if (done) return; done = true; close(v === null); resolve(v); };
    input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') { e.preventDefault(); finish(input.value.trim() || null); }
      if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); finish(null); }
    });
    wrap.addEventListener('mousedown', (e) => { if (e.target === wrap) finish(null); });
    input.focus();
    if (select) input.setSelectionRange(select[0], select[1]); else input.select();
  });
}

// ======= 오른쪽 클릭 메뉴 =======
// entries: [{ label, key, act(), disabled }] · '-' = 구분선
export function contextMenu(x, y, entries) {
  const { wrap, close } = overlay('is-clear');
  const menu = h(`<div class="dv-menu" role="menu">${entries.map((e, i) => (e === '-' ? '<div class="dv-menu-sep"></div>'
    : `<div class="dv-menu-item${e.disabled ? ' is-off' : ''}" data-i="${i}">${e.icon ? icon(e.icon) : '<span class="ic"></span>'}<span>${esc(e.label)}</span><kbd>${esc(e.key || '')}</kbd></div>`)).join('')}</div>`);
  wrap.append(menu);
  const r = menu.getBoundingClientRect();
  menu.style.left = `${Math.max(4, Math.min(x, innerWidth - r.width - 4))}px`;
  menu.style.top = `${Math.max(4, Math.min(y, innerHeight - r.height - 4))}px`;
  menu.addEventListener('click', (ev) => {
    const it = ev.target.closest('[data-i]');
    if (!it || it.classList.contains('is-off')) return;
    close(false);
    entries[Number(it.dataset.i)].act();
  });
  wrap.addEventListener('contextmenu', (ev) => { ev.preventDefault(); close(); });
  const onKey = (ev) => { if (ev.key === 'Escape') { close(); document.removeEventListener('keydown', onKey, true); } };
  document.addEventListener('keydown', onKey, true);
}

// ======= 큰 창 =======
export function openModal({ title, body, actions = [], wide = true, onClose }) {
  const { wrap, close } = overlay('is-modal');
  const box = h(`<div class="dv-modal${wide ? ' is-wide' : ''}" role="dialog">
    <div class="dv-modal-head"><span class="dv-pop-title">${esc(title)}</span><span class="dv-modal-acts"></span>
    <button class="dv-ib" data-x title="닫기 (Esc)">${icon('x')}</button></div><div class="dv-modal-body"></div></div>`);
  wrap.append(box);
  box.querySelector('.dv-modal-body').append(body);
  const acts = box.querySelector('.dv-modal-acts');
  const onKey = (ev) => {
    if (ev.key === 'Escape' && current?.el === wrap) { ev.stopPropagation(); done(); }
  };
  const done = () => { document.removeEventListener('keydown', onKey, true); close(); onClose?.(); };
  for (const a of actions) {
    const b = h(`<button class="dv-btn${a.primary ? ' is-primary' : ''}">${esc(a.label)}</button>`);
    b.addEventListener('click', () => { if (a.run() !== false) done(); });
    acts.append(b);
  }
  box.querySelector('[data-x]').addEventListener('click', done);
  document.addEventListener('keydown', onKey, true);
  return { close: done, box };
}
