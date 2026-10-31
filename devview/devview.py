#!/usr/bin/env python3
"""devview — 작업 폴더의 코드 · md · git 이력을 브라우저에서 보고 고치는 서버. 표준 라이브러리만 사용

    python3 devview.py [작업 폴더=현재 폴더] [--host 0.0.0.0] [--port 8701] [--log 로그 경로]

화면(static/)
- 코드 탭: 파일 트리 · Monaco 편집기(PyCharm Dark 색 · 키맵) · md 는 mdview 라이브 프리뷰 편집기
- Git 탭 : 브랜치 그래프 · 커밋 상세 · 파일별 diff · 파일 이력 · 커밋하지 않은 변경
서버
- 파일 저장은 디스크 내용 해시 대조. 다른 곳(공식 IDE · Codex)이 먼저 고쳤으면 409 응답, 덮어쓰기 없음
- 인코딩(UTF-8 · UTF-8 BOM · CP949) · 줄바꿈(LF · CRLF) · 파일 권한은 원래 파일 기준 유지
- git 은 읽기 명령만 실행. GIT_OPTIONAL_LOCKS=0 — 폴링 중 index.lock 미점유(Codex 커밋과 충돌 방지)
- 쓰기 요청(POST)은 X-Devview 헤더 필수 — 다른 사이트에서 보낸 요청 차단
- 경로 규칙: /api/ · /static/ 앞에 프록시 접두어가 붙어 와도 그대로 처리
- 로그: ~/.devview/devview.log  (날짜 시간 | 중요도 | 종류 | 영역 | 내용)
"""
import argparse
import fnmatch
import gzip
import hashlib
import importlib.util
import json
import logging
import logging.handlers
import os
import re
import stat
import subprocess
import sys
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

VERSION = "1.0.0"
HERE = Path(__file__).resolve().parent
STATIC = HERE / "static"

ROOT = None                      # 작업 폴더(절대 경로)
GIT = None                       # Git 저장소 정보
SURVEY = None                    # 설문 도구(survey.py) 모듈 — 찾으면 /sv/ 아래로 연결, 없으면 설문 탭 숨김
LOG = logging.getLogger("devview")

SKIP_DIRS = {".git"}             # 목록에서 제외
LAZY_DIRS = {"node_modules", ".venv", "venv", "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache",
             ".tox", ".cache", ".next", ".nuxt", ".gradle", ".parcel-cache", ".turbo"}   # 펼칠 때만 읽는 폴더
MAX_TREE = 20000                 # 트리 항목 상한
MAX_READ = 5 * 1024 * 1024       # 편집기로 여는 파일 상한
MAX_RAW = 30 * 1024 * 1024       # 그림 등 원본 전송 상한
MAX_SEARCH_FILE = 2 * 1024 * 1024
MAX_HITS = 2000
MAX_STATUS = 5000                # git status 항목 상한
MAX_BODY = 50 * 1024 * 1024
EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"   # git 빈 트리(첫 커밋 · 빈 저장소 비교 기준)
GZIP_MIN = 2048

MIME = {".html": "text/html; charset=utf-8", ".js": "application/javascript; charset=utf-8",
        ".mjs": "application/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
        ".json": "application/json; charset=utf-8", ".map": "application/json; charset=utf-8",
        ".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".gif": "image/gif", ".webp": "image/webp", ".bmp": "image/bmp", ".ico": "image/x-icon",
        ".woff2": "font/woff2", ".woff": "font/woff", ".ttf": "font/ttf", ".txt": "text/plain; charset=utf-8",
        ".pdf": "application/pdf"}
COMPRESSIBLE = (".html", ".js", ".mjs", ".css", ".json", ".map", ".svg", ".txt")

WRITE_LOCK = threading.Lock()
GZ_CACHE = {}                    # (경로, mtime, 크기) → 압축 바이트
GZ_LOCK = threading.Lock()


# ======= 로그 =======
def setup_logging(path):
    # 고정 스키마: 날짜 시간 | 중요도 | 종류 | 영역 | 내용. 기본 위치는 작업 폴더 밖(제출물 오염 방지)
    candidates = [Path(path).expanduser()] if path else [Path.home() / ".devview" / "devview.log",
                                                           Path("/tmp") / "devview" / "devview.log"]
    for p in candidates:
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            h = logging.handlers.RotatingFileHandler(p, maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8")
        except OSError:
            continue
        h.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(kind)s | %(area)s | %(message)s",
                                         "%Y-%m-%d %H:%M:%S"))
        LOG.addHandler(h)
        LOG.setLevel(logging.INFO)
        return p
    LOG.addHandler(logging.NullHandler())
    return None


def log(level, kind, area, msg):
    LOG.log(level, msg, extra={"kind": kind, "area": area})


# ======= 오류 =======
class HttpError(Exception):
    def __init__(self, status, error, **extra):
        super().__init__(error)
        self.status = status
        self.payload = {"error": error, **extra}


class GitError(Exception):
    pass


# ======= 경로 =======
def norm_rel(rel):
    return (rel or "").replace("\\", "/").strip("/")


def safe(rel):
    # 작업 폴더 밖(.. · 밖을 가리키는 심볼릭 링크) 차단. 반환값은 링크를 따라간 실제 경로
    p = (ROOT / norm_rel(rel)).resolve()
    if p != ROOT and ROOT not in p.parents:
        raise HttpError(403, "작업 폴더 밖 경로")
    return p


def rel_of(p):
    r = os.path.relpath(str(p), str(ROOT)).replace(os.sep, "/")
    return "" if r == "." else r


def sig_of(st):
    return f"{st.st_mtime_ns}:{st.st_size}"


def digest(raw):
    # 충돌 판정 기준. mtime 은 같은 시계 틱(수 ms) 안의 연속 쓰기를 구분하지 못함
    return hashlib.sha1(raw).hexdigest()


