#!/usr/bin/env python3
# 세션 이름 확인 — «나는 MAIN · INSP · 2ND 중 누구인가» 와 «이름 → UUID»
#   python3 ~/.codex/skills/ready-start/whoami.py mark            표식 한 줄 출력(1단계 — 이 출력이 내 세션 기록에 남는다)
#   python3 ~/.codex/skills/ready-start/whoami.py find 표식        표식이 든 세션 기록 = 나 → UUID · 이름 · 기록 파일(2단계)
#   python3 ~/.codex/skills/ready-start/whoami.py name MAIN        이름 → UUID · 기록 파일(같은 이름이 여럿이면 가장 최근 것)
#   python3 ~/.codex/skills/ready-start/whoami.py list             세션 목록(UUID 마다 지금 이름 · 갱신 시각)
#   python3 ~/.codex/skills/ready-start/whoami.py check 표식 --name MAIN --effort medium [--model gpt-6.1-sol] [--reviewer auto_review]
#                                                         표식으로 내 세션을 찾아 «실제 적용된» 이름 · 모델 · 생각 강도 · 승인 방식을 기대값과 비교
#                                                         (세션 기록의 마지막 turn_context 를 읽음 · 하나라도 다르면 종료코드 1)
#   python3 ~/.codex/skills/ready-start/whoami.py check-name INSP --effort high   다른 세션을 이름으로 찾아 같은 검사(MAIN 이 셋을 다 볼 때)
#
# 왜 두 단계인가
#   - 세션 기록(~/.codex/sessions/…/rollout-시각-UUID.jsonl)에는 이름이 없고, 이름은 세션 목록 파일(~/.codex/session_index.jsonl)에만 있다
#   - 세션은 자기 UUID 를 모른다 — 세 세션이 동시에 돌면 «목록 맨 끝 = 나» 는 틀릴 수 있다
#   - 그래서 1단계에서 아무도 모르는 표식을 출력 → Codex 가 그 출력을 내 세션 기록에 적는다 → 2단계에서 표식이 든 기록 파일을 찾으면 그게 나
# 목록 파일 규칙: 이름을 바꾸면 같은 UUID 로 새 줄이 붙는다 → UUID 마다 updated_at 이 가장 최신인 줄의 이름이 지금 이름
# 종료코드: 0 찾음 · 1 못 찾음(표식이 아직 기록에 안 적힘 · 이름 없음) · 2 폴더 · 인자 오류
# 표준 라이브러리만 · 읽기 전용(아무 파일도 쓰지 않는다)
from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import sys
from pathlib import Path

