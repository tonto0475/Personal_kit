#!/usr/bin/env python3
"""devview — 작업 폴더의 코드 · md · git 이력을 브라우저에서 보고 고치는 서버. 표준 라이브러리만 사용

    python3 devview.py [작업 폴더=현재 폴더] [--host 0.0.0.0] [--port 8701] [--log 로그 경로]

화면(static/)
- 코드 탭: 파일 트리 · Monaco 편집기(PyCharm Dark 색 · 키맵) · md 는 mdview 라이브 프리뷰 편집기
- Git 탭 : 브랜치 그래프 · 커밋 상세 · 파일별 diff · 파일 이력 · 커밋하지 않은 변경
- 그래프 탭: flowtree(기능 · 결정 트리 · 코드 연결) — /ft/ 아래로 연결 · 처음 화면 · Alt+Q = MAIN 마법봉
서버
- 파일 저장은 디스크 내용 해시 대조. 다른 곳(공식 IDE · Codex)이 먼저 고쳤으면 409 응답, 덮어쓰기 없음
- 인코딩(UTF-8 · UTF-8 BOM · CP949) · 줄바꿈(LF · CRLF) · 파일 권한은 원래 파일 기준 유지
- git 은 읽기 명령만 실행. GIT_OPTIONAL_LOCKS=0 — 폴링 중 index.lock 미점유(Codex 커밋과 충돌 방지)
- 쓰기 요청(POST)은 X-Devview 헤더 필수 — 다른 사이트에서 보낸 요청 차단
- 경로 규칙: /api/ · /static/ 앞에 프록시 접두어가 붙어 와도 그대로 처리
- 키트 폴더(--kit · 기본 = 작업 폴더/kit 에 AGENTS.md 가 있으면 그것 · 없으면 작업 폴더): 문서 단축키 · 그래프 기본 tree · Book · 설문 저장소 · 허브(.codex-hub) · 캡처 기준
  코드 트리 · git · 검색 · 파일 열기는 작업 폴더 전체(대회 = 과제 루트 · 키트는 그 안 kit/)
- 페이지 서버: --port + 100(--page-port) 에 작업 폴더 파일을 읽기 전용으로. md 의 .html 링크는 대회 미리보기 주소의 그 포트로 새 탭
- 로그: ~/.devview/devview.log  (날짜 시간 | 중요도 | 종류 | 영역 | 내용)
"""
import argparse
import datetime
import fnmatch
import gzip
import hashlib
import importlib.util
import io
import json
import logging
import logging.handlers
import os
import posixpath
import re
import stat
import subprocess
import sys
import threading
import time
import traceback
import xml.etree.ElementTree as ET
import zipfile
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

VERSION = "1.0.0"
HERE = Path(__file__).resolve().parent
STATIC = HERE / "static"
sys.path.insert(0, str(HERE))
try:
    import codex_sessions        # Codex 세션 상태(같은 폴더) — 없으면 /api/codex/sessions 가 404
except ImportError:
    codex_sessions = None
try:
    import codex_hub             # 코덱스 허브(같은 폴더) — 없으면 /api/hub 가 404
except ImportError:
    codex_hub = None
try:
    import notify                # 알림 종(같은 폴더) — 없으면 /api/notify 가 404 · 화면에 종 없음
except ImportError:
    notify = None

ROOT = None                      # 작업 폴더(절대 경로)
KIT = None                       # 키트 폴더 — 문서 단축키 · flowtree 기본 tree · Book · 설문 저장소 · 허브 기준(ROOT/kit 에 AGENTS.md 가 있으면 그것 · 없으면 ROOT · --kit)
GIT = None                       # Git 저장소 정보
SURVEY = None                    # 설문 도구(survey.py) 모듈 — 찾으면 /sv/ 아래로 연결, 없으면 설문 탭 숨김
FT = None                        # 그래프 화면(flowtree server.py) 모듈 — 찾으면 /ft/ 아래로 연결, 없으면 그래프 탭에 «flowtree 없음»
FT_WS = None                     # flowtree 작업 공간(tree.json · 코드 스캔 · 유저 칸) — 기준 루트 = 작업 폴더
START_VIEW = "graph"             # 처음 보기(--start-view) — flowtree 가 없으면 화면이 코드로 바꿈
PORT = 0                         # devview 포트(--port) — 화면이 대회 미리보기 주소의 포트 자리를 찾는 데 씀
PAGE_PORT = 0                    # 페이지 서버 포트(기본 devview 포트 + 100 · 0 = 꺼짐) — md 의 .html 링크를 여기서 연다
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
    folder = KIT / "docs" / "captures"
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


# ======= 오피스 문서 보기(xlsx · docx) — 읽기 전용, 표준 라이브러리(zipfile + xml.etree)로 해석 =======
# 엑셀 확장자
OFFICE_XLSX = {".xlsx", ".xlsm"}
# 워드 확장자
OFFICE_DOCX = {".docx"}
# 시트 한 장에서 보내는 줄 상한
MAX_SHEET_ROWS = 2000
# 시트 한 장에서 보내는 열 상한
MAX_SHEET_COLS = 200
# 워드에서 보내는 문단 · 표 상한
MAX_DOC_BLOCKS = 5000
# 압축 안 파일 하나의 풀린 크기 상한(압축 폭탄 차단)
MAX_ZIP_PART = 64 * 1024 * 1024
# 엑셀 본문 이름공간
NS_X = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
# 워드 본문 이름공간
NS_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
# 관계 id 속성 이름공간
NS_R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
# 관계 파일(.rels) 이름공간
NS_PR = "{http://schemas.openxmlformats.org/package/2006/relationships}"
# 날짜 기본 서식 번호(14~17 · 22 · 동아시아 27~36 · 50~58)
DATE_FMT_IDS = {14, 15, 16, 17, 22} | set(range(27, 37)) | set(range(50, 59))
# 시각 기본 서식 번호
TIME_FMT_IDS = {18, 19, 20, 21, 45, 46, 47}


# 압축 안 파일 하나 읽기 — 없으면 None, 풀린 크기가 상한을 넘으면 실패
def zip_part(zf, name):
    try:
        # 압축 안 파일 정보
        info = zf.getinfo(name)
    except KeyError:
        return None
    if info.file_size > MAX_ZIP_PART:
        raise HttpError(422, f"읽기 실패: 내부 파일이 너무 큼 ({name})")
    return zf.read(info)


# 관계 파일(.rels) → {관계 id: 압축 안 경로}
def zip_rels(zf, base_dir, rels_name):
    # 관계 id → 경로
    out = {}
    # 관계 파일 바이트
    data = zip_part(zf, rels_name)
    if data is None:
        return out
    # 관계 요소마다
    for rel in ET.fromstring(data).iter(NS_PR + "Relationship"):
        # 대상 경로(상대 또는 / 로 시작하는 절대)
        target = rel.get("Target") or ""
        out[rel.get("Id")] = target.lstrip("/") if target.startswith("/") \
            else posixpath.normpath(posixpath.join(base_dir, target))
    return out