# ======= 글자 · 인코딩 =======
def decode(raw):
    # 반환: (본문, 인코딩). 본문 None = 바이너리
    if b"\x00" in raw[:8000]:
        return None, "binary"
    if raw.startswith(b"\xef\xbb\xbf"):
        try:
            return raw[3:].decode("utf-8"), "utf-8-sig"
        except UnicodeDecodeError:
            pass
    try:
        return raw.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        pass
    try:
        return raw.decode("cp949"), "cp949"
    except UnicodeDecodeError:
        return None, "binary"


def eol_of(raw):
    return "CRLF" if b"\r\n" in raw else "LF"


def to_lf(text):
    return text.replace("\r\n", "\n")


def text_payload(raw):
    # 편집기용: 본문은 LF 로 통일해 보내고 원래 줄바꿈은 eol 로 전달(저장 때 되돌림)
    text, enc = decode(raw)
    out = {"hash": digest(raw), "encoding": enc, "binary": text is None, "size": len(raw)}
    if text is not None:
        out.update(content=to_lf(text), eol=eol_of(raw))
    return out


# ======= 파일 =======
def is_lazy(name):
    return name in LAZY_DIRS or name.endswith(".egg-info")


def walk(base, deep=True, cap=MAX_TREE):
    # 반환: (항목 목록, 상한 초과 여부). 항목 = {p, d, s, m[, lazy, link]}. deep=False 면 한 단계만
    out = []
    stack = [str(base)]
    while stack:
        d = stack.pop()
        try:
            entries = list(os.scandir(d))
        except OSError:
            continue
        for e in entries:
            if e.name in SKIP_DIRS:
                continue
            try:
                link = e.is_symlink()
                isdir = e.is_dir()
                st = e.stat(follow_symlinks=False)
            except OSError:
                continue
            item = {"p": rel_of(e.path), "d": isdir, "s": st.st_size, "m": st.st_mtime_ns}
            if link:
                item["link"] = True
            if isdir:
                if link or is_lazy(e.name):
                    item["lazy"] = True
                elif deep:
                    stack.append(e.path)
            out.append(item)
            if len(out) >= cap:
                return out, True
    return out, False


def tree_fingerprint():
    # 폴링용 지문 — 경로 · 수정 시각 · 크기. 파일 추가 · 삭제 · 내용 변경을 모두 반영
    h = hashlib.sha1()
    n = 0
    stack = [str(ROOT)]
    while stack:
        d = stack.pop()
        try:
            entries = sorted(os.scandir(d), key=lambda e: e.name)
        except OSError:
            continue
        for e in entries:
            if e.name in SKIP_DIRS:
                continue
            try:
                st = e.stat(follow_symlinks=False)
                isdir = e.is_dir(follow_symlinks=False)
            except OSError:
                continue
            h.update(f"{e.path}\0{st.st_mtime_ns}\0{st.st_size}\n".encode("utf-8", "surrogateescape"))
            n += 1
            if isdir and not is_lazy(e.name):
                stack.append(e.path)
            if n >= MAX_TREE:
                return h.hexdigest()[:16]
    return h.hexdigest()[:16]


def api_tree(q):
    sub = norm_rel(q.get("dir"))
    if sub:
        base = safe(sub)
        if not base.is_dir():
            raise HttpError(404, "폴더 없음")
        entries, truncated = walk(base, deep=False)
    else:
        entries, truncated = walk(ROOT)
    return {"dir": sub, "entries": entries, "truncated": truncated}


def api_file(q):
    p = safe(q.get("path"))
    if not p.is_file():
        raise HttpError(404, "파일 없음", missing=True)
    st = p.stat()
    out = {"path": rel_of(p), "sig": sig_of(st), "size": st.st_size, "mtime": st.st_mtime_ns,
           "exec": bool(st.st_mode & stat.S_IXUSR)}
    if st.st_size > MAX_READ:
        out["too_large"] = True
        return out
    out.update(text_payload(p.read_bytes()))
    return out


def write_atomic(p, data):
    # 임시 파일에 쓰고 교체 — 읽는 쪽(공식 IDE · Codex)이 반쯤 쓴 파일을 보지 않게. 원래 권한 유지
    mode = None
    try:
        mode = stat.S_IMODE(os.stat(p).st_mode)
    except FileNotFoundError:
        pass
    tmp = p.with_name(f".{p.name}.devview-{os.getpid()}-{threading.get_ident()}.tmp")
    try:
        with open(tmp, "wb") as f:
            f.write(data)
        if mode is not None:
            os.chmod(tmp, mode)
        os.replace(tmp, p)
    finally:
        if tmp.exists():
            tmp.unlink()


def api_save(b):
    rel = norm_rel(b.get("path"))
    p = safe(rel)
    if p.is_dir():
        raise HttpError(400, "폴더는 저장할 수 없음")
    enc = b.get("encoding") or "utf-8"
    if enc not in ("utf-8", "utf-8-sig", "cp949"):
        raise HttpError(400, f"저장할 수 없는 인코딩 ({enc})")
    content = to_lf(b.get("content") or "")
    eol = "CRLF" if b.get("eol") == "CRLF" else "LF"
    base = b.get("base")
    force = bool(b.get("force"))
    with WRITE_LOCK:
        exists = p.is_file()
        if not force and base:
            if not exists:
                raise HttpError(409, "디스크에서 삭제됨", missing=True)
            raw = p.read_bytes()
            cur = digest(raw)
            if cur != base:
                disk = text_payload(raw)
                if disk.get("content") != content:
                    log(logging.INFO, "충돌", "파일", f"{rel} 외부 변경 감지 (기준 {base[:8]} · 현재 {cur[:8]})")
                    raise HttpError(409, "외부 변경", conflict=True, sig=sig_of(p.stat()), **disk)
                # 디스크가 이미 같은 내용 — 쓰지 않고 기준만 맞춤
                return {"path": rel, "hash": cur, "sig": sig_of(p.stat()), "unchanged": True}
        text = content.replace("\n", "\r\n") if eol == "CRLF" else content
        try:
            data = b"\xef\xbb\xbf" + text.encode("utf-8") if enc == "utf-8-sig" else text.encode(enc)
        except UnicodeEncodeError as e:
            bad = text[e.start:e.end]
            raise HttpError(422, f"{enc.upper()} 로 저장할 수 없는 글자 «{bad}»", encoding_error=True)
        p.parent.mkdir(parents=True, exist_ok=True)
        write_atomic(p, data)
        st = p.stat()
    log(logging.INFO, "저장", "파일", f"{rel} {len(data)}B {enc} {eol}{' (강제)' if force else ''}")
    return {"path": rel, "hash": digest(data), "sig": sig_of(st), "size": st.st_size}


