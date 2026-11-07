// 줄 단위 diff (Myers) — 편집기 왼쪽 변경 막대 계산용
// 반환 hunk: { o: 옛 시작(0 기준), ol: 옛 줄 수, n: 새 시작(0 기준), nl: 새 줄 수, old: 옛 줄 배열 }
// 앞뒤 공통 줄을 먼저 떼어 내고 가운데만 비교. 편집 거리가 MAX_D 를 넘으면 가운데 전체를 한 덩어리로 처리

const MAX_D = 1500;

export function splitLines(text) {
  return text === '' ? [] : text.split('\n');
}

export function lineDiff(oldText, newText) {
  const a = splitLines(oldText);
  const b = splitLines(newText);
  let pre = 0;
  while (pre < a.length && pre < b.length && a[pre] === b[pre]) pre++;
  let suf = 0;
  while (suf < a.length - pre && suf < b.length - pre && a[a.length - 1 - suf] === b[b.length - 1 - suf]) suf++;
  const A = a.slice(pre, a.length - suf);
  const B = b.slice(pre, b.length - suf);
  if (!A.length && !B.length) return [];
  if (!A.length || !B.length) return [{ o: pre, ol: A.length, n: pre, nl: B.length, old: A }];
  // 줄 → 정수
  const ids = new Map();
  const id = (s) => { let v = ids.get(s); if (v === undefined) { v = ids.size; ids.set(s, v); } return v; };
  const x = Int32Array.from(A, id);
  const y = Int32Array.from(B, id);
  const ops = myers(x, y);
  if (!ops) return [{ o: pre, ol: A.length, n: pre, nl: B.length, old: A }];
  // ops: 'e' 같음 · 'd' 삭제 · 'i' 추가 → 연속된 d/i 를 hunk 로
  const hunks = [];
  let i = 0, j = 0, cur = null;
  for (const op of ops) {
    if (op === 'e') {
      if (cur) { hunks.push(cur); cur = null; }
      i++; j++;
      continue;
    }
    if (!cur) cur = { o: pre + i, ol: 0, n: pre + j, nl: 0, old: [] };
    if (op === 'd') { cur.ol++; cur.old.push(A[i]); i++; } else { cur.nl++; j++; }
  }
  if (cur) hunks.push(cur);
  return hunks;
}

function myers(a, b) {
  const n = a.length, m = b.length;
  const max = n + m;
  const off = max + 1;
  const v = new Int32Array(2 * max + 3);
  const trace = [];
  for (let d = 0; d <= max; d++) {
    if (d > MAX_D) return null;
    // 이번 단계 시작 상태 저장(되짚기용) — 필요한 대각선 [-(d+1), d+1] 만
    trace.push(v.slice(off - d - 1, off + d + 2));
    for (let k = -d; k <= d; k += 2) {
      let xx;
      if (k === -d || (k !== d && v[off + k - 1] < v[off + k + 1])) xx = v[off + k + 1];
      else xx = v[off + k - 1] + 1;
      let yy = xx - k;
      while (xx < n && yy < m && a[xx] === b[yy]) { xx++; yy++; }
      v[off + k] = xx;
      if (xx >= n && yy >= m) return backtrack(trace, n, m);
    }
  }
  return null;
}

function backtrack(trace, n, m) {
  const ops = [];
  let x = n, y = m;
  for (let d = trace.length - 1; d >= 0; d--) {
    const t = trace[d];
    const at = (k) => t[k + d + 1];
    const k = x - y;
    let pk;
    if (k === -d || (k !== d && at(k - 1) < at(k + 1))) pk = k + 1; else pk = k - 1;
    const px = d === 0 ? 0 : at(pk);
    const py = px - pk;
    while (x > px && y > py) { ops.push('e'); x--; y--; }
    if (d > 0) {
      if (x === px) { ops.push('i'); y--; } else { ops.push('d'); x--; }
    }
  }
  while (x > 0 && y > 0) { ops.push('e'); x--; y--; }
  return ops.reverse();
}
