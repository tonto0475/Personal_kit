#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kit worklog — docs/WORKLOG.md 에 덧붙이기만(기존 줄은 안 건드림)

    ./kit worklog add --section 1-2 --kind 구현 --did "한 일" [--files "a.py · b.py"] [--run "명령 → 결과"] [--commit 해시] [--start-commit 해시]
    ./kit worklog fact --type "AI 제안 고침" "1-2 · 재시도가 끝없이 돎 → 재현 테스트 실패 확인 → 3회 제한 · a1b2c3"

- add = «## 기록» 맨 끝에 «### 시각 · 섹션 · 종류» 한 덩어리 · 칸마다 한 줄
- fact = «## 서술형 재료» 칸 끝에 «- [유형] 문장» 한 줄
- 맨 위 «🔄 인계» 칸은 고쳐 쓰는 글이라 도구 밖 — $hand-off 가 파일에서 직접
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import KitError, Doc, doc_path, one_line, now_short, run  # noqa: E402

FACT_TYPES = ("핵심 동작", "AI 제안 고침", "설계 결정", "장애 대응", "안 한 것", "더 고칠 것")


def cmd_add(doc, a):
    sec = one_line("section", a.section, 20)
    kind = one_line("kind", a.kind, 30)
    did = one_line("did", a.did, 300)
    if not did:
        raise KitError("--did(한 일)은 꼭 준다")
    rows = [("한 일", did), ("바뀐 파일", one_line("files", a.files, 300)), ("실행 · 결과", one_line("run", a.run, 300)),
            ("커밋", one_line("commit", a.commit, 80)), ("섹션 시작 커밋", one_line("start-commit", a.start_commit, 80))]
    block = ["", f"### {now_short()} · {sec} · {kind}"] + [f"- **{k}**: {v}" for k, v in rows if v]
    lines = doc.lines
    while lines and lines[-1].strip() == "":
        lines.pop()
    at = len(lines) + 2
    lines += block + [""]
    doc.save()
    print(f"WORKLOG 덧붙임 · {doc.path.name}:{at} · {sec} · {kind}")
    return 0


def cmd_fact(doc, a):
    if a.type not in FACT_TYPES:
        raise KitError(f"--type 은 {' · '.join(FACT_TYPES)} 중 하나")
    text = one_line("문장", a.text, 300)
    lines = doc.lines
    try:
        s = next(i for i, l in enumerate(lines) if l.startswith("## 서술형 재료"))
    except StopIteration:
        raise KitError("«## 서술형 재료» 절이 없음 — WORKLOG 양식과 다름")
    e = next((i for i in range(s + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
    # 절 안 마지막 «- » 줄 다음 · 없으면 머리 설명(«>») 다음
    last = max((i for i in range(s + 1, e) if lines[i].startswith("- ") or lines[i].startswith("> ")), default=s)
    lines.insert(last + 1, f"- [{a.type}] {text}")
    doc.save()
    print(f"서술형 재료 덧붙임 · {doc.path.name}:{last + 2} · [{a.type}]")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="kit worklog", description="WORKLOG 덧붙이기(기존 줄 불변)")
    ap.add_argument("--doc", default=None, help="WORKLOG 경로(기본 키트 docs/WORKLOG.md)")
    sub = ap.add_subparsers(dest="cmd", required=True, metavar="명령")
    p = sub.add_parser("add", help="기록 한 덩어리")
    p.add_argument("--section", required=True, help="섹션 번호(섹션 밖이면 «전체»)")
    p.add_argument("--kind", required=True, help="섹션 시작 · 구현 · 검증 요청 · 디버깅 N회차 · 수정 · 논의 변경")
    p.add_argument("--did", required=True, help="한 일(한 줄)")
    p.add_argument("--files", default=None, help="바뀐 파일")
    p.add_argument("--run", default=None, help="실행 · 결과(명령 → 통과 · 실패 수 · 종료코드)")
    p.add_argument("--commit", default=None)
    p.add_argument("--start-commit", dest="start_commit", default=None, help="섹션 시작 기록일 때만")
    p = sub.add_parser("fact", help="서술형 재료 한 줄")
    p.add_argument("--type", required=True, help=" · ".join(FACT_TYPES))
    p.add_argument("text", help="섹션 · 무엇을 무엇으로 확인 · 커밋")
    a = ap.parse_args(argv)
    with Doc(doc_path(a.doc, "docs/WORKLOG.md")) as doc:
        return {"add": cmd_add, "fact": cmd_fact}[a.cmd](doc, a)


if __name__ == "__main__":
    run(main)