# 열 글자 → 0부터 세는 번호("A1" → 0, "AB3" → 27)
def xlsx_col(ref):
    # 열 번호(1부터)
    n = 0
    # 주소 글자마다(숫자가 나오면 멈춤)
    for ch in ref.upper():
        if not "A" <= ch <= "Z":
            break
        n = n * 26 + ord(ch) - 64
    return n - 1


# 문자열 칸(si · is) 글자 — 서식 조각(r/t)을 이어 붙임, 읽는 법(rPh) 제외
def xlsx_text(el):
    # 글자 조각 목록
    parts = []
    # 서식 없는 글자
    t = el.find(NS_X + "t")
    if t is not None:
        parts.append(t.text or "")
    # 서식 조각(r)마다
    for r in el.findall(NS_X + "r"):
        # 서식 조각 글자
        rt = r.find(NS_X + "t")
        if rt is not None:
            parts.append(rt.text or "")
    return "".join(parts)


# 표시 서식 → 'date' · 'time' · None
def xlsx_fmt_kind(fid, code):
    if code is None:
        return "date" if fid in DATE_FMT_IDS else "time" if fid in TIME_FMT_IDS else None
    # 따옴표 글자 · [색 · 조건] · 이스케이프를 뺀 서식 글자
    s = re.sub(r'"[^"]*"|\[[^\]]*\]|\\.|_.|\*.', "", code).lower().replace("general", "")
    if re.search(r"[yd]", s):
        return "date"
    if re.search(r"[hs]", s):
        return "time"
    if "m" in s and not re.search(r"[0#?]", s):
        return "date"
    return None


# 칸 스타일 번호 → 날짜 · 시각 종류 목록(styles.xml 의 cellXfs 순서)
def xlsx_styles(zf):
    # 스타일 번호 순 종류
    kinds = []
    # styles.xml 바이트
    data = zip_part(zf, "xl/styles.xml")
    if data is None:
        return kinds
    # styles.xml 뿌리 요소
    root = ET.fromstring(data)
    # 사용자 지정 서식 번호 → 서식 글자
    custom = {}
    # 사용자 지정 서식 요소마다
    for f in root.iter(NS_X + "numFmt"):
        try:
            custom[int(f.get("numFmtId"))] = f.get("formatCode") or ""
        except (TypeError, ValueError):
            pass
    # 칸 서식 목록 요소
    xfs = root.find(NS_X + "cellXfs")
    if xfs is None:
        return kinds
    # 칸 서식 요소마다
    for xf in xfs.findall(NS_X + "xf"):
        try:
            # 서식 번호
            fid = int(xf.get("numFmtId") or 0)
        except ValueError:
            fid = 0
        kinds.append(xlsx_fmt_kind(fid, custom.get(fid)))
    return kinds


# 날짜 일련번호 → 글자(날짜 · 날짜 시각 · 시각). 바꿀 수 없으면 None
def xlsx_date(num, kind, d1904):
    if num < 0:
        return None
    # 일련번호 0 기준일(1900 체계는 윤년 오류 보정으로 1899-12-30)
    base = datetime.datetime(1904, 1, 1) if d1904 else datetime.datetime(1899, 12, 30)
    # 초 단위 반올림한 경과 초
    secs = int(round(num * 86400))
    try:
        # 날짜 시각
        dt = base + datetime.timedelta(seconds=secs)
    except OverflowError:
        return None
    # 시각 글자(초가 0 이면 생략)
    hms = dt.strftime("%H:%M" if secs % 60 == 0 else "%H:%M:%S")
    if kind == "time":
        return hms
    if secs % 86400 == 0:
        return dt.strftime("%Y-%m-%d")
    return f"{dt.strftime('%Y-%m-%d')} {hms}"


# 칸(c) 하나 → 표시 글자. 수식 칸은 저장된 계산값(v)
def xlsx_cell(c, shared, styles, d1904):
    # 칸 종류(s 공유 문자열 · inlineStr · str 수식 글자 · b 불린 · e 오류 · d ISO 날짜 · n 숫자)
    t = c.get("t") or "n"
    if t == "inlineStr":
        # 칸 안 문자열 요소
        inl = c.find(NS_X + "is")
        return xlsx_text(inl) if inl is not None else ""
    # 값 요소
    v = c.find(NS_X + "v")
    # 값 글자
    txt = v.text if v is not None and v.text is not None else None
    if txt is None:
        return ""
    if t == "s":
        try:
            return shared[int(txt)]
        except (ValueError, IndexError):
            return ""
    if t == "b":
        return "TRUE" if txt.strip() == "1" else "FALSE"
    if t in ("str", "e", "d"):
        return txt
    try:
        # 숫자 값
        num = float(txt)
    except ValueError:
        return txt
    try:
        # 칸 스타일 번호
        si = int(c.get("s") or 0)
    except ValueError:
        si = 0
    # 날짜 · 시각 종류
    kind = styles[si] if 0 <= si < len(styles) else None
    if kind:
        # 날짜 글자
        d = xlsx_date(num, kind, d1904)
        if d:
            return d
    if num.is_integer() and abs(num) < 1e15:
        return str(int(num))
    return repr(num)


# 시트 XML → (보낼 줄 [[엑셀 줄 번호, [칸 글자…]]…], 전체 줄 수, 열 수, 줄 상한에서 끊었나, 열 상한에서 끊었나)
def xlsx_rows(data, shared, styles, d1904):
    # 보낼 줄 목록
    rows = []
    # 전체 줄 수
    total = 0
    # 가장 긴 줄의 열 수
    ncols = 0
    # 열 상한을 넘은 칸이 있었나
    cols_cut = False
    # 끝난 요소마다(_ev 사건 종류 · el 요소) — 줄(row)만 처리하고 비워 메모리 절약
    for _ev, el in ET.iterparse(io.BytesIO(data), events=("end",)):
        if el.tag != NS_X + "row":
            continue
        total += 1
        if len(rows) < MAX_SHEET_ROWS:
            try:
                # 엑셀 줄 번호(없으면 앞 줄 + 1)
                rnum = int(el.get("r"))
            except (TypeError, ValueError):
                rnum = rows[-1][0] + 1 if rows else 1
            # 이 줄의 칸 글자
            cells = []
            # 칸 요소마다
            for c in el.findall(NS_X + "c"):
                # 칸 주소(B3)
                ref = c.get("r")
                # 열 번호
                idx = xlsx_col(ref) if ref else len(cells)
                if idx >= MAX_SHEET_COLS:
                    cols_cut = True
                    continue
                if idx < len(cells):
                    cells[idx] = xlsx_cell(c, shared, styles, d1904)
                    continue
                cells.extend([""] * (idx - len(cells)))
                cells.append(xlsx_cell(c, shared, styles, d1904))
            while cells and cells[-1] == "":
                cells.pop()
            ncols = max(ncols, len(cells))
            rows.append([rnum, cells])
        el.clear()
    return rows, total, ncols, total > len(rows), cols_cut