def api_create(b):
    rel = norm_rel(b.get("path"))
    if not rel:
        raise HttpError(400, "이름 없음")
    p = safe(rel)
    if p.exists():
        raise HttpError(409, "이미 있음")
    if b.get("dir"):
        p.mkdir(parents=True)
    else:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.touch()
    log(logging.INFO, "생성", "파일", f"{'폴더' if b.get('dir') else '파일'} {rel}")
    st = p.stat()
    return {"path": rel, "sig": sig_of(st), "hash": None if b.get("dir") else digest(b"")}


# 화면 캡처 저장 — 브라우저가 그린 PNG(base64)를 작업 폴더 docs/captures/날짜_시각_보기.png 로
#   Codex · Claude 가 그 파일을 바로 열어 화면을 본다
def api_capture(b):
    import base64
    try:
        data = base64.b64decode(b.get("png") or "", validate=True)
    except ValueError:
        raise HttpError(400, "그림 자료가 깨짐")
    if not data.startswith(b"\x89PNG"):
        raise HttpError(400, "PNG 아님")
    view = re.sub(r"[^0-9A-Za-z_-]", "", str(b.get("view") or "")) or "screen"
    folder = ROOT / "docs" / "captures"
    folder.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    p = folder / f"{stamp}_{view}.png"
    n = 1
    while p.exists():
        n += 1
        p = folder / f"{stamp}_{view}_{n}.png"
    p.write_bytes(data)
    rel = p.relative_to(ROOT).as_posix()
    log(logging.INFO, "캡처", "파일", f"{rel} {len(data)}B")
    return {"path": rel, "abs": str(p), "bytes": len(data)}


def api_raw(q):
    p = safe(q.get("path"))
    if not p.is_file():
        raise HttpError(404, "파일 없음")
    if p.stat().st_size > MAX_RAW:
        raise HttpError(413, "파일이 너무 큼")
    return p


# ======= 검색 · 정의 찾기 =======
def candidate_files():
    # 검색 대상: git 이 아는 파일(추적 + 무시 안 된 새 파일). git 이 아니면 폴더를 훑되 무거운 폴더 제외
    if GIT and GIT.ok:
        try:
            out = GIT.run(["ls-files", "-z", "--cached", "--others", "--exclude-standard"])
            seen = set()
            files = []
            for gp in out.decode("utf-8", "replace").split("\0"):
                local = GIT.to_local(gp)
                if not local or local in seen:
                    continue
                seen.add(local)
                files.append(local)
            return files
        except GitError:
            pass
    files = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not is_lazy(d))
        for name in sorted(filenames):
            files.append(rel_of(os.path.join(dirpath, name)))
            if len(files) >= MAX_TREE:
                return files
    return files


def glob_filter(patterns):
    # 파일 이름 걸러 내기: "*.py, !tests/*" — ! 는 제외
    inc =[x.strip() for x in patterns.split(",") if x.strip() and not x.strip().startswith("!")]
    exc = [x.strip()[1:] for x in patterns.split(",") if x.strip().startswith("!")]

    def ok(path):
        name = path.rsplit("/", 1)[-1]
        if inc and not any(fnmatch.fnmatch(path, g) or fnmatch.fnmatch(name, g) for g in inc):
            return False
        return not any(fnmatch.fnmatch(path, g) or fnmatch.fnmatch(name, g) for g in exc)
    return ok


def read_text(local):
    p = ROOT / local
    try:
        if not p.is_file() or p.stat().st_size > MAX_SEARCH_FILE:
            return None
        raw = p.read_bytes()
    except OSError:
        return None
    text, _ = decode(raw)
    return to_lf(text) if text is not None else None


def api_search(q):
    query = q.get("q") or ""
    if not query:
        return {"hits": [], "files": 0, "scanned": 0}
    flags = 0 if q.get("case") == "1" else re.IGNORECASE
    pat = query if q.get("regex") == "1" else re.escape(query)
    if q.get("word") == "1":
        pat = rf"(?<![\w]){pat}(?![\w])"
    try:
        rx = re.compile(pat, flags)
    except re.error as e:
        raise HttpError(400, f"정규식 오류: {e}")
    ok = glob_filter(q.get("glob") or "")
    hits, files, scanned = [], 0, 0
    for local in candidate_files():
        if not ok(local):
            continue
        text = read_text(local)
        if text is None:
            continue
        scanned += 1
        found = False
        for n, line in enumerate(text.split("\n"), 1):
            m = rx.search(line)
            if not m:
                continue
            found = True
            hits.append({"p": local, "n": n, "c": m.start(), "e": m.end(), "t": line[:500]})
            if len(hits) >= MAX_HITS:
                return {"hits": hits, "files": files + 1, "scanned": scanned, "truncated": True}
        files += found
    return {"hits": hits, "files": files, "scanned": scanned}


SYM_EXT = {".py", ".pyi", ".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx", ".sh"}


