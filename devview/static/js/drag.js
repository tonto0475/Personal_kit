// 끌어서 옮기기 공용 모듈 — 코덱스 허브 · 알림 종처럼 부모(position 기준) 안에 떠 있는 상자
//   위치 = 부모 왼쪽 · 아래에서 잰 거리(left · bottom) — 상자 높이가 바뀌어도(접기 · 펼치기) 아래 끝이 그대로
//   저장 = store[키] = {left, bottom} · 없으면 css 기본 자리 · 창이 줄어 밖으로 나가면 화면 안으로 당겨서 보임(저장값은 그대로)
//   끌기 = 손잡이에서 4px 넘게 움직여야 시작(그 전은 클릭) · 끌고 난 뒤 클릭 1번은 먹음
//   손잡이 안이라도 button · textarea · input · select · a · [data-no-drag] 위에서는 시작 안 함
//   되돌리기 = 손잡이 더블클릭(저장 지움 → css 기본 자리)
import { store } from './util.js';

// 끌기 시작 거리(px)
const THRESH = 4;
// 더블클릭 간격(ms)
const DBL_MS = 400;
// 끌기를 시작하지 않는 칸
const NO_DRAG = 'button, textarea, input, select, a, [data-no-drag]';
// 누른 동안 iframe 이 포인터를 못 가져가게 — 모듈 하나로 끝나게 css 를 여기서 한 번 넣음
document.head.append(Object.assign(document.createElement('style'), { textContent: '.dv-drag-armed iframe { pointer-events: none !important; }' }));

// 상자를 끌어서 옮길 수 있게
// el: 옮길 상자(position: absolute · 부모가 기준) / handle: 잡는 곳 / key: 저장 이름(글 또는 글을 돌려주는 함수 — 상태별 위치를 따로 둘 때)
// opts.keep: () => {top, right, bottom, left} — 상자 밖으로 붙는 것(위로 뜨는 창 등)까지 화면에 남길 여유 px
// opts.onMove: (pos | null) => void — 끌기 · 되돌리기 뒤 알림
// 돌려줌: {apply() 저장값 다시 적용(크기 · 상태가 바뀐 뒤) · reset() 기본 자리로 · pos() 지금 저장값}
export function makeMovable(el, handle, key, opts = {}) {
  // 지금 저장 이름
  const keyOf = () => (typeof key === 'function' ? key() : key);
  // 끌기 상태 — 시작 좌표 · 시작 위치 · 끌기 중 여부
  let drag = null;

  // 부모 안에 들어오게 자른 위치
  // p: {left, bottom}
  function clamp(p) {
    const par = el.offsetParent;
    if (!par) return p;
    const k = opts.keep?.() || {};
    // 소수 폭(글자 폭)이 넘치지 않게 내림
    const r = el.getBoundingClientRect();
    const maxL = Math.floor(par.clientWidth - r.width - (k.right || 0));
    const maxB = Math.floor(par.clientHeight - r.height - (k.top || 0));
    return { left: Math.round(Math.max(k.left || 0, Math.min(p.left, maxL))), bottom: Math.round(Math.max(k.bottom || 0, Math.min(p.bottom, maxB))) };
  }

  // 화면에 놓기 — 저장값이 없으면 inline 을 비워 css 기본 자리 · 끄는 중에는 안 건드림
  function apply() {
    if (drag?.on) return;
    const p = store.get(keyOf(), null);
    if (!p || typeof p.left !== 'number' || typeof p.bottom !== 'number') {
      el.style.left = '';
      el.style.bottom = '';
      el.classList.remove('is-moved');
      return;
    }
    el.classList.add('is-moved');
    // 먼저 저장값 그대로 놓고(크기를 재려면) 자름
    el.style.left = `${p.left}px`;
    el.style.bottom = `${p.bottom}px`;
    const c = clamp(p);
    el.style.left = `${c.left}px`;
    el.style.bottom = `${c.bottom}px`;
  }

  function reset() {
    store.set(keyOf(), null);
    apply();
    opts.onMove?.(null);
  }

  // 직전 누름(시각 · 좌표) — 더블클릭을 직접 셈(손잡이 안 글이 첫 클릭에 다시 그려지면 브라우저 dblclick 이 안 옴)
  let last = null;
  handle.addEventListener('pointerdown', (e) => {
    if (e.button !== 0 || e.target.closest(NO_DRAG)) return;
    const par = el.offsetParent;
    if (!par) return;
    const now = performance.now();
    if (last && now - last.t < DBL_MS && Math.hypot(e.clientX - last.x, e.clientY - last.y) < THRESH) {
      last = null;
      reset();
      return;
    }
    last = { t: now, x: e.clientX, y: e.clientY };
    drag = { x: e.clientX, y: e.clientY, left: el.offsetLeft, bottom: par.clientHeight - el.offsetTop - el.offsetHeight, on: false, id: e.pointerId };
    // 누른 동안 iframe 이 포인터를 못 가져가게(작은 상자에서 첫 움직임이 바로 iframe 위로 나가면 그 뒤 움직임이 iframe 문서로 감)
    //   · 움직임 · 뗌은 window 에서 받음(손잡이 밖으로 나가도) — 잡기(capture)는 클릭 대상을 바꿔서 안 씀
    document.documentElement.classList.add('dv-drag-armed');
    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', end);
    window.addEventListener('pointercancel', end);
  });
  const move = (e) => {
    if (!drag || e.pointerId !== drag.id) return;
    const dx = e.clientX - drag.x;
    const dy = e.clientY - drag.y;
    if (!drag.on) {
      if (Math.hypot(dx, dy) < THRESH) return;
      drag.on = true;
      el.classList.add('is-dragging');
    }
    const c = clamp({ left: drag.left + dx, bottom: drag.bottom - dy });
    el.style.left = `${c.left}px`;
    el.style.bottom = `${c.bottom}px`;
  };
  // 끝 — 끌었으면 저장 · 뒤따르는 클릭 1번 먹음
  const end = (e) => {
    if (!drag || e.pointerId !== drag.id) return;
    const was = drag.on;
    drag = null;
    document.documentElement.classList.remove('dv-drag-armed');
    window.removeEventListener('pointermove', move);
    window.removeEventListener('pointerup', end);
    window.removeEventListener('pointercancel', end);
    if (!was) return;
    el.classList.remove('is-dragging');
    el.classList.add('is-moved');
    const pos = { left: parseFloat(el.style.left) || 0, bottom: parseFloat(el.style.bottom) || 0 };
    store.set(keyOf(), pos);
    // 클릭 먹기 — 클릭은 pointerup 과 같은 차례에 오므로 다음 틱에 풂(클릭이 안 왔으면 그대로 사라짐)
    const eat = (ce) => { ce.stopPropagation(); ce.preventDefault(); };
    handle.addEventListener('click', eat, { capture: true, once: true });
    setTimeout(() => handle.removeEventListener('click', eat, { capture: true }), 0);
    opts.onMove?.(pos);
  };
  window.addEventListener('resize', apply);
  apply();
  return { apply, reset, pos: () => store.get(keyOf(), null) };
}
