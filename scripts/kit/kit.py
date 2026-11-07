#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kit — 키트 도구 진입점(./kit · 윈도우는 kit.cmd)

    ./kit help                       도구 목록
    ./kit <도구> [하위 명령] -h      인자 상세
    ./kit <도구> … --args '<JSON>'   인자를 JSON 으로(셸 따옴표 · 한글 깨짐 방지)

--args 값: «[…]»(인자 목록 그대로) · «{"_": [위치 인자…], "옵션": 값}»(true = 플래그 · 목록 = 여러 번)
          · «@파일»(그 파일의 JSON) · «-»(표준입력 — 단 heredoc 은 규칙 자동 허용이 안 걸려 승인을 물을 수 있다)
옛 명령(python3 devview/flowtree/flowtree.py …)도 그대로 돈다 — kit 은 같은 스크립트를 부른다.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

KIT = Path(__file__).resolve().parents[2]
SKILLS = [Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")) / "skills", KIT / ".agents" / "skills", KIT / "skills_src"]


# 스킬 안 스크립트 — 설치본(~/.codex/skills) → 키트 원본(.agents/skills) → 설치 뒤 이름(skills_src)
def skill(name: str, file: str) -> Path:
    for d in SKILLS:
        p = d / name / file
        if p.is_file():
            return p
    return SKILLS[1] / name / file


# 도구 표 — 이름: (스크립트 또는 {하위 이름: 스크립트}, 하는 일, 언제)
# 하위 이름이 있는 도구는 «kit <도구> <하위> …» 의 <하위> 를 먹고 나머지를 넘긴다 · "" 키 = 하위 없이 부를 때
TOOLS = {
    "status": ("scripts/kit/status.py", "지금 상태 한 장 — 인계 · 그래프 할 일 · hand_off 🟠🔴 · 답 없는 설문 · 알림 · 미커밋", "세션 시작 · 압축 뒤 · 마법봉 · 섹션 시작 전 — 문서를 하나씩 열기 전에"),
    "graph": ({"": "devview/flowtree/flowtree.py", "skeleton": "skeleton/to_flowtree.py"}, "작업 그래프(flowtree) 명령 전부 · skeleton = 뼈대 묶음을 섹션 틀에", "노드 만들기 · 채우기 · start · done · run · answer · inbox — tree.json 직접 편집 금지"),
    "handoff": ("scripts/kit/handoff.py", "hand_off.md 형식 칸 — list · show · section-new · scope-approve · scope-change · verify-log · order-add · progress", "섹션 뼈대 · 승인 기호 · 검증 기록 행 · 작업 순서 줄 · 진행 결과(본문 글은 파일에서 직접)"),
    "worklog": ("scripts/kit/worklog.py", "WORKLOG 덧붙이기 — add(기록 한 덩어리) · fact(서술형 재료 한 줄)", "구현 · 검증 · 디버깅 · 수정이 끝날 때마다(인계 칸은 파일에서 직접)"),
    "commit": ("scripts/kit/commit.py", "정확한 파일만 커밋(. · -A · 폴더 거부)", "문서 · 코드를 고친 직후 — git add/commit 대신"),
    "notify": ("devview/notify.py", "알림 종 — add · list", "AGENTS.md 2-7 표의 때"),
    "notes": ("bookkit/notes.py", "책 스티커 — list · answer", "2ND 스티커 답"),
    "survey": (lambda: skill("survey", "survey.py"), "설문 — new · wait · result · open · serve", "$survey 절차대로"),
    "hub": (lambda: skill("codex-hub", "hub.py"), "코덱스 허브 — register · status · log · send · whoami", "$codex-hub 절차대로"),
    "magic": (lambda: skill("codex-hub", "magic.py"), "마법봉 요청 — show · answer-node …", "$main-magic · $2nd-magic 절차대로"),
    "book": ({"new": "bookkit/new_book.py", "build": "bookkit/engine/build_book.py"}, "과제 파악 책 — new(새 책) · build(빌드)", "$ontology 절차대로"),
    "analysis": (None, "분석 틀 — kit analysis <틀> …(bookkit/analysis/<틀>.py)", "$ontology 절차대로"),
    "contract": ("bookkit/contracts/check_contract.py", "계약 형식 검사", "$ontology 절차대로"),
    "skeleton": ({"plan": "skeleton/plan.py", "copy": "skeleton/copy_parts.py", "check": "skeleton/check.py"}, "뼈대 — plan(계획표) · copy(부품 복사) · check(냉시동 판정)", "skeleton/README 절차대로"),
    "ontology": ({"from-bookkit": "scripts/ontology/from_bookkit.py", "profile": "scripts/ontology/profile.py"}, "데이터 지도 — from-bookkit(책 → 지도 초안) · profile(자료 윤곽)", "$ontology 절차대로"),
    "env": ("scripts/envcheck/envcheck.py", "환경 점검", "$ready-start"),
    "race": ("scripts/race/race_check.py", "같은 요청 두 번 테스트 틀", "민감 섹션 동시성 검증"),
    "precheck": (lambda: skill("precheck", "precheck.py"), "사전 체험 왕복 점검", "$precheck(본선 흐름 밖)"),
    "config": ("scripts/codex_config/merge.py", "키트 Codex 설정 · 규칙(kit.rules) «없는 것만» 넣기", "$ready-start"),
}


def show_help() -> int:
    print("kit — 키트 도구(./kit <도구> -h 로 인자 상세 · 인자는 --args '<JSON>' 로도)")
    w = max(len(k) for k in TOOLS)
    for k, (_t, what, when) in TOOLS.items():
        print(f"  {k:<{w}}  {what}")
        print(f"  {'':<{w}}    언제: {when}")
    print("규칙: 형식 칸(그래프 · hand_off 기호 · 표 · WORKLOG · 커밋)은 kit 로만 · 본문 글은 파일에서 직접 · 글 인자는 한 줄")
    return 0


# --args 풀기 → 인자 목록
def expand_args(argv):
    if "--args" not in argv:
        return argv
    i = argv.index("--args")
    if i + 1 >= len(argv):
        sys.exit("거부: --args 뒤에 JSON · @파일 · - 중 하나")
    raw = argv[i + 1]
    if raw == "-":
        raw = sys.stdin.read()
    elif raw.startswith("@"):
        raw = Path(raw[1:]).read_text(encoding="utf-8")
    try:
        data = json.loads(raw)
    except ValueError as e:
        sys.exit(f"거부: --args JSON 해석 실패 — {e}")
    out = []
    if isinstance(data, list):
        out = [str(x) for x in data]
    elif isinstance(data, dict):
        out = [str(x) for x in data.get("_", [])]
        for k, v in data.items():
            if k == "_" or v is None or v is False:
                continue
            flag = k if k.startswith("-") else "--" + k.replace("_", "-")
            if v is True:
                out.append(flag)
            elif isinstance(v, list):
                for x in v:
                    out += [flag, str(x)]
            else:
                out += [flag, str(v)]
    else:
        sys.exit("거부: --args 는 목록 · 객체 JSON")
    return argv[:i] + out + argv[i + 2:]


def main() -> int:
    for st in (sys.stdout, sys.stderr):
        if hasattr(st, "reconfigure"):
            st.reconfigure(encoding="utf-8", errors="replace")
    argv = sys.argv[1:]
    if not argv or argv[0] in ("help", "-h", "--help"):
        return show_help()
    name, rest = argv[0], argv[1:]
    if name not in TOOLS:
        print(f"거부: 없는 도구 «{name}» — ./kit help", file=sys.stderr)
        return 2
    target = TOOLS[name][0]
    if name == "analysis":
        if not rest or rest[0].startswith("-"):
            names = sorted(p.stem for p in (KIT / "bookkit/analysis").glob("*.py") if not p.stem.startswith("_"))
            print("kit analysis <틀> … — 틀: " + " · ".join(names))
            return 0 if rest[:1] in ([], ["-h"], ["--help"]) else 2
        target, rest = f"bookkit/analysis/{rest[0]}.py", rest[1:]
    elif isinstance(target, dict):
        if rest and rest[0] in target and rest[0] != "":
            target, rest = target[rest[0]], rest[1:]
        elif "" in target:
            target = target[""]
        else:
            print(f"kit {name} <{' · '.join(target)}> …", file=sys.stderr)
            return 0 if rest[:1] in ([], ["-h"], ["--help"]) else 2
    script = target() if callable(target) else KIT / target
    if not Path(script).is_file():
        print(f"거부: 스크립트 없음 {script}", file=sys.stderr)
        return 2
    args = expand_args(rest)
    env = dict(os.environ, PYTHONUTF8="1")
    return subprocess.run([sys.executable, str(script), *args], env=env).returncode


if __name__ == "__main__":
    sys.exit(main())
