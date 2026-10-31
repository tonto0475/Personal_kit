#!/usr/bin/env python3
# whoami.py 시험 — 임시 Codex 홈(CODEX_HOME)에 세션 목록 · 기록 파일을 만들고 실제로 실행해 판정
#   python3 -m pytest -q .agents/skills/ready-start
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

# 시험 대상 스크립트
TOOL = Path(__file__).resolve().with_name("whoami.py")
# 세션 셋 — MAIN 은 이름을 두 번 바꿈(옛 이름 «새 세션» 줄이 남음) · 옛 세션 하나가 MAIN 이름을 먼저 썼음
MAIN = "01a20000-0000-7000-8000-000000000001"
INSP = "01a20000-0000-7000-8000-000000000002"
OLD = "01a20000-0000-7000-8000-000000000003"


# 임시 Codex 홈 만들기 — 목록 파일 + 세션마다 기록 파일
# home: 임시 폴더
def make_home(home: Path) -> None:
    rows = [{"id": OLD, "thread_name": "MAIN", "updated_at": "2026-10-30T01:00:00Z"},
            {"id": MAIN, "thread_name": "새 세션", "updated_at": "2026-10-31T01:00:00Z"},
            {"id": INSP, "thread_name": "INSP", "updated_at": "2026-10-31T01:01:00Z"},
            {"id": MAIN, "thread_name": "MAIN", "updated_at": "2026-10-31T01:02:00Z"}]
    (home / "session_index.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    day = home / "sessions" / "2026" / "10" / "31"
    day.mkdir(parents=True)
    for uid in (MAIN, INSP, OLD):
        (day / f"rollout-2026-10-31T10-00-00-{uid}.jsonl").write_text(
            json.dumps({"type": "session_meta", "payload": {"id": uid}}) + "\n", encoding="utf-8")


# 스크립트 실행 → (종료코드, 표준 출력, 표준 오류)
# home: 임시 Codex 홈 / args: 인자
def run(home: Path, *args: str) -> tuple:
    r = subprocess.run([sys.executable, str(TOOL), *args], capture_output=True, encoding="utf-8", timeout=60,
                       env={**os.environ, "CODEX_HOME": str(home)})
    return r.returncode, r.stdout, r.stderr


def test_mark_then_find_picks_own_session(tmp_path):
    make_home(tmp_path)
    code, mark, _ = run(tmp_path, "mark")
    mark = mark.strip()
    assert code == 0 and mark.startswith("WHOAMI-")
    # Codex 가 mark 출력을 INSP 세션 기록에 적은 상황
    rec = next((tmp_path / "sessions").rglob(f"*{INSP}.jsonl"))
    with open(rec, "a", encoding="utf-8") as f:
        f.write(json.dumps({"type": "response_item", "payload": {"output": mark}}) + "\n")
    code, out, _ = run(tmp_path, "find", mark)
    got = json.loads(out)
    assert code == 0 and got["uuid"] == INSP and got["name"] == "INSP" and got["session_file"].endswith(f"{INSP}.jsonl")


def test_find_without_record_is_1(tmp_path):
    make_home(tmp_path)
    code, _, err = run(tmp_path, "find", "WHOAMI-0000")
    assert code == 1 and "따로" in err


def test_name_falls_back_to_start_prompt(tmp_path):
    # /rename 을 안 해 이름이 자동 이름뿐이어도 — 띄울 때 넣은 첫 메시지 '$insp' 로 찾는다(AGENTS 지시문 줄은 건너뜀)
    home = tmp_path
    (home / "session_index.jsonl").write_text(
        json.dumps({"id": INSP, "thread_name": "검증 세션 시작하기", "updated_at": "2026-10-31T01:01:00Z"}) + "\n", encoding="utf-8")
    day = home / "sessions" / "2026" / "10" / "31"
    day.mkdir(parents=True)

    def rec(uid, first, src="user"):
        rows = [{"type": "session_meta", "payload": {"id": uid, "thread_source": src}},
                {"type": "response_item", "payload": {"type": "message", "role": "user",
                                                      "content": [{"type": "input_text", "text": "# AGENTS.md instructions for /k"}]}},
                {"type": "response_item", "payload": {"type": "message", "role": "user",
                                                      "content": [{"type": "input_text", "text": first}]}}]
        (day / f"rollout-2026-10-31T10-00-00-{uid}.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n",
                                                                      encoding="utf-8")

    rec(INSP, "$insp")
    rec(MAIN, "$ready-start")
    rec("01a20000-0000-7000-8000-000000000009", "$insp", src="guardian_review")
    code, out, _ = run(home, "name", "INSP")
    assert code == 0 and json.loads(out)["uuid"] == INSP and json.loads(out)["how"] == "prompt", out
    code, out, _ = run(home, "name", "MAIN")
    assert code == 0 and json.loads(out)["uuid"] == MAIN, out
    code, _, err = run(home, "name", "2ND")
    assert code == 1 and "$2nd" in err


def test_find_skips_guardian_review_thread(tmp_path):
    # «Approve for me» 승인 판정은 하위 세션(thread_source guardian_review · parent_thread_id)을 따로 만들고
    # 판정할 명령 글을 읽어 표식이 그 기록에도 남는다(2026-10-31 연습 IDE · 엔진 0.166 실측) → find 는 유저 세션 하나만
    make_home(tmp_path)
    code, mark, _ = run(tmp_path, "mark")
    mark = mark.strip()
    day = tmp_path / "sessions" / "2026" / "10" / "31"
    rec = next(day.glob(f"*{MAIN}.jsonl"))
    rec.write_text(json.dumps({"type": "session_meta", "payload": {"id": MAIN, "thread_source": "user"}}) + "\n"
                   + json.dumps({"type": "response_item", "payload": {"output": mark}}) + "\n", encoding="utf-8")
    guard = "01a20000-0000-7000-8000-000000000009"
    (day / f"rollout-2026-10-31T10-00-05-{guard}.jsonl").write_text(
        json.dumps({"type": "session_meta", "payload": {"id": guard, "thread_source": "guardian_review",
                                                         "parent_thread_id": MAIN}}) + "\n"
        + json.dumps({"type": "response_item", "payload": {"input": f"whoami.py find {mark}"}}) + "\n", encoding="utf-8")
    code, out, _ = run(tmp_path, "find", mark)
    rows = [json.loads(x) for x in out.splitlines() if x.strip()]
    assert code == 0 and [r["uuid"] for r in rows] == [MAIN], rows


def test_find_bad_mark_is_2(tmp_path):
    make_home(tmp_path)
    assert run(tmp_path, "find", "abc")[0] == 2


def test_name_uses_latest_line_and_latest_owner(tmp_path):
    make_home(tmp_path)
    # MAIN 이름은 옛 세션과 지금 세션이 둘 다 가짐 → 가장 최근에 MAIN 이 된 것
    code, out, err = run(tmp_path, "name", "MAIN")
    assert code == 0 and json.loads(out)["uuid"] == MAIN and "2개" in err
    # 옛 이름(«새 세션»)으로는 안 걸림
    assert run(tmp_path, "name", "새 세션")[0] == 1


# INSP 기록에 turn_context(실제 적용값) 두 개 — 마지막 것이 기준
def add_turns(home: Path, mark: str, effort: str = "high") -> None:
    rec = next((home / "sessions").rglob(f"*{INSP}.jsonl"))
    with open(rec, "a", encoding="utf-8") as f:
        f.write(json.dumps({"type": "turn_context", "payload": {"model": "gpt-6.1-sol", "effort": "low",
                            "approval_policy": "on-request", "approvals_reviewer": "user"}}) + "\n")
        f.write(json.dumps({"type": "turn_context", "payload": {"model": "gpt-6.1-sol", "effort": effort,
                            "approval_policy": "on-request", "approvals_reviewer": "auto_review",
                            "sandbox_policy": {"type": "workspace-write"}}}) + "\n")
        f.write(json.dumps({"type": "response_item", "payload": {"output": mark}}) + "\n")


def test_check_all_match(tmp_path):
    make_home(tmp_path)
    add_turns(tmp_path, "WHOAMI-c1")
    code, out, _ = run(tmp_path, "check", "WHOAMI-c1", "--name", "INSP", "--effort", "high")
    assert code == 0 and out.count("맞음 |") == 4 and "다름" not in out and "workspace-write" in out


def test_check_effort_mismatch_is_1(tmp_path):
    make_home(tmp_path)
    add_turns(tmp_path, "WHOAMI-c2", effort="medium")
    code, out, _ = run(tmp_path, "check", "WHOAMI-c2", "--name", "INSP", "--effort", "high")
    assert code == 1 and "다름 | 생각 강도: medium (기대 high)" in out


def test_check_name_missing_tells_rename(tmp_path):
    make_home(tmp_path)
    add_turns(tmp_path, "WHOAMI-c3")
    code, out, _ = run(tmp_path, "check", "WHOAMI-c3", "--name", "2ND", "--effort", "high")
    assert code == 1 and "/rename 2ND" in out


def test_check_name_other_session(tmp_path):
    make_home(tmp_path)
    add_turns(tmp_path, "WHOAMI-c4")
    code, out, _ = run(tmp_path, "check-name", "INSP", "--effort", "high")
    assert code == 0 and out.count("맞음 |") == 4
    code, out, _ = run(tmp_path, "check-name", "2ND", "--effort", "medium")
    assert code == 1 and "/rename 2ND" in out
    # MAIN 은 대화가 한 번도 안 돈 세션 — 적용값 없음 안내
    code, out, _ = run(tmp_path, "check-name", "MAIN", "--effort", "medium")
    assert code == 1 and "적용값 기록이 없음" in out


def test_list_newest_first(tmp_path):
    make_home(tmp_path)
    code, out, _ = run(tmp_path, "list")
    lines = out.strip().splitlines()
    assert code == 0 and len(lines) == 3 and lines[0].endswith("MAIN") and MAIN in lines[0]