# 엑셀 꾸러미 → 시트 이름 목록 + 고른 시트(sheet_i) 표
def xlsx_read(zf, sheet_i):
    # workbook.xml 바이트
    wb = zip_part(zf, "xl/workbook.xml")
    if wb is None:
        raise HttpError(422, "읽기 실패: xl/workbook.xml 없음")
    # workbook.xml 뿌리 요소
    root = ET.fromstring(wb)
    # 통합 문서 속성(날짜 1904 체계 여부)
    pr = root.find(NS_X + "workbookPr")
    # 1904 날짜 체계 여부
    d1904 = pr is not None and (pr.get("date1904") or "").lower() in ("1", "true")
    # 관계 id → 시트 파일 경로
    rels = zip_rels(zf, "xl", "xl/_rels/workbook.xml.rels")
    # (시트 이름, 시트 파일 경로) 목록
    sheets = [(sh.get("name") or "", rels.get(sh.get(NS_R + "id"))) for sh in root.iter(NS_X + "sheet")]
    if not sheets:
        raise HttpError(422, "읽기 실패: 시트 없음")
    # 고른 시트 번호(범위 밖이면 첫 시트)
    i = sheet_i if 0 <= sheet_i < len(sheets) else 0
    # 고른 시트 파일 경로
    part = sheets[i][1]
    # 시트 XML 바이트
    data = zip_part(zf, part) if part else None
    if data is None:
        raise HttpError(422, f"읽기 실패: 시트 파일 없음 ({sheets[i][0]})")
    # 공유 문자열 목록
    shared = []
    # sharedStrings.xml 바이트
    ss = zip_part(zf, "xl/sharedStrings.xml")
    if ss is not None:
        shared = [xlsx_text(si) for si in ET.fromstring(ss).iter(NS_X + "si")]
    # 보낼 줄 · 전체 줄 수 · 열 수 · 줄 상한에서 끊었나 · 열 상한에서 끊었나
    rows, total, ncols, cut, cols_cut = xlsx_rows(data, shared, xlsx_styles(zf), d1904)
    return {"kind": "xlsx", "sheets": [n for n, _ in sheets], "sheet": i, "rows": rows, "total": total,
            "cols": ncols, "cut": cut, "cols_cut": cols_cut}


# 워드 스타일 id → 제목 수준(1~6). 이름이 Heading N · 제목 N · Title · 제목 인 것
def docx_heading_styles(zf):
    # 스타일 id → 수준
    out = {}
    # styles.xml 바이트
    data = zip_part(zf, "word/styles.xml")
    if data is None:
        return out
    # 스타일 요소마다
    for st in ET.fromstring(data).iter(NS_W + "style"):
        # 스타일 id
        sid = st.get(NS_W + "styleId") or ""
        # 스타일 이름 요소
        nm = st.find(NS_W + "name")
        # 스타일 이름
        name = (nm.get(NS_W + "val") if nm is not None else "") or ""
        # 제목 수준
        lv = docx_level_of(name) or docx_level_of(sid)
        if lv:
            out[sid] = lv
    return out


# 스타일 이름 · id → 제목 수준. 제목이 아니면 0
def docx_level_of(name):
    # 공백 없앤 소문자 이름
    s = re.sub(r"\s+", "", (name or "").lower())
    # Heading1 · 제목1 꼴
    m = re.match(r"^(heading|제목)(\d)$", s)
    if m:
        return min(6, max(1, int(m.group(2))))
    return 1 if s in ("title", "제목") else 0


# 문단(p) 글자 — 탭 · 줄바꿈 반영, 지운 글자(delText) 제외
def docx_para_text(p):
    # 글자 조각 목록
    parts = []
    # 문단 안 요소마다
    for el in p.iter():
        if el.tag == NS_W + "t":
            parts.append(el.text or "")
        elif el.tag == NS_W + "tab":
            parts.append("\t")
        elif el.tag in (NS_W + "br", NS_W + "cr"):
            parts.append("\n")
    return "".join(parts)


# 본문 요소를 순서대로 훑어 블록 목록에 추가 — 문단 · 제목 · 표, 내용 컨트롤(sdt)은 안으로 들어감
def docx_walk(parent, heads, blocks):
    # 바로 아래 요소마다
    for el in parent:
        if len(blocks) >= MAX_DOC_BLOCKS:
            return
        if el.tag == NS_W + "p":
            # 문단 글자
            text = docx_para_text(el)
            if not text.strip():
                continue
            # 문단 속성
            ppr = el.find(NS_W + "pPr")
            # 문단 스타일 요소
            ps = ppr.find(NS_W + "pStyle") if ppr is not None else None
            # 개요 수준 요소
            ol = ppr.find(NS_W + "outlineLvl") if ppr is not None else None
            # 제목 수준(스타일 → 개요 수준 순)
            lv = heads.get(ps.get(NS_W + "val"), 0) if ps is not None else 0
            if not lv and ps is not None:
                lv = docx_level_of(ps.get(NS_W + "val"))
            if not lv and ol is not None and (ol.get(NS_W + "val") or "").isdigit() and int(ol.get(NS_W + "val")) < 6:
                lv = int(ol.get(NS_W + "val")) + 1
            blocks.append({"t": "h", "level": lv, "text": text} if lv else {"t": "p", "text": text})
        elif el.tag == NS_W + "tbl":
            # 표의 줄 목록(칸 = 칸 안 문단을 줄바꿈으로 이은 글자)
            rows = [["\n".join(docx_para_text(p) for p in tc.iter(NS_W + "p")) for tc in tr.findall(NS_W + "tc")]
                    for tr in el.findall(NS_W + "tr")]
            blocks.append({"t": "table", "rows": rows})
        elif el.tag == NS_W + "sdt":
            # 내용 컨트롤 본문
            sc = el.find(NS_W + "sdtContent")
            if sc is not None:
                docx_walk(sc, heads, blocks)


# 워드 꾸러미 → 블록 목록(문단 · 제목 · 표 순서대로)
def docx_read(zf):
    # document.xml 바이트
    data = zip_part(zf, "word/document.xml")
    if data is None:
        raise HttpError(422, "읽기 실패: word/document.xml 없음")
    # 본문 요소
    body = ET.fromstring(data).find(NS_W + "body")
    # 블록 목록
    blocks = []
    if body is not None:
        docx_walk(body, docx_heading_styles(zf), blocks)
    return {"kind": "docx", "blocks": blocks, "cut": len(blocks) >= MAX_DOC_BLOCKS}


