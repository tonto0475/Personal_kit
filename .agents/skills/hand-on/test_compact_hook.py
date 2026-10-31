# compact_hook.py 시험 — 가짜 훅 입력(stdin JSON)으로 PreCompact 스냅숏 · SessionStart(compact) 출력을 본다
#   python3 -m pytest -q .agents/skills/hand-on
import json
import os
import subprocess
import sys
from pathlib import Path

HOOK = Path(__file__).resolve().parent / "compact_hook.py"


def msg(role, text):
    kind = "input_text" if role == "user" else "output_text"
    return json.dumps({"type": "response_item", "payload": {"type": "message", "role": role,
                                                            "content": [{"type": kind, "text": text}]}}, ensure_ascii=False)


def run(ev, snapdir):
    env = dict(os.environ, CODEX_HANDOFF_DIR=str(snapdir))
    r = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(ev, ensure_ascii=False), capture_output=True,
                       text=True, encoding="utf-8", env=env, timeout=30)
    return r


# ======= 준비: 대화 기록 12턴 + 도구 출력 · WORKLOG 인계 칸이 있는 작업 폴더 =======
def make_case(tmp_path):
    rec = tmp_path / "rollout.jsonl"
    lines = []
    for i in range(1, 13):
        lines.append(msg("user", f"질문{i}"))
        lines.append(json.dumps({"type": "response_item", "payload": {"type": "function_call_output", "output": "도구출력"}}))
        lines.append(msg("assistant", f"답{i}"))
    rec.write_text("\n".join(lines) + "\n", encoding="utf-8")
    work = tmp_path / "work"
    (work / "docs").mkdir(parents=True)
    (work / "docs" / "WORKLOG.md").write_text(
        "# WORKLOG\n\n> [!abstract] 🔄 인계 — 칸\n> - **지금 하던 일**: 2절 구현\n\n---\n\n## 0. 기준선\n본문\n", encoding="utf-8")
    return rec, work


def test_precompact_saves_snapshot_and_prints_nothing(tmp_path):
    rec, work = make_case(tmp_path)
    snaps = tmp_path / "snaps"
    r = run({"hook_event_name": "PreCompact", "session_id": "abcd1234-xxxx", "transcript_path": str(rec),
             "cwd": str(work), "trigger": "auto"}, snaps)
    assert r.returncode == 0
    assert r.stdout.strip() == ""                       # 모델로 가는 출력 없음
    files = list(snaps.glob("abcd1234_*.md"))
    assert len(files) == 1
    s = files[0].read_text(encoding="utf-8")
    assert "질문12" in s and "답12" in s and "질문3" in s  # 마지막 10턴 = 3~12
    assert "질문2\n" not in s and "[유저] 질문2" not in s
    assert "도구출력" not in s                           # 도구 출력은 뺀다
    assert "지금 하던 일**: 2절 구현" in s                # 인계 칸
    assert "기준선" not in s.split("## WORKLOG 인계 칸")[1]  # --- 뒤는 안 가져옴


def test_sessionstart_compact_outputs_context_with_snapshot(tmp_path):
    rec, work = make_case(tmp_path)
    snaps = tmp_path / "snaps"
    run({"hook_event_name": "PreCompact", "session_id": "abcd1234-xxxx", "transcript_path": str(rec),
         "cwd": str(work), "trigger": "manual"}, snaps)
    r = run({"hook_event_name": "SessionStart", "session_id": "abcd1234-xxxx", "source": "compact", "cwd": str(work)}, snaps)
    assert r.returncode == 0
    out = json.loads(r.stdout)
    ctx = out["hookSpecificOutput"]["additionalContext"]
    assert out["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    assert "$hand-on" in ctx and "2절 구현" in ctx
    assert "질문12" not in ctx and str(snaps) in ctx       # 10턴 본문 대신 스냅숏 경로(한도 2500토큰)
    assert len(ctx) <= 2100
    assert "4) 내 역할 스킬 파일을 직접 다시 읽는다" in ctx and "~/.codex/skills/<역할>/SKILL.md" in ctx  # 압축 뒤 역할 맥락 복구
    assert "…(한도 때문에 잘림" not in ctx                # 한도 안에 다 들어간다


def test_sessionstart_compact_without_snapshot_says_so(tmp_path):
    _, work = make_case(tmp_path)
    r = run({"hook_event_name": "SessionStart", "session_id": "ffff0000", "source": "compact", "cwd": str(work)},
            tmp_path / "none")
    ctx = json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"]
    assert "스냅숏 없음" in ctx and "2절 구현" in ctx


def test_other_events_and_bad_input_are_silent(tmp_path):
    for ev in ({"hook_event_name": "SessionStart", "source": "startup"}, {"hook_event_name": "Stop"}):
        r = run(ev, tmp_path / "s")
        assert r.returncode == 0 and r.stdout.strip() == ""
    env_r = subprocess.run([sys.executable, str(HOOK)], input="not json", capture_output=True, text=True,
                           encoding="utf-8", timeout=30)
    assert env_r.returncode == 0 and env_r.stdout.strip() == ""
