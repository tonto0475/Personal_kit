#!/usr/bin/env python3
# 압축 전후 훅 — Codex hooks.json 이 부른다(직접 실행은 시험용). 표준 라이브러리만
#   PreCompact             → 스냅숏 파일 저장: 압축 직전 10턴(유저 · 어시스턴트 말만) · git 상태 · 최근 커밋 · WORKLOG 인계 칸
#                            출력 없음(PreCompact 출력은 모델에 안 들어간다 — 스크립트 실행만)
#   SessionStart(compact)  → 모델에 넣을 글(additionalContext) 출력: «방금 압축됨 → $hand-on 절차» + 인계 칸 + 가장 최근 스냅숏 «경로»
#                            (본문은 안 싣는다 — 기본 한도 2500토큰 · 0.163 내장 스키마와 공식 문서 확인 10/30)
#   그 밖의 이벤트          → 아무것도 안 함
# 왜: 모델이 판단해서 쓰는 인계는 유저가 압축 전에 $hand-off 로 남긴다. 자동 압축이 갑자기 걸려도 직전 대화가 남게 하는 안전망
#
# 입력: stdin JSON — hook_event_name · session_id · transcript_path · cwd · trigger(PreCompact) · source(SessionStart)
# 스냅숏 위치: ~/.handoff/<세션 앞 8자리>_<UTC 시각>.md (CODEX_HANDOFF_DIR 로 바꿈) — 과제 저장소 밖이라 git 에 안 섞인다
# 시험: python3 -m pytest -q .agents/skills/hand-on
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from last_turns import last_turns, read_events  # noqa: E402  같은 폴더의 10턴 뽑기

TURNS = 10
LIMIT_CHARS = 2000      # SessionStart additionalContext 기본 한도 2500토큰 — 한글 1글자가 1토큰 넘게 잡힐 수 있어 여유 있게


def snap_dir() -> Path:
    return Path(os.environ.get("CODEX_HANDOFF_DIR") or Path.home() / ".handoff")


# WORKLOG 맨 위 «🔄 인계» 칸 — 그 줄부터 다음 «---» 줄 앞까지. 없으면 빈 글
def handoff_block(cwd: Path) -> str:
    for p in (cwd / "docs" / "WORKLOG.md", cwd / "WORKLOG.md"):
        if not p.is_file():
            continue
        lines, out, on = p.read_text(encoding="utf-8", errors="replace").splitlines(), [], False
        for ln in lines:
            if "🔄 인계" in ln:
                on = True
            elif on and ln.strip() == "---":
                break
            if on:
                out.append(ln)
        if out:
            return f"({p})\n" + "\n".join(out)
    return ""


def git(cwd: Path, *args: str) -> str:
    try:
        r = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=10)
        return (r.stdout or r.stderr).strip()
    except (OSError, subprocess.SubprocessError) as e:
        return f"(git 실패: {e})"


# 스냅숏 글 만들기 — 압축 직전이라 파일 끝 10턴(이전 압축 표시는 무시)
def build_snapshot(ev: dict) -> str:
    cwd = Path(ev.get("cwd") or os.getcwd())
    out = [f"# 압축 직전 스냅숏 — {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
           f"- 세션 {ev.get('session_id')} · 압축 계기 {ev.get('trigger')} · 폴더 {cwd}", ""]
    tp = ev.get("transcript_path")
    out.append(f"## 압축 직전 {TURNS}턴 (유저 · 어시스턴트 말만)")
    if tp and Path(tp).is_file():
        picked, _, total = last_turns(read_events(Path(tp)), TURNS, ignore_compact=True)
        out.append(f"(기록 {tp} · 전체 {total}턴 중 마지막 {len(picked)}턴)")
        for i, t in enumerate(picked, 1):
            out.append(f"\n### {i}/{len(picked)}\n[유저] {t['user']}")
            out.extend(f"[어시스턴트] {m}" for m in t["assistant"])
    else:
        out.append(f"(대화 기록 경로 없음 · {tp})")
    out += ["", "## git", "```", git(cwd, "status", "--short", "--branch"), "", git(cwd, "log", "--oneline", "-5"), "```",
            "", "## WORKLOG 인계 칸", handoff_block(cwd) or "(인계 칸 없음)"]
    return "\n".join(out) + "\n"


