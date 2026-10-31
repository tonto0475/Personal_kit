// 문서 — 열린 파일 하나의 디스크 기준(해시) · 저장 상태 · 편집기 연결(Monaco 모델 또는 md 편집기)
// 상태: saved 저장됨 · dirty 저장 안 됨 · saving 저장 중 · failed 저장 실패 · conflict 외부 변경 충돌 · deleted 디스크에서 삭제됨
// 저장 규칙
//   코드: 입력이 멈추고 1초 뒤 자동 저장(공식 IDE 의 afterDelay 와 같은 값) · Ctrl+S 즉시
//   md  : mdview 기준 — 커서가 다른 블록으로 이동 · 포커스 이탈 · Ctrl+S
//   서버가 디스크 해시를 대조 → 다른 곳이 먼저 고쳤으면 409 → conflict(사람이 고름)
import { api } from './api.js';
import { emit, extOf } from './util.js';
import { langOf } from './theme.js';

const AUTOSAVE_MS = 1000;
const docs = new Map();          // 경로 → 문서
let monaco = null;
let mdFactory = null;            // (doc, text) → md 편집기 손잡이 (editor.js 가 제공)

export function initDocs(m, makeMd) {
  monaco = m;
  mdFactory = makeMd;
}

export const getDoc = (path) => docs.get(path);
export const allDocs = () => [...docs.values()];

