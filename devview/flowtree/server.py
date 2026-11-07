# flowtree 서버 — 정적 화면 + API(데이터 · 유저 칸 저장 · 다시 스캔 · 변경 감지)
"""
실행: python server.py <tree.json> [--port 8786] [--host 127.0.0.1] [--root 프로젝트 루트(기본 현재 폴더)]
  devview 는 이 파일을 불러와 handle() 을 /ft/ 아래로 연결한다(서버 하나 · 포트 하나)
  GET  /               static/index.html
  GET  /static/<파일>   정적 자원(no-cache — 고친 화면이 옛 판으로 남는 캐시 방지)
  GET  /api/data       {tree, auto, user, check, version, meta(+ root · code_rel · docs = 노드 연결 문서 풀이)}
                       tree.json 이 없으면 빈 그래프 + meta.missing(경로) — 화면은 빈 그래프로 뜨고 첫 노드를 만들면 파일이 생김(개편 2026-11-03)
  GET  /api/version    {version} — tree · user 파일이나 코드가 바뀌면 값이 바뀜. 코드가 바뀌었으면 자동 다시 스캔
  GET  /api/source?file=<코드 루트 기준 .py 경로>   {file, text} — 펼침 단계 · 함수 패널의 실제 코드(코드 루트 밖 거부)
  POST /api/user       tree.user.json 저장(임시 파일 → 교체) → {ok, version, check, saved_at}
  POST /api/scan       다시 스캔 → {version}
  POST /api/act        {op, args} 유저(화면) 명령 — 질문 만들기 · 고치기 · 닫기 · 지우기 · 질문 선 잇기 · 끊기
                       · 설문 답(vote) · 작업 · 검증 고치기(edit) · 함수 표 칸(funcs) · 검증 항목 추가(check-add)
                       · 노드 추가 단추(node-add — 작업 · 검증 · 설문) → {ok, id, msg, version}
                       역할은 user 로 고정(flowtree_store 가 다른 역할 칸을 거부)
쓰는 쪽 규칙: tree.json = flowtree_store 하나(flowtree.py · 이 서버의 /api/act) · tree.auto.json = 스캐너 · tree.user.json = 이 서버(화면)만
파이썬 3.10 이상 · 표준 라이브러리만
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

# 이 파일이 있는 폴더 — scan_code · tree_check import 와 정적 자원 위치
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import flowtree_store  # noqa: E402
import scan_code  # noqa: E402
import tree_check  # noqa: E402

# 정적 자원 폴더
STATIC = HERE / "static"
# 확장자 → 내용 종류
CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8", ".js": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8", ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml", ".png": "image/png", ".woff2": "font/woff2", ".map": "application/json",
}
# 유저 칸 허용 키 → 값 종류
#   seen = 노드 id → 유저가 확인한 결과 기록 번호(seq) · questions · collapsed 는 옛 형식(받기만 하고 화면은 안 씀)
USER_KEYS = {"version": int, "picks": dict, "verify": dict, "questions": list, "edges": list,
             "nodes": list, "positions": dict, "collapsed": list, "seen": dict, "updated": str, "screen": int}
# 요청 본문 최대 크기(바이트)
MAX_BODY = 2 * 1024 * 1024
# 코드 원문 응답 최대 크기(바이트)
MAX_SOURCE = 512 * 1024
# 코드 변경 확인 최소 간격(초)
CODE_CHECK_SEC = 1.0


# 고정 형식 로그 한 줄 — 날짜 시간 | 종류 | 중요도 | 관련 로직 | 내용
# kind: 동작 · 에러 / level: INFO · WARN · ERROR / area: 저장 · 스캔 · 요청 / msg: 내용
def log(kind, level, area, msg):
    print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} | {kind} | {level} | {area} | {msg}", flush=True)


# 트리 작업 공간 — 파일 셋 · 스캔 · 변경 감지
class Workspace:
    # tree_path: tree.json 경로 / root: 프로젝트 루트(노드 doc 경로 기준 · 없으면 현재 폴더)
    def __init__(self, tree_path, root=None):
        # tree.json 경로
        self.tree_path = Path(tree_path).resolve()
        # 프로젝트 루트 — devview 는 작업 폴더를 넘김
        self.root = Path(root).resolve() if root else Path.cwd().resolve()
        # tree.auto.json 경로
        self.auto_path = self.tree_path.with_name("tree.auto.json")
        # tree.user.json 경로
        self.user_path = self.tree_path.with_name("tree.user.json")
        # 파일 쓰기 · 스캔 잠금
        self.lock = threading.Lock()
        # 마지막 스캔 때 코드 최신 수정 시각
        self.scanned_code_mtime = -1.0
        # 마지막 코드 변경 확인 시각
        self.code_checked_at = 0.0

    # tree.json 의 코드 루트 · 설정
    def code_config(self):
        # tree.json 내용
        tree = flowtree_store.read_json(self.tree_path, {}) or {}
        # code 칸
        code = tree.get("code", {})
        return (self.tree_path.parent / code.get("root", ".")).resolve(), code

    # 코드 폴더의 파이썬 파일 최신 수정 시각
    # root: 코드 루트
    def code_mtime(self, root):
        # 최신 시각
        latest = 0.0
        if not root.exists():
            return latest
        # 파이썬 파일 하나
        for path in scan_code.collect_files(root):
            try:
                latest = max(latest, path.stat().st_mtime)
            # 스캔 도중 지워진 파일
            except OSError:
                pass
        return latest

    # 코드가 바뀌었으면 다시 스캔(force 면 무조건)
    # force: 무조건 스캔
    def ensure_scan(self, force=False):
        if not self.tree_path.exists():
            return
        # 지금 시각
        now = time.time()
        if not force and now - self.code_checked_at < CODE_CHECK_SEC and self.auto_path.exists():
            return
        self.code_checked_at = now
        # 코드 루트 · 설정
        root, config = self.code_config()
        # 코드 최신 수정 시각
        mtime = self.code_mtime(root)
        if not force and mtime == self.scanned_code_mtime and self.auto_path.exists():
            return
        with self.lock:
            try:
                # 스캔 결과
                res = scan_code.scan(root, config)
            # 스캔 실패 — 화면에 오류로 남기고 계속
            except Exception as err:  # noqa: BLE001
                log("에러", "ERROR", "스캔", f"{type(err).__name__}: {err}")
                return
            self._write(self.auto_path, res)
            self.scanned_code_mtime = mtime
        log("동작", "INFO", "스캔", f"모듈 {len(res['modules'])} · 호출 {len(res['calls'])} · 위반 {len(res['violations'])}")

    # 임시 파일에 쓰고 교체(쓰다 끊겨도 원본이 반쯤 남지 않게 · 읽는 쪽이 열고 있으면 잠깐 쉬고 다시)
    # path: 대상 파일 / data: 내용
    def _write(self, path, data):
        flowtree_store.write_json(path, data)

    # 판 토큰 — 세 파일 수정 시각 묶음
    def version(self):
        # 파일 하나의 수정 시각(없으면 0)
        def mt(p):
            return f"{p.stat().st_mtime_ns}" if p.exists() else "0"
        return "-".join(mt(p) for p in (self.tree_path, self.user_path, self.auto_path))

    # 화면용 데이터 묶음
    def data(self):
        self.ensure_scan()
        flowtree_store.ensure_frames(self.tree_path)
        # 세 파일 내용
        tree = flowtree_store.read_json(self.tree_path, {}) or {}
        auto = flowtree_store.read_json(self.auto_path)
        user = flowtree_store.read_json(self.user_path, {}) or {}
        # 코드 루트
        root, _ = self.code_config()
        return {
            "tree": tree, "auto": auto, "user": user,
            "check": tree_check.check(tree, auto, user, root=self.root),
            "version": self.version(),
            "meta": {"tree_path": str(self.tree_path), "code_root": str(root), "root": str(self.root),
                     "missing": None if self.tree_path.exists() else str(self.tree_path),
                     "code_rel": self.rel_to_root(root), "docs": tree_check.resolve_docs(tree, self.root),
                     "file_types": self.file_types(tree), "screens": flowtree_store.SCREENS},
        }

    # 키트 폴더 — AGENTS.md 가 있는 작업 폴더(프로젝트 루트부터 위로 git 루트까지 처음 만난 곳 · 없으면 None)
    def kit_dir(self):
        for d in (self.root, *self.root.parents):
            if (d / "AGENTS.md").is_file():
                return d
            if (d / ".git").exists():
                break
        return None

    # 파일 노드 형식 — 노드 id → csv · pdf · md-task(과제 제공 md) · md-kit(키트 안 md) · other. 화면이 위 색 줄을 고름
    #   md 판정: 파일이 키트 폴더 안이면 키트 문서, 밖(git 루트의 과제 원본)이거나 키트 폴더가 없으면 과제 제공
    # tree: tree.json 내용
    def file_types(self, tree):
        # 키트 폴더 · 결과
        kit = self.kit_dir()
        out = {}
        for n in tree.get("nodes", []):
            if not isinstance(n, dict) or n.get("kind") != "file" or not n.get("id"):
                continue
            # 연결 파일 — 경로 칸이 없으면 제목(파일 이름)으로 형식만
            ref = tree_check.doc_ref(n)
            # 형식을 볼 이름
            name = ref[0] if ref else str(n.get("title") or "")
            # 확장자 · 실제 경로(경로 칸이 없으면 위치 모름 → 과제 제공으로 봄)
            ext = Path(name).suffix.lower()
            p = (self.root / ref[0]).resolve() if ref else None
            if ext in (".csv", ".pdf"):
                out[n["id"]] = ext[1:]
            elif ext == ".md":
                out[n["id"]] = "md-kit" if kit and p and (p == kit or kit in p.parents) else "md-task"
            else:
                out[n["id"]] = "other"
        return out

    # 프로젝트 루트 기준 상대 경로(/ 구분 · 루트 밖이면 None) — 화면이 devview 에 파일을 열어 달라고 할 때 씀
    # path: 절대 경로
    def rel_to_root(self, path):
        # 절대 경로
        p = Path(path).resolve()
        if p == self.root:
            return ""
        if self.root not in p.parents:
            return None
        return p.relative_to(self.root).as_posix()

    # 유저 칸 저장 — 키 · 값 종류 확인 후 교체
    # body: 요청 본문 사전
    def save_user(self, body):
        if not isinstance(body, dict):
            raise ValueError("유저 칸은 사전이어야 함")
        # 키 · 값
        for key, val in body.items():
            if key not in USER_KEYS:
                raise ValueError(f"모르는 키 «{key}»")
            if not isinstance(val, USER_KEYS[key]):
                raise ValueError(f"«{key}» 값 종류가 {USER_KEYS[key].__name__} 아님")
        body["updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
        with self.lock:
            self._write(self.user_path, body)
        log("동작", "INFO", "저장", f"tree.user.json (선택 {len(body.get('picks', {}))} · 질문 {len(body.get('questions', []))}"
                                   f" · 유저 선 {len(body.get('edges', []))} · 유저 노드 {len(body.get('nodes', []))})")
        # 다시 읽은 세 파일로 점검
        tree = flowtree_store.read_json(self.tree_path, {}) or {}
        auto = flowtree_store.read_json(self.auto_path)
        return {"ok": True, "version": self.version(), "check": tree_check.check(tree, auto, body, root=self.root),
                "saved_at": body["updated"]}

    # 유저(화면) 명령 — flowtree_store 로 tree.json 에 씀(역할 user 고정)
    # body: {op: 명령, args: 인자 사전}
    def act(self, body):
        if not isinstance(body, dict) or not isinstance(body.get("args", {}), dict):
            raise ValueError("본문은 {op, args}")
        # 명령 이름
        op = str(body.get("op") or "")
        if flowtree_store.OP_ROLES.get(op) != "user":
            raise ValueError(f"화면에서 못 쓰는 명령 «{op}»")
        try:
            # 실행 결과
            res = flowtree_store.apply(self.tree_path, "user", op, **body.get("args", {}))
        # 거부 — 400 으로
        except (flowtree_store.StoreError, TypeError) as err:
            raise ValueError(str(err)) from None
        log("동작", "INFO", "저장", f"tree.json 화면 명령 {op} — {res['msg']}")
        return {"ok": True, "id": res.get("id"), "msg": res["msg"], "version": self.version()}

    # 코드 원문 — 코드 루트 안 .py 파일만
    # rel: 코드 루트 기준 경로
    def source(self, rel):
        # 코드 루트
        root, _ = self.code_config()
        # 실제 파일 경로
        path = (root / rel).resolve()
        if root not in path.parents or path.suffix != ".py" or not path.is_file():
            return None
        if path.stat().st_size > MAX_SOURCE:
            raise ValueError(f"파일이 너무 큼: {rel}")
        return {"file": rel, "text": path.read_text(encoding="utf-8", errors="replace")}


# JSON 응답 묶음 — (상태 코드, 내용 종류, 바이트, 머리글)
# code: 상태 코드 / obj: 응답 사전
def json_reply(code, obj):
    return (code, "application/json; charset=utf-8", json.dumps(obj, ensure_ascii=False).encode("utf-8"),
            {"Cache-Control": "no-store"})


# 정적 파일 응답 묶음 — static 폴더 밖 경로 거부
# rel: 요청 경로(static 기준)
def static_reply(rel):
    # 실제 파일 경로
    path = (STATIC / rel).resolve()
    if STATIC not in path.parents and path != STATIC or not path.is_file():
        return json_reply(404, {"error": f"없음: {rel}"})
    return 200, CONTENT_TYPES.get(path.suffix, "application/octet-stream"), path.read_bytes(), {"Cache-Control": "no-cache"}


# 요청 하나 처리 — 단독 서버 · devview(/ft/ 아래로 연결) 공용. 반환 (상태 코드, 내용 종류, 바이트, 머리글)
# ws: 작업 공간 / method: GET · POST / target: 경로 + ?질의(앞 접두어 뗀 것) / raw: 요청 본문 바이트
def handle(ws, method, target, raw=b""):
    # 경로 · 질의 나누기
    u = urlparse(target)
    # 요청 경로
    path = u.path or "/"
    try:
        if method == "GET":
            if path in ("/", "/index.html"):
                return static_reply("index.html")
            if path.startswith("/static/"):
                return static_reply(path[len("/static/"):])
            if path == "/api/data":
                # tree.json 이 없어도 빈 그래프로(meta.missing) — 예시 tree 없이 시작 · 첫 노드를 만들면 파일이 생김
                return json_reply(200, ws.data())
            if path == "/api/version":
                ws.ensure_scan()
                return json_reply(200, {"version": ws.version()})
            if path == "/api/source":
                # 요청한 파일 경로
                rel = (parse_qs(u.query).get("file") or [""])[0]
                # 코드 원문
                res = ws.source(rel) if rel else None
                if res is None:
                    return json_reply(404, {"error": f"코드 없음: {rel}"})
                return json_reply(200, res)
            return json_reply(404, {"error": f"없음: {path}"})
        if method == "POST":
            if len(raw or b"") > MAX_BODY:
                return json_reply(413, {"error": "본문이 너무 큼"})
            # 본문 사전
            body = json.loads(raw.decode("utf-8") or "null") if raw else None
            if path == "/api/user":
                return json_reply(200, ws.save_user(body))
            if path == "/api/scan":
                ws.ensure_scan(force=True)
                return json_reply(200, {"version": ws.version()})
            if path == "/api/act":
                return json_reply(200, ws.act(body))
            return json_reply(404, {"error": f"없음: {path}"})
        return json_reply(405, {"error": f"허용 안 됨: {method}"})
    # 형식 오류 — 400
    except (ValueError, json.JSONDecodeError) as err:
        log("에러", "WARN", "요청", f"{method} {path} 거부 — {err}")
        return json_reply(400, {"error": str(err)})
    # 처리 중 예외 — 500 으로 알리고 로그
    except Exception as err:  # noqa: BLE001
        log("에러", "ERROR", "요청", f"{method} {path} — {type(err).__name__}: {err}")
        return json_reply(500, {"error": f"{type(err).__name__}: {err}"})


# 요청 처리기 — 서버마다 작업 공간 하나(처리 본체는 handle)
class Handler(BaseHTTPRequestHandler):
    # 작업 공간(서버 시작 때 지정)
    ws = None

    # 기본 접속 로그 끔(고정 형식 로그만 사용)
    # fmt: 형식 / args: 값
    def log_message(self, fmt, *args):
        pass

    # 처리 결과 보내기
    # res: (상태 코드, 내용 종류, 바이트, 머리글)
    def reply(self, res):
        # 상태 코드 · 내용 종류 · 바이트 · 머리글
        code, ctype, data, headers = res
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        # 머리글 이름 · 값
        for k, v in headers.items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    # GET 처리
    def do_GET(self):
        self.reply(handle(self.ws, "GET", self.path))

    # POST 처리 — 본문이 너무 크면 읽지 않고 거부
    def do_POST(self):
        # 본문 길이
        size = int(self.headers.get("Content-Length") or 0)
        if size > MAX_BODY:
            self.reply(json_reply(413, {"error": "본문이 너무 큼"}))
            return
        self.reply(handle(self.ws, "POST", self.path, self.rfile.read(size) if size else b""))


# 서버 만들기(시험에서 포트 0 으로 띄울 때도 사용)
# tree_path: tree.json / host: 바인딩 주소 / port: 포트 / root: 프로젝트 루트(없으면 현재 폴더)
def make_server(tree_path, host="127.0.0.1", port=8786, root=None):
    # 작업 공간
    ws = Workspace(tree_path, root)
    ws.ensure_scan(force=True)
    # 이 서버 전용 처리기 클래스
    handler = type("FlowtreeHandler", (Handler,), {"ws": ws})
    return ThreadingHTTPServer((host, port), handler)


# 명령줄 실행
def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    # 명령줄 해석기
    ap = argparse.ArgumentParser(description="flowtree 서버 — 기능 · 결정 트리 + 코드 연결 보기")
    ap.add_argument("tree", help="tree.json 경로")
    ap.add_argument("--host", default="127.0.0.1", help="바인딩 주소(대회 IDE 브라우저에서 보려면 0.0.0.0)")
    ap.add_argument("--port", type=int, default=8786, help="포트(기본 8786 — 8790 은 설문 서버)")
    ap.add_argument("--root", default=".", help="프로젝트 루트 — 노드 doc 경로의 기준(기본 현재 폴더)")
    # 해석 결과
    args = ap.parse_args(argv)
    if not Path(args.tree).exists():
        log("에러", "ERROR", "시작", f"tree.json 없음: {args.tree}")
        return 1
    if not (STATIC / "index.html").exists():
        log("에러", "ERROR", "시작", f"화면 파일 없음: {STATIC / 'index.html'} — web 폴더에서 npm run build")
        return 1
    # 서버
    srv = make_server(args.tree, args.host, args.port, root=args.root)
    log("동작", "INFO", "시작", f"http://{args.host}:{srv.server_address[1]}/ · {Path(args.tree).resolve()}")
    try:
        srv.serve_forever()
    # Ctrl+C
    except KeyboardInterrupt:
        log("동작", "INFO", "종료", "Ctrl+C")
    return 0


if __name__ == "__main__":
    sys.exit(main())