# Codex 홈 폴더 — CODEX_HOME 이 있으면 그것
HOME = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
# 기록 파일 이름 끝의 UUID
UUID_RE = re.compile(r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\.jsonl$")
# 표식 머리 — 대화 속 다른 글과 겹치지 않게
MARK = "WHOAMI-"


# 목록 파일 → UUID 마다 지금 이름 줄(dict). 없으면 빈 dict
def current_names() -> dict:
    # 목록 파일
    index = HOME / "session_index.jsonl"
    # UUID → 가장 최신 줄
    latest = {}
    if not index.exists():
        return latest
    for line in index.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        uid = row.get("id")
        if uid and (uid not in latest or str(row.get("updated_at", "")) > str(latest[uid].get("updated_at", ""))):
            latest[uid] = row
    return latest


# UUID → 세션 기록 파일(가장 최근 것). 없으면 None
def session_file(uid: str):
    # 후보 파일
    hits = sorted((HOME / "sessions").rglob(f"*{uid}.jsonl"), key=lambda p: p.stat().st_mtime)
    return hits[-1] if hits else None


# 결과 한 줄(json) 출력
def emit(uid: str, names: dict, how: str) -> None:
    row = names.get(uid, {})
    f = session_file(uid)
    print(json.dumps({"uuid": uid, "name": row.get("thread_name"), "updated_at": row.get("updated_at"),
                      "session_file": str(f) if f else None, "how": how}, ensure_ascii=False))


# 1단계 — 표식 출력
def cmd_mark(_args) -> int:
    print(MARK + secrets.token_hex(8))
    return 0


# 유저가 연 세션 기록인가 — 첫 줄(session_meta)의 thread_source 가 «user» 가 아니면 아니다
#   «Approve for me» 승인 판정은 «Guardian review» 라는 하위 세션(thread_source guardian_review · parent_thread_id)을 따로 만들고,
#   판정할 명령 글을 그대로 읽어 표식이 그 기록에도 남는다 → 빼지 않으면 find 가 UUID 를 두 개 내고, 재시작 명령이 검토 세션을 열 수 있다
#   (2026-10-31 연습 IDE 실측 · 엔진 0.166) · 옛 형식처럼 thread_source 가 없으면 유저 세션으로 본다
def user_thread(path: Path) -> bool:
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            head = json.loads(fh.readline() or "{}")
    except ValueError:
        return True
    meta = head.get("payload") or {} if head.get("type") == "session_meta" else {}
    return meta.get("thread_source", "user") == "user" and not meta.get("parent_thread_id")


# 표식이 든 세션 기록의 UUID 목록(최근 것부터) · 폴더가 없으면 None
def mark_owners(mark: str, scan: int):
    root = HOME / "sessions"
    if not root.is_dir():
        return None
    # 최근 수정된 기록부터 — 지금 도는 세션은 방금 적혔다
    files = sorted(root.rglob("rollout-*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    found = []
    for f in files[:scan]:
        m = UUID_RE.search(f.name)
        if not m or not user_thread(f):
            continue
        with open(f, encoding="utf-8", errors="replace") as fh:
            if any(mark in line for line in fh):
                found.append(m.group(1))
    return list(dict.fromkeys(found))


# 표식 형식 · 찾기 공통 — (UUID 목록, 오류 종료코드)
def owners_or_fail(mark: str, scan: int):
    if not mark.startswith(MARK):
        print(f"표식은 {MARK} 로 시작해야 함 — 먼저 mark", file=sys.stderr)
        return None, 2
    found = mark_owners(mark, scan)
    if found is None:
        print(f"세션 기록 폴더 없음: {HOME / 'sessions'}", file=sys.stderr)
        return None, 2
    if not found:
        print("표식이 든 세션 기록 없음 — mark 와 find 를 같은 명령 안에서 부르지 말고 따로(기록은 명령이 끝난 뒤 적힌다)",
              file=sys.stderr)
        return None, 1
    return found, 0


# 2단계 — 표식이 든 세션 기록 찾기
def cmd_find(args) -> int:
    found, code = owners_or_fail(args.mark, args.scan)
    if code:
        return code
    names = current_names()
    for uid in found:
        emit(uid, names, "mark")
    return 0


# 세션 기록의 마지막 turn_context → 실제 적용된 모델 · 생각 강도 · 승인 · 샌드박스
def applied(path: Path) -> dict:
    last = {}
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if '"turn_context"' not in line:
                continue
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if d.get("type") == "turn_context":
                last = d.get("payload") or {}
    sb = last.get("sandbox_policy")
    return {"model": last.get("model"), "effort": last.get("effort"),
            "reviewer": last.get("approvals_reviewer"), "approval": last.get("approval_policy"),
            "sandbox": sb.get("type") if isinstance(sb, dict) else sb}


# 설정 검사 — 표식(check) 또는 이름(check-name)으로 세션을 찾고 이름 · 모델 · 강도 · 승인을 기대값과 비교
def cmd_check(args) -> int:
    if getattr(args, "by_name", None):
        hits = sorted((r for r in current_names().values() if r.get("thread_name") == args.by_name),
                      key=lambda r: str(r.get("updated_at", "")))
        if not hits:
            print(f"다름 | 이름: 이름이 «{args.by_name}» 인 세션 없음 — 그 창에서 /rename {args.by_name}")
            return 1
        uid = hits[-1]["id"]
        args.name = args.by_name
    else:
        found, code = owners_or_fail(args.mark, args.scan)
        if code:
            return code
        uid = found[0]
    f = session_file(uid)
    name = current_names().get(uid, {}).get("thread_name")
    if f and not applied(f).get("model"):
        print(f"참고 | 세션 {uid[:8]} 은 아직 대화가 한 번도 안 돌아 적용값 기록이 없음 — 그 창에서 첫 지시 뒤 다시")
    got = applied(f) if f else {}
    rows = [("이름", args.name, name), ("모델", args.model, got.get("model")),
            ("생각 강도", args.effort, got.get("effort")), ("승인 방식", args.reviewer, got.get("reviewer"))]
    bad = 0
    print(f"세션 {uid[:8]} · 기록 {f}")
    for label, want, have in rows:
        if want is None:
            continue
        ok = str(have).lower() == str(want).lower()
        bad += not ok
        print(f"{'맞음' if ok else '다름'} | {label}: {have} (기대 {want})")
    print(f"참고 | 승인 정책 {got.get('approval')} · 샌드박스 {got.get('sandbox')}")
    if name != args.name and args.name:
        print(f"→ 이름이 안 붙음 — 이 창에서 /rename {args.name} 를 한 번 치고 다시 check")
    return 1 if bad else 0


# 역할 → 그 세션을 띄울 때 넣는 시작 메시지(ReadyStart.txt 명령의 '$insp' 등) — 이름(/rename)이 없을 때 이것으로 찾는다
ROLE_PROMPTS = {"MAIN": ("$main", "$ready-start"), "INSP": ("$insp",), "2ND": ("$2nd",)}


# 세션 기록의 첫 «유저가 보낸» 메시지 — 자동으로 들어가는 AGENTS 지시문(«# AGENTS.md …» · «<…>»)은 건너뛴다
def first_user_text(path: Path, limit: int = 400) -> str:
    with open(path, encoding="utf-8", errors="replace") as fh:
        for n, line in enumerate(fh):
            if n >= limit:
                break
            if '"role":"user"' not in line.replace(" ", ""):
                continue
            try:
                p = json.loads(line).get("payload") or {}
            except ValueError:
                continue
            if p.get("type") != "message" or p.get("role") != "user":
                continue
            text = " ".join(c.get("text", "") for c in p.get("content") or [] if isinstance(c, dict)).strip()
            if text and not text.startswith(("# AGENTS.md", "<")):
                return text
    return ""


# 시작 메시지로 역할 세션 찾기 — 유저 세션(검토 세션 제외) 중 첫 메시지가 그 역할 프롬프트로 시작하는 것, 최근 것부터
def by_prompt(name: str):
    prompts = ROLE_PROMPTS.get(name.upper(), ("$" + name.lower(),))
    root = HOME / "sessions"
    if not root.is_dir():
        return None
    for f in sorted(root.rglob("rollout-*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)[:80]:
        m = UUID_RE.search(f.name)
        if m and user_thread(f) and first_user_text(f).startswith(prompts):
            return m.group(1)
    return None


# 이름 → UUID. 같은 이름이 여럿이면 가장 최근에 그 이름이 된 것 · 이름이 없으면 시작 메시지로(/rename 안 해도 됨)
def cmd_name(args) -> int:
    names = current_names()
    hits = [r for r in names.values() if r.get("thread_name") == args.name]
    if not hits:
        uid = by_prompt(args.name)
        if uid:
            emit(uid, names, "prompt")
            return 0
        print(f"«{args.name}» 세션 없음 — 이름도 없고, 시작 메시지({' · '.join(ROLE_PROMPTS.get(args.name.upper(), ('$' + args.name.lower(),)))})로 시작한 세션도 없다",
              file=sys.stderr)
        return 1
    hits.sort(key=lambda r: str(r.get("updated_at", "")))
    if len(hits) > 1:
        print(f"같은 이름 {len(hits)}개 — 가장 최근 것을 고름", file=sys.stderr)
    emit(hits[-1]["id"], names, "name")
    return 0


# 세션 목록 — 최근 갱신 순
def cmd_list(_args) -> int:
    for row in sorted(current_names().values(), key=lambda r: str(r.get("updated_at", "")), reverse=True):
        print(f"{row.get('updated_at', '')}  {row['id']}  {row.get('thread_name')}")
    return 0


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="세션 이름 확인")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("mark")
    p = sub.add_parser("find")
    p.add_argument("mark")
    p.add_argument("--scan", type=int, default=50, help="최근 기록 파일 몇 개까지 볼지")
    p = sub.add_parser("name")
    p.add_argument("name")
    sub.add_parser("list")
    p = sub.add_parser("check")
    p.add_argument("mark")
    p.add_argument("--name")
    p.add_argument("--model", default="gpt-6.1-sol")
    p.add_argument("--effort")
    p.add_argument("--reviewer", default="auto_review", help="Approve for me = auto_review · 유저 승인 = user")
    p.add_argument("--scan", type=int, default=50)
    # 다른 세션을 이름으로 — MAIN 이 INSP · 2ND 설정을 검사할 때(그 세션이 한 번은 대화를 돌았어야 적용값이 있음)
    p = sub.add_parser("check-name")
    p.add_argument("by_name")
    p.add_argument("--model", default="gpt-6.1-sol")
    p.add_argument("--effort")
    p.add_argument("--reviewer", default="auto_review")
    args = ap.parse_args()
    return {"mark": cmd_mark, "find": cmd_find, "name": cmd_name, "list": cmd_list, "check": cmd_check,
            "check-name": cmd_check}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