def save_snapshot(ev: dict) -> Path:
    d = snap_dir()
    d.mkdir(parents=True, exist_ok=True)
    sid = str(ev.get("session_id") or "nosession")[:8]
    p = d / f"{sid}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}.md"
    p.write_text(build_snapshot(ev), encoding="utf-8")
    return p


# 이 세션의 가장 최근 스냅숏 — 없으면 None
def latest_snapshot(session_id: str | None) -> Path | None:
    d = snap_dir()
    if not d.is_dir():
        return None
    sid = str(session_id or "")[:8]
    files = sorted(d.glob(f"{sid}_*.md")) if sid else []
    return files[-1] if files else None


# 압축 직후 모델에 넣을 글
def context_after_compact(ev: dict) -> str:
    cwd = Path(ev.get("cwd") or os.getcwd())
    snap = latest_snapshot(ev.get("session_id"))
    parts = ["[압축 직후 안내 — 훅이 넣은 글] 방금 대화가 압축됐다. 작업을 이어 가기 전에 $hand-on 절차를 따른다:",
             "1) 아래 WORKLOG 인계 칸 2) 인계 칸의 «참조 중인 문서» 적힌 부분만 3) 아래 압축 직전 스냅숏(10턴)",
             "4) 내 역할 스킬 파일을 직접 다시 읽는다(모델은 $스킬 을 못 부른다) — MAIN=main · INSP=insp · 2ND=2nd,"
             " ~/.codex/skills/<역할>/SKILL.md · 세션 이름은 whoami.py mark → find, 이름이 없으면 압축 요약 · 시작 메시지로, 그것도 없으면 유저에게"
             " — 공통 대회 맥락 · 역할 · 0-1 시작할 때 읽을 문서가 압축 요약에서 빠졌을 수 있다",
             "5) 유저에게 «지금 하던 일 · 다음 할 일 · 열린 질문» 세 줄을 보여 주고 유저 한 마디를 기다린다. 확정한 값은 압축 요약이 아니라 문서에서 다시 확인한다.",
             "", "=== WORKLOG 인계 칸(MAIN 의 인계 — INSP · 2ND 는 참고만) ===", handoff_block(cwd) or "(인계 칸 없음 — $hand-off 가 안 됐을 수 있다. 유저에게 알린다)"]
    if snap:
        parts += ["", f"=== 압축 직전 스냅숏: {snap} — 이 파일을 읽어 10턴 · git 상태를 확인한다(본문은 한도 때문에 싣지 않음) ==="]
    else:
        parts += ["", "=== 압축 직전 스냅숏 없음 — PreCompact 훅이 안 돌았다. hand-on 3절(whoami → last_turns)로 직접 뽑는다 ==="]
    text = "\n".join(parts)
    # 모델에 넣는 글은 기본 2500토큰 한도(additionalContextLimit) — 한글이라 글자 수로 넉넉히 자른다
    return text if len(text) <= LIMIT_CHARS else text[:LIMIT_CHARS] + "\n…(한도 때문에 잘림 — WORKLOG 인계 칸을 직접 읽는다)"


def main() -> int:
    for s in (sys.stdout, sys.stderr):
        s.reconfigure(encoding="utf-8")
    try:
        ev = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        print("훅 입력 JSON 아님", file=sys.stderr)
        return 0                          # 훅 실패로 Codex 를 막지 않는다
    name = ev.get("hook_event_name")
    try:
        if name == "PreCompact":
            p = save_snapshot(ev)
            print(f"스냅숏 저장: {p}", file=sys.stderr)
        elif name == "SessionStart" and ev.get("source") == "compact":
            print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart",
                                                     "additionalContext": context_after_compact(ev)}},
                             ensure_ascii=False))
    except Exception as e:                # 어떤 실패도 압축 · 세션을 막지 않게 — 사유만 남긴다
        print(f"compact_hook 실패: {type(e).__name__}: {e}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