# 오피스 문서 보기 API — path(작업 폴더 안) · sheet(엑셀 시트 번호). 옛 형식은 415, 깨진 파일은 422
def api_office(q):
    # 실제 파일 경로(작업 폴더 밖이면 403)
    p = safe(q.get("path"))
    if not p.is_file():
        raise HttpError(404, "파일 없음")
    # 확장자(소문자)
    ext = p.suffix.lower()
    if ext not in OFFICE_XLSX and ext not in OFFICE_DOCX:
        raise HttpError(415, f"미지원 형식({ext or '확장자 없음'})")
    if p.stat().st_size > MAX_RAW:
        raise HttpError(413, "파일이 너무 큼")
    try:
        # 고른 시트 번호
        sheet_i = int(q.get("sheet") or 0)
    except ValueError:
        sheet_i = 0
    try:
        with zipfile.ZipFile(p) as zf:
            # 해석 결과
            out = xlsx_read(zf, sheet_i) if ext in OFFICE_XLSX else docx_read(zf)
    except HttpError:
        raise
    except zipfile.BadZipFile:
        raise HttpError(422, "읽기 실패: zip 형식 아님")
    except ET.ParseError as e:
        raise HttpError(422, f"읽기 실패: XML 오류 ({e})")
    except Exception as e:
        log(logging.WARNING, "실패", "오피스", f"{rel_of(p)}: {type(e).__name__}: {e}")
        raise HttpError(422, f"읽기 실패: {type(e).__name__}: {e}")
    out["path"] = rel_of(p)
    return out


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
            "python": sys.version.split()[0], "git": api_git_info(q), "survey": SURVEY is not None,
            "flowtree": ft_info(), "start_view": START_VIEW, "hub": codex_hub is not None, "notify": notify is not None,
            "port": PORT, "page_port": PAGE_PORT, "kit": rel_of(KIT), "kit_abs": str(KIT)}


# ======= 그래프 화면(flowtree) 연결 =======
# flowtree 상태 — 연결 여부 · tree.json 경로 · 있는지
def ft_info():
    if FT is None:
        return {"ok": False}
    return {"ok": True, "tree": str(FT_WS.tree_path), "exists": FT_WS.tree_path.is_file(), "dir": str(Path(FT.__file__).parent)}


# flowtree 불러오기 — devview 폴더/flowtree(키트) → devview 폴더/../flowtree(로컬 형제) 순. 작업 공간은 tree.json 을 몰라도 만듦
# tree: --tree 값(없으면 <키트>/docs/flowtree/tree.json · 노드 doc 경로 기준 = 키트)
def load_flowtree(tree):
    global FT_WS
    for d in (HERE / "flowtree", HERE.parent / "flowtree"):
        p = d / "server.py"
        if not (p.is_file() and (d / "static" / "index.html").is_file()):
            continue
        try:
            spec = importlib.util.spec_from_file_location("devview_flowtree", p)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            FT_WS = mod.Workspace(Path(tree).expanduser() if tree else KIT / "docs" / "flowtree" / "tree.json", KIT)
        except Exception as e:
            log(logging.WARNING, "실패", "그래프", f"불러오기 {p}: {e}")
            continue
        log(logging.INFO, "연결", "그래프", f"{p} · {FT_WS.tree_path}")
        return mod
    return None


# Codex 세션 상태 목록(codex_sessions.py — 같은 폴더) · 화면은 아직 없음
def api_codex_sessions(q):
    if codex_sessions is None:
        raise HttpError(404, "codex_sessions.py 없음")
    return codex_sessions.list_sessions(limit=int(q.get("limit") or codex_sessions.DEFAULT_LIMIT),
                                        thread=q.get("thread") or None)


# ======= 코덱스 허브(codex_hub.py — 같은 폴더) =======
# 허브 함수 부르기 — 허브 오류는 HTTP 오류로
# name: codex_hub 함수 이름 / a: 인자 / kw: 이름 인자
def hub_call(name, *a, **kw):
    if codex_hub is None:
        raise HttpError(404, "codex_hub.py 없음")
    try:
        return getattr(codex_hub, name)(*a, **kw)
    except codex_hub.HubError as e:
        raise HttpError(e.status, str(e))


# GET /api/hub — 행 목록 · GET /api/hub/log?nick= — 누적 · GET /api/hub/chat?nick=&after= — 대화
def api_hub(q):
    return hub_call("rows", KIT)


def api_hub_log(q):
    return hub_call("log", KIT, q.get("nick"))


def api_hub_chat(q):
    return hub_call("chat", KIT, q.get("nick"), int(q.get("after") or 0))


# GET /api/hub/subagents?nick= — 그 세션의 서브 상태
def api_hub_subagents(q):
    return hub_call("subagents", KIT, q.get("nick"))


# POST /api/hub/queue {nick, text} · POST /api/hub/magic {nick, view, selection, question}
def api_hub_queue(b):
    return hub_call("send", KIT, b)


def api_hub_magic(b):
    sel = b.get("selection") if isinstance(b.get("selection"), dict) else {}
    if (b.get("view") == "book" and str(b.get("nick") or "").lower() == "2nd" and sel.get("note") and sel.get("doc")
            and str(b.get("instruction") or "").strip()):
        return hub_note_instruction(str(sel["doc"]), str(sel["note"]), str(b["instruction"]).strip())
    return hub_call("magic", KIT, b, ft=FT, ws=FT_WS, resolve=safe)


def hub_note_instruction(doc, nid, text):
    """2ND 지시 붙은 마법봉(Alt+R) + 책 스티커 — 스티커 마법봉 길(note_magic_api: 409 판정 · magic_rid)로
    답이 달린 스티커는 지시 글을 꼬리 질문(thread)으로 만들어 그 꼬리를 보냄(원 답을 덮지 않음)"""
    # 책 html 이 든 폴더(= 페이지 경로의 «/api/notes» 앞) · notes.json
    prefix = "/".join(norm_rel(doc).split("/")[:-1])
    p = notes_file(prefix)
    with NOTES_LOCK:
        hit = next((n for n in notes_load(p) if n.get("id") == nid), None)
    if hit is None:
        raise HttpError(404, "그런 스티커 없음")
    if hit.get("answer"):
        _, full = notes_api("POST", prefix, f"{nid}/thread", {}, json.dumps({"q": text}, ensure_ascii=False).encode("utf-8"))
        tid = full["thread"][-1]["id"]
        _, res = note_magic_api(p, nid, tid)
        return {"ok": True, "id": res.get("rid"), "msg": f"스티커 {nid} 꼬리 질문 {tid} · 2ND 에 보냄 {res.get('rid')}"}
    _, res = note_magic_api(p, nid, instruction=text)
    return {"ok": True, "id": res.get("rid"), "msg": f"스티커 {nid} · 지시 · 2ND 에 보냄 {res.get('rid')}"}


# ======= Book 보기 — 북키트 책 목록 =======
# 만든 책의 판 하나 = 한 줄(그룹 없음 · 최신이 위) — <키트>/bookkit/books/<책>/dist/versions.json(빌드가 판마다 적는 목록)
#   versions.json 이 없는 책은 dist/*.html 하나하나가 한 줄 · «_» 로 시작하는 책 · 파일은 시험용이라 뺀다
#   경로는 작업 폴더 기준(페이지 서버 주소와 같음) · latest = 그 책의 마지막 판(나머지는 회색)
EDITION_RE = re.compile(r"(\d+차(?:판)?|v\d+)", re.I)


