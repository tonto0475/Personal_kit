"""hub.py 시험 — 등록 · effort 순서(기록 → 프로세스 → --effort → 설정 → ?) · 상태 줄 · 누적 · whoami · 훅 · 작업 폴더 찾기 · 이름 정하기(옛 con-dev) · send
    python3 -m pytest -q .agents/skills/codex-hub        (임시 폴더 · 가짜 Codex 홈 — 실제 ~/.codex 무관)
"""
import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import hub  # noqa: E402

# 시험 세션 id
TH = "019a1111-2222-7333-8444-555566667777"


# rollout 한 개 쓰기
# home: Codex 홈 / effort: turn_context effort(None 이면 칸 없음) / model: 모델
def write_rollout(home, effort="high", model="gpt-y"):
    p = home / "sessions" / "2026" / "11" / "02" / f"rollout-2026-11-02T00-00-00-{TH}.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    tc = {"turn_id": "u1", "model": model, "collaboration_mode": {"settings": {"reasoning_effort": None}}}
    if effort:
        tc["effort"] = effort
    lines = [{"type": "session_meta", "payload": {"id": TH}}, {"type": "turn_context", "payload": tc}]
    p.write_text("\n".join(json.dumps(x) for x in lines) + "\n", encoding="utf-8")
    return p


@pytest.fixture
def world(tmp_path, monkeypatch):
    # 작업 폴더(키트 표시 AGENTS.md) · 하위 폴더 · Codex 홈
    work = tmp_path / "kit"
    (work / "sub").mkdir(parents=True)
    (work / "AGENTS.md").write_text("# 키트\n", encoding="utf-8")
    home = tmp_path / "codex"
    home.mkdir()
    monkeypatch.chdir(work)
    monkeypatch.setenv("CODEX_HOME", str(home))
    monkeypatch.setenv("CODEX_THREAD_ID", TH)
    monkeypatch.delenv("CODEX_HUB_DIR", raising=False)
    # Claude 홈도 임시(실행 환경이 Claude 세션이어도 그 세션을 자기로 찾지 않게)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude"))
    monkeypatch.delenv("CODEX_HUB_CLAUDE_PID", raising=False)
    monkeypatch.delenv("TMUX_PANE", raising=False)
    monkeypatch.delenv("TMUX", raising=False)
    # 프로세스 인자 effort 는 시험마다 직접 정함(실행 환경의 부모 프로세스 영향 제거)
    monkeypatch.setattr(hub, "process_effort", lambda: None)
    return {"work": work, "home": home}


# hub.main 실행 → (종료코드, 표준 출력, 표준 오류)
def run(capsys, *argv):
    code = hub.main(list(argv))
    out = capsys.readouterr()
    return code, out.out.strip(), out.err.strip()


def test_register_effort_from_rollout(world, capsys):
    write_rollout(world["home"], "high", "gpt-y")
    code, out, _ = run(capsys, "register", "--nick", "MAIN", "--effort", "low")
    d = json.loads((world["work"] / ".codex-hub" / "sessions" / "main.json").read_text(encoding="utf-8"))
    assert code == 0 and out.startswith("허브 등록: main")
    # 기록이 --effort 보다 먼저
    assert d["thread"] == TH and d["effort"] == "high" and d["effort_src"] == "기록" and d["model"] == "gpt-y"


def test_register_effort_order(world, capsys, monkeypatch):
    write_rollout(world["home"], None)
    monkeypatch.setattr(hub, "process_effort", lambda: "xhigh")
    run(capsys, "register", "--nick", "2nd", "--effort", "low")
    d = json.loads((world["work"] / ".codex-hub" / "sessions" / "2nd.json").read_text(encoding="utf-8"))
    assert (d["effort"], d["effort_src"]) == ("xhigh", "프로세스")
    monkeypatch.setattr(hub, "process_effort", lambda: None)
    run(capsys, "register", "--nick", "2nd", "--effort", "low")
    d = json.loads((world["work"] / ".codex-hub" / "sessions" / "2nd.json").read_text(encoding="utf-8"))
    assert (d["effort"], d["effort_src"]) == ("low", "인자")
    (world["home"] / "config.toml").write_text('model = "x"\nmodel_reasoning_effort = "medium"\n[tui]\nmodel_reasoning_effort = "high"\n',
                                               encoding="utf-8")
    run(capsys, "register", "--nick", "2nd")
    d = json.loads((world["work"] / ".codex-hub" / "sessions" / "2nd.json").read_text(encoding="utf-8"))
    assert (d["effort"], d["effort_src"]) == ("medium", "설정")
    (world["home"] / "config.toml").unlink()
    run(capsys, "register", "--nick", "2nd")
    d = json.loads((world["work"] / ".codex-hub" / "sessions" / "2nd.json").read_text(encoding="utf-8"))
    assert (d["effort"], d["effort_src"]) == ("?", "?")


