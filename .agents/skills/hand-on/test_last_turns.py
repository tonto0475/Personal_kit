#!/usr/bin/env python3
# last_turns.py 시험 — 도구 호출 · 출력 · 생각 · Codex 주입 글이 섞인 가짜 세션 기록을 만들고 실제로 실행해 판정
#   python3 -m pytest -q .agents/skills/hand-on
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

# 시험 대상 스크립트
TOOL = Path(__file__).resolve().with_name("last_turns.py")


# 기록 한 줄
def item(kind: str, payload: dict) -> dict:
    return {"timestamp": "2026-10-31T01:00:00Z", "type": kind, "payload": payload}


# 유저 · 어시스턴트 메시지 줄
def msg(role: str, text: str) -> dict:
    part = "input_text" if role == "user" else "output_text"
    return item("response_item", {"type": "message", "role": role, "content": [{"type": part, "text": text}]})


# 한 턴 — 유저 질문 → 생각 → 도구 호출 · 출력 → 어시스턴트 중간 말 · 최종 답
def turn(n: int) -> list:
    return [msg("user", f"질문 {n}"),
            item("turn_context", {"model": "gpt-6.1-sol", "effort": "medium"}),
            item("response_item", {"type": "reasoning", "summary": [{"type": "summary_text", "text": f"생각 {n}"}]}),
            item("response_item", {"type": "function_call", "name": "shell", "arguments": f"{{\"cmd\": \"도구호출 {n}\"}}"}),
            item("response_item", {"type": "function_call_output", "output": f"도구출력 {n}"}),
            item("response_item", {"type": "custom_tool_call", "name": "apply_patch", "input": f"패치 {n}"}),
            item("response_item", {"type": "custom_tool_call_output", "output": f"패치출력 {n}"}),
            msg("assistant", f"중간 {n}"),
            msg("assistant", f"답 {n}"),
            item("event_msg", {"type": "token_count", "info": None})]


# 기록 머리 — 세션 정보 · developer 지침 · Codex 가 유저 자리에 넣는 글
def head() -> list:
    return [item("session_meta", {"id": "01a20000-0000-7000-8000-000000000001"}),
            item("response_item", {"type": "message", "role": "developer",
                                   "content": [{"type": "input_text", "text": "<permissions instructions>개발자 지침</permissions instructions>"}]}),
            msg("user", "# AGENTS.md instructions for /home/user\n\n<INSTRUCTIONS>규칙</INSTRUCTIONS>"),
            msg("user", "<environment_context>\n  <cwd>/home/user</cwd>\n</environment_context>")]


# 줄 목록 → 기록 파일
def write(path: Path, rows: list) -> Path:
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    return path


# 스크립트 실행 → (종료코드, 표준 출력, 표준 오류)
def run(*args: str) -> tuple:
    r = subprocess.run([sys.executable, str(TOOL), *args], capture_output=True, encoding="utf-8", timeout=60)
    return r.returncode, r.stdout, r.stderr


# json 출력의 턴 목록
def turns_of(path: Path, *extra: str) -> list:
    code, out, err = run(str(path), "--json", *extra)
    assert code == 0, err
    return json.loads(out)["turns"]


def test_compact_takes_10_turns_before_marker(tmp_path):
    rows = head() + sum((turn(n) for n in range(1, 13)), [])
    rows += [item("compacted", {"message": "요약 글", "replacement_history": []}),
             item("event_msg", {"type": "context_compacted"}),
             msg("user", "Another language model started to solve this problem and produced a summary"),
             *turn(13), *turn(14)]
    got = turns_of(write(tmp_path / "rollout.jsonl", rows))
    assert [t["user"] for t in got] == [f"질문 {n}" for n in range(3, 13)]
    assert got[0]["assistant"] == ["중간 3", "답 3"] and got[-1]["assistant"] == ["중간 12", "답 12"]
    flat = json.dumps(got, ensure_ascii=False)
    for bad in ("도구호출", "도구출력", "패치", "생각", "environment_context", "AGENTS.md", "개발자 지침", "요약 글"):
        assert bad not in flat


def test_no_marker_takes_file_end(tmp_path):
    rows = head() + sum((turn(n) for n in range(1, 15)), [])
    got = turns_of(write(tmp_path / "rollout.jsonl", rows))
    assert [t["user"] for t in got] == [f"질문 {n}" for n in range(5, 15)]


def test_last_marker_wins_and_ignore_flag(tmp_path):
    rows = head() + turn(1) + [item("event_msg", {"type": "context_compacted"})] + sum((turn(n) for n in range(2, 6)), [])
    rows += [item("compacted", {"message": "둘째 압축"})] + turn(6)
    path = write(tmp_path / "rollout.jsonl", rows)
    assert [t["user"] for t in turns_of(path)] == [f"질문 {n}" for n in range(1, 6)]
    assert [t["user"] for t in turns_of(path, "--ignore-compact", "--turns", "2")] == ["질문 5", "질문 6"]


def test_text_output_is_untruncated(tmp_path):
    long = "가" * 5000
    path = write(tmp_path / "rollout.jsonl", head() + [msg("user", long), msg("assistant", "응")])
    code, out, _ = run(str(path))
    assert code == 0 and f"[유저] {long}" in out and "[어시스턴트] 응" in out and "1턴" in out


def test_event_msg_fallback(tmp_path):
    rows = [item("session_meta", {"id": "x"}),
            item("event_msg", {"type": "user_message", "message": "옛 형식 질문"}),
            item("response_item", {"type": "function_call", "name": "shell", "arguments": "{}"}),
            item("event_msg", {"type": "agent_message", "message": "옛 형식 답"})]
    got = turns_of(write(tmp_path / "rollout.jsonl", rows))
    assert got == [{"user": "옛 형식 질문", "assistant": ["옛 형식 답"]}]


def test_exit_codes(tmp_path):
    code, _, err = run(str(tmp_path / "없음.jsonl"))
    assert code == 2 and "기록 파일 없음" in err
    path = write(tmp_path / "rollout.jsonl", head() + [item("compacted", {"message": "요약"})] + turn(1))
    code, _, err = run(str(path))
    assert code == 1 and "압축 표시 앞" in err
