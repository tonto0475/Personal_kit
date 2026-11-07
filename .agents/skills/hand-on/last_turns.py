#!/usr/bin/env python3
# 압축 직전 대화 뽑기 — Codex 세션 기록(jsonl)에서 유저 · 어시스턴트 메시지만 마지막 N턴
#   python3 ~/.codex/skills/hand-on/last_turns.py 기록파일 [--turns 10] [--ignore-compact] [--json]
#   기록 파일은 ready-start 스킬의 whoami.py 로 찾는다: whoami.py mark → (다음 명령) whoami.py find 표식 → session_file
#
# 무엇을 뽑나
#   - response_item 의 message 중 role 이 user · assistant 인 것의 글(input_text · output_text)
#   - 도구 호출 · 도구 출력 · 생각(reasoning) · developer 메시지는 뺀다
#   - Codex 가 넣은 글(<environment_context> 같은 태그 한 덩이 · AGENTS.md 주입 · 압축 요약)도 뺀다
#   - response_item 메시지가 하나도 없는 옛 형식이면 event_msg 의 user_message · agent_message 를 쓴다
# 턴 = 유저 메시지 하나 + 그 뒤 다음 유저 메시지 전까지의 어시스턴트 메시지
# 압축 표시(줄 종류에 compact 가 든 줄 — compacted · context_compacted)가 있으면 마지막 압축 표시 «직전» N턴, 없으면 파일 끝 N턴
# 길이 상한 없음(메시지를 자르지 않는다)
# 종료코드: 0 뽑음 · 1 메시지 없음 · 2 파일 · 인자 오류
# 표준 라이브러리만 · 읽기 전용
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# Codex 가 유저 자리에 넣는 글 — 태그 한 덩이(<environment_context>…</environment_context> 등)
INJECTED_TAG = re.compile(r"^\s*<([a-zA-Z_][\w-]*)[^>]*>.*</\1>\s*$", re.S)
# Codex 가 유저 자리에 넣는 글 — 머리말로 구별
INJECTED_HEAD = ("# AGENTS.md instructions", "<user_instructions>", "<environment_context>",
                 "Another language model started to solve this problem")


# Codex 가 넣은 글인가
def injected(text: str) -> bool:
    t = text.lstrip()
    return t.startswith(INJECTED_HEAD) or bool(INJECTED_TAG.match(t))


# message 항목의 글 이어 붙이기 — 글 조각(input_text · output_text · text)만
def message_text(payload: dict) -> str:
    parts = []
    for it in payload.get("content") or []:
        if isinstance(it, dict) and it.get("type") in ("input_text", "output_text", "text"):
            t = it.get("text") or ""
            if t and not (payload.get("role") == "user" and injected(t)):
                parts.append(t)
    return "\n".join(parts).strip()


# 기록 파일 → 사건 목록 [("user"|"assistant", 글) | ("compact", 줄 번호)]
def read_events(path: Path) -> list:
    main, fallback = [], []
    with open(path, encoding="utf-8", errors="replace") as fh:
        for no, line in enumerate(fh, 1):
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if not isinstance(d, dict):
                continue
            p = d.get("payload") if isinstance(d.get("payload"), dict) else {}
            kind, ptype = str(d.get("type")), str(p.get("type"))
            if "compact" in kind or "compact" in ptype:
                main.append(("compact", no))
                fallback.append(("compact", no))
            elif kind == "response_item" and ptype == "message" and p.get("role") in ("user", "assistant"):
                t = message_text(p)
                if t:
                    main.append((p["role"], t))
            elif kind == "event_msg" and ptype in ("user_message", "agent_message"):
                t = str(p.get("message") or "").strip()
                if t and not injected(t):
                    fallback.append(("user" if ptype == "user_message" else "assistant", t))
    # response_item 메시지가 하나라도 있으면 그것(event_msg 는 같은 내용의 사본)
    return main if any(k != "compact" for k, _ in main) else fallback


# 사건 목록 → (턴 목록, 압축 표시 줄 번호 목록, 전체 턴 수). 턴 = {"user": 글, "assistant": [글…]}
def last_turns(events: list, turns: int, ignore_compact: bool = False) -> tuple:
    marks = [v for k, v in events if k == "compact"]
    if marks and not ignore_compact:
        cut = max(i for i, (k, _) in enumerate(events) if k == "compact")
        events = events[:cut]
    groups = []
    for k, v in events:
        if k == "user":
            groups.append({"user": v, "assistant": []})
        elif k == "assistant" and groups:
            groups[-1]["assistant"].append(v)
    return groups[-turns:] if turns > 0 else [], marks, len(groups)


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="세션 기록에서 압축 직전 N턴(유저 · 어시스턴트 메시지만)")
    ap.add_argument("record", help="세션 기록 파일(whoami.py find 의 session_file)")
    ap.add_argument("--turns", type=int, default=10)
    ap.add_argument("--ignore-compact", action="store_true", help="압축 표시를 무시하고 파일 끝 N턴")
    ap.add_argument("--json", action="store_true", help="json 한 덩이로 출력")
    a = ap.parse_args()
    path = Path(a.record)
    if not path.is_file():
        print(f"기록 파일 없음: {path} — whoami.py find 의 session_file 을 준다", file=sys.stderr)
        return 2
    picked, marks, total = last_turns(read_events(path), a.turns, a.ignore_compact)
    if not picked:
        print("유저 · 어시스턴트 메시지 없음" + (" (마지막 압축 표시 앞)" if marks and not a.ignore_compact else ""),
              file=sys.stderr)
        return 1
    where = (f"마지막 압축 표시(줄 {marks[-1]}) 직전" if marks and not a.ignore_compact else "파일 끝")
    if a.json:
        print(json.dumps({"record": str(path), "compact_lines": marks, "where": where, "total_turns": total,
                          "turns": picked}, ensure_ascii=False))
        return 0
    print(f"기록 {path} · 압축 표시 줄 {len(marks)}개 · {where} {len(picked)}턴(그 앞 전체 {total}턴)")
    for i, t in enumerate(picked, 1):
        print(f"\n=== {i}/{len(picked)} ===")
        print(f"[유저] {t['user']}")
        for m in t["assistant"]:
            print(f"[어시스턴트] {m}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
