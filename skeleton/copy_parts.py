#!/usr/bin/env python3
# lib 부품 복사 — 카드가 고른 부품을 src · tests · 루트로 · from lib. import 를 복사한 자리로 · WORKLOG 한 줄 덧붙이기
"""
사용: python3 skeleton/copy_parts.py K0 [K3 auth …] [observe/obs_log.py …] [--app <앱 폴더>] [--lib <lib 폴더>] [--deploy-dir <루트>] [--why "이유"] [--dry]
- 묶음 이름(K0 · K1 · K2 · K3 · K5 · auth) 또는 lib 안 경로(observe/obs_log.py)
- 이미 있는 파일은 덮지 않는다(«있음» 한 줄) · 복사한 부품이 다른 lib 부품을 import 하면 그 부품도 같이
- WORKLOG(<앱>/docs/WORKLOG.md)는 맨 끝에 덧붙이기만 — 기존 줄을 건드리지 않음
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# 이 파일이 있는 폴더(skeleton) · 키트 폴더
HERE = Path(__file__).resolve().parent
KIT = HERE.parent
# 묶음 → lib 부품(lib 기준 경로)
BUNDLES = {
    "K0": ["observe/obs_log.py", "observe/obs_config.py", "observe/obs_health.py",
           "deploy/Dockerfile", "deploy/.dockerignore", "deploy/compose.yaml"],
    "K1": ["data/csv_load.py", "data/quality.py"],
    "K2": ["db/db_sqlite.py"],
    "K3": ["ui/upload_check.py", "ui/progress_confirm.py"],
    "K4": [],
    "K5": ["testing/boundary.py"],
    "auth": ["auth/auth_core.py", "auth/auth_web.py", "auth/auth_nicegui.py"],
}
# lib 분야 → 복사할 자리(앱 기준) · «<루트>» = 배포 폴더
DEST = {
    "observe": "src/observe", "data": "src/core", "judge": "src/core", "output": "src/core", "db": "src/db",
    "api": "src/api", "llm": "src/api", "ui": "src/ui", "testing": "tests", "deploy": "<루트>",
}
# 파일별 예외 자리 — 인증 핵심은 core(화면 · 웹 프레임워크 없음) · 웹 · 화면 부분은 ui
DEST_FILE = {"auth/auth_core.py": "src/core", "auth/auth_web.py": "src/ui", "auth/auth_nicegui.py": "src/ui"}
# from lib.x.y import … · import lib.x.y 를 찾는 정규식
LIB_IMPORT = re.compile(r"^(\s*)(from|import)\s+lib\.(\w+)\.(\w+)", re.M)


# lib 부품 → 복사할 자리(앱 기준 상대 · «<루트>» 그대로)
# part: lib 기준 경로
def 자리_찾기(part):
    if part in DEST_FILE:
        return DEST_FILE[part]
    # 분야
    area = part.split("/")[0]
    if area not in DEST:
        raise SystemExit(f"실패: 자리를 모르는 부품 — {part}")
    return DEST[area]


# 자리 → 파이썬 패키지 이름(src/core → src.core) · tests 는 같은 폴더라 이름만
# dest: 자리
def 패키지_이름(dest):
    return dest.replace("/", ".")


# 이름들 펼치기 — 묶음 이름 · 경로 → 부품 목록(의존 부품 포함 · 순서 유지 · 시험 파일 제외)
# names: 명령줄 이름 / lib: lib 폴더
def 부품_펼치기(names, lib):
    # 결과 · 볼 것
    out, queue = [], []
    # 이름
    for n in names:
        queue += BUNDLES[n] if n in BUNDLES else [n]
    while queue:
        # 부품
        part = queue.pop(0).replace("\\", "/")
        if part in out:
            continue
        if not (lib / part).is_file():
            raise SystemExit(f"실패: lib 에 없는 부품 — {part}")
        out.append(part)
        if part.endswith(".py"):
            # 부품이 부르는 lib 부품
            for m in LIB_IMPORT.finditer((lib / part).read_text(encoding="utf-8")):
                queue.append(f"{m.group(3)}/{m.group(4)}.py")
    return out


# import 바꾸기 — lib.<분야>.<모듈> → 복사한 자리
# text: 파일 글자
def 임포트_바꾸기(text):
    # 바꿀 함수
    def repl(m):
        # 원래 부품 · 자리
        part = f"{m.group(3)}/{m.group(4)}.py"
        dest = 자리_찾기(part)
        return f"{m.group(1)}{m.group(2)} {패키지_이름(dest)}.{m.group(4)}"
    return LIB_IMPORT.sub(repl, text)


# 배포 폴더 기본값 — 앱 폴더의 git 최상위(대회: <루트>) · git 이 아니면 앱 폴더
# app: 앱 폴더
def 배포_폴더(app):
    try:
        # git 최상위
        r = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=app, capture_output=True, text=True, encoding="utf-8")
        if r.returncode == 0 and r.stdout.strip():
            return Path(r.stdout.strip())
    # git 없음
    except OSError:
        pass
    return app


# 실행
# argv: 인자(없으면 sys.argv)
def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    # 해석기
    ap = argparse.ArgumentParser(description="lib 부품 복사")
    ap.add_argument("names", nargs="+", help="묶음(K0 · K1 · K2 · K3 · K5 · auth) 또는 lib 경로")
    ap.add_argument("--app", default=str(KIT), help="앱 폴더(기본 키트 = 작업 폴더)")
    ap.add_argument("--lib", default=str(KIT / "lib"), help="lib 폴더")
    ap.add_argument("--deploy-dir", default=None, help="Dockerfile 등을 둘 폴더(기본 git 최상위)")
    ap.add_argument("--why", default="", help="WORKLOG 에 남길 이유(기본 «뼈대 <묶음>»)")
    ap.add_argument("--dry", action="store_true", help="복사하지 않고 목록만")
    # 해석 결과
    a = ap.parse_args(argv)
    # 앱 · lib · 배포 폴더
    app, lib = Path(a.app).resolve(), Path(a.lib).resolve()
    deploy = Path(a.deploy_dir).resolve() if a.deploy_dir else 배포_폴더(app)
    # 부품 목록
    parts = 부품_펼치기(a.names, lib)
    # 복사한 것(WORKLOG 용)
    copied = []
    # 부품
    for part in parts:
        # 자리 · 대상 파일
        dest = 자리_찾기(part)
        folder = deploy if dest == "<루트>" else app / dest
        target = folder / Path(part).name
        # 보이는 경로
        shown = f"<루트>/{target.name}" if dest == "<루트>" else target.relative_to(app).as_posix()
        if target.exists():
            print(f"있음 — {shown}(덮지 않음)")
            continue
        if a.dry:
            print(f"복사 예정 — lib/{part} → {shown}")
            continue
        folder.mkdir(parents=True, exist_ok=True)
        # 새 패키지 폴더면 __init__.py
        if dest.startswith("src/") and not (folder / "__init__.py").exists():
            (folder / "__init__.py").write_text("", encoding="utf-8")
        # 원본 바이트
        raw = (lib / part).read_bytes()
        if part.endswith(".py"):
            target.write_text(임포트_바꾸기(raw.decode("utf-8")), encoding="utf-8")
        else:
            target.write_bytes(raw)
        copied.append(f"lib/{part} → {shown}")
        print(f"복사 — lib/{part} → {shown}")
    if copied and not a.dry:
        # 작업 기록 파일
        worklog = app / "docs" / "WORKLOG.md"
        worklog.parent.mkdir(parents=True, exist_ok=True)
        # 이유
        why = a.why or f"뼈대 {' · '.join(a.names)}"
        with worklog.open("a", encoding="utf-8") as f:
            f.write(f"\n- {datetime.now():%Y-%m-%d %H:%M} 부품 복사({why}): {' · '.join(copied)}\n")
        print(f"WORKLOG 한 줄 — {worklog}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