def test_register_needs_nick_and_shape(world, capsys):
    code, _, err = run(capsys, "register")
    assert code == 1 and "--nick 없음" in err and "허브에 쓸 이름" in err
    code, _, err = run(capsys, "register", "--nick", "../x")
    assert code == 1 and "닉네임" in err
    code, _, err = run(capsys, "register", "--nick", "x", "--effort", "huge")
    assert code == 1 and "--effort" in err


def test_status_log_whoami(world, capsys):
    run(capsys, "register", "--nick", "2nd", "--effort", "low")
    code, out, _ = run(capsys, "status", "❇️_1 : UI 구현. 운영자\n화면")
    d = json.loads((world["work"] / ".codex-hub" / "sessions" / "2nd.json").read_text(encoding="utf-8"))
    assert code == 0 and out == "상태 줄 갱신: 2nd" and d["status"] == "❇️_1 : UI 구현. 운영자 · 화면" and d["status_at"]
    run(capsys, "log", "❇️_1 운영자 화면 완료 · src/ui/admin.py")
    code, out, _ = run(capsys, "log", "❇️_1 검증 통과 · tests/test_admin.py")
    lines = (world["work"] / ".codex-hub" / "logs" / "2nd.jsonl").read_text(encoding="utf-8").splitlines()
    assert code == 0 and out == "누적 1줄: 2nd" and [json.loads(x)["text"][:6] for x in lines] == ["❇️_1 운", "❇️_1 검"]
    code, out, _ = run(capsys, "whoami")
    assert code == 0 and out.startswith(f"2nd · thread {TH} · effort low(인자)")
    # 다시 등록해도(같은 thread) 상태 줄 유지
    run(capsys, "register", "--nick", "2nd")
    d = json.loads((world["work"] / ".codex-hub" / "sessions" / "2nd.json").read_text(encoding="utf-8"))
    assert d["status"] == "❇️_1 : UI 구현. 운영자 · 화면"


def test_status_needs_registration_or_nick(world, capsys, monkeypatch):
    code, _, err = run(capsys, "status", "x")
    assert code == 1 and "등록 안 됨" in err
    run(capsys, "register", "--nick", "main")
    monkeypatch.delenv("CODEX_THREAD_ID")
    code, _, err = run(capsys, "log", "x")
    assert code == 1 and "CODEX_THREAD_ID 없음" in err
    code, out, _ = run(capsys, "log", "x", "--nick", "main")
    assert code == 0 and out == "누적 1줄: main"


def test_text_limits(world, capsys):
    run(capsys, "register", "--nick", "main")
    code, _, err = run(capsys, "status", "가" * 201)
    assert code == 1 and "200자" in err
    code, _, err = run(capsys, "status", "  \n ")
    assert code == 1 and "없음" in err


def test_hub_dir_from_subdir(world, capsys, monkeypatch):
    monkeypatch.chdir(world["work"] / "sub")
    run(capsys, "register", "--nick", "main")
    assert (world["work"] / ".codex-hub" / "sessions" / "main.json").is_file()
    assert not (world["work"] / "sub" / ".codex-hub").exists()


def test_hook_event_line(world, capsys, monkeypatch):
    payload = {"hook_event_name": "Stop", "session_id": TH, "cwd": str(world["work"]), "turn_id": "t9", "prompt": "비밀 본문"}
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    code, out, err = run(capsys, "hook")
    f = world["work"] / ".codex-hub" / "events" / f"{TH}.jsonl"
    line = json.loads(f.read_text(encoding="utf-8").splitlines()[-1])
    assert code == 0 and out == "" and err == "" and line["event"] == "Stop" and line["turn_id"] == "t9" and "prompt" not in line
    monkeypatch.setattr(sys, "stdin", io.StringIO("깨진 입력"))
    assert run(capsys, "hook")[0] == 0


