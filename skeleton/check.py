#!/usr/bin/env python3
# 냉시동 한 바퀴 판정 — 새 DB → 과제 자료 적용(K1 · K2) → 기본 계산(K4) → 앱 기동 · 주요 경로(K0 · K3) → 종료
"""
사용: python3 skeleton/check.py --task <과제 폴더> [--app <앱 폴더>] [--plan skeleton/out/plan.json] [--only K1 K2 …] [--entry K1=모듈:함수 …]
- 단계마다 «Kn 통과 · 실패 · 건너뜀 — 근거» 한 줄 · 첫 실패에서 멈춤(종료코드 1) · 전부 통과 · 건너뜀이면 0
- 아직 없는 묶음(진입 모듈이 없음) · 설치 안 된 바깥 라이브러리(nicegui · fastapi …)는 «건너뜀»
- 앱 기동은 빈 포트 · 새 DB(DB_PATH) · 띄운 프로세스만 PID 로 끔 · 판정은 프로세스 종료 · 응답 코드로(시간 아님 — 무언 정지 대비 상한만)
"""
from __future__ import annotations

import argparse
import importlib
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

# 이 파일이 있는 폴더(skeleton) · 키트 폴더
HERE = Path(__file__).resolve().parent
KIT = HERE.parent
# 진입점 기본값(계획표에 없을 때)
DEFAULT_ENTRY = {"K1": "src.core.입력:전부_읽기", "K2": "src.db.저장:적용", "K4": "src.core.계산:계획_계산"}
# 무언 정지 상한 초 — 앱이 죽지도 답하지도 않을 때만 쓰는 2차 가드
SILENT_LIMIT_SEC = 90


# 건너뜀 신호
class 건너뜀(Exception):
    pass


# 실패 신호
class 실패(Exception):
    pass


# 진입점 불러오기 — «모듈:함수» → 함수. 모듈이 없거나 바깥 라이브러리가 없으면 건너뜀
# spec: «모듈:함수»
def 진입점_불러오기(spec):
    # 모듈 이름 · 함수 이름
    mod_name, _, func_name = spec.partition(":")
    try:
        # 모듈
        mod = importlib.import_module(mod_name)
    # 모듈 · 라이브러리 없음
    except ModuleNotFoundError as err:
        # 못 찾은 이름
        missing = err.name or ""
        if mod_name == missing or mod_name.startswith(missing + "."):
            raise 건너뜀(f"묶음 없음({mod_name})")
        if not missing.startswith("src"):
            raise 건너뜀(f"라이브러리 없음({missing})")
        raise 실패(f"{mod_name} import 실패 — {err}")
    if not hasattr(mod, func_name):
        raise 실패(f"{mod_name} 에 {func_name} 없음")
    return getattr(mod, func_name)


# 행 수 — DataFrame · 목록 · 그 밖
# table: 표
def 행_수(table):
    return len(table) if hasattr(table, "__len__") else 0


# K1 — 과제 폴더 → tables · report
# entry: 진입점 / task: 과제 폴더
def 입력_단계(entry, task):
    # 결과
    r = 진입점_불러오기(entry)(task)
    if not isinstance(r, dict) or not isinstance(r.get("tables"), dict) or not isinstance(r.get("report"), list):
        raise 실패("돌려준 값이 {tables: {…}, report: […]} 모양이 아님")
    if not r["tables"]:
        raise 실패("tables 비어 있음")
    # 표마다 행 수
    sizes = {k: 행_수(v) for k, v in r["tables"].items()}
    return r, f"표 {len(sizes)}개({' · '.join(f'{k} {n}' for k, n in sizes.items())}) · 리포트 {len(r['report'])}줄"


