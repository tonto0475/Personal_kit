// 커밋 그래프 — 레인 배정 · 줄마다 SVG. 전제: 자식이 부모보다 먼저 오는 순서(git log --date-order)
// 줄 하나 = 위 반쪽(이전 레인 → 이 줄 가운데) + 아래 반쪽(가운데 → 다음 레인)
//   위: 이 커밋을 기다리던 레인은 커밋 점으로 모이고, 나머지는 그대로 내려옴
//   아래: 커밋 점 → 첫 부모(같은 색 이어 감) · 나머지 부모(이미 기다리는 레인이 있으면 합류, 없으면 새 레인)
//         빠진 레인 자리는 왼쪽으로 당김(사선)
export const LANE_W = 14;
export const COLORS = ['#56a8f5', '#6aab73', '#c77dbb', '#cf8e6d', '#2aacb8', '#b3ae60', '#e88f89', '#8888c6',
  '#73bd79', '#d5b778', '#548af7', '#c94f6d'];

export function newGraph() {
  return { lanes: [], color: 0, max: 1 };
}

// 커밋 묶음을 이어서 배치(더 불러오기 때 상태를 이어 감). 반환: 줄 배열
export function place(g, commits) {
  const out = [];
  for (const c of commits) {
    const prev = g.lanes;
    let col = prev.findIndex((l) => l.h === c.h);
    const tip = col < 0;
    let color;
    if (tip) { col = prev.length; color = g.color++ % COLORS.length; } else color = prev[col].c;
    const top = [];
    for (let j = 0; j < prev.length; j++) {
      top.push(prev[j].h === c.h ? { a: j, b: col, c: prev[j].c } : { a: j, b: j, c: prev[j].c });
    }
    const next = [];
    const from = [];               // next[t] 가 이 줄 가운데 어디서 내려오나
    let nodeAt = -1;
    const putNode = () => {
      if (c.p.length) { nodeAt = next.length; next.push({ h: c.p[0], c: color }); from.push({ x: col, c: color }); }
    };
    let placed = false;
    for (let j = 0; j < prev.length; j++) {
      if (prev[j].h === c.h) {
        if (j === col && !placed) { putNode(); placed = true; }
        continue;
      }
      next.push(prev[j]);
      from.push({ x: j, c: prev[j].c });
    }
    if (!placed) putNode();
    const joins = [];
    let added = 0;
    for (let k = 1; k < c.p.length; k++) {
      const p = c.p[k];
      if (next.some((l) => l.h === p)) { joins.push(p); continue; }
      const pos = nodeAt >= 0 ? nodeAt + 1 + added : next.length;
      const nc = g.color++ % COLORS.length;
      next.splice(pos, 0, { h: p, c: nc });
      from.splice(pos, 0, { x: col, c: nc });
      added++;
    }
    const bot = from.map((f, t) => ({ a: f.x, b: t, c: f.c }));
    for (const p of joins) {
      const t = next.findIndex((l) => l.h === p);
      bot.push({ a: col, b: t, c: next[t].c });
    }
    const w = Math.max(prev.length, next.length, col + 1);
    g.max = Math.max(g.max, w);
    g.lanes = next;
    out.push({ col, color, top, bot, w, merge: c.p.length > 1 });
  }
  return out;
}

const X = (i) => i * LANE_W + LANE_W / 2 + 3;

function seg(x1, y1, x2, y2, color) {
  if (x1 === x2) return `<path d="M${x1} ${y1}V${y2}" stroke="${color}"/>`;
  const ym = (y1 + y2) / 2;
  return `<path d="M${x1} ${y1}C${x1} ${ym} ${x2} ${ym} ${x2} ${y2}" stroke="${color}"/>`;
}

export function rowSvg(r, H, width, isHead) {
  if (!r) return '';
  const mid = H / 2;
  let s = '';
  for (const t of r.top) s += seg(X(t.a), 0, X(t.b), mid, COLORS[t.c]);
  for (const t of r.bot) s += seg(X(t.a), mid, X(t.b), H, COLORS[t.c]);
  const cx = X(r.col);
  const col = COLORS[r.color];
  const node = isHead
    ? `<circle cx="${cx}" cy="${mid}" r="4.6" fill="#1e1f22" stroke="${col}" stroke-width="2.2"/>`
    : `<circle cx="${cx}" cy="${mid}" r="${r.merge ? 3 : 3.8}" fill="${col}"${r.merge ? ` stroke="${col}" stroke-width="1"` : ''}/>`;
  return `<svg class="dv-graph" width="${width}" height="${H}" viewBox="0 0 ${width} ${H}" fill="none" stroke-width="1.7">${s}${node}</svg>`;
}

export const graphWidth = (lanes) => Math.min(lanes, 16) * LANE_W + 6;