def api_symbols(q):
    # 이름으로 정의 위치 찾기(정규식 기반). 순위: 0 def · class · function / 1 대입 · 상수 / 2 import
    name = q.get("name") or ""
    if not re.fullmatch(r"[A-Za-z_$][\w$]*", name):
        return {"hits": []}
    n = re.escape(name)
    rules = [
        (0, re.compile(rf"^\s*(?:async\s+)?def\s+{n}\b")),
        (0, re.compile(rf"^\s*class\s+{n}\b")),
        (0, re.compile(rf"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s*\*?\s*{n}\b")),
        (0, re.compile(rf"^\s*(?:export\s+)?(?:default\s+)?class\s+{n}\b")),
        (0, re.compile(rf"^\s*(?:function\s+)?{n}\s*\(\)\s*\{{")),              # 셸 함수
        (1, re.compile(rf"^\s*(?:export\s+)?(?:const|let|var)\s+{n}\b")),
        (1, re.compile(rf"^\s*{n}\s*(?::[^=]+)?=(?!=)")),
        (1, re.compile(rf"^\s*(?:static\s+|async\s+|get\s+|set\s+)*{n}\s*\([^)]*\)\s*\{{")),   # JS 메서드
        (2, re.compile(rf"^\s*(?:from\s+\S+\s+)?import\s+.*\b{n}\b")),
    ]
    hits = []
    for local in candidate_files():
        if os.path.splitext(local)[1].lower() not in SYM_EXT:
            continue
        text = read_text(local)
        if text is None or name not in text:
            continue
        for i, line in enumerate(text.split("\n"), 1):
            if name not in line:
                continue
            for rank, rx in rules:
                if rx.search(line):
                    hits.append({"p": local, "n": i, "c": line.find(name), "t": line.strip()[:300], "r": rank})
                    break
            if len(hits) >= 300:
                break
    hits.sort(key=lambda h: (h["r"], h["p"], h["n"]))
    return {"hits": hits}


# ======= git =======
LOG_FMT = "%H%x1f%P%x1f%an%x1f%ae%x1f%at%x1f%cn%x1f%ct%x1f%s"
SHOW_FMT = "%H%x1f%P%x1f%an%x1f%ae%x1f%at%x1f%cn%x1f%ce%x1f%ct%x1f%B"
HEX_RE = re.compile(r"^[0-9a-fA-F]{4,64}$")


class Git:
    def __init__(self, root):
        self.root = root
        self.ok = False
        self.top = None
        self.prefix = ""
        self.error = None
        self.safe_all = False         # 소유자가 다른 저장소(dubious ownership) 우회 여부
        try:
            top = self.run(["rev-parse", "--show-toplevel"], cwd=root).decode("utf-8", "replace").strip()
        except GitError as e:
            self.error = str(e)
            return
        self.ok = True
        self.top = Path(top).resolve()
        rel = os.path.relpath(str(root), str(self.top)).replace(os.sep, "/")
        self.prefix = "" if rel == "." else rel

    def run(self, args, cwd=None, check=True, timeout=30):
        cmd = ["git"] + (["-c", "safe.directory=*"] if self.safe_all else []) + [
            "-c", "core.quotepath=off", "-c", "color.ui=never", "-c", "i18n.logOutputEncoding=UTF-8",
            "-c", "log.showSignature=false", "--no-pager"] + args
        env = dict(os.environ, GIT_OPTIONAL_LOCKS="0", GIT_TERMINAL_PROMPT="0", GIT_PAGER="cat")
        try:
            r = subprocess.run(cmd, cwd=str(cwd or self.top or self.root), capture_output=True, timeout=timeout, env=env)
        except FileNotFoundError:
            raise GitError("git 명령 없음")
        except subprocess.TimeoutExpired:
            log(logging.WARNING, "응답 없음", "git", f"{timeout}초 초과: git {' '.join(args[:4])}")
            raise GitError(f"git 응답 없음 ({timeout}초): {' '.join(args[:2])}")
        if r.returncode != 0 and check:
            err = r.stderr.decode("utf-8", "replace").strip()
            if "dubious ownership" in err and not self.safe_all:
                log(logging.WARNING, "소유자 불일치", "git", "safe.directory=* 로 다시 실행")
                self.safe_all = True
                return self.run(args, cwd, check, timeout)
            raise GitError(err or f"git 실패 (코드 {r.returncode})")
        return r.stdout

    def text(self, args, **kw):
        return self.run(args, **kw).decode("utf-8", "replace")

    def to_local(self, gp):
        # 저장소 기준 경로 → 작업 폴더 기준 경로(작업 폴더 밖이면 None)
        if not gp:
            return None
        if not self.prefix:
            return gp
        return gp[len(self.prefix) + 1:] if gp.startswith(self.prefix + "/") else None

    def to_git(self, local):
        local = norm_rel(local)
        return f"{self.prefix}/{local}" if self.prefix else local

    def head(self):
        try:
            return self.text(["rev-parse", "--verify", "-q", "HEAD"]).strip() or None
        except GitError:
            return None

    def branch(self):
        try:
            b = self.text(["symbolic-ref", "-q", "--short", "HEAD"], check=False).strip()
            return b or None
        except GitError:
            return None

    def refs(self):
        # 반환: [{name(전체), short, type, hash(커밋)}] — 주석 태그는 가리키는 커밋으로 풀어서
        out = self.text(["for-each-ref", "--format=%(refname)%00%(objectname)%00%(*objectname)",
                         "refs/heads", "refs/remotes", "refs/tags"])
        refs = []
        for line in out.splitlines():
            parts = line.split("\0")
            if len(parts) < 3:
                continue
            name, obj, peeled = parts
            if name.endswith("/HEAD") and name.startswith("refs/remotes/"):
                continue
            if name.startswith("refs/heads/"):
                kind, short = "branch", name[11:]
            elif name.startswith("refs/remotes/"):
                kind, short = "remote", name[13:]
            else:
                kind, short = "tag", name[10:]
            refs.append({"name": name, "short": short, "type": kind, "hash": peeled or obj})
        return refs


