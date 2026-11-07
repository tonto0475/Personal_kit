#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kit commit — 정확한 파일 경로만 받아 그 파일만 커밋한다

    ./kit commit <파일> [<파일> …] -m "[섹션] 무엇 - 왜" [--role main]

- «.» · «-A» · «--all» · 와일드카드 · 폴더는 거부(다른 세션 · 서브의 변경이 섞이지 않게)
- git add -- <파일> → git commit -- <파일>(이미 스테이지된 다른 파일은 이 커밋에 안 들어간다)
- --role(또는 KIT_ROLE)을 주면 메시지 끝에 «Kit-Role: <역할>» 한 줄 · --trailer «키: 값» 은 여러 번
- ./kit 는 규칙(.codex/rules/kit.rules)으로 샌드박스 밖에서 돈다 → .git 쓰기 승인을 따로 묻지 않는다
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import KitError, one_line, run  # noqa: E402


def git(*args, check=True):
    r = subprocess.run(["git", *args], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if check and r.returncode != 0:
        raise KitError(f"git {' '.join(args[:2])} 실패: {(r.stderr or r.stdout).strip()[:300]}")
    return r


def main(argv=None):
    ap = argparse.ArgumentParser(prog="kit commit", description="정확한 파일만 커밋")
    ap.add_argument("paths", nargs="+", help="파일 경로(정확히 · 폴더 · 와일드카드 금지)")
    ap.add_argument("-m", "--message", required=True, help="커밋 메시지 «[섹션] 무엇 - 왜»(한 줄)")
    ap.add_argument("--role", default=os.environ.get("KIT_ROLE"), help="main · 2nd · 서브 이름")
    ap.add_argument("--trailer", action="append", default=[], help="메시지 끝 «키: 값» 한 줄(여러 번)")
    a = ap.parse_args(argv)
    msg = one_line("메시지", a.message, 300)
    for p in a.paths:
        if p in (".", "./", "-A", "--all", "*") or any(ch in p for ch in "*?[") or p.startswith("-"):
            raise KitError(f"«{p}» 는 안 됨 — 파일을 정확한 경로로 하나씩")
        if os.path.isdir(p):
            raise KitError(f"«{p}» 는 폴더 — 그 안의 파일을 하나씩")
        if not os.path.exists(p) and not git("ls-files", "--error-unmatch", "--", p, check=False).returncode == 0:
            raise KitError(f"«{p}» 없음(지운 파일이면 git 에 있던 파일이어야 함)")
    top = git("rev-parse", "--show-toplevel").stdout.strip()
    staged = [x for x in git("diff", "--cached", "--name-only").stdout.splitlines() if x]
    want = {Path(os.path.abspath(p)).resolve().as_posix() for p in a.paths}
    other = [x for x in staged if Path(top, x).resolve().as_posix() not in want]
    git("add", "--", *a.paths)
    tails = ([f"Kit-Role: {a.role}"] if a.role else []) + [one_line("trailer", t, 200) for t in a.trailer]
    full = msg + ("\n\n" + "\n".join(tails) if tails else "")
    r = git("commit", "-m", full, "--", *a.paths, check=False)
    if r.returncode != 0:
        out = (r.stdout + r.stderr).strip()
        if "nothing to commit" in out or "no changes added" in out:
            print("바뀐 것 없음 — 커밋 안 함")
            return 0
        raise KitError(f"git commit 실패: {out[:400]}")
    head = git("log", "-1", "--format=%h %s").stdout.strip()
    files = git("show", "--name-only", "--format=", "HEAD").stdout.split()
    print(f"커밋 {head} · 파일 {len(files)}개: {' · '.join(files)}")
    if other:
        print(f"참고: 다른 스테이지 파일 {len(other)}개는 이 커밋에 안 넣음 — {' · '.join(other[:5])}")
    return 0


if __name__ == "__main__":
    run(main)