def book_versions(dist, book):
    """versions.json → 판 줄 목록(파일이 남아 있는 판만 · 없거나 깨졌으면 None)"""
    try:
        vj = json.loads((dist / "versions.json").read_text(encoding="utf-8"))
        vs = vj["versions"]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    title = vj.get("title") or book
    out = []
    for v in vs:
        p = dist / str(v.get("file", ""))
        if not v.get("file") or not p.is_file():
            continue
        try:
            mt = time.mktime(time.strptime(v.get("at", ""), "%Y-%m-%d %H:%M:%S"))
        except ValueError:
            mt = p.stat().st_mtime
        sub = [time.strftime("%m-%d %H:%M", time.localtime(mt)), f"블록 {v.get('blocks', 0)}"]
        if v.get("new") is not None:
            sub.append(f"새로 {v['new']}")
        if v.get("blanks"):
            sub.append(f"빈 칸 {v['blanks']}")
        out.append({"path": rel_of(p), "book": book, "n": int(v.get("n", 0)), "title": f"{title} · v{v.get('n')} · {v.get('name', '')}",
                    "edition": v.get("name", ""), "sub": " · ".join(sub), "mtime": mt})
    return out


def api_books(q):
    books = []
    for dist in sorted((KIT / "bookkit" / "books").glob("*/dist")):
        book = dist.parent.name
        if book.startswith("_"):
            continue
        rows = book_versions(dist, book)
        if rows is None:  # 판 목록이 없는 책(옛 빌드) — html 하나가 한 줄
            rows = []
            for p in sorted(dist.glob("*.html")):
                if p.name.startswith("_"):
                    continue
                mt = p.stat().st_mtime
                m = EDITION_RE.search(p.stem)
                rows.append({"path": rel_of(p), "book": book, "n": 0, "title": book if p.stem == book else f"{book} · {p.stem}",
                             "edition": m.group(1) if m else "", "sub": time.strftime("%m-%d %H:%M", time.localtime(mt)), "mtime": mt})
        rows.sort(key=lambda x: (-x["mtime"], -x["n"]))
        for i, r in enumerate(rows):
            r["latest"] = i == 0
        books += rows
    books.sort(key=lambda x: (-x["mtime"], -x["n"]))
    return {"books": books, "kit": rel_of(KIT) if KIT != ROOT else ""}