# ======= 이름 정하기(옛 con-dev) — whoami list 의 세션 이름 → 그 이름으로 등록 =======
# 스크립트를 따로 띄워 실행 → (종료코드, 출력)
# script: 파일 / args: 인자 / work: 작업 폴더 / env: 환경
def run_proc(script, args, work, env):
    r = subprocess.run([sys.executable, str(script), *args], cwd=work, env=env, capture_output=True, text=True, encoding="utf-8")
    return r.returncode, r.stdout + r.stderr


@pytest.fixture
def world_name(tmp_path):
    # 작업 폴더 · Codex 홈(세션 목록에 이 세션 이름 «보조1») · 환경
    work = tmp_path / "kit"
    work.mkdir()
    (work / "AGENTS.md").write_text("# 키트\n", encoding="utf-8")
    home = tmp_path / "codex"
    home.mkdir()
    (home / "session_index.jsonl").write_text(
        json.dumps({"id": TH, "thread_name": "보조1", "updated_at": "2026-11-03T10:00:00Z"}) + "\n", encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if k != "CODEX_HUB_DIR"}
    env.update(CODEX_HOME=str(home), CODEX_THREAD_ID=TH, PYTHONUTF8="1")
    return {"work": work, "env": env}


def test_session_name_register(world_name):
    whoami = HERE.parent / "ready-start" / "whoami.py"
    code, out = run_proc(whoami, ["list"], world_name["work"], world_name["env"])
    assert code == 0
    # 이 thread 줄의 UUID 뒤 글자
    name = next(line.split(TH, 1)[1].strip() for line in out.splitlines() if TH in line)
    assert name == "보조1"
    code, out = run_proc(HERE / "hub.py", ["register", "--nick", name], world_name["work"], world_name["env"])
    assert code == 0 and "보조1" in out and TH[:8] in out, out
    data = json.loads((world_name["work"] / ".codex-hub" / "sessions" / "보조1.json").read_text(encoding="utf-8"))
    assert data["nick"] == "보조1" and data["thread"] == TH


def test_user_name_and_bad_name(world_name):
    code, out = run_proc(HERE / "hub.py", ["register", "--nick", "리뷰어"], world_name["work"], world_name["env"])
    assert code == 0 and (world_name["work"] / ".codex-hub" / "sessions" / "리뷰어.json").is_file(), out
    code, out = run_proc(HERE / "hub.py", ["register", "--nick", "../x"], world_name["work"], world_name["env"])
    assert code != 0 and "실패" in out, out


# ======= send — 다른 세션에 codex queue · 앞에 «@보낸이름 » =======
@pytest.fixture
def fake_codex(tmp_path, monkeypatch):
    # 가짜 codex — 인자를 줄마다 적음 · fail-thread 면 종료코드 3
    log = tmp_path / "queue.jsonl"
    fake = tmp_path / "fake_codex.py"
    fake.write_text("import json, sys\nargs = sys.argv[1:]\n"
                    f"open({str(log)!r}, 'a', encoding='utf-8').write(json.dumps(args, ensure_ascii=False) + '\\n')\n"
                    "th = args[args.index('--thread') + 1]\n"
                    "if th == 'fail-thread':\n    print('Error: no session', file=sys.stderr)\n    sys.exit(3)\n"
                    "print(f'Queued message m-1 for thread {th}.')\n", encoding="utf-8")
    monkeypatch.setenv("CODEX_HUB_CODEX", str(fake))
    return log


def test_send_prefix_and_target(world, capsys, fake_codex):
    run(capsys, "register", "--nick", "main")
    (world["work"] / ".codex-hub" / "sessions" / "2nd.json").write_text(json.dumps({"nick": "2nd", "thread": "th-2nd"}), encoding="utf-8")
    text = '기호 $HOME "따옴표" -- --message=가짜\n둘째 줄'
    code, out, err = run(capsys, "send", "--to", "2ND", text)
    args = json.loads(fake_codex.read_text(encoding="utf-8").splitlines()[-1])
    assert code == 0 and out.startswith("보냄: main → 2nd") and "Queued" in out, (out, err)
    # 받는 세션 thread · 글 앞 «@main » · 셸 없이 그대로
    assert args == ["queue", "--thread", "th-2nd", f"--message=@main {text}"]


