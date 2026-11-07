#!/usr/bin/env python3
# 설문 제출 → MAIN · 2ND 전송 시험 — 확정 문항 = MAIN · 질문 문항 = 2ND 에 허브 마법봉(🪄 $역할-magic 요청id)
#   python3 -m pytest .agents/skills/survey/test_survey_route.py -q
#   임시 작업 폴더(.codex-hub 등록 · devview/codex_hub.py 복사본) + 따로 띄운 설문 서버 + 가짜 codex(받은 인자를 파일에 적음)
#   단언 = 가짜 codex 가 받은 thread · 메시지 · 결과 파일 route 칸 · 설문 화면의 전송 줄
#   실제 Codex 세션 · 실행 중인 devview(8701 · 8702) 는 건드리지 않는다(빈 포트 · 임시 목록 파일)
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

import pytest

# ======= 경로 · 가짜 세션 =======
# 시험 대상 · 키트 · 허브 도구
HERE = Path(__file__).resolve().parent
TOOL = HERE / "survey.py"
KIT = HERE.parents[2]
MAGIC = KIT / ".agents" / "skills" / "codex-hub" / "magic.py"
# 가짜 세션 thread — 등록 세션 · MAIN · 2ND
REG, MAIN, SECOND = "T-REG", "T-MAIN", "T-2ND"
# 질문 파일 — 세 문항(선택지 A · B)
SPEC = {"title": "라우팅 시험", "questions": [{"id": str(i), "question": f"q{i}", "options": ["A", "B"]} for i in (1, 2, 3)]}
# 가짜 codex — 받은 인자를 한 줄 json 으로 덧붙이고 «queued» 출력
FAKE = ("import json, os, sys\n"
        "with open(os.environ['FAKE_OUT'], 'a', encoding='utf-8') as f:\n"
        "    f.write(json.dumps(sys.argv[1:], ensure_ascii=False) + '\\n')\n"
        "print('queued')\n")


# 비어 있는 포트 하나
def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class World:
    # tmp: 작업 폴더 / env: 서버 · 명령 환경 / base: 서버 주소 / out: 가짜 codex 기록
    def __init__(self, tmp: Path, env: dict, base: str, out: Path):
        self.tmp, self.env, self.base, self.out = tmp, env, base, out
        self.store = tmp / "docs" / "surveys"

    # 가짜 codex 가 받은 호출 목록(인자 목록)
    def calls(self) -> list:
        if not self.out.exists():
            return []
        return [json.loads(x) for x in self.out.read_text(encoding="utf-8").splitlines() if x.strip()]

    # 새 호출 — n 개가 올 때까지 보고, 등록 세션 알림(따로 띄움)이 늦게 와도 잡게 잠깐 더 봄
    def new_calls(self, before: int, n: int) -> list:
        for _ in range(60):
            if len(self.calls()) >= before + n:
                break
            time.sleep(0.1)
        time.sleep(1.0)
        return self.calls()[before:]

    # 설문 등록 — 반환 new 출력 json
    def new(self, spec=SPEC, thread=REG, *extra) -> dict:
        q = self.tmp / f"q_{time.time_ns()}.json"
        q.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
        r = subprocess.run([sys.executable, str(TOOL), "--dir", str(self.store), "new", str(q), "--project", "시험",
                            "--thread", thread, *extra], capture_output=True, text=True, encoding="utf-8", env=self.env, timeout=30)
        assert r.returncode == 0, r.stderr
        return json.loads(r.stdout)

    # 제출(폼 값) — 반환 HTTP 상태
    def post(self, info: dict, form: dict) -> int:
        data = urllib.parse.urlencode({**form, "_act": "submit"}).encode("utf-8")
        req = urllib.request.Request(self.base + info["path"], data=data)
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status

    # 결과 파일
    def result(self, info: dict) -> dict:
        return json.loads(Path(info["file"]).with_suffix("").with_suffix(".result.json").read_text(encoding="utf-8"))

    # 설문 화면 HTML
    def page(self, info: dict) -> str:
        with urllib.request.urlopen(self.base + info["path"], timeout=10) as resp:
            return resp.read().decode("utf-8")

    # magic.py 실행 — (종료코드, 출력)
    def magic(self, *args) -> tuple:
        env = dict(self.env, CODEX_HUB_DIR=str(self.tmp / ".codex-hub"), MAGIC_SURVEY_DIR=str(self.tmp / "sv"))
        r = subprocess.run([sys.executable, str(MAGIC), *args], capture_output=True, text=True, encoding="utf-8",
                           env=env, timeout=60, cwd=str(self.tmp))
        return r.returncode, r.stdout + r.stderr


