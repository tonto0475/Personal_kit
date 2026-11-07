// 서버 호출 — 상대 주소(api/…)라 프록시 접두어 아래에서도 동작. 쓰기 요청엔 X-Devview 헤더
import { emit } from './util.js';

export class ApiError extends Error {
  constructor(message, status, data) {
    super(message);
    this.status = status;
    this.data = data;
  }
}

let online = true;
function setOnline(v) {
  if (v === online) return;
  online = v;
  emit('online', v);
}
export const isOnline = () => online;

export async function api(path, { query, body, method } = {}) {
  let url = `api/${path}`;
  if (query) {
    const qs = new URLSearchParams();
    for (const [k, v] of Object.entries(query)) if (v !== undefined && v !== null) qs.set(k, v);
    const s = qs.toString();
    if (s) url += `?${s}`;
  }
  const init = { method: method || (body !== undefined ? 'POST' : 'GET'), cache: 'no-store', headers: {} };
  if (body !== undefined) {
    init.headers['Content-Type'] = 'application/json';
    init.headers['X-Devview'] = '1';
    init.body = JSON.stringify(body);
  }
  let r;
  try {
    r = await fetch(url, init);
  } catch (e) {
    setOnline(false);
    throw new ApiError('서버 연결 실패', 0, null);
  }
  setOnline(true);
  let data = null;
  try { data = await r.json(); } catch { data = null; }
  if (!r.ok) throw new ApiError(data?.error || `HTTP ${r.status}`, r.status, data);
  return data;
}

export const rawUrl = (path) => `api/raw?path=${encodeURIComponent(path)}`;
