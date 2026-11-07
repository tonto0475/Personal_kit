# -*- coding: utf-8 -*-
# precheck 시험 — 임시 키트 사본 + 가짜 세션 기록 · 가짜 devview 로 판정 · 양식을 본다
"""
사용: python3 -m pytest -q -p no:cacheprovider .agents/skills/precheck
- 진짜 키트 · ~/.codex · 떠 있는 서버는 건드리지 않는다(임시 폴더 · CODEX_HOME · HOME · 빈 포트)
- 대회에서만 되는 부분(세션 기록 · queue · 화면 제출)은 실제 기록 모양을 본뜬 가짜 입력으로
"""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
SK = HERE.parent
SRC = next((p for p in HERE.parents if (p / "AGENTS.md").is_file() and (p / "docs").is_dir()), None)
pytestmark = pytest.mark.skipif(SRC is None or not (SRC / "devview").is_dir(), reason="키트 밖(설치본)")
MAIN_T, SECOND_T = "aaaa1111-main", "bbbb2222-second"


# 모듈로 불러오기 — 판정 함수 직접 시험용
def load():
    spec = importlib.util.spec_from_file_location("precheck_under_test", HERE / "precheck.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# 임시 키트 — 도구가 쓰는 것만 복사 · git 저장소로
@pytest.fixture
def world(tmp_path, monkeypatch):
    kit = tmp_path / "root" / "kit"
    skills = kit / ".agents" / "skills"
    skills.mkdir(parents=True)
    for n in ("precheck", "survey", "ready-start", "codex-hub", "insp", "main-magic", "2nd-magic"):
        shutil.copytree(SK / n, skills / n, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
    (kit / "AGENTS.md").write_text("# 시험\n", encoding="utf-8")
    (kit / "docs").mkdir()
    (kit / "devview").mkdir()
    shutil.copytree(SRC / "devview" / "flowtree", kit / "devview" / "flowtree", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copyfile(SRC / "devview" / "notify.py", kit / "devview" / "notify.py")
    (kit / "bookkit" / "book_example" / "task09").mkdir(parents=True)
    (kit / "bookkit" / "book_example" / "task09" / "task09_kit.html").write_text(
        '<style>옛 판</style><div data-id="pv-001"></div><script id="bkmeta">{"doc": "task09"}</script>\n<script>옛 판</script>', encoding="utf-8")
    (kit / "bookkit" / "engine" / "book" / "assets").mkdir(parents=True)
    (kit / "bookkit" / "engine" / "book" / "assets" / "book.css").write_text("/* 지금 판 */", encoding="utf-8")
    (kit / "bookkit" / "engine" / "book" / "assets" / "book.js").write_text("/* 지금 판 */", encoding="utf-8")
    home = tmp_path / "home"
    (home / ".codex" / "sessions" / "2026" / "11" / "05").mkdir(parents=True)
    env = {**os.environ, "HOME": str(home), "USERPROFILE": str(home), "CODEX_HOME": str(home / ".codex"),
           "MAGIC_SURVEY_DIR": str(tmp_path / "sv"), "PYTHONUTF8": "1"}
    monkeypatch.setenv("CODEX_HOME", str(home / ".codex"))
    monkeypatch.setenv("MAGIC_SURVEY_DIR", str(tmp_path / "sv"))
    root = kit.parent
    for args in (["init", "-q"], ["config", "user.email", "t@t"], ["config", "user.name", "t"]):
        subprocess.run(["git", "-C", str(root), *args], check=True)
    (root / "README.md").write_text("시험\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", "README.md"], check=True)
    subprocess.run(["git", "-C", str(root), "commit", "-qm", "첫 커밋"], check=True)
    return {"kit": kit, "root": root, "env": env, "home": home, "tool": skills / "precheck" / "precheck.py", "tmp": tmp_path}


# 명령 실행
def pc(w, *args, ok=True):
    r = subprocess.run([sys.executable, str(w["tool"]), "--kit", str(w["kit"]), *args], env=w["env"], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", cwd=str(w["kit"]))
    if ok:
        assert r.returncode == 0, r.stdout + r.stderr
    return r


# prepare 한 번 → (run, state)
def prepare(w, port=1):
    pc(w, "prepare", "--port", str(port), "--root", str(w["root"]))
    run = (w["kit"] / ".codex-hub" / "precheck" / "current.txt").read_text(encoding="utf-8").strip()
    return run, json.loads((w["kit"] / ".codex-hub" / "precheck" / run / "state.json").read_text(encoding="utf-8"))


# 가짜 세션 기록 — 실제 줄 모양(0.164 기록) 그대로
class Fake:
    def __init__(self, w, thread, parent=None, path=None, effort="low"):
        self.file = w["home"] / ".codex" / "sessions" / "2026" / "11" / "05" / f"rollout-2026-11-05T00-00-00-{thread}.jsonl"
        self.n = 0
        src = {"subagent": {"thread_spawn": {"parent_thread_id": parent, "depth": 1, "agent_path": path}}} if parent else "cli"
        self.line("session_meta", {"id": thread, "cwd": str(w["kit"]), "cli_version": "0.163.0", "source": src,
                                   **({"parent_thread_id": parent} if parent else {})})
        self.line("turn_context", {"model": "gpt-6.1-sol", "effort": effort, "multi_agent_version": "v2"})

    def line(self, kind, payload):
        self.n += 1
        ts = time.strftime("%Y-%m-%dT%H:%M:", time.gmtime()) + f"{self.n % 60:02d}.000Z"
        with open(self.file, "a", encoding="utf-8") as f:
            f.write(json.dumps({"timestamp": ts, "type": kind, "payload": payload}, ensure_ascii=False) + "\n")

    def user(self, text):
        self.line("event_msg", {"type": "item_completed", "item": {"type": "UserMessage", "content": [{"type": "text", "text": text}]}})

    def turn(self, say=None):
        self.line("event_msg", {"type": "task_started", "turn_id": "t"})
        if say:
            self.line("event_msg", {"type": "task_complete", "last_agent_message": say})

    def call(self, name, cid="c", **args):
        self.line("response_item", {"type": "function_call", "name": name, "arguments": json.dumps(args), "call_id": cid})

    def out(self, cid, text):
        self.line("response_item", {"type": "function_call_output", "call_id": cid, "output": text})

    def agent(self, author, text):
        self.line("response_item", {"type": "agent_message", "author": author, "recipient": "/root",
                                    "content": [{"type": "input_text", "text": f"Message Type: FINAL_ANSWER\nPayload:\n{text}"}]})


# 허브 등록 파일
def register(w, nick, thread):
    p = w["kit"] / ".codex-hub" / "sessions" / f"{nick}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"nick": nick, "thread": thread, "cwd": str(w["kit"]), "registered_at": "2999-01-01 00:00:00"}), encoding="utf-8")


# check 뒤 표에서 항목 결과 읽기
def table(w):
    pc(w, "check")
    text = (w["kit"] / "precheck.md").read_text(encoding="utf-8")
    rows = {}
    for ln in text.splitlines():
        c = [x.strip() for x in ln.split("|")]
        if len(c) > 9 and c[1] and c[3] and c[1] != "ID" and not c[1].startswith("-"):
            rows[c[1]] = c[3]
    return rows, text


# ======= prepare · 양식 =======
def test_prepare_makes_materials_and_report(world):
    run, st = prepare(world)
    kit = world["kit"]
    assert all(v["ok"] for v in st["seed"].values()), st["seed"]
    assert (kit / "ReadyStart.md").is_file()
    assert (kit / ".codex-hub" / "precheck" / run / "start.sh.txt").is_file()
    assert len(st["start_lines"]) == 2
    # 시험 명령 = ReadyStart 옵션 그대로 · 시작 메시지만 precheck(대회 시작 메시지 금지)
    for ln in st["start_lines"]:
        assert "features.multi_agent_v2.enabled=true" in ln and "agents.max_concurrent_threads_per_session=8" in ln
        assert "model_reasoning_effort=low" in ln and "'$main'" not in ln and "$2nd" not in ln and run in ln
    rows, text = table(world)
    assert text.count(f"<!-- precheck-run:{run} -->") == 1
    for h in ("### 실행 정보", "### 항목별 결과", "### 남긴 것", "총 판정"):
        assert h in text
    assert rows["R1"] == "통과" and rows["G1"] == "통과" and rows["G2"] == "통과"
    assert rows["S8"] == "미실행" and rows["U1"] == "미실행"


def test_book_copy_uses_current_runtime(world):
    _, st = prepare(world)
    html = (Path(st["note"]["book"]) / "dist" / "task09_kit.html").read_text(encoding="utf-8")
    assert "옛 판" not in html and html.count("지금 판") == 2


def test_marked_nodes_do_not_touch_frames(world):
    run, st = prepare(world)
    tree = json.loads((world["kit"] / "docs" / "flowtree" / "tree.json").read_text(encoding="utf-8"))
    mine = [n for n in tree["nodes"] if f"[precheck {run}]" in str(n.get("title"))]
    assert {n["kind"] for n in mine} == {"task", "verify", "question", "survey"}
    # 운영 틀은 비어 있다 — fill 은 run 폴더 사본에만
    assert not any(n.get("frame") and n.get("title") for n in tree["nodes"])
    assert not (world["kit"] / "docs" / "flowtree" / "x").exists()


def test_report_appends_per_run_and_keeps_old(world):
    run1, _ = prepare(world)
    report = world["kit"] / "precheck.md"
    report.write_text(report.read_text(encoding="utf-8") + "유저 메모 줄\n", encoding="utf-8")
    time.sleep(1.1)
    run2, _ = prepare(world)
    assert run1 != run2
    pc(world, "check")
    pc(world, "check")
    text = report.read_text(encoding="utf-8")
    assert text.count(f"<!-- precheck-run:{run1} -->") == 1 and text.count(f"<!-- precheck-run:{run2} -->") == 1
    assert "유저 메모 줄" in text and text.startswith("# precheck")


def test_existing_readystart_is_kept(world):
    p = world["kit"] / "ReadyStart.md"
    p.write_text("유저 준비 상태\n", encoding="utf-8")
    prepare(world)
    assert p.read_text(encoding="utf-8") == "유저 준비 상태\n"
    assert table(world)[0]["R1"] == "실패"


def test_old_registration_is_conflict_and_not_used(world):
    p = world["kit"] / ".codex-hub" / "sessions" / "main.json"
    p.parent.mkdir(parents=True)
    p.write_text(json.dumps({"thread": "old", "cwd": str(world["kit"]), "registered_at": "2000-01-01 00:00:00"}), encoding="utf-8")
    prepare(world)
    rows, _ = table(world)
    assert rows["H0"] == "미확인" and rows["H1"] == "미실행"


# ======= 큐 · 등록 =======
def test_queue_needs_real_receipt_not_exit_code(world):
    run, _ = prepare(world)
    register(world, "main", MAIN_T)
    f = Fake(world, MAIN_T)
    ev = world["kit"] / ".codex-hub" / "precheck" / run / "evidence"
    ev.mkdir(parents=True, exist_ok=True)
    (ev / "q1.json").write_text(json.dumps({"rc": 0, "out": "queued"}), encoding="utf-8")
    assert table(world)[0]["Q1"] == "미확인"
    f.user(f"[precheck {run}] Q1-{run} 받았으면 ACK-Q1-{run} 한 줄만")
    assert table(world)[0]["Q1"] == "실패"
    f.turn(f"ACK-Q1-{run}")
    rows, _ = table(world)
    assert rows["Q1"] == "통과" and rows["H1"] == "통과"


def test_failure_blocks_only_dependents(world):
    run, st = prepare(world)
    register(world, "main", MAIN_T)
    Fake(world, MAIN_T, effort="high")
    # H2 없음(미실행) · 스킬 경로 없음(실패) — 그래프 쓰기는 그대로 통과
    pc(world, "mark", "H2", "실패", "--note", "등록 안 됨")
    rows, _ = table(world)
    assert rows["P1"] == "실패" and rows["G1"] == "통과"
    assert rows["SV3"] == "미실행" or rows["SV3"] == "선행 실패로 차단"
    assert rows["ST1"] == "선행 실패로 차단" and rows["V1"] == "실패"


# ======= 서브 =======
def subs(w, run, n=8):
    out = {}
    for i in range(1, n + 1):
        f = Fake(w, f"cccc000{i}-child", parent=MAIN_T, path=f"/root/c{i}")
        f.turn(f"READY-c{i}-{run}")
        out[i] = f
    return out


def test_eight_subs_and_comms(world):
    run, _ = prepare(world)
    register(world, "main", MAIN_T)
    m = Fake(world, MAIN_T)
    s = subs(world, run)
    a, b = s[1], s[2]
    m.call("followup_task", target="/root/c1")
    a.n = b.n = m.n = 10
    a.call("send_message", target="/root/c2")
    b.n = 12
    a.n = 13
    a.call("followup_task", target="/root/c2")
    b.n = 14
    b.turn(f"B-FOLLOW-{run}")
    a.call("send_message", target="/root")
    m.n = 20
    m.agent("/root/c1", f"A-REPORT-{run}")
    m.call("followup_task", target="/root/c2")
    m.call("wait_agent", cid="w", timeout_ms=600000)
    b.n = 22
    b.turn(f"B-WAIT-{run}")
    m.n = 23
    m.agent("/root/c2", f"B-WAIT-{run}")
    rows, text = table(world)
    assert rows["S8"] == "통과" and rows["C1"] == "통과" and rows["F1"] == "통과" and rows["C2"] == "통과" and rows["W1"] == "통과"
    assert "미래 도착 순서 미확인" in text
    # READY 8줄로 로드 유지를 대신하지 않는다
    assert rows["L8"] == "미확인"


def test_seven_subs_fail_s8_but_comms_continue(world):
    run, _ = prepare(world)
    register(world, "main", MAIN_T)
    Fake(world, MAIN_T)
    subs(world, run, 7)
    rows, _ = table(world)
    assert rows["S8"] == "실패" and rows["L8"] == "선행 실패로 차단" and rows["C1"] == "미실행"


def test_send_starting_turn_is_failure(world):
    run, _ = prepare(world)
    register(world, "main", MAIN_T)
    Fake(world, MAIN_T)
    s = subs(world, run, 2)
    s[1].n = 10
    s[1].call("send_message", target="/root/c2")
    s[2].n = 11
    s[2].turn("뜻밖의 턴")
    s[1].n = 13
    s[1].call("followup_task", target="/root/c2")
    assert table(world)[0]["C1"] == "실패"


def test_l8_reads_list_agents(world):
    run, _ = prepare(world)
    register(world, "main", MAIN_T)
    m = Fake(world, MAIN_T)
    subs(world, run)
    good = " ".join(f"/root/c{i} idle" for i in range(1, 9))
    for cid in ("l1", "l2"):
        m.call("list_agents", cid=cid)
        m.out(cid, good)
    assert table(world)[0]["L8"] == "통과"
    m.call("list_agents", cid="l3")
    m.out("l3", good.replace("/root/c1 idle", "/root/c1 notLoaded"))
    assert table(world)[0]["L8"] == "실패"


# ======= 서브 도우미 =======
def test_sub_skill_compares_with_file(world):
    prepare(world)
    want = next(x for x in (world["kit"] / ".agents" / "skills" / "insp" / "SKILL.md").read_text(encoding="utf-8").splitlines() if x.startswith("## "))
    assert pc(world, "sub-skill", "틀린 줄", ok=False).returncode == 1
    assert table(world)[0]["K1"] == "실패"
    pc(world, "sub-skill", want)
    assert table(world)[0]["K1"] == "통과"


def test_sub_worktree_real_git(world):
    run, _ = prepare(world)
    world["env"]["CODEX_THREAD_ID"] = "sub-thread"
    pc(world, "sub-worktree")
    rows, text = table(world)
    assert rows["WT"] == "통과"
    assert not (world["kit"] / ".codex-hub" / "precheck" / run / "worktree").exists()
    out = subprocess.run(["git", "-C", str(world["root"]), "worktree", "list"], capture_output=True, text=True, encoding="utf-8").stdout
    assert len(out.strip().splitlines()) == 1
    # xdist 는 환경 따라 — 없으면 실패로 적고 설치하지 않는다
    assert rows["XD"] in ("통과", "실패")


def test_worktree_from_terminal_is_not_pass(world):
    prepare(world)
    world["env"].pop("CODEX_THREAD_ID", None)
    pc(world, "sub-worktree")
    assert table(world)[0]["WT"] == "미확인"


def test_worktree_without_commit_makes_seed_commit(world):
    prepare(world)
    empty = world["tmp"] / "empty"
    empty.mkdir()
    subprocess.run(["git", "-C", str(empty), "init", "-q"], check=True)
    run = (world["kit"] / ".codex-hub" / "precheck" / "current.txt").read_text(encoding="utf-8").strip()
    sp = world["kit"] / ".codex-hub" / "precheck" / run / "state.json"
    st = json.loads(sp.read_text(encoding="utf-8"))
    st["root"] = str(empty)
    sp.write_text(json.dumps(st), encoding="utf-8")
    world["env"]["CODEX_THREAD_ID"] = "sub"
    pc(world, "sub-worktree")
    rows, text = table(world)
    assert rows["WT"] == "통과" and rows["G1"] == "통과" and "시험 빈 커밋" in text


def test_test_book_is_listed_and_main_short_name_counts(world):
    _, st = prepare(world)
    assert not Path(st["note"]["book"]).name.startswith("_")
    p = load()
    k = type("K", (), {"id": "x", "agent_path": "/root/c1"})
    assert "c1" in p.names(k)


# ======= 화면 왕복 =======
class Api(BaseHTTPRequestHandler):
    info, notify = {}, {}

    def do_GET(self):
        body = json.dumps(self.info if "info" in self.path else self.notify, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


@pytest.fixture
def api():
    srv = HTTPServer(("127.0.0.1", 0), Api)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv.server_address[1]
    srv.shutdown()
    srv.server_close()


def test_devview_tree_mismatch_fails_and_observation_is_kept(world, api):
    run, st = prepare(world, api)
    Api.info = {"kit_abs": str(world["kit"]), "flowtree": {"tree": st["tree"]}, "page_port": 8801, "root": str(world["root"])}
    Api.notify = {"items": [{"title": f"N1-{run}"}]}
    rows, _ = table(world)
    assert rows["D1"] == "통과" and rows["N1"] == "통과"
    Api.info = {**Api.info, "flowtree": {"tree": "/다른/tree.json"}}
    assert table(world)[0]["D1"] == "실패"


def test_devview_down_is_unsure_and_keeps_earlier(world, api):
    run, st = prepare(world, api)
    Api.info = {"kit_abs": str(world["kit"]), "flowtree": {"tree": st["tree"]}, "page_port": 8801}
    Api.notify = {"items": [{"title": f"N1-{run}"}]}
    assert table(world)[0]["D1"] == "통과"
    sp = world["kit"] / ".codex-hub" / "precheck" / run / "state.json"
    s2 = json.loads(sp.read_text(encoding="utf-8"))
    s2["port"] = 1
    sp.write_text(json.dumps(s2, ensure_ascii=False), encoding="utf-8")
    rows, text = table(world)
    assert rows["D1"] == "통과" and "앞선 관측" in text


def test_survey_route_and_answer_places(world):
    run, st = prepare(world)
    register(world, "main", MAIN_T)
    register(world, "2nd", SECOND_T)
    m, s = Fake(world, MAIN_T), Fake(world, SECOND_T)
    res_file = Path(st["survey"]["file"]).with_name(st["survey"]["id"] + ".result.json")
    res_file.write_text(json.dumps({"route": [{"to": "MAIN", "ok": True, "request": "m1105-000000-aaaa"},
                                              {"to": "2ND", "ok": True, "request": "m1105-000000-bbbb"}]}), encoding="utf-8")
    rows, _ = table(world)
    assert rows["SV1"] == "통과" and rows["SV2"] == "미확인" and rows["SV3"] == "미확인"
    m.user("🪄 설문\n$main-magic m1105-000000-aaaa")
    m.turn(f"ACK-SV-{run}")
    s.user("🪄 설문\n$2nd-magic m1105-000000-bbbb")
    s.turn("채팅으로만 답")
    rows, _ = table(world)
    assert rows["SV2"] == "통과" and rows["SV3"] == "실패"
    form = world["tmp"] / "sv" / "2nd" / "f.json"
    form.parent.mkdir(parents=True)
    form.write_text(json.dumps({"intro": "요청 m1105-000000-bbbb"}), encoding="utf-8")
    assert table(world)[0]["SV3"] == "통과"


def test_sticker_answer_must_land_in_note(world):
    run, st = prepare(world)
    register(world, "2nd", SECOND_T)
    s = Fake(world, SECOND_T)
    nf = Path(st["note"]["file"])
    notes = json.loads(nf.read_text(encoding="utf-8"))
    assert table(world)[0]["ST1"] == "미실행"
    notes[0]["magic_rid"] = "m1105-000000-cccc"
    nf.write_text(json.dumps(notes), encoding="utf-8")
    s.user("🪄 책\n$2nd-magic m1105-000000-cccc")
    s.turn("채팅 답")
    assert table(world)[0]["ST1"] == "실패"
    notes[0]["answer"] = f"ST-{run} 시험 답"
    nf.write_text(json.dumps(notes), encoding="utf-8")
    assert table(world)[0]["ST1"] == "통과"


def test_graph_magic_task_verify_question(world):
    run, st = prepare(world)
    register(world, "main", MAIN_T)
    m = Fake(world, MAIN_T)
    ids = st["nodes"]
    assert table(world)[0]["M1"] == "미실행"
    req = world["kit"] / ".codex-hub" / "requests" / "m1105-000000-dddd.json"
    req.parent.mkdir(parents=True)
    req.write_text(json.dumps({"id": "m1105-000000-dddd", "role": "main", "tree": st["tree"],
                               "nodes": [{"id": i} for i in ids.values()]}), encoding="utf-8")
    m.user("🪄 ...\n$main-magic m1105-000000-dddd")
    ft = [sys.executable, str(world["kit"] / "devview" / "flowtree" / "flowtree.py")]

    def flow(role, *a):
        subprocess.run([*ft, *a, "--tree", st["tree"], "--root", str(world["kit"]), "--role", role], check=True, env=world["env"],
                       capture_output=True)
    flow("main", "start", ids["task"])
    pc(world, "sub-task", ids["task"])
    flow("main", "done", ids["task"])
    flow("insp", "verify-start", ids["verify"])
    flow("insp", "run", ids["verify"], "pass", f"precheck {run} 시험")
    flow("2nd", "answer-start", ids["question"])
    flow("2nd", "answer", ids["question"], "--short", f"precheck {run}", f"시험 답 {run}")
    rows, _ = table(world)
    assert [rows[k] for k in ("M1", "M2", "M3", "M4")] == ["통과"] * 4


def test_sub_env_passes_only_known_numbers(world):
    tool = world["kit"] / "scripts" / "envcheck" / "envcheck.py"
    tool.parent.mkdir(parents=True)
    prepare(world)
    tool.write_text("print('A6 실패')\nprint('요약: A6 B4')\n", encoding="utf-8")
    pc(world, "sub-env")
    rows, text = table(world)
    assert rows["E1"] == "통과" and "요약: A6 B4" in text
    tool.write_text("print('요약: A6 C2')\n", encoding="utf-8")
    pc(world, "sub-env")
    assert table(world)[0]["E1"] == "실패"


def test_sub_file_makes_node(world):
    prepare(world)
    pc(world, "sub-file")
    rows, text = table(world)
    assert rows["E3"] == "통과" and "시험 파일 노드" in text


def test_sub_book_records_without_install(world):
    prepare(world)
    pc(world, "sub-book")
    rows, _ = table(world)
    assert rows["E2"] in ("통과", "실패") and rows["E5"] == "실패"


def test_hub_send_needs_tag_and_ack(world):
    run, _ = prepare(world)
    register(world, "main", MAIN_T)
    register(world, "2nd", SECOND_T)
    f = Fake(world, SECOND_T)
    f.user(f"[precheck {run}] E4-{run} 받았으면 ACK-E4-{run} 한 줄만")
    assert table(world)[0]["E4"] == "실패"
    f.user(f"@main [precheck {run}] E4-{run} 받았으면 ACK-E4-{run} 한 줄만")
    f.turn(f"ACK-E4-{run}")
    assert table(world)[0]["E4"] == "통과"


def test_mark_rules(world):
    prepare(world)
    assert pc(world, "mark", "없는칸", "통과", ok=False).returncode == 2
    assert pc(world, "mark", "U1", "좋음", ok=False).returncode == 2
    pc(world, "mark", "U1", "통과")
    # 자동 판정이 통과면 mark 가 뒤집지 못한다
    pc(world, "mark", "G1", "실패", "--note", "오입력")
    pc(world, "mark", "W1", "제한 내 미완료", "--note", "wait 제한 도달")
    rows, text = table(world)
    assert rows["U1"] == "통과" and rows["G1"] == "통과" and rows["W1"] == "제한 내 미완료"
    assert "wait 제한 도달" in text


def test_verdict():
    p = load()
    ok = {i[0]: {"result": p.PASS} for i in p.ITEMS}
    assert p.verdict(ok) == p.PASS
    assert p.verdict({**ok, "L8": {"result": p.UNSURE}}) == "미완료"
    assert p.verdict({**ok, "S8": {"result": p.FAIL}}) == "일부 실패"
    assert p.verdict({**ok, "XD": {"result": p.FAIL}}) == p.PASS


def test_final_adds_readystart_line(world):
    run, _ = prepare(world)
    pc(world, "check", "--final")
    assert f"run {run}" in (world["kit"] / "ReadyStart.md").read_text(encoding="utf-8")


def test_no_task_words_in_public_files():
    words = ("버스", "노선", "정류장")
    for f in (HERE / "SKILL.md", HERE / "precheck.py", HERE / "agents" / "openai.yaml"):
        text = f.read_text(encoding="utf-8")
        assert not any(w in text for w in words), f
