#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kit status — 지금 상태 한 장(읽기 전용)

    ./kit status [--role main|2nd|insp] [--full]

한 번에 보이는 것: WORKLOG 인계 칸 · 그래프 할 일(inbox) · hand_off 섹션 상태(🟠 승인 대기 · 🔴 논의 · 검증 상자)
· 답 없는 설문 · (2nd) 답할 책 스티커 · 안 읽은 알림 · 커밋 안 된 파일 · 마지막 커밋
세션 시작 · 압축 뒤 · 마법봉 전에 문서를 하나씩 열기 전에 먼저 이것 하나.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import KIT, run  # noqa: E402
import handoff  # noqa: E402


def sh(args, limit=12):
    try:
        r = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=str(KIT),
                           env=dict(os.environ, PYTHONUTF8="1"), timeout=60)
        err = (r.stderr or "").strip().splitlines()
        out = (r.stdout or "").rstrip().splitlines() + ([f"(오류 · 종료코드 {r.returncode}) {err[-1][:200]}"] if r.returncode and err else [])
    except Exception as e:  # 한 칸이 실패해도 나머지는 보인다
        out = [f"(실행 실패) {e}"]
    if len(out) > limit:
        out = out[:limit] + [f"… {len(out) - limit}줄 더(--full)"]
    return out


def part(title, rows):
    print(f"## {title}")
    for r in rows or ["(없음)"]:
        print(f"  {r}")


def worklog_handover():
    p = KIT / "docs" / "WORKLOG.md"
    if not p.is_file():
        return ["(WORKLOG 없음)"]
    lines = p.read_text(encoding="utf-8").splitlines()
    i = next((k for k, l in enumerate(lines) if "🔄 인계" in l and l.startswith("> [!")), None)
    if i is None:
        return ["(인계 칸 없음)"]
    out = []
    for l in lines[i + 1:handoff.box_end(lines, i)]:
        t = l[1:].strip()
        # 양식 그대로(값이 비었거나 «(…)» 안내문)인 칸은 뺀다
        if t.startswith("- **") and "**:" in t:
            val = t.split("**:", 1)[1].strip()
            if val and not val.startswith("("):
                out.append(t[2:])
    return out or ["(인계 칸 비어 있음)"]


def handoff_state():
    p = KIT / "docs" / "hand_off.md"
    if not p.is_file():
        return ["(hand_off 없음)"]
    lines = p.read_text(encoding="utf-8").splitlines()
    out = []
    if handoff.PLACE_HEAD in lines:
        out.append("(양식의 빈 섹션 — ./kit handoff section-new 로 첫 섹션)")
    for n, name, risk, s, e in handoff.sections(lines):
        seg = lines[s:e]
        scope = next(("🟢" if "[!success]" in l else "🟠" for l in reversed(seg) if handoff.SCOPE_RE.match(l)), "—")
        red = sum(1 for l in seg if l.startswith("> - 🔴"))
        ver = next(("🟢" if "decision-done" in l else "🔴" for l in seg if handoff.VERIFY_RE.match(l)), "—")
        flag = " ⭐ 승인 대기" if scope == "🟠" else ""
        out.append(f"{n} · {name} — 수정 범위 {scope} · 🔴 논의 {red} · 검증 {ver}{flag} · hand_off.md:{s + 1}")
    return out


def surveys_pending():
    root = KIT / "docs" / "surveys"
    out = []
    if root.is_dir():
        for f in sorted(root.rglob("*.json")):
            if f.name.endswith((".result.json", ".draft.json")):
                continue
            try:
                d = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if isinstance(d, dict) and "questions" in d and not f.with_name(f.stem + ".result.json").exists():
                out.append(f"{f.stem} · {d.get('title', '')} · 유저 답 대기")
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(prog="kit status", description="지금 상태 한 장(읽기 전용)")
    ap.add_argument("--role", default=os.environ.get("KIT_ROLE", "main"), help="main · 2nd · insp(그래프 할 일 기준)")
    ap.add_argument("--full", action="store_true", help="줄 수 제한 없이")
    a = ap.parse_args(argv)
    lim = 10 ** 6 if a.full else 12
    py = sys.executable
    print(f"# kit status · 역할 {a.role} · {KIT}")
    part("인계(WORKLOG)", worklog_handover())
    part(f"그래프 할 일(inbox · {a.role})", sh([py, str(KIT / "devview/flowtree/flowtree.py"), "--role", a.role, "inbox"], lim))
    if a.role == "main":
        part("검증 노드(insp inbox)", sh([py, str(KIT / "devview/flowtree/flowtree.py"), "--role", "insp", "inbox"], 6 if not a.full else lim))
    part("hand_off 섹션", handoff_state())
    part("답 없는 설문", surveys_pending())
    if a.role == "2nd":
        part("답할 책 스티커", sh([py, str(KIT / "bookkit/notes.py"), "list"], lim))
    part("알림(안 읽음)", sh([py, str(KIT / "devview/notify.py"), "list", "--unread", "-n", "5"], 6))
    part("커밋 안 된 파일", sh(["git", "status", "--short"], 15 if not a.full else lim))
    part("마지막 커밋", sh(["git", "log", "-3", "--format=%h %s"], 3))
    return 0


if __name__ == "__main__":
    run(main)