def need_git():
    if not (GIT and GIT.ok):
        raise HttpError(409, "git 저장소 아님", nogit=True, detail=GIT.error if GIT else None)


def valid_rev(r):
    # 옵션 주입 방지: 해시 · HEAD · 실제 ref 이름만 허용
    if not r:
        raise HttpError(400, "리비전 없음")
    if r == "HEAD" or HEX_RE.match(r):
        return r
    if not r.startswith("-") and any(x["short"] == r or x["name"] == r for x in GIT.refs()):
        return r
    raise HttpError(400, f"알 수 없는 리비전 ({r[:40]})")


def parse_commits(out):
    commits = []
    for rec in out.split("\0"):
        rec = rec.strip("\n")
        if not rec:
            continue
        f = rec.split("\x1f")
        if len(f) < 8:
            continue
        commits.append({"h": f[0], "p": f[1].split() if f[1] else [], "an": f[2], "ae": f[3], "at": int(f[4] or 0),
                        "cn": f[5], "ct": int(f[6] or 0), "s": f[7]})
    return commits


def api_git_info(q):
    if not (GIT and GIT.ok):
        return {"repo": False, "error": GIT.error if GIT else "git 없음"}
    return {"repo": True, "top": str(GIT.top), "prefix": GIT.prefix, "head": GIT.head(), "branch": GIT.branch(),
            "refs": GIT.refs()}


def api_git_log(q):
    need_git()
    skip = max(0, int(q.get("skip") or 0))
    limit = min(max(1, int(q.get("limit") or 300)), 3000)
    ref = q.get("ref") or "all"
    args = ["log", "-z", f"--format={LOG_FMT}", "--date-order", f"--skip={skip}", f"-n{limit}"]
    if ref == "all":
        revs = ["--branches", "--tags", "--remotes", "HEAD"]
    elif ref == "head":
        revs = ["HEAD"]
    else:
        revs = [valid_rev(ref)]
    try:
        out = GIT.text(args + revs + ["--"])
    except GitError as e:
        msg = str(e)
        if "does not have any commits" in msg or "unknown revision" in msg or "bad revision" in msg:
            if ref == "all":            # HEAD 가 아직 없는 저장소 — 브랜치만으로 다시
                try:
                    out = GIT.text(args + ["--branches", "--tags", "--remotes", "--"])
                except GitError:
                    out = ""
            else:
                out = ""
        else:
            raise
    commits = parse_commits(out)
    return {"commits": commits, "skip": skip, "more": len(commits) == limit, "head": GIT.head()}


def parse_name_status(raw):
    toks = raw.decode("utf-8", "replace").split("\0")
    out, i = [], 0
    while i < len(toks):
        st = toks[i]
        if not st:
            i += 1
            continue
        if st[0] in "RC" and i + 2 < len(toks):
            out.append({"st": st[0], "score": st[1:], "old": toks[i + 1], "path": toks[i + 2]})
            i += 3
        elif i + 1 < len(toks):
            out.append({"st": st[0], "path": toks[i + 1]})
            i += 2
        else:
            break
    return out


def parse_numstat(raw):
    # -z 형식: "추가\t삭제\t경로\0" · 이름 변경은 "추가\t삭제\t\0옛 경로\0새 경로\0"
    toks = raw.decode("utf-8", "replace").split("\0")
    out, i = {}, 0
    while i < len(toks):
        t = toks[i]
        if not t:
            i += 1
            continue
        parts = t.split("\t")
        if len(parts) < 3:
            i += 1
            continue
        a, d, path = parts[0], parts[1], parts[2]
        if path == "" and i + 2 < len(toks):
            path = toks[i + 2]
            i += 3
        else:
            i += 1
        out[path] = (None if a == "-" else int(a), None if d == "-" else int(d))
    return out


def changed_files(base, target):
    # base None = 빈 트리(첫 커밋), target None = 작업 트리(커밋 안 한 변경, 스테이징 포함)
    a = base or EMPTY_TREE
    common = ["diff", "--no-ext-diff", "--no-textconv", "-z", "-M"]
    revs = [a] if target is None else [a, target]
    ns = parse_name_status(GIT.run(common + ["--name-status"] + revs + ["--"]))
    num = parse_numstat(GIT.run(common + ["--numstat"] + revs + ["--"]))
    files = []
    for f in ns:
        add, dele = num.get(f["path"], (0, 0))
        f.update(add=add, dele=dele, binary=add is None, local=GIT.to_local(f["path"]))
        if f.get("old"):
            f["old_local"] = GIT.to_local(f["old"])
        files.append(f)
    return files


def api_git_commit(q):
    need_git()
    h = valid_rev(q.get("h"))
    f = GIT.text(["show", "-s", f"--format={SHOW_FMT}", h, "--"]).split("\x1f", 8)
    if len(f) < 9:
        raise HttpError(404, "커밋 없음")
    parents = f[1].split() if f[1] else []
    pi = min(max(0, int(q.get("parent") or 0)), max(0, len(parents) - 1))
    base = parents[pi] if parents else None
    return {"h": f[0], "p": parents, "an": f[2], "ae": f[3], "at": int(f[4] or 0), "cn": f[5], "ce": f[6],
            "ct": int(f[7] or 0), "msg": f[8].rstrip("\n"), "base": base, "parent": pi,
            "files": changed_files(base, h)}


def parse_status(raw):
    toks = raw.decode("utf-8", "replace").split("\0")
    branch_line = None
    items, i = [], 0
    while i < len(toks):
        t = toks[i]
        i += 1
        if not t:
            continue
        if t.startswith("## "):
            branch_line = t[3:]
            continue
        if len(t) < 4:
            continue
        x, y, path = t[0], t[1], t[3:]
        item = {"x": x, "y": y, "path": path, "local": GIT.to_local(path.rstrip("/"))}
        if x in "RC" or y in "RC":
            if i < len(toks):
                item["old"] = toks[i]
                i += 1
        items.append(item)
    return branch_line, items