def test_send_failures(world, capsys, fake_codex, monkeypatch):
    # 보낸 세션 등록 없음 → «등록 안 됨»
    code, _, err = run(capsys, "send", "--to", "2nd", "x")
    assert code == 1 and "등록 안 됨" in err
    run(capsys, "register", "--nick", "main")
    code, _, err = run(capsys, "send", "--to", "2nd", "x")
    assert code == 1 and "«2nd» 등록 없음" in err
    (world["work"] / ".codex-hub" / "sessions" / "bad.json").write_text(json.dumps({"nick": "bad", "thread": "fail-thread"}), encoding="utf-8")
    code, _, err = run(capsys, "send", "--to", "bad", "x")
    assert code == 1 and "종료코드 3" in err and "no session" in err
    code, _, err = run(capsys, "send", "--to", "main", "x")
    assert code == 1 and "자기 자신" in err
    code, _, err = run(capsys, "send", "--to", "bad", "  ")
    assert code == 1 and "보낼 글 없음" in err
    assert not fake_codex.is_file() or len(fake_codex.read_text(encoding="utf-8").splitlines()) == 1


@pytest.mark.skipif(os.name == "nt", reason="리눅스 /proc 전용")
def test_process_effort_from_parent_args(tmp_path):
    # 부모(bash) 인자에 model_reasoning_effort=high — Codex 를 -c 로 띄운 모양
    work = tmp_path / "kit"
    work.mkdir()
    (work / "AGENTS.md").write_text("#\n", encoding="utf-8")
    env = dict(os.environ, CODEX_HOME=str(tmp_path / "codex"), CODEX_THREAD_ID=TH)
    env.pop("CODEX_HUB_DIR", None)
    # 끝의 «; true» — bash 가 마지막 명령을 exec 로 바꿔 자기 인자를 지우지 않게
    r = subprocess.run(["bash", "-c", f'"{sys.executable}" "{HERE / "hub.py"}" register --nick main; true', "model_reasoning_effort=high"],
                       cwd=work, env=env, capture_output=True, text=True)
    d = json.loads((work / ".codex-hub" / "sessions" / "main.json").read_text(encoding="utf-8"))
    assert r.returncode == 0 and (d["effort"], d["effort_src"]) == ("high", "프로세스")


# ======= Claude — register --claude · tmux 로 보내기 =======
# Claude 세션 id · 가짜 claude 프로세스 번호
CSID = "5e81db89-d239-4f42-950a-1d119300ee36"
CPID = 4242


@pytest.fixture
def claude(world, monkeypatch):
    # 가짜 Claude 홈 — sessions/<pid>.json(세션 id · 작업 폴더) · 기록 jsonl(모델) · CODEX_THREAD_ID 없음
    ch = Path(os.environ["CLAUDE_CONFIG_DIR"])
    (ch / "sessions").mkdir(parents=True)
    (ch / "sessions" / f"{CPID}.json").write_text(json.dumps({"pid": CPID, "sessionId": CSID, "cwd": str(world["work"]), "procStart": "77"}),
                                                  encoding="utf-8")
    proj = ch / "projects" / hub.claude_project(world["work"])
    proj.mkdir(parents=True)
    (proj / f"{CSID}.jsonl").write_text(json.dumps({"type": "assistant", "message": {"model": "claude-sonnet-5-5", "content": []}}) + "\n",
                                        encoding="utf-8")
    monkeypatch.delenv("CODEX_THREAD_ID")
    monkeypatch.setenv("CODEX_HUB_CLAUDE_PID", str(CPID))
    return {"home": ch, "proj": proj}


@pytest.fixture
def fake_tmux(tmp_path, monkeypatch):
    # 가짜 tmux — 인자 · 표준 입력을 줄마다 적음 · 대상 %9 는 «can't find pane»(종료코드 1)
    log = tmp_path / "tmux.jsonl"
    fake = tmp_path / "fake_tmux.py"
    fake.write_text("import json, sys\nargs = sys.argv[1:]\ndata = sys.stdin.buffer.read().decode('utf-8')\n"
                    f"open({str(log)!r}, 'a', encoding='utf-8').write(json.dumps([args, data], ensure_ascii=False) + '\\n')\n"
                    "if '%9' in args:\n    print(\"can't find pane: %9\", file=sys.stderr)\n    sys.exit(1)\n"
                    "if 'display-message' in args:\n    print(args[args.index('-t') + 1])\n", encoding="utf-8")
    monkeypatch.setenv("CODEX_HUB_TMUX", str(fake))
    return log


