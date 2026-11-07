# compact_hook.py 시험 — 가짜 훅 입력(stdin JSON) · 가짜 대화 기록(jsonl)으로 SessionStart(compact) 참조 목록을 본다
#   python3 -m pytest -q .agents/skills/hand-on
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parent / "compact_hook.py"
SKILLS = HOOK.parents[1]          # .agents/skills
KIT = HOOK.parents[3]             # 키트 루트(docs/ 가 있는 곳)
LIMIT = 1500                      # 목표 600토큰 ≈ 한글 1,500자

sys.path.insert(0, str(HOOK.parent))
import compact_hook  # noqa: E402


def msg(role, text):
    kind = "input_text" if role == "user" else "output_text"
    return json.dumps({"type": "response_item", "payload": {"type": "message", "role": role,
                                                            "content": [{"type": kind, "text": text}]}}, ensure_ascii=False)


# 가짜 대화 기록 — 자동 지시문(AGENTS) 다음에 첫 유저 메시지 · 뒤에 압축 표시와 다른 말
def transcript(tmp_path, first):
    p = tmp_path / "rollout.jsonl"
    lines = [json.dumps({"type": "session_meta", "payload": {"id": "s1", "thread_source": "user"}}),
             msg("user", "# AGENTS.md instructions for /home/user/kit\n...")]
    if first:
        lines.append(msg("user", first))
    lines += [msg("assistant", "준비됨"), json.dumps({"type": "compacted", "payload": {"message": "요약"}}),
              msg("user", "$2nd 이건 나중 메시지라 판별에 안 쓴다")]
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def run(ev, codex_home):
    env = dict(os.environ, CODEX_HOME=str(codex_home))
    return subprocess.run([sys.executable, str(HOOK)], input=json.dumps(ev, ensure_ascii=False), capture_output=True,
                          text=True, encoding="utf-8", env=env, timeout=30)


def compact_ev(tp, cwd=KIT, sid="s1"):
    return {"hook_event_name": "SessionStart", "source": "compact", "session_id": sid,
            "transcript_path": str(tp) if tp else None, "cwd": str(cwd)}


# ======= 세 경우 — 첫 메시지 $main / $2nd / 역할 프롬프트 없음(뒤 메시지의 $2nd 는 안 본다) =======
@pytest.mark.parametrize("first, role", [("$main", "MAIN"), ("$2nd 파악시작", "2ND"), ("과제 README 읽어 줘", None)])
def test_compact_reference_list(tmp_path, first, role):
    r = run(compact_ev(transcript(tmp_path, first)), tmp_path / "codex")
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)                                   # 올바른 JSON
    hso = out["hookSpecificOutput"]
    assert hso["hookEventName"] == "SessionStart"
    ctx = hso["additionalContext"]
    assert ctx.startswith("[압축 직후 — 훅이 넣은 참조 목록] 아래는 경로다. 통째로 다시 읽지 말고")
    assert len(ctx) <= LIMIT, len(ctx)
    assert "docs/WORKLOG.md 맨 위 «🔄 인계» 칸" in ctx and "참조 중인 문서" in ctx
    assert "$hand-on" not in ctx and "스냅숏" not in ctx           # 옛 판(절차 · 스냅숏) 문구 없음
    heads = [ln for ln in ctx.splitlines() if not ln.startswith(("-", "["))]
    if role:
        assert f"내 역할 = {role}(첫 메시지 {first.split()[0]})" in ctx
        assert not any(h.rstrip(":") in compact_hook.REFS for h in heads)  # 다른 역할 묶음 없음
        assert f"스킬 {role.lower()} " in ctx
    else:
        assert "역할 못 정함" in ctx and "내 역할 줄만" in ctx
        assert [h for h in heads if h.endswith(":")] == ["MAIN:", "2ND:"]


# ======= 세션 이름(/rename)이 있으면 첫 메시지보다 먼저 =======
def test_role_by_session_name(tmp_path):
    home = tmp_path / "codex"
    home.mkdir()
    (home / "session_index.jsonl").write_text(json.dumps({"id": "s9", "thread_name": "2ND",
                                                          "updated_at": "2026-11-01T00:00:00Z"}) + "\n", encoding="utf-8")
    r = run(compact_ev(transcript(tmp_path, "$main"), sid="s9"), home)
    assert "내 역할 = 2ND(세션 이름 2ND)" in json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"]


# ======= 루트에서 뜬 세션(cwd = 루트 · 키트는 그 아래 kit/) → 키트 경로 =======
def test_kit_under_root(tmp_path):
    (tmp_path / "kit" / "docs").mkdir(parents=True)
    (tmp_path / "kit" / "docs" / "WORKLOG.md").write_text("# WORKLOG\n", encoding="utf-8")
    r = run(compact_ev(None, cwd=tmp_path), tmp_path / "codex")
    assert f"키트(작업 폴더) = {tmp_path / 'kit'} " in json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"]


# ======= 넣는 경로 · 절이 키트에 실제로 있나(지어낸 절 없음) =======
def test_refs_exist_in_kit():
    assert (KIT / "docs" / "WORKLOG.md").is_file()
    for role, rows in compact_hook.REFS.items():
        assert (SKILLS / role.lower() / "SKILL.md").is_file(), role
        for _, target, nums in rows:
            f = KIT / target if target.startswith(compact_hook.KIT_PREFIXES) else SKILLS / target / "SKILL.md"
            assert f.is_file(), target
            text = f.read_text(encoding="utf-8")
            for n in nums:
                assert re.search(rf"^#{{2,3}} {re.escape(n)}\. \S", text, re.M), f"{target} {n}절 없음"
                assert compact_hook.headings(f).get(n), f"{target} {n}절 제목 못 뽑음"


# ======= 다른 이벤트 · 깨진 입력 → 출력 없음 · 종료코드 0 =======
def test_other_events_and_bad_input_are_silent(tmp_path):
    for ev in ({"hook_event_name": "SessionStart", "source": "startup"}, {"hook_event_name": "PreCompact", "trigger": "auto"},
               {"hook_event_name": "Stop"}, []):
        r = run(ev, tmp_path / "c")
        assert r.returncode == 0 and r.stdout.strip() == ""
    bad = subprocess.run([sys.executable, str(HOOK)], input="not json", capture_output=True, text=True,
                         encoding="utf-8", timeout=30)
    assert bad.returncode == 0 and bad.stdout.strip() == ""