def api_git_status(q):
    need_git()
    raw = GIT.run(["status", "--porcelain=v1", "-z", "-b", "-uall"])
    branch_line, items = parse_status(raw)
    # 무시된 항목: 통째로 무시된 폴더는 «폴더/» 한 줄로(node_modules 같은 큰 폴더를 훑지 않게)
    try:
        ign = GIT.run(["ls-files", "-z", "--others", "--ignored", "--exclude-standard", "--directory"])
        for gp in ign.decode("utf-8", "replace").split("\0")[:MAX_STATUS]:
            if gp:
                items.append({"x": "!", "y": "!", "path": gp, "local": GIT.to_local(gp.rstrip("/"))})
    except GitError as e:
        log(logging.WARNING, "실패", "git", f"무시 목록: {e}")
    truncated = len(items) > MAX_STATUS
    head = GIT.head()
    changes = []
    try:
        changes = changed_files(head, None)
    except GitError as e:
        log(logging.WARNING, "실패", "git", f"작업 트리 diff: {e}")
    known = {c["path"] for c in changes}
    for it in items:
        if it["x"] == "?" and it["path"] not in known:
            p = ROOT / it["local"] if it["local"] else None
            lines = None
            if p and p.is_file() and p.stat().st_size <= MAX_SEARCH_FILE:
                t = read_text(it["local"])
                lines = None if t is None else (t.count("\n") + (0 if t.endswith("\n") or not t else 1))
            changes.append({"st": "U", "path": it["path"], "local": it["local"], "add": lines, "dele": 0,
                            "binary": lines is None})
    ahead = behind = 0
    m = re.search(r"\[(?:ahead (\d+))?(?:, )?(?:behind (\d+))?\]", branch_line or "")
    if m:
        ahead, behind = int(m.group(1) or 0), int(m.group(2) or 0)
    return {"head": head, "branch": GIT.branch(), "branch_line": branch_line, "ahead": ahead, "behind": behind,
            "items": items[:MAX_STATUS], "truncated": truncated, "changes": changes}


def api_git_blob(q):
    need_git()
    rev = q.get("rev") or "HEAD"
    if rev != ":":                       # ":" = 인덱스(스테이징 영역)
        rev = valid_rev(rev)
    gp = q.get("gpath") or GIT.to_git(q.get("path") or "")
    if not gp or "\0" in gp:
        raise HttpError(400, "경로 없음")
    spec = f"{rev}:{gp}" if rev != ":" else f":{gp}"
    try:
        size = int(GIT.text(["cat-file", "-s", spec]).strip())
    except GitError:
        return {"missing": True, "rev": rev, "gpath": gp}
    if size > MAX_READ:
        return {"too_large": True, "size": size, "rev": rev, "gpath": gp}
    out = text_payload(GIT.run(["cat-file", "blob", spec]))
    out.update(rev=rev, gpath=gp)
    return out


def api_git_file_log(q):
    need_git()
    gp = q.get("gpath") or GIT.to_git(q.get("path") or "")
    if not gp:
        raise HttpError(400, "경로 없음")
    limit = min(max(1, int(q.get("limit") or 500)), 3000)
    try:
        out = GIT.text(["log", "--follow", "-M", f"-n{limit}", "--name-status", f"--format=%x1e{LOG_FMT}", "--", gp])
    except GitError as e:
        if "does not have any commits" in str(e):
            return {"commits": [], "gpath": gp}
        raise
    commits = []
    for chunk in out.split("\x1e")[1:]:
        lines = chunk.split("\n")
        c = parse_commits(lines[0])
        if not c:
            continue
        c = c[0]
        for ln in lines[1:]:
            parts = ln.split("\t")
            if len(parts) < 2 or not parts[0]:
                continue
            c["fst"] = parts[0][0]
            if parts[0][0] in "RC" and len(parts) >= 3:
                c["fold"], c["fpath"] = parts[1], parts[2]
            else:
                c["fpath"] = parts[-1]
        commits.append(c)
    return {"commits": commits, "gpath": gp}


def api_git_blame(q):
    need_git()
    local = norm_rel(q.get("path"))
    p = safe(local)
    if not p.is_file():
        raise HttpError(404, "파일 없음")
    if p.stat().st_size > MAX_SEARCH_FILE:
        return {"too_large": True}
    try:
        out = GIT.run(["blame", "--porcelain", "--", GIT.to_git(local)])
    except GitError as e:
        msg = str(e)
        if "no such path" in msg or "no such ref" in msg or "does not have any commits" in msg:
            return {"untracked": True}
        raise
    commits, lines = {}, []
    cur = None
    for raw in out.split(b"\n"):
        if raw.startswith(b"\t"):
            lines.append(cur)
            continue
        line = raw.decode("utf-8", "replace")
        parts = line.split(" ")
        if len(parts) >= 3 and len(parts[0]) == 40 and HEX_RE.match(parts[0]):
            cur = parts[0]
            commits.setdefault(cur, {})
            continue
        if cur is None:
            continue
        key, _, val = line.partition(" ")
        info = commits[cur]
        if key == "author":
            info["an"] = val
        elif key == "author-time":
            info["at"] = int(val or 0)
        elif key == "summary":
            info["s"] = val
    return {"commits": commits, "lines": lines, "head": GIT.head()}


def api_git_sig():
    # 폴링용: HEAD · ref 목록 · 인덱스 변경 지문
    if not (GIT and GIT.ok):
        return None
    try:
        head = GIT.head() or ""
        refs = GIT.text(["for-each-ref", "--format=%(objectname) %(refname)", "refs/heads", "refs/remotes", "refs/tags"])
        idx = GIT.text(["rev-parse", "--git-path", "index"]).strip()
        ip = Path(idx) if os.path.isabs(idx) else GIT.top / idx
        try:
            ist = ip.stat()
            istamp = f"{ist.st_mtime_ns}:{ist.st_size}"
        except OSError:
            istamp = ""
    except GitError:
        return None
    return hashlib.sha1(f"{head}\n{refs}\n{istamp}".encode()).hexdigest()[:16]