# K2 — 새 DB 에 두 번 적용 → 행 수 · 판 번호 같음
# entry: 진입점 / tables: K1 표 / db: 새 DB 경로
def 저장_단계(entry, tables, db):
    # 적용 함수
    apply = 진입점_불러오기(entry)
    # 첫째 · 둘째 결과
    r1 = apply(db, tables)
    r2 = apply(db, tables)
    for r in (r1, r2):
        if not isinstance(r, dict) or "rows" not in r or "version" not in r:
            raise 실패("돌려준 값이 {version, rows} 모양이 아님")
    if r1["rows"] != r2["rows"]:
        raise 실패(f"같은 자료 두 번 → 행 수 달라짐 {r1['rows']} → {r2['rows']}")
    if r1["version"] != r2["version"]:
        raise 실패(f"같은 자료 두 번 → 판 번호 늘어남 {r1['version']} → {r2['version']}")
    if not any(r1["rows"].values()):
        raise 실패("적용 행 0")
    return f"판 {r1['version']} · 행 {r1['rows']} · 두 번 적용해도 같음"


# K4 — 정리된 표 → 결과(비어 있지 않음)
# entry: 진입점 / tables: K1 표
def 계산_단계(entry, tables):
    # 결과
    r = 진입점_불러오기(entry)(tables)
    if r is None or (hasattr(r, "__len__") and len(r) == 0):
        raise 실패("결과 비어 있음")
    return f"결과 {type(r).__name__} {len(r) if hasattr(r, '__len__') else ''}".strip()


# 빈 포트 하나
def 빈_포트():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# 주소 하나 부르기 → 상태 코드(연결 안 되면 None)
# url: 주소
def 부르기(url):
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            return resp.status
    # 4xx · 5xx
    except urllib.error.HTTPError as err:
        return err.code
    # 아직 안 뜸
    except (urllib.error.URLError, ConnectionError, socket.timeout, OSError):
        return None


# K0 · K3 — 앱을 띄워 /health · 페이지들 · 끔
# app: 앱 폴더 / module: 앱 모듈 / pages: 부를 경로 / db: 새 DB 경로 / log: 앱 출력 파일
def 앱_단계(app, module, pages, db, log):
    if not (app / Path(*module.split("."))).with_suffix(".py").is_file():
        raise 건너뜀(f"앱 모듈 없음({module})")
    # 포트 · 환경
    port = 빈_포트()
    env = dict(os.environ, PORT=str(port), DB_PATH=str(db), PYTHONUTF8="1")
    # 출력 파일
    with open(log, "w", encoding="utf-8") as out:
        # 앱 프로세스
        proc = subprocess.Popen([sys.executable, "-m", module], cwd=app, env=env, stdout=out, stderr=subprocess.STDOUT)
    try:
        # 시작 시각(무언 정지 상한용)
        started = time.monotonic()
        # 상태 코드
        code = None
        while code is None:
            if proc.poll() is not None:
                # 앱 출력
                text = Path(log).read_text(encoding="utf-8", errors="replace")
                if "ModuleNotFoundError" in text:
                    # 못 찾은 모듈 줄
                    line = next((ln for ln in text.splitlines() if "ModuleNotFoundError" in ln), "")
                    if "'src" not in line:
                        raise 건너뜀(f"라이브러리 없음 — {line.strip()}")
                raise 실패(f"앱이 종료코드 {proc.returncode} 로 꺼짐 — {text.strip().splitlines()[-1] if text.strip() else '출력 없음'}")
            if time.monotonic() - started > SILENT_LIMIT_SEC:
                raise 실패(f"무언 정지 — {SILENT_LIMIT_SEC}초 동안 죽지도 답하지도 않음(출력 {log})")
            code = 부르기(f"http://127.0.0.1:{port}/health")
            if code is None:
                time.sleep(0.3)
        # 경로 → 코드
        codes = {"/health": code}
        # 경로
        for p in pages:
            if p not in codes:
                codes[p] = 부르기(f"http://127.0.0.1:{port}{p}")
        return codes
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            # 안 꺼짐 — 그 PID 만 강제 종료
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()