const IMAGE = new Set(['png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'ico']);
export const isMd = (path) => /\.(md|markdown)$/i.test(path);

export function isDirty(doc) {
  if (!doc || doc.readonly) return false;
  if (doc.kind === 'code') return doc.model.getAlternativeVersionId() !== doc.savedVersion;
  if (doc.kind === 'md') return !doc.md.same(doc.savedDoc);
  return false;
}
export function textOf(doc) {
  if (doc.kind === 'code') return doc.model.getValue(monaco.editor.EndOfLinePreference.LF);
  if (doc.kind === 'md') return doc.md.text();
  return '';
}
export function statusOf(doc) {
  if (doc.status === 'saved' && isDirty(doc)) return 'dirty';
  return doc.status;
}

function changed(doc) {
  emit('doc-status', doc);
}

// ======= 열기 =======
export async function openDoc(path) {
  if (docs.has(path)) return docs.get(path);
  const r = await api('file', { query: { path } });
  if (docs.has(path)) return docs.get(path);          // 기다리는 사이 다른 호출이 먼저 엶
  const doc = { path, status: 'saved', hash: r.hash || null, sig: r.sig, encoding: r.encoding, eol: r.eol || 'LF',
    size: r.size, exec: r.exec, timer: null, saving: false, again: false, disk: null, note: '' };
  if (r.too_large) {
    doc.kind = 'large';
    doc.note = `${(r.size / 1048576).toFixed(1)}MB — 5MB 넘는 파일은 열지 않음`;
  } else if (IMAGE.has(extOf(path))) {
    doc.kind = 'image';
  } else if (r.binary) {
    doc.kind = 'binary';
    doc.note = `바이너리 파일 · ${r.size.toLocaleString()}B`;
  } else if (isMd(path)) {
    doc.kind = 'md';
    doc.md = mdFactory(doc, r.content);
    doc.savedDoc = doc.md.doc();
  } else {
    doc.kind = 'code';
    doc.model = monaco.editor.createModel(r.content, langOf(path), monaco.Uri.from({ scheme: 'file', path: '/' + path }));
    doc.model.setEOL(monaco.editor.EndOfLineSequence.LF);
    doc.savedVersion = doc.model.getAlternativeVersionId();
    doc.model.onDidChangeContent(() => onEdit(doc));
  }
  docs.set(path, doc);
  return doc;
}

// 읽기 전용 문서(특정 리비전의 파일) — 경로 키: rev:<해시>:<경로>
export function openRevDoc(key, path, content, label) {
  if (docs.has(key)) return docs.get(key);
  const doc = { path: key, realPath: path, label, readonly: true, status: 'saved', note: '' };
  if (isMd(path)) {
    doc.kind = 'md';
    doc.md = mdFactory(doc, content, true);
    doc.savedDoc = doc.md.doc();
  } else {
    doc.kind = 'code';
    doc.model = monaco.editor.createModel(content, langOf(path), monaco.Uri.from({ scheme: 'rev', path: '/' + key }));
  }
  docs.set(key, doc);
  return doc;
}

export function closeDoc(doc) {
  clearTimeout(doc.timer);
  if (doc.kind === 'code') doc.model.dispose();
  if (doc.kind === 'md') doc.md.destroy();
  docs.delete(doc.path);
}

// ======= 편집 → 자동 저장 =======
function onEdit(doc) {
  if (doc.suppress) return;
  if (doc.status === 'failed') doc.status = 'saved';
  changed(doc);
  emit('doc-edit', doc);
  if (doc.status === 'saved' && isDirty(doc)) {
    clearTimeout(doc.timer);
    doc.timer = setTimeout(() => save(doc), AUTOSAVE_MS);
  }
}
export function mdEdited(doc) {
  if (doc.status === 'failed') doc.status = 'saved';
  changed(doc);
  emit('doc-edit', doc);
}

// ======= 저장 =======
export async function save(doc, { force = false, manual = false } = {}) {
  if (!doc || doc.readonly || (doc.kind !== 'code' && doc.kind !== 'md')) return;
  clearTimeout(doc.timer);
  if (doc.saving) { doc.again = true; return; }
  if (doc.status === 'conflict' && !force) return;                  // 충돌은 사람이 고름
  if (doc.status === 'deleted' && !force && !manual) return;
  if (!isDirty(doc) && !force && doc.status !== 'deleted') return;
  const content = textOf(doc);
  const mark = doc.kind === 'code' ? doc.model.getAlternativeVersionId() : doc.md.doc();
  const recreate = doc.status === 'deleted';           // 지워진 파일을 지금 내용으로 다시 만듦
  doc.saving = true;
  doc.status = 'saving';
  changed(doc);
  try {
    const r = await api('save', { body: { path: doc.path, content, base: recreate ? null : doc.hash,
      encoding: doc.encoding, eol: doc.eol, force: force || recreate } });
    doc.hash = r.hash;
    doc.sig = r.sig;
    if (doc.kind === 'code') doc.savedVersion = mark; else doc.savedDoc = mark;
    doc.disk = null;
    doc.status = 'saved';
    emit('doc-saved', doc);
  } catch (e) {
    if (e.status === 409 && e.data?.missing) {
      doc.status = 'deleted';
    } else if (e.status === 409) {
      doc.disk = e.data;
      doc.status = 'conflict';
    } else if (e.status === 422 && e.data?.encoding_error) {
      doc.status = 'failed';
      doc.note = e.message;
    } else {
      doc.status = 'failed';
      doc.note = e.message;
    }
  } finally {
    doc.saving = false;
    changed(doc);
    if (doc.status === 'saved' && isDirty(doc)) {
      clearTimeout(doc.timer);
      doc.timer = setTimeout(() => save(doc), doc.again ? 0 : AUTOSAVE_MS);
    }
    doc.again = false;
  }
}

export function saveAll() {
  for (const doc of docs.values()) {
    if (doc.readonly || doc.status === 'conflict') continue;
    if (isDirty(doc) || doc.status === 'failed') save(doc, { manual: true });
  }
}

// ======= 디스크 내용 반영 =======
function replaceText(doc, text) {
  if (doc.kind === 'code') {
    // 앞뒤 공통 부분을 뺀 최소 범위만 교체 — 커서 · 스크롤 유지
    const cur = doc.model.getValue(monaco.editor.EndOfLinePreference.LF);
    if (cur === text) return;
    let a = 0;
    const min = Math.min(cur.length, text.length);
    while (a < min && cur.charCodeAt(a) === text.charCodeAt(a)) a++;
    let b = 0;
    while (b < min - a && cur.charCodeAt(cur.length - 1 - b) === text.charCodeAt(text.length - 1 - b)) b++;
    const from = doc.model.getPositionAt(a);
    const to = doc.model.getPositionAt(cur.length - b);
    doc.model.pushEditOperations([], [{ range: new monaco.Range(from.lineNumber, from.column, to.lineNumber, to.column),
      text: text.slice(a, text.length - b) }], () => null);
  } else if (doc.kind === 'md') {
    doc.md.setText(text);
  }
}

export function applyDisk(doc, disk) {
  doc.suppress = true;
  try { replaceText(doc, disk.content); } finally { doc.suppress = false; }
  if (doc.kind === 'code') doc.savedVersion = doc.model.getAlternativeVersionId(); else doc.savedDoc = doc.md.doc();
  doc.hash = disk.hash;
  if (disk.sig) doc.sig = disk.sig;
  if (disk.encoding) doc.encoding = disk.encoding;
  if (disk.eol) doc.eol = disk.eol;
  doc.disk = null;
  doc.status = 'saved';
  changed(doc);
  emit('doc-reloaded', doc);
}

// 충돌 해결: 디스크 내용 불러오기
export function takeDisk(doc) {
  if (doc.disk && doc.disk.content !== undefined) applyDisk(doc, doc.disk);
}
// 충돌 해결: 내 내용으로 덮어쓰기
export function keepMine(doc) {
  return save(doc, { force: true });
}

// ======= 외부 변경 감지 — 폴링 결과(경로 → "mtime:크기" 또는 null)마다 =======
export async function checkExternal(files) {
  for (const doc of [...docs.values()]) {
    if (doc.readonly || doc.saving || doc.checking || !(doc.path in files)) continue;
    const sig = files[doc.path];
    if (sig === null) {
      if (doc.status !== 'deleted') { doc.status = 'deleted'; clearTimeout(doc.timer); changed(doc); }
      continue;
    }
    if (sig === doc.sig && doc.status !== 'deleted') continue;
    if (doc.kind !== 'code' && doc.kind !== 'md') { doc.sig = sig; emit('doc-reloaded', doc); continue; }
    doc.checking = true;
    try {
      const r = await api('file', { query: { path: doc.path } });
      if (doc.saving) continue;                       // 그사이 저장 시작 — 다음 폴링 때 다시
      doc.sig = r.sig;
      if (r.binary || r.too_large) continue;
      const mine = textOf(doc);
      if (r.hash === doc.hash || r.content === mine) {
        // 내용은 그대로(시각만 바뀜) 또는 디스크가 이미 내 내용과 같음
        doc.hash = r.hash;
        if (r.content === mine) {
          if (doc.kind === 'code') doc.savedVersion = doc.model.getAlternativeVersionId(); else doc.savedDoc = doc.md.doc();
          if (doc.status !== 'saving') doc.status = 'saved';
        } else if (doc.status === 'deleted') {
          doc.status = 'saved';
        }
        changed(doc);
        continue;
      }
      if (!isDirty(doc) && doc.status !== 'conflict') applyDisk(doc, r);        // 손대지 않은 파일 → 최신 내용으로
      else { doc.disk = r; doc.status = 'conflict'; clearTimeout(doc.timer); changed(doc); }   // 고치던 파일 → 사람이 고름
    } catch (err) {
      if (err.status === 404 && doc.status !== 'deleted') { doc.status = 'deleted'; changed(doc); }
    } finally {
      doc.checking = false;
    }
  }
}

// 폴링 대상 경로 목록
export const watchedPaths = () => allDocs().filter((d) => !d.readonly).map((d) => d.path);