# ======= 폴링 · 정보 =======
def api_poll(q):
    files = {}
    for rel in (q.get("paths") or "").split("\n"):
        rel = norm_rel(rel)
        if not rel:
            continue
        try:
            p = safe(rel)
            st = p.stat()
            files[rel] = sig_of(st) if p.is_file() else None
        except (OSError, HttpError):
            files[rel] = None
    return {"tree": tree_fingerprint(), "files": files, "git": api_git_sig(), "t": time.time()}


def api_info(q):
    return {"version": VERSION, "root": str(ROOT), "name": ROOT.name or str(ROOT), "pid": os.getpid(),
            "python": sys.version.split()[0], "git": api_git_info(q), "survey": SURVEY is not None}


# ======= 설문 도구 연결 =======
# 설문 도구(survey.py) 불러오기 — 지정값 → 작업 폴더 · 키트(devview 옆) · 로컬 Claude 스킬 순. 화면 · 저장은 그 파일이 맡음
def load_survey(given):
    cands = ([Path(given).expanduser()] if given else []) + [
        ROOT / ".agents" / "skills" / "survey" / "survey.py",
        HERE.parent / ".agents" / "skills" / "survey" / "survey.py",
        Path.home() / ".codex" / "skills" / "survey" / "survey.py",
        HERE.parent / "skills_src" / "skills" / "survey" / "survey.py",
        Path.home() / ".claude" / "skills" / "adr-survey" / "survey.py"]
    for p in cands:
        if not p.is_file():
            continue
        try:
            spec = importlib.util.spec_from_file_location("devview_survey", p)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
        except Exception as e:
            log(logging.WARNING, "실패", "설문", f"불러오기 {p}: {e}")
            continue
        # 작업 폴더의 docs/surveys 는 등록 목록에 없어도 늘 보임
        mod.EXTRA_STORES.append(ROOT / "docs" / "surveys")
        log(logging.INFO, "연결", "설문", str(p))
        return mod
    return None


# ======= 보던 상태(탭 · 열린 파일 · 보기) =======
# 대회 Browser 도구는 다른 도구에서 돌아올 때 빈 저장소로 페이지를 새로 연다 → 화면 저장값을 서버에도 둔다
#   ~/.devview/state.json = { ns(작업 폴더별 접두어): { 키: JSON 문자열 } } — 작업 폴더 밖(제출물에 안 섞임)
STATE = Path.home() / ".devview" / "state.json"
MAX_STATE = 512 * 1024


def read_state():
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def api_state_get(q):
    return {"data": read_state().get(q.get("ns") or "", {})}


def api_state_post(b):
    ns, data = b.get("ns"), b.get("data")
    if not isinstance(ns, str) or not ns or not isinstance(data, dict) \
            or not all(isinstance(k, str) and isinstance(v, str) for k, v in data.items()):
        raise HttpError(400, "형식은 {ns: 문자열, data: {키: 문자열}}")
    raw = json.dumps(data, ensure_ascii=False)
    if len(raw) > MAX_STATE:
        raise HttpError(413, "보던 상태가 너무 큼")
    with WRITE_LOCK:
        allst = read_state()
        allst[ns] = data
        STATE.parent.mkdir(parents=True, exist_ok=True)
        write_atomic(STATE, json.dumps(allst, ensure_ascii=False).encode("utf-8"))
    return {"ok": True, "keys": len(data)}


GET_ROUTES = {"info": api_info, "tree": api_tree, "file": api_file, "search": api_search, "symbols": api_symbols,
              "poll": api_poll, "git/info": api_git_info, "git/log": api_git_log, "git/commit": api_git_commit,
              "git/status": api_git_status, "git/blob": api_git_blob, "git/file-log": api_git_file_log,
              "git/blame": api_git_blame, "state": api_state_get}
POST_ROUTES = {"save": api_save, "create": api_create, "capture": api_capture, "state": api_state_post}