# 실행
# argv: 인자(없으면 sys.argv)
def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    # 해석기
    ap = argparse.ArgumentParser(description="냉시동 한 바퀴 판정")
    ap.add_argument("--task", default=None, help="과제 폴더(K1 입력 · 없으면 K1 · K2 · K4 건너뜀)")
    ap.add_argument("--app", default=str(KIT), help="앱 폴더(기본 키트)")
    ap.add_argument("--plan", default=None, help="계획표(기본 <앱>/skeleton/out/plan.json · 없으면 기본 진입점)")
    ap.add_argument("--only", nargs="+", default=None, help="이 묶음만(K0 K1 K2 K3 K4)")
    ap.add_argument("--entry", action="append", default=[], help="진입점 바꾸기 «K1=모듈:함수»")
    # 해석 결과
    a = ap.parse_args(argv)
    # 앱 폴더
    app = Path(a.app).resolve()
    sys.path.insert(0, str(app))
    # 계획표
    plan_path = Path(a.plan) if a.plan else app / "skeleton" / "out" / "plan.json"
    plan = json.loads(plan_path.read_text(encoding="utf-8")) if plan_path.is_file() else {}
    # 진입점
    entry = dict(DEFAULT_ENTRY)
    entry.update({b["id"]: b["entry"] for b in plan.get("bundles", []) if b.get("entry")})
    for e in a.entry:
        # 묶음 · 값
        k, _, v = e.partition("=")
        entry[k] = v
    # 앱 모듈 · 페이지
    module = plan.get("app_module", "src.ui.app")
    pages = plan.get("pages", ["/", "/health"])
    # 돌릴 묶음
    want = set(a.only or ["K0", "K1", "K2", "K3", "K4"])
    # 임시 폴더 — 새 DB · 앱 출력
    tmp = Path(tempfile.mkdtemp(prefix="skeleton_check_"))
    # K1 결과
    tables = None

    # 한 줄 출력
    # k: 묶음 / state: 통과 · 실패 · 건너뜀 / why: 근거
    def say(k, state, why):
        print(f"{k} {state} — {why}", flush=True)

    # 단계 실행 — 통과면 True · 건너뜀 None · 실패 False
    # k: 묶음 / fn: 인자 없는 함수(근거 글자 돌려줌)
    def step(k, fn):
        try:
            say(k, "통과", fn())
            return True
        # 건너뜀
        except 건너뜀 as err:
            say(k, "건너뜀", err)
            return None
        # 실패 · 예상 못 한 예외
        except Exception as err:
            say(k, "실패", str(err) if isinstance(err, 실패) else f"{type(err).__name__}: {err}")
            return False

    # ── K1 ──
    if want & {"K1", "K2", "K4"}:
        if not a.task:
            say("K1", "건너뜀", "--task 없음")
        else:
            # K1 결과 칸
            box = {}

            # K1 실행
            def run_k1():
                box["r"], why = 입력_단계(entry["K1"], Path(a.task).resolve())
                return why
            ok = step("K1", run_k1)
            if ok is False:
                return 1
            tables = box["r"]["tables"] if ok else None
    # ── K2 · K4 ──
    for k, fn in (("K2", lambda: 저장_단계(entry["K2"], tables, tmp / "new.db")), ("K4", lambda: 계산_단계(entry["K4"], tables))):
        if k not in want:
            continue
        if tables is None:
            say(k, "건너뜀", "K1 결과 없음")
            continue
        if step(k, fn) is False:
            return 1
    # ── K0 · K3 ──
    if want & {"K0", "K3"}:
        # 앱 결과 칸
        box = {}

        # 앱 실행
        def run_app():
            box["codes"] = 앱_단계(app, module, pages, tmp / "app.db", tmp / "app_out.log")
            if box["codes"]["/health"] != 200:
                raise 실패(f"/health {box['codes']['/health']}")
            return f"{module} 기동 · /health 200 · 새 DB(DB_PATH)"
        ok = step("K0", run_app) if "K0" in want or "K3" in want else None
        if ok is False:
            return 1
        if "K3" in want:
            if not ok:
                say("K3", "건너뜀", "앱이 안 뜸")
            else:
                # 200 이 아닌 경로
                bad = {p: c for p, c in box["codes"].items() if c != 200}
                if bad:
                    say("K3", "실패", f"응답 200 아님 {bad}")
                    return 1
                say("K3", "통과", f"경로 {len(box['codes'])}개 200 ({' · '.join(box['codes'])})")
    print("냉시동: 끝(실패 없음)")
    # 통과면 이번 임시 폴더(새 DB · 앱 출력)만 지움 — 실패면 근거로 남김
    shutil.rmtree(tmp, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