# 받은 호출 → (thread, 메시지)
def tm(call: list) -> tuple:
    assert call[:2] == ["queue", "--thread"] and call[3].startswith("--message="), call
    return call[2], call[3][len("--message="):]


# 등록 파일 쓰기 — 세션 하나
def register(tmp: Path, nick: str, thread: str) -> None:
    p = tmp / ".codex-hub" / "sessions" / f"{nick}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"nick": nick, "thread": thread}), encoding="utf-8")


# ======= 시험 세계 — 임시 작업 폴더 · 서버 =======
# 허브 도구는 키트 devview 의 복사본(저장 폴더 위로 .codex-hub 를 찾아 그 폴더의 devview/codex_hub.py 를 부름)
@pytest.fixture(scope="module")
def world(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("route")
    (tmp / "devview").mkdir()
    for name in ("codex_hub.py", "codex_sessions.py"):
        shutil.copyfile(KIT / "devview" / name, tmp / "devview" / name)
    register(tmp, "main", MAIN)
    register(tmp, "2nd", SECOND)
    fake = tmp / "fake_codex.py"
    fake.write_text(FAKE, encoding="utf-8")
    out = tmp / "calls.jsonl"
    env = dict(os.environ, SURVEY_REGISTRY=str(tmp / "_registry.json"), FAKE_OUT=str(out), DEVVIEW_CODEX=str(fake),
               PYTHONUTF8="1")
    for k in ("SURVEY_NO_QUEUE", "CODEX_HUB_DIR", "CODEX_THREAD_ID"):
        env.pop(k, None)
    port = free_port()
    server = subprocess.Popen([sys.executable, str(TOOL), "--dir", str(tmp / "docs" / "surveys"), "serve", "--host", "127.0.0.1",
                               "--port", str(port)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
    base = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            urllib.request.urlopen(base + "/api/state?probe=1", timeout=1).read()
            break
        except OSError:
            time.sleep(0.1)
    try:
        yield World(tmp, env, base, out)
    finally:
        server.terminate()
        server.wait(timeout=10)


# ======= 경우별 시험 =======
# 확정 문항만(선택지 · 기타) → MAIN 한 번 · 등록 세션 알림 없음 · magic.py show 가 할 일을 보여 줌
def test_main_only(world):
    info = world.new()
    before = len(world.calls())
    assert world.post(info, {"q1": "A", "q2": "기타", "q2_memo": "C안으로", "q3": "보류"}) == 200
    calls = world.new_calls(before, 1)
    assert len(calls) == 1
    thread, msg = tm(calls[0])
    res = world.result(info)
    rid = res["route"][0]["request"]
    assert thread == MAIN
    assert msg.startswith(f"🪄 설문 ‹라우팅 시험›({info['id']}) 확정 2개")
    assert "[1] q1 → A" in msg and "[2] q2 → C안으로" in msg and "q3" not in msg
    assert msg.endswith(f"\n$main-magic {rid}")
    assert res["route"] == [{"to": "MAIN", "count": 2, "items": ["1", "2"], "ok": True, "request": rid}]
    req = json.loads((world.tmp / ".codex-hub" / "requests" / f"{rid}.json").read_text(encoding="utf-8"))
    assert req["target"]["kind"] == "survey" and req["target"]["survey"] == info["id"]
    code, out = world.magic("show", rid)
    assert code == 0, out
    assert "할 일: 확정 문항을 결정 문서에 반영" in out and f"result {info['id']}" in out and "[2] q2 → C안으로" in out
    assert "MAIN 전송 · 문항 2개" in world.page(info)


# 질문 문항만 → 2ND 한 번 · show 가 answer-form 자리 · answer-form 이 설명 폼으로 등록됨
def test_2nd_only(world):
    info = world.new()
    before = len(world.calls())
    world.post(info, {"q1": "질문", "q1_memo": "A 를 고르면 무엇이 바뀌나?"})
    calls = world.new_calls(before, 1)
    assert len(calls) == 1
    thread, msg = tm(calls[0])
    rid = world.result(info)["route"][0]["request"]
    assert thread == SECOND
    assert msg.startswith(f"🪄 설문 ‹라우팅 시험›({info['id']}) 질문 1개")
    assert "[1] q1 → A 를 고르면 무엇이 바뀌나?" in msg and msg.endswith(f"\n$2nd-magic {rid}")
    code, out = world.magic("show", rid)
    assert code == 0, out
    assert f"answer-form {rid}" in out and "hub.py send --to main" in out
    code, out = world.magic("answer-form", rid, "바뀌는 것: 결정 문서 1-2 절")
    assert code == 0 and out.startswith("설명 폼 등록:"), out
    code, out = world.magic("answer-md", rid, "답")
    assert code == 1 and "answer-form" in out


# 섞임(확정 + 질문 + 메모 없는 보류) → MAIN · 2ND 각각 한 번 · 등록 세션 알림 없음
def test_mixed(world):
    info = world.new()
    before = len(world.calls())
    world.post(info, {"q1": "B", "q2": "질문", "q2_memo": "왜 B?", "q3": "보류"})
    calls = world.new_calls(before, 2)
    got = sorted(tm(c) for c in calls)
    assert [t for t, _ in got] == [SECOND, MAIN]
    assert "확정 1개" in dict(got)[MAIN] and "질문 1개" in dict(got)[SECOND]
    assert [r["to"] for r in world.result(info)["route"]] == ["MAIN", "2ND"]


# 메모가 남은 보류 → 등록 세션 알림 덧붙음 · 등록 세션이 곧 MAIN 이면 한 번만
def test_left_memo_and_reg_is_main(world):
    info = world.new()
    before = len(world.calls())
    world.post(info, {"q1": "A", "q3": "보류", "q3_memo": "나중에"})
    got = sorted(tm(c)[0] for c in world.new_calls(before, 2))
    assert got == [MAIN, REG]
    info = world.new(SPEC, MAIN)
    before = len(world.calls())
    world.post(info, {"q1": "A", "q3": "보류", "q3_memo": "나중에"})
    calls = world.new_calls(before, 1)
    assert [tm(c)[0] for c in calls] == [MAIN] and tm(calls[0])[1].startswith("🪄 ")


# 받을 세션 없음 → 결과 route 실패 · 화면 빨간 줄 · 등록 세션 알림으로 넘어감
def test_no_session(world):
    reg2 = world.tmp / ".codex-hub" / "sessions" / "2nd.json"
    reg2.unlink()
    try:
        info = world.new()
        before = len(world.calls())
        world.post(info, {"q1": "질문", "q1_memo": "왜?"})
        calls = world.new_calls(before, 1)
    finally:
        register(world.tmp, "2nd", SECOND)
    assert [tm(c)[0] for c in calls] == [REG] and tm(calls[0])[1].startswith(f"@설문 ---설문 완료 · {info['id']}")
    row = world.result(info)["route"][0]
    assert row["to"] == "2ND" and row["ok"] is False and "2ND 미연결" in row["error"]
    page = world.page(info)
    assert "class='rt fail'" in page and "2ND 전송 실패 · 문항 1개 — 2ND 미연결" in page


# 보내지 않음(--no-route · 질문 파일 "route": false) → 등록 세션 알림만
def test_no_route(world):
    for info in (world.new(SPEC, REG, "--no-route"), world.new(dict(SPEC, route=False))):
        saved = json.loads(Path(info["file"]).read_text(encoding="utf-8"))
        assert saved.get("no_route") is True
        before = len(world.calls())
        world.post(info, {"q1": "A", "q2": "질문", "q2_memo": "왜?"})
        calls = world.new_calls(before, 1)
        assert [tm(c)[0] for c in calls] == [REG] and tm(calls[0])[1].startswith(f"@설문 ---설문 완료 · {info['id']}")
        assert "route" not in world.result(info)


# 화면 제출(headless 브라우저) — 선택지 클릭 → 제출 → 결과 화면 맨 위 전송 줄 · MAIN 이 받음
def test_browser_submit(world):
    sync_playwright = pytest.importorskip("playwright.sync_api").sync_playwright
    info = world.new()
    before = len(world.calls())
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.goto(world.base + info["path"])
            page.locator("label.opt", has_text="B").first.click()
            page.locator("button.ok").click()
            page.wait_for_selector("#route", timeout=30000)
            text = page.locator("#route").inner_text()
        finally:
            browser.close()
    assert "MAIN 전송 · 문항 1개" in text
    calls = world.new_calls(before, 1)
    assert [tm(c)[0] for c in calls] == [MAIN] and "[1] q1 → B" in tm(calls[0])[1]