# ======= 설문 도구 연결 =======
# 설문 도구(survey.py) 불러오기 — 지정값 → 작업 폴더 · 키트(devview 옆) · 로컬 Claude 스킬 순. 화면 · 저장은 그 파일이 맡음
def load_survey(given):
    cands = ([Path(given).expanduser()] if given else []) + [
        KIT / ".agents" / "skills" / "survey" / "survey.py",
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
        # 키트의 docs/surveys 는 등록 목록에 없어도 늘 보임
        mod.EXTRA_STORES.append(KIT / "docs" / "surveys")
        # 제출 때 MAIN · 2ND 전송 — 이 devview 의 허브(키트 .codex-hub)를 그대로 씀(옛 survey.py 면 칸만 생기고 안 씀)
        if codex_hub is not None:
            mod.HUB, mod.HUB_ROOT = codex_hub, KIT
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


# ======= 알림 종(notify.py — 같은 폴더) =======
# 저장 = <키트>/.codex-hub/notify.jsonl(덧붙이기) · 자동 수집 = 서버 뒤 스레드(Collector) · 화면 = static/js/notify.js
NOTIFY_FEED = None


def need_notify():
    if NOTIFY_FEED is None:
        raise HttpError(404, "notify.py 없음")
    return NOTIFY_FEED


# GET /api/notify — 알림 목록(최근 것이 위) · 안 읽은 개수
def api_notify(q):
    return need_notify().view()


# POST /api/notify/read — {ids: [...]} 또는 {all: true}
def api_notify_read(b):
    feed = need_notify()
    ids = feed.view(limit=0)["unread_ids"] if b.get("all") else b.get("ids")
    if not isinstance(ids, list):
        raise HttpError(400, "형식은 {ids: [...]} 또는 {all: true}")
    notify.mark_read(KIT, ids)
    return feed.view()


# 책 폴더 이름 → 그 책 마지막 판 html(작업 폴더 기준 · Book 목록과 같은 규칙)
def notify_book_path(book):
    return next((b["path"] for b in api_books({})["books"] if b["book"] == book), None)


# 알림 수집 시작 — 서버가 뜰 때 한 번
def notify_start():
    global NOTIFY_FEED
    if notify is None:
        return
    NOTIFY_FEED = notify.Feed(KIT)
    notify.feed_path(KIT).parent.mkdir(parents=True, exist_ok=True)
    notify.feed_path(KIT).touch()        # 세션의 notify.py 가 위로 찾을 수 있게
    col = notify.Collector(KIT, tree_path=lambda: FT_WS.tree_path if FT_WS else None, survey=SURVEY, hub=codex_hub,
                           book_path=notify_book_path)
    col.start(1.5, log=lambda m: log(logging.WARNING, "실패", "알림", m))


GET_ROUTES = {"info": api_info, "tree": api_tree, "file": api_file, "search": api_search, "symbols": api_symbols,
              "poll": api_poll, "git/info": api_git_info, "git/log": api_git_log, "git/commit": api_git_commit,
              "git/status": api_git_status, "git/blob": api_git_blob, "git/file-log": api_git_file_log,
              "git/blame": api_git_blame, "state": api_state_get, "office": api_office,
              "codex/sessions": api_codex_sessions,
              "hub": api_hub, "hub/log": api_hub_log, "hub/chat": api_hub_chat, "hub/subagents": api_hub_subagents, "books": api_books, "notify": api_notify}
POST_ROUTES = {"save": api_save, "create": api_create, "capture": api_capture, "state": api_state_post,
               "hub/queue": api_hub_queue, "hub/magic": api_hub_magic, "notify/read": api_notify_read}


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

    # 책 스티커(/pg/…/api/notes)만 — 그 밖의 경로는 dispatch 가 405
    def do_PATCH(self):
        self.dispatch("PATCH")

    def do_DELETE(self):
        self.dispatch("DELETE")

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
        # 페이지(/pg/<경로>) — 책 · md 의 .html 을 devview 와 같은 주소(출처)로. 대회 브라우저는 다른 주소(포트) 이동이 막혀
        # 페이지 서버(포트 +100) iframe 이 흰 화면이 됐다(2026-11-05 사전 체험). /sv/ · /ft/ · /api/ 보다 먼저(경로 안 /api/notes)
        m = PG_RE.match(path)
        if m:
            return PageHandler.serve_page(self, method, unquote(m.group(1)), u)
        if method not in ("GET", "POST", "HEAD"):
            return self.json(405, {"error": "허용 안 됨"})
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
            # 그래프 화면(/ft/…) — flowtree server.py 의 handle 이 처리. /api/ · /static/ 보다 먼저(/ft/api/data · /ft/static/…)
            j = path.find("/ft/")
            if j >= 0:
                if FT is None:
                    raise HttpError(404, "flowtree 없음")
                if method == "POST" and self.headers.get("X-Devview") != "1":
                    raise HttpError(403, "X-Devview 헤더 없음")
                code, ctype, data, hdrs = FT.handle(FT_WS, method, path[j + 3:] + ("?" + u.query if u.query else ""),
                                                    raw_body)
                return self.send_bytes(code, data, ctype, hdrs)
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
                    # 응답 머리글 — PDF 는 내장 보기 제목 · 내려받기 이름이 «raw» 대신 파일 이름이 되게
                    hdrs = {"Cache-Control": "no-store"}
                    if p.suffix.lower() == ".pdf":
                        hdrs["Content-Disposition"] = f"inline; filename*=UTF-8''{quote(p.name)}"
                    return self.send_bytes(200, p.read_bytes(), MIME.get(p.suffix.lower(), "application/octet-stream"),
                                           hdrs)
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


# ======= 책 스티커(페이지 서버) — 책 html 의 book.js 가 같은 출처의 «api/notes»(상대 경로)로 저장 · 읽기 =======
# 저장 = 작업 폴더 안 notes.json — 책 html 이 «…/dist/» 아래면 그 위 책 폴더(bookkit/books/<책>/notes.json), 아니면 html 옆
# 항목 = {id, ts, doc, slide, x, y, w, h, ctx(«… | b=<블록 ID>»), text} + 답(answer · answer_ts · title — bookkit/notes.py answer 가 단다)
#   + 꼬리 질문 thread [{id(t1 …), q, ts, magic_rid, a, a_ts}] — 책 아래 질문 줄 행 안에서 이어 묻기(답은 notes.py answer --thread)
# 스티커 파일 쓰기 잠금
NOTES_LOCK = threading.Lock()
# 스티커 한 장 글 최대 길이 · 파일 하나의 최대 장 수 · 스티커 하나의 꼬리 질문 최대 수
NOTES_MAX_TEXT = 2000
NOTES_MAX = 2000
NOTES_MAX_THREAD = 50
# 마법봉 보내는 중인 (notes.json, 스티커 id, 꼬리 id) — 동시에 두 번 눌러도 한 번만 보냄
NOTES_SENDING = set()


def notes_file(prefix):
    """요청 경로의 «/api/notes» 앞부분(= 책 html 이 있는 폴더) → notes.json 경로"""
    parts = [x for x in norm_rel(prefix).split("/") if x]
    if "dist" in parts:
        parts = parts[:parts.index("dist")]
    return safe("/".join(parts + ["notes.json"]))


def notes_load(p):
    """notes.json → 목록(없으면 빈 목록)"""
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else []
    except (OSError, ValueError):
        return []


def notes_save(p, notes):
    """notes.json 쓰기(임시 파일 → 바꿔 넣기)"""
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(notes, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, p)


def notes_api(method, prefix, rest, query, raw):
    """스티커 API — GET ?doc= 목록 · POST 새로 · PATCH /<id> 글 · 자리 · 크기 · DELETE /<id>
    · POST /<id>/magic · POST /<id>/thread {q} 꼬리 질문 · POST /<id>/thread/<꼬리 id>/magic → (상태 코드, 응답 dict | list)"""
    p = notes_file(prefix)
    nid = rest.strip("/")
    # 하위 경로(마법봉 · 꼬리 질문)
    sub = nid.split("/")
    if method == "POST" and len(sub) == 2 and sub[1] == "magic":
        return note_magic_api(p, sub[0])
    if method == "POST" and len(sub) == 4 and sub[1] == "thread" and sub[3] == "magic":
        return note_magic_api(p, sub[0], sub[2])
    body = {}
    if method in ("POST", "PATCH"):
        try:
            body = json.loads(raw.decode("utf-8") or "{}")
        except ValueError:
            raise HttpError(400, "json 아님")
    with NOTES_LOCK:
        notes = notes_load(p)
        if method == "GET" and not nid:
            doc = query.get("doc")
            return 200, [n for n in notes if doc is None or n.get("doc") == doc]
        if method == "POST" and not nid:
            text = str(body.get("text", "")).strip()
            if not text or len(text) > NOTES_MAX_TEXT:
                raise HttpError(400, "글이 비었거나 너무 김")
            if len(notes) >= NOTES_MAX:
                raise HttpError(507, "스티커가 너무 많음")
            try:
                note = {"id": os.urandom(4).hex(), "ts": time.strftime("%Y-%m-%d %H:%M:%S"), "doc": str(body.get("doc", ""))[:60],
                        "slide": int(body.get("slide", 0)), "x": float(body.get("x", 0)), "y": float(body.get("y", 0)),
                        "w": float(body.get("w", 0)), "h": float(body.get("h", 0)), "ctx": str(body.get("ctx", ""))[:300], "text": text}
            except (TypeError, ValueError) as e:
                raise HttpError(400, f"칸 값 오류 — {e}")
            notes.append(note)
            p.parent.mkdir(parents=True, exist_ok=True)
            notes_save(p, notes)
            return 201, note
        if method == "POST" and len(sub) == 2 and sub[1] == "thread":
            # 꼬리 질문 — 원 질문에 답이 달린 뒤만(행 안에서 이어 묻기) · 반환 = 스티커 전체
            hit = next((n for n in notes if n.get("id") == sub[0]), None)
            if hit is None:
                raise HttpError(404, "그런 스티커 없음")
            if not hit.get("answer"):
                raise HttpError(409, "원 질문 답 대기 중")
            q = str(body.get("q", "")).strip()
            if not q or len(q) > NOTES_MAX_TEXT:
                raise HttpError(400, "글이 비었거나 너무 김")
            th = [t for t in hit.get("thread") or [] if isinstance(t, dict)]
            if len(th) >= NOTES_MAX_THREAD:
                raise HttpError(507, "꼬리 질문이 너무 많음")
            # 꼬리 id — 이 스티커 안에서 고유(t1 · t2 …)
            k = max([int(t["id"][1:]) for t in th if re.fullmatch(r"t\d+", str(t.get("id") or ""))] or [0]) + 1
            th.append({"id": f"t{k}", "q": q, "ts": time.strftime("%Y-%m-%d %H:%M:%S")})
            hit["thread"] = th
            notes_save(p, notes)
            return 201, hit
        hit = next((n for n in notes if n.get("id") == nid), None) if nid else None
        if hit is None:
            raise HttpError(404, "그런 스티커 없음")
        if method == "PATCH":
            try:
                upd = {k: float(body[k]) for k in ("x", "y", "w", "h") if k in body}
            except (TypeError, ValueError) as e:
                raise HttpError(400, f"칸 값 오류 — {e}")
            if "text" in body:
                text = str(body["text"]).strip()
                if not text or len(text) > NOTES_MAX_TEXT:
                    raise HttpError(400, "글이 비었거나 너무 김")
                upd["text"] = text
            hit.update(upd)
            notes_save(p, notes)
            return 200, hit
        if method == "DELETE":
            notes_save(p, [n for n in notes if n is not hit])
            return 200, {"deleted": nid}
    raise HttpError(405, "허용 안 됨")


def note_magic_api(p, nid, tid=None, instruction=""):
    """POST …/api/notes/<id>/magic · …/<id>/thread/<꼬리 id>/magic — 그 스티커(꼬리 질문) 글 · 자리로 2ND 마법봉(허브)
    본문은 안 읽음(서버가 notes.json 에서 다시 읽음) · 답이 달리기 전 같은 질문 재요청은 409(꼬리는 꼬리 단위) · 반환 (상태 코드, {ok, rid})"""
    key = (str(p), nid, tid)
    with NOTES_LOCK:
        hit = next((n for n in notes_load(p) if n.get("id") == nid), None)
        if hit is None:
            raise HttpError(404, "그런 스티커 없음")
        # 판정 대상 — 원 질문 또는 그 꼬리 질문
        cur = hit
        if tid:
            cur = next((t for t in hit.get("thread") or [] if isinstance(t, dict) and t.get("id") == tid), None)
            if cur is None:
                raise HttpError(404, "그런 꼬리 질문 없음")
        if (cur.get("magic_rid") and not cur.get("a" if tid else "answer")) or key in NOTES_SENDING:
            raise HttpError(409, f"이미 보냄({cur.get('magic_rid') or '보내는 중'}) — 답을 기다리는 중")
        NOTES_SENDING.add(key)
    # queue 는 잠금 밖에서(최대 30초)
    try:
        res = hub_call("note_magic", KIT, hit, p, str(hit.get("doc") or ""), **({"tid": tid} if tid else {}),
                       **({"instruction": instruction} if instruction else {}))
    finally:
        with NOTES_LOCK:
            NOTES_SENDING.discard(key)
    with NOTES_LOCK:
        notes = notes_load(p)
        for n in notes:
            if n.get("id") != nid:
                continue
            if not tid:
                n["magic_rid"] = res.get("id")
                continue
            for t in n.get("thread") or []:
                if isinstance(t, dict) and t.get("id") == tid:
                    t["magic_rid"] = res.get("id")
        notes_save(p, notes)
    return 200, {"ok": True, "rid": res.get("id")}


# 페이지 경로 — «/pg/<경로>»(앞에 프록시 접두어 /proxy/8701 · /absproxy/8701 이 붙어도)
PG_RE = re.compile(r"^(?:/(?:abs)?proxy/\d+)?/pg(/.*)$")


# ======= 페이지 서버 — md 의 .html 링크를 devview 와 다른 포트에서 연다(본 서버 /pg/ 와 같은 내용 · 예전 주소 호환) =======
# 작업 폴더 파일을 원래 경로 그대로 읽기 전용으로 내준다(HTML 이 옆 그림 · js · css 를 상대 경로로 부르므로)
# 포트가 다르면 출처가 달라 HTML 안 스크립트가 devview API(저장 등)를 부를 수 없다
class PageHandler(Handler):
    server_version = f"devview-page/{VERSION}"

    def do_HEAD(self):
        self.dispatch("HEAD")

    # 책 스티커(…/api/notes)만 쓰기 허용 — 나머지는 읽기 전용
    def do_PATCH(self):
        self.dispatch("PATCH")

    def do_DELETE(self):
        self.dispatch("DELETE")

    def dispatch(self, method):
        u = urlparse(self.path)
        path = unquote(u.path)
        # 프록시 접두어(/absproxy/8801/)가 붙어 와도 그 뒤만
        m = re.match(r"^/(?:abs)?proxy/\d+(/.*)?$", path)
        prefix = ""
        if m:
            prefix = path[:len(path) - len(m.group(1) or "")].rstrip("/")
            path = m.group(1) or "/"
        # 맨 위(/) = 가장 최근 책의 마지막 판을 그 자리에서(주소 이동 없음) — 대회 미리보기 칸은 PORT 숫자만 바꿀 수 있고
        # 경로는 못 친다(2026-11-05 사전 체험). <base> 로 책 폴더를 가리켜 api/notes · 그림 등 상대 경로가 그 책으로 간다
        if path == "/" and method in ("GET", "HEAD"):
            return self.latest_book(prefix)
        return self.serve_page(method, path, u)

    # 가장 최근 책 내주기 — 책이 여럿이면 화면 아래 왼쪽에 작은 책 목록(같은 서버의 책 주소 링크)
    # prefix: 프록시 접두어(«/absproxy/8801» 또는 "")
    def latest_book(self, prefix):
        try:
            rows = [r for r in api_books({})["books"] if r.get("latest")]
            if not rows:
                return self.send_bytes(200, "<!doctype html><meta charset=utf-8><title>책</title><p>만든 책 없음</p>".encode("utf-8"),
                                       MIME[".html"], {"Cache-Control": "no-store"})
            path = rows[0]["path"]
            html = safe("/" + path).read_text(encoding="utf-8")
            folder = quote(prefix + "/" + path.rsplit("/", 1)[0] + "/")
            base = f'<base href="{folder}">'
            html = re.sub(r"<head[^>]*>", lambda h: h.group(0) + base, html, count=1, flags=re.I) if re.search(r"<head[^>]*>", html, re.I) else base + html
            if len(rows) > 1:
                links = " · ".join(f'<a href="{quote(prefix + "/" + r["path"])}">{escape(r["book"])}</a>' for r in rows)
                bar = f'<div style="position:fixed;left:8px;bottom:8px;z-index:99;font:12px sans-serif;background:#fff;border:1px solid #ccc;border-radius:6px;padding:4px 8px">책: {links}</div>'
                html = re.sub(r"</body>", lambda b: bar + b.group(0), html, count=1, flags=re.I) if re.search(r"</body>", html, re.I) else html + bar
            return self.send_bytes(200, html.encode("utf-8"), MIME[".html"], {"Cache-Control": "no-store"})
        except HttpError as e:
            return self.json(e.status, e.payload)

    # 페이지 내주기(작업 폴더 파일 읽기 전용 + 책 스티커 api/notes) — 본 서버 /pg/ 도 이걸 부른다
    # method: GET · HEAD · POST · PATCH · DELETE / path: 작업 폴더 기준 «/…» 경로 / u: urlparse 결과(질의 문자열)
    def serve_page(self, method, path, u):
        try:
            # 책 스티커 — 책 html 옆 상대 경로 «api/notes»(본문은 json 만 · 다른 출처 폼 전송 막기)
            j = path.find("/api/notes")
            if j >= 0 and path[j + 10:j + 11] in ("", "/"):
                raw = b""
                if method in ("POST", "PATCH"):
                    if "application/json" not in (self.headers.get("Content-Type") or ""):
                        raise HttpError(415, "json 만")
                    n = int(self.headers.get("Content-Length") or 0)
                    if n > 64 * 1024:
                        self.close_connection = True
                        raise HttpError(413, "요청이 너무 큼")
                    raw = self.rfile.read(n) if n else b""
                q = {k: v[-1] for k, v in parse_qs(u.query, keep_blank_values=True).items()}
                code, obj = notes_api(method, path[:j], path[j + 10:], q, raw)
                return self.json(code, obj)
            if method not in ("GET", "HEAD"):
                raise HttpError(405, "읽기 전용")
            p = safe(path)
            if p.is_dir() and (p / "index.html").is_file():
                p = p / "index.html"
            if not p.is_file():
                raise HttpError(404, "파일 없음")
            if p.stat().st_size > MAX_RAW:
                raise HttpError(413, "파일이 너무 큼")
            return self.send_bytes(200, p.read_bytes(), MIME.get(p.suffix.lower(), "application/octet-stream"),
                                   {"Cache-Control": "no-store"})
        except HttpError as e:
            return self.json(e.status, e.payload)
        except (BrokenPipeError, ConnectionResetError):
            return None
        except Exception as e:
            log(logging.ERROR, "예외", "페이지", f"{method} {path}: {e}\n{traceback.format_exc()}")
            try:
                return self.json(500, {"error": f"서버 오류 — {type(e).__name__}: {e}"})
            except OSError:
                return None


# 키트 폴더 정하기 — --kit(작업 폴더 안이어야) → 작업 폴더/kit(AGENTS.md 있음) → 작업 폴더(옛 방식: 키트를 작업 폴더로 띄움)
# root: 작업 폴더 / given: --kit 값
def find_kit(root, given=None):
    if given:
        k = Path(given).expanduser().resolve()
        if not k.is_dir():
            sys.exit(f"키트 폴더 없음: {k}")
        if k != root and root not in k.parents:
            sys.exit(f"키트 폴더가 작업 폴더 밖: {k} (작업 폴더 {root})")
        return k
    if (root / "kit" / "AGENTS.md").is_file():
        return (root / "kit").resolve()
    return root


def main():
    global ROOT, KIT, GIT, SURVEY, FT, START_VIEW, PORT, PAGE_PORT
    # 콘솔 출력 인코딩 고정 — UTF-8 모드가 없는 윈도우(cp949)는 시작 메시지의 «—» 에서 UnicodeEncodeError 로 죽는다
    for st in (sys.stdout, sys.stderr):
        if st is not None and hasattr(st, "reconfigure"):
            st.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="devview — 코드 · md · git 이력 보기/편집 서버")
    ap.add_argument("root", nargs="?", default=".", help="작업 폴더 (기본: 현재 폴더)")
    ap.add_argument("--host", default="0.0.0.0", help="묶을 주소 (기본 0.0.0.0 — 대회 미리보기 조건)")
    ap.add_argument("--port", type=int, default=8701)
    ap.add_argument("--page-port", type=int, default=None,
                    help="페이지 서버 포트 — md 의 .html 링크를 여기서 연다 (기본 --port + 100 · 0 = 끔)")
    ap.add_argument("--log", default=None, help="로그 파일 (기본 ~/.devview/devview.log)")
    ap.add_argument("--survey", default=None, help="설문 도구 survey.py 경로 (기본: 작업 폴더 · 키트 · 로컬 스킬에서 찾음)")
    ap.add_argument("--kit", default=None, help="키트 폴더(작업 폴더 안) — 기본: 작업 폴더/kit 에 AGENTS.md 가 있으면 그것 · 없으면 작업 폴더")
    ap.add_argument("--tree", default=None, help="그래프 tree.json 경로 (기본: 작업 폴더/docs/flowtree/tree.json)")
    ap.add_argument("--start-view", default="graph", choices=["graph", "code"],
                    help="처음 보기 (기본 graph — 그래프 화면)")
    a = ap.parse_args()
    if sys.version_info < (3, 8):
        sys.exit("파이썬 3.8 이상 필요")
    ROOT = Path(a.root).expanduser().resolve()
    if not ROOT.is_dir():
        sys.exit(f"폴더 없음: {ROOT}")
    KIT = find_kit(ROOT, a.kit)
    missing = [x for x in ("index.html", "md.bundle.js", "monaco/vs/loader.js") if not (STATIC / x).is_file()]
    if missing:
        sys.exit(f"화면 파일 없음: {', '.join(missing)} (web/ 에서 npm run build)")
    logpath = setup_logging(a.log)
    GIT = Git(ROOT)
    SURVEY = load_survey(a.survey)
    FT = load_flowtree(a.tree)
    START_VIEW = a.start_view
    notify_start()
    try:
        srv = ThreadingHTTPServer((a.host, a.port), Handler)
    except OSError as e:
        sys.exit(f"포트 {a.port} 를 열 수 없음: {e}")
    srv.daemon_threads = True
    PORT = a.port
    page_port = a.port + 100 if a.page_port is None else a.page_port
    if page_port:
        try:
            psrv = ThreadingHTTPServer((a.host, page_port), PageHandler)
            psrv.daemon_threads = True
            threading.Thread(target=psrv.serve_forever, name="page", daemon=True).start()
            PAGE_PORT = page_port
        except (OSError, OverflowError) as e:           # 쓰는 중 · 65535 넘음(시험의 높은 빈 포트 + 100)
            log(logging.WARNING, "실패", "페이지", f"포트 {page_port} 를 열 수 없음 — .html 링크는 원문으로 엶: {e}")
    log(logging.INFO, "시작", "서버", f"{VERSION} {a.host}:{a.port} 작업 폴더 {ROOT} git {GIT.top or GIT.error}")
    shown = "localhost" if a.host in ("0.0.0.0", "", "::") else a.host
    print(f"devview {VERSION} — 작업 폴더 {ROOT}" + (f" · 키트 {KIT}" if KIT != ROOT else ""), flush=True)
    print(f"  주소 http://{shown}:{a.port}/   (IDE 미리보기에는 포트 {a.port} 입력)", flush=True)
    print(f"  git {GIT.top if GIT.ok else '없음 (' + (GIT.error or '') + ')'} · 로그 {logpath or '없음'}", flush=True)
    print(f"  설문 {'연결 (위쪽 «설문» 탭)' if SURVEY else '없음'}", flush=True)
    print(f"  페이지 {f'포트 {PAGE_PORT} (md 의 .html 링크를 여기서 엶)' if PAGE_PORT else '꺼짐'}", flush=True)
    print(f"  그래프 {'연결 (' + str(FT_WS.tree_path) + (')' if FT_WS.tree_path.is_file() else ' — 아직 없음)') if FT else 'flowtree 없음'}"
          " · Alt+Q = MAIN 마법봉", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        log(logging.INFO, "종료", "서버", "정지")


if __name__ == "__main__":
    main()