def test_register_claude_session_from_process(world, claude, capsys, monkeypatch):
    monkeypatch.setenv("TMUX_PANE", "%3")
    monkeypatch.setenv("TMUX", "/tmp/tmux-1000/default,123,0")
    code, out, err = run(capsys, "register", "--nick", "MAIN", "--claude")
    d = json.loads((world["work"] / ".codex-hub" / "sessions" / "main.json").read_text(encoding="utf-8"))
    assert code == 0 and "Claude" in out and CSID[:8] in out and "tmux %3" in out, (out, err)
    assert d["kind"] == "claude" and d["thread"] == CSID and d["claude_pid"] == CPID and d["tmux"] == "%3"
    assert d["tmux_socket"] == "/tmp/tmux-1000/default" and d["model"] == "claude-sonnet-5-5" and d["transcript"].endswith(f"{CSID}.jsonl")
    # 자기 찾기 — CODEX_THREAD_ID 없이 claude 프로세스로
    code, out, _ = run(capsys, "status", "❇️_1 : 시험")
    assert code == 0 and out == "상태 줄 갱신: main"


def test_register_claude_outside_tmux_and_fallback(world, claude, capsys, monkeypatch):
    # tmux 밖 — 읽기만(경고) · 프로세스 기록 없음 → 작업 폴더 projects 의 최근 jsonl
    monkeypatch.setattr(hub, "my_claude", lambda: None)
    code, out, _ = run(capsys, "register", "--nick", "2nd", "--claude")
    d = json.loads((world["work"] / ".codex-hub" / "sessions" / "2nd.json").read_text(encoding="utf-8"))
    assert code == 0 and "tmux 밖" in out and d["tmux"] is None and d["thread"] == CSID


def test_send_to_claude_by_tmux(world, claude, capsys, fake_tmux):
    # 보낸 쪽 = Claude main · 받는 쪽 = Claude 2nd(tmux %5 · 소켓)
    run(capsys, "register", "--nick", "main", "--claude")
    (world["work"] / ".codex-hub" / "sessions" / "2nd.json").write_text(
        json.dumps({"nick": "2nd", "kind": "claude", "thread": "c-2nd", "tmux": "%5", "tmux_socket": "/tmp/s"}), encoding="utf-8")
    text = '첫 줄 $HOME "따옴표" `x`\n둘째 줄'
    code, out, err = run(capsys, "send", "--to", "2nd", text)
    calls = [json.loads(x) for x in fake_tmux.read_text(encoding="utf-8").splitlines()]
    assert code == 0 and out.startswith("보냄: main → 2nd · tmux %5"), (out, err)
    assert [c[0][2] for c in calls] == ["display-message", "load-buffer", "paste-buffer", "send-keys"]
    assert all(c[0][:2] == ["-S", "/tmp/s"] for c in calls)
    # 글은 셸 없이 표준 입력으로(괄호 붙여넣기 -p) · 끝에 Enter
    assert calls[1][1] == f"@main {text}" and "-p" in calls[2][0] and calls[3][0][-1] == "Enter"
    # 대상 없음 · 창 없음 = 분명한 오류
    (world["work"] / ".codex-hub" / "sessions" / "x1.json").write_text(json.dumps({"nick": "x1", "kind": "claude", "thread": "c1"}), encoding="utf-8")
    code, _, err = run(capsys, "send", "--to", "x1", "a")
    assert code == 1 and "tmux 대상 없음" in err
    (world["work"] / ".codex-hub" / "sessions" / "x2.json").write_text(json.dumps({"nick": "x2", "kind": "claude", "thread": "c2", "tmux": "%9"}),
                                                                      encoding="utf-8")
    code, _, err = run(capsys, "send", "--to", "x2", "a")
    assert code == 1 and "can't find pane" in err and "display-message" in err