# ======= HTTP =======
class Handler(BaseHTTPRequestHandler):
    server_version = f"devview/{VERSION}"
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def do_GET(self):
        self.dispatch("GET")

    def do_POST(self):
        self.dispatch("POST")

    def wants_gzip(self):
        return "gzip" in (self.headers.get("Accept-Encoding") or "")

    def send_bytes(self, code, data, ctype, headers=None, cache_key=None):
        if len(data) >= GZIP_MIN and self.wants_gzip() and (ctype.startswith(("text/", "application/javascript",
                                                                                 "application/json", "image/svg"))):
            if cache_key:
                with GZ_LOCK:
                    z = GZ_CACHE.get(cache_key)
                if z is None:
                    z = gzip.compress(data, 6)
                    with GZ_LOCK:
                        if len(GZ_CACHE) > 400:
                            GZ_CACHE.clear()
                        GZ_CACHE[cache_key] = z
            else:
                z = gzip.compress(data, 5)
            data = z
            headers = dict(headers or {}, **{"Content-Encoding": "gzip", "Vary": "Accept-Encoding"})
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def json(self, code, obj):
        data = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_bytes(code, data, "application/json; charset=utf-8", {"Cache-Control": "no-store"})

    def static(self, rel):
        p = (STATIC / rel).resolve()
        if p != STATIC and STATIC not in p.parents or not p.is_file():
            raise HttpError(404, "없음")
        st = p.stat()
        etag = f'"{st.st_mtime_ns:x}-{st.st_size:x}"'
        if self.headers.get("If-None-Match") == etag:
            self.send_response(304)
            self.send_header("ETag", etag)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        # 판 갱신이 바로 반영되게 no-cache(ES 모듈 캐시 함정). 바뀌지 않았으면 304 라 손해 없음
        self.send_bytes(200, p.read_bytes(), MIME.get(p.suffix.lower(), "application/octet-stream"),
                        {"ETag": etag, "Cache-Control": "no-cache"}, cache_key=(str(p), st.st_mtime_ns, st.st_size))

    def dispatch(self, method):
        u = urlparse(self.path)
        path = u.path
        q = {k: v[-1] for k, v in parse_qs(u.query, keep_blank_values=True).items()}
        try:
            raw_body = b""
            if method == "POST":
                # 본문은 먼저 다 읽음 — 남기면 연결 재사용(keep-alive) 때 다음 요청이 깨짐
                n = int(self.headers.get("Content-Length") or 0)
                if n > MAX_BODY:
                    self.close_connection = True
                    raise HttpError(413, "요청이 너무 큼")
                raw_body = self.rfile.read(n) if n else b""
            # 설문 화면(/sv/…) — survey.py 가 처리. /api/ 보다 먼저 봄(/sv/api/state 도 여기로)
            j = path.find("/sv/")
            if j >= 0:
                if SURVEY is None:
                    raise HttpError(404, "설문 도구 없음")
                code, ctype, data, hdrs = SURVEY.handle(method, path[j + 3:] + ("?" + u.query if u.query else ""),
                                                        raw_body)
                return self.send_bytes(code, data, ctype, dict(hdrs, **{"Cache-Control": "no-store"}))
            i = path.find("/api/")
            if i >= 0:
                route = path[i + 5:].strip("/")
                if method == "POST":
                    if self.headers.get("X-Devview") != "1":
                        raise HttpError(403, "X-Devview 헤더 없음")
                    body = json.loads(raw_body.decode("utf-8") or "{}") if raw_body else {}
                    fn = POST_ROUTES.get(route)
                    if not fn:
                        raise HttpError(404, f"없는 API ({route})")
                    return self.json(200, fn(body))
                if route == "raw":
                    p = api_raw(q)
                    return self.send_bytes(200, p.read_bytes(), MIME.get(p.suffix.lower(), "application/octet-stream"),
                                           {"Cache-Control": "no-store"})
                fn = GET_ROUTES.get(route)
                if not fn:
                    raise HttpError(404, f"없는 API ({route})")
                return self.json(200, fn(q))
            if method != "GET":
                raise HttpError(405, "허용 안 됨")
            i = path.find("/static/")
            if i >= 0:
                return self.static(path[i + 8:])
            # 그 밖의 경로 = 화면(프록시 접두어 아래 어디서 열어도 같은 화면)
            data = (STATIC / "index.html").read_bytes()
            return self.send_bytes(200, data, MIME[".html"], {"Cache-Control": "no-store"})
        except HttpError as e:
            if e.status >= 500:
                log(logging.ERROR, "오류", "HTTP", f"{method} {path}: {e}")
            return self.json(e.status, e.payload)
        except GitError as e:
            log(logging.WARNING, "실패", "git", f"{method} {path}: {e}")
            return self.json(502, {"error": str(e), "git": True})
        except (BrokenPipeError, ConnectionResetError):
            return None
        except Exception as e:
            log(logging.ERROR, "예외", "HTTP", f"{method} {path}: {e}\n{traceback.format_exc()}")
            try:
                return self.json(500, {"error": f"서버 오류 — {type(e).__name__}: {e}"})
            except OSError:
                return None


def main():
    global ROOT, GIT, SURVEY
    ap = argparse.ArgumentParser(description="devview — 코드 · md · git 이력 보기/편집 서버")
    ap.add_argument("root", nargs="?", default=".", help="작업 폴더 (기본: 현재 폴더)")
    ap.add_argument("--host", default="0.0.0.0", help="묶을 주소 (기본 0.0.0.0 — 대회 미리보기 조건)")
    ap.add_argument("--port", type=int, default=8701)
    ap.add_argument("--log", default=None, help="로그 파일 (기본 ~/.devview/devview.log)")
    ap.add_argument("--survey", default=None, help="설문 도구 survey.py 경로 (기본: 작업 폴더 · 키트 · 로컬 스킬에서 찾음)")
    a = ap.parse_args()
    if sys.version_info < (3, 8):
        sys.exit("파이썬 3.8 이상 필요")
    ROOT = Path(a.root).expanduser().resolve()
    if not ROOT.is_dir():
        sys.exit(f"폴더 없음: {ROOT}")
    missing = [x for x in ("index.html", "md.bundle.js", "monaco/vs/loader.js") if not (STATIC / x).is_file()]
    if missing:
        sys.exit(f"화면 파일 없음: {', '.join(missing)} (web/ 에서 npm run build)")
    logpath = setup_logging(a.log)
    GIT = Git(ROOT)
    SURVEY = load_survey(a.survey)
    try:
        srv = ThreadingHTTPServer((a.host, a.port), Handler)
    except OSError as e:
        sys.exit(f"포트 {a.port} 를 열 수 없음: {e}")
    srv.daemon_threads = True
    log(logging.INFO, "시작", "서버", f"{VERSION} {a.host}:{a.port} 작업 폴더 {ROOT} git {GIT.top or GIT.error}")
    shown = "localhost" if a.host in ("0.0.0.0", "", "::") else a.host
    print(f"devview {VERSION} — 작업 폴더 {ROOT}", flush=True)
    print(f"  주소 http://{shown}:{a.port}/   (IDE 미리보기에는 포트 {a.port} 입력)", flush=True)
    print(f"  git {GIT.top if GIT.ok else '없음 (' + (GIT.error or '') + ')'} · 로그 {logpath or '없음'}", flush=True)
    print(f"  설문 {'연결 (위쪽 «설문» 탭)' if SURVEY else '없음'}", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        log(logging.INFO, "종료", "서버", "정지")


if __name__ == "__main__":
    main()
