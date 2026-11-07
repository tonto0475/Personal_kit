"""devview 대화 탭 서브 상태 패널 시험 — 가짜 부모 · 서브 rollout + 임시 작업 폴더 + 시험 서버(빈 포트) + 헤드리스 크롬

    py -3 tests/test_hub_subs.py              판정 · API · 화면 · 캡처 tests/shots/hub_subs_*.png
    py -3 tests/test_hub_subs.py --api-only   브라우저 없이(WSL python3 에서도)

서브 rollout 모양은 2026-11-04 WSL Codex 0.163 실측 기록에서 칸 이름을 본떴다 — session_meta.source.subagent.thread_spawn
· agent_message(Payload 뒤 본문 · 암호화면 빈 본문) · custom_tool_call exec · task_complete · turn_aborted
실제 ~/.codex · ~/.devview · 8701 무관 · 창을 띄우지 않음(headless=True 고정)
"""
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import codex_hub  # noqa: E402
import test_hub as th  # noqa: E402
from test_hub import check, ev, http, wait_for  # noqa: E402

# 부모 세션 id
PARENT = {"main": "019b0000-0000-7000-8000-00000000aaaa", "2nd": "019b0000-0000-7000-8000-00000000bbbb"}
# 기준 시각(에포크 초)
T = time.time() - 60
# 긴 명령(70자 넘음 — 자름 · 말줄임 시험)
LONG_CMD = "python3 scripts/check_all.py --target app --target tests --target docs --verbose --report out/report.json --strict --retry 3"


# 서브 머리 줄 — 실측처럼 머리 앞쪽에 긴 지침 칸이 있다
# sid: 서브 id / parent: 부모 id / path: agent_path / nick: 별명
def meta(sid, parent, path, nick="Raman"):
    return ev(T, "session_meta", {"id": sid, "session_id": parent, "parent_thread_id": parent, "agent_path": path, "agent_nickname": nick,
                                  "base_instructions": {"text": "지침 " * 2000},
                                  "source": {"subagent": {"thread_spawn": {"parent_thread_id": parent, "depth": 1, "agent_path": path,
                                                                           "agent_nickname": nick, "agent_role": None}}}})


# 턴 시작 · 끝 · 중단 줄
# t: 턴 id
def started(t):
    return ev(T + 1, "event_msg", {"type": "task_started", "turn_id": t, "turn_attribution": {"initiating_agent_path": "/root"}})


def done(t, text="완료 보고\n둘째 줄"):
    return ev(T + 2, "event_msg", {"type": "task_complete", "turn_id": t, "last_agent_message": text})


def aborted(t):
    return ev(T + 2, "event_msg", {"type": "turn_aborted", "turn_id": t, "reason": "interrupted"})


# 부모 지시 줄 — body 가 없으면 실측의 암호화 모양
# body: 본문 / kind: 메시지 종류
def order(body=None, kind="NEW_TASK"):
    head = f"Message Type: {kind}\nTask name: /root/a\nSender: /root\nPayload:\n"
    content = [{"type": "input_text", "text": head + (body or "")}]
    if body is None:
        content.append({"type": "encrypted_content", "encrypted_content": "gAAAA암호"})
    return ev(T + 1, "response_item", {"type": "agent_message", "author": "/root", "recipient": "/root/a", "content": content})


# 스크립트로 싼 셸 호출 줄(실측 custom_tool_call exec)
# cmd: 명령
def shell(cmd):
    return ev(T + 1, "response_item", {"type": "custom_tool_call", "name": "exec", "call_id": "c1",
                                       "input": f"text(await tools.exec_command({{cmd:{json.dumps(cmd, ensure_ascii=False)},\"max_output_tokens\":3000}}));\n"})


# 혼잣말 줄
# text: 글
def commentary(text):
    return th.amsg(T + 1, text, "commentary")


# 줄 목록 → 파일에 덧붙일 바이트
# lines: 줄 사전 목록
def blob(lines):
    return "".join(json.dumps(x, ensure_ascii=False) + "\n" for x in lines).encode("utf-8")


# 서브 기록 파일 쓰기 — 반환 경로
# home: Codex 홈 / sid: 서브 id / parent: 부모 id / path: agent_path / lines: 머리 뒤 줄 / day: 날짜 폴더
def write_sub(home, sid, parent, path, lines=(), day=("2026", "11", "05"), nick="Raman"):
    p = home / "sessions" / Path(*day) / f"rollout-2026-11-05T10-00-00-{sid}.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(blob([meta(sid, parent, path, nick), *lines]))
    return p


# 파일 끝에 덧붙이기
# p: 파일 / data: 바이트
def append(p, data):
    with open(p, "ab") as f:
        f.write(data)


# 허브 등록 파일
# root: 작업 폴더 / nick: 닉네임 / thread: 세션 id / extra: 덧붙일 칸
def register(root, nick, thread, **extra):
    d = root / ".codex-hub" / "sessions"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{nick}.json").write_text(json.dumps({"nick": nick, "thread": thread, "effort": "low", **extra}), encoding="utf-8")


# 서브 줄 찾기
# r: subagents 결과 / name: agent_path
def sub(r, name):
    return next((x for x in r["subs"] if x["name"] == name), None)


# 판정 · 묶음 · 증분 · 한 줄 — 서버 없이 codex_hub 를 바로 부름
# base: 임시 폴더
def test_logic(base):
    home, root = base / "codex", base / "proj"
    root.mkdir()
    os.environ["CODEX_HOME"] = str(home)
    (home / "sessions").mkdir(parents=True)
    register(root, "main", PARENT["main"])
    register(root, "2nd", PARENT["2nd"])
    get = lambda n="main": codex_hub.subagents(root, n)  # noqa: E731

    check("서브 없음 — 빈 목록", get()["subs"] == [] and get()["working"] == 0, get())
    check("등록 없는 세션 — 오류 없이 빈 목록", get("nobody")["subs"] == [])
    register(root, "cl", "claude-id", kind="claude")
    check("Claude 세션 — 빈 목록", get("cl")["subs"] == [])

    # 일함 → 쉼 → 일함 → 중단
    a = write_sub(home, "s-a", PARENT["main"], "/root/a", [started("t1"), order(), shell("pytest -q tests")])
    r = sub(get(), "/root/a")
    check("task_started 뒤 = 일함 · 암호화 지시는 건너뛰고 명령", r and r["state"] == "work" and r["text"] == "pytest -q tests", r)
    time.sleep(0.01)
    check("기록이 조용해도 일함 유지", sub(get(), "/root/a")["state"] == "work")
    append(a, blob([done("t1")]))
    r = sub(get(), "/root/a")
    check("task_complete 뒤 = 쉼 · 결과 첫 줄", r["state"] == "rest" and r["text"] == "완료 보고" and not r["stopped"], r)
    append(a, blob([shell("늦게 온 도구 줄")]))
    check("끝난 뒤 늦은 도구 줄 — 일함으로 안 돌아감", sub(get(), "/root/a")["state"] == "rest")
    append(a, blob([started("t2"), done("다른 턴"), shell("두 번째 일")]))
    r = sub(get(), "/root/a")
    check("다른 턴 id 의 끝 줄 — 지금 턴을 안 닫음", r["state"] == "work" and r["text"] == "두 번째 일", r)
    append(a, blob([aborted("t2")]))
    r = sub(get(), "/root/a")
    check("turn_aborted = 쉼 + 중단", r["state"] == "rest" and r["stopped"] and "interrupted" in r["why"] and "턴 중단됨" in r["text"], r)
    append(a, blob([started("t3")]))
    r = sub(get(), "/root/a")
    check("새 턴 — 중단 표시 지움 · 자료 없으면 «턴 실행 중»", r["state"] == "work" and not r["stopped"] and r["text"] == "턴 실행 중", r)
    append(a, blob([ev(T + 2, "event_msg", {"type": "task_complete", "turn_id": "t3", "last_agent_message": None,
                                            "error": {"message": "모델 응답 실패"}})]))
    r = sub(get(), "/root/a")
    check("오류로 끝남 = 쉼 + 중단 · 오류 글", r["state"] == "rest" and r["stopped"] and r["text"] == "모델 응답 실패", r)

    # 한 줄 우선순위
    b = write_sub(home, "s-b", PARENT["main"], "/root/b", [started("u1"), commentary("파일을 살펴볼게")])
    check("한 줄 — 혼잣말만 있으면 혼잣말", sub(get(), "/root/b")["text"] == "파일을 살펴볼게")
    append(b, blob([shell("ls -la")]))
    check("한 줄 — 도구 호출이 혼잣말보다 먼저", sub(get(), "/root/b")["text"] == "ls -la")
    append(b, blob([ev(T, "response_item", {"type": "custom_tool_call", "name": "exec", "input": "text(await tools.write_stdin({session_id:3}));\n"})]))
    check("write_stdin 후속 조회 — 새 일로 안 보임", sub(get(), "/root/b")["text"] == "ls -la")
    append(b, blob([ev(T, "response_item", {"type": "custom_tool_call", "name": "exec", "input": "await tools.apply_patch({patch:'x'});\n"})]))
    check("셸 아닌 도구 — 도구 이름", sub(get(), "/root/b")["text"] == "apply_patch")
    append(b, blob([ev(T, "response_item", {"type": "function_call", "name": "wait_agent", "arguments": "{}"})]))
    check("function_call — 이름", sub(get(), "/root/b")["text"] == "wait_agent")
    append(b, blob([order("보고만 왔음", "FINAL_ANSWER")]))
    check("FINAL_ANSWER 보고 — 지시로 안 봄", sub(get(), "/root/b")["text"] == "wait_agent")
    append(b, blob([order("검증 · 섹션 1-2 · C3\n자세한 내용")]))
    check("평문 부모 지시 — 첫 줄이 맨 먼저", sub(get(), "/root/b")["text"] == "검증 · 섹션 1-2 · C3")
    append(b, blob([shell(LONG_CMD), order(LONG_CMD)]))
    r = sub(get(), "/root/b")
    check("한 줄 70자 자름", len(r["text"]) == 70 and r["text"].endswith("…"), r["text"])
    c = write_sub(home, "s-c", PARENT["main"], "/root/c", [started("c1"), th.umsg(T, "<environment_context>주입</environment_context>"),
                                                           th.umsg(T, "첫 일감 글\n둘째 줄")])
    check("유저 역할 첫 일감 — 주입 문서는 빼고 글만", sub(get(), "/root/c")["text"] == "첫 일감 글")
    c.unlink()

    # 부모별 묶음 · 내부 세션 제외 · 이름
    write_sub(home, "s-d", PARENT["2nd"], "/root/other", [started("d1")])
    write_sub(home, "s-e", PARENT["main"], "", [started("e1")], nick="Erdos")
    g = home / "sessions" / "2026" / "11" / "05" / "rollout-2026-11-05T10-00-00-guard.jsonl"
    g.write_bytes(blob([ev(T, "session_meta", {"id": "guard", "parent_thread_id": PARENT["main"], "source": {"subagent": {"other": "guardian"}}})]))
    w = home / "sessions" / "2026" / "11" / "05" / "rollout-2026-11-05T10-00-00-root.jsonl"
    w.write_bytes(blob([ev(T, "session_meta", {"id": PARENT["main"], "source": "cli"})]))
    r = get()
    check("부모별 묶음 — 2ND 서브는 MAIN 에 안 나옴", sub(r, "/root/other") is None and sub(get("2nd"), "/root/other") is not None, [x["name"] for x in r["subs"]])
    check("subagent.other(승인 검토) · 부모 자신 — 안 나옴", {x["id"] for x in r["subs"]} == {"s-a", "s-b", "s-e"}, [x["id"] for x in r["subs"]])
    check("agent_path 없으면 별명", sub(r, "Erdos") is not None)
    check("일하는 서브가 위", [x["state"] for x in r["subs"]] == ["work", "work", "rest"], [x["state"] for x in r["subs"]])
    check("working 집계", r["working"] == 2)

    # 증분 읽기 — 줄마다 한 번만 · 머리는 파일마다 한 번만
    fed, heads = [], []
    feed0, head0 = codex_hub.SubState.feed, codex_hub.sub_head
    codex_hub.SubState.feed = lambda self, o: (fed.append(o), feed0(self, o))[1]
    codex_hub.sub_head = lambda p: (heads.append(p), head0(p))[1]
    try:
        f = write_sub(home, "s-f", PARENT["main"], "/root/f", [started("f1"), shell("하나")])
        get()
        n = len(fed)
        check("새 파일 — 머리 한 번 · 줄 2개", len(heads) == 1 and n == 2, (len(heads), n))
        get()
        check("변화 없음 — 머리 · 줄 다시 안 읽음", len(heads) == 1 and len(fed) == n, (len(heads), len(fed)))
        # 쓰는 중(끝이 잘린 줄) — 다음 주기에 다시
        line = blob([shell("둘")])
        append(f, line[:30])
        r = sub(get(), "/root/f")
        check("끝이 잘린 줄 — 이번엔 안 읽음", r["text"] == "하나" and len(fed) == n, r["text"])
        append(f, line[30:])
        r = sub(get(), "/root/f")
        check("다음 주기에 이어 읽음 · 한 번만", r["text"] == "둘" and len(fed) == n + 1, (r["text"], len(fed) - n))
        # 망가진 줄 · 글자 중간에서 끊긴 줄
        append(f, b'{"type": "event_msg", "payload": {"type": "task_complete"\n')
        append(f, blob([shell("망가진 줄 다음")]))
        check("망가진 줄 — 건너뛰고 계속", sub(get(), "/root/f")["text"] == "망가진 줄 다음")
        line = blob([shell("한글 끊김")])
        cut = line.index("끊".encode("utf-8")) + 1
        append(f, line[:cut])
        get()
        append(f, line[cut:])
        check("글자 중간 잘림 — 이어 붙여 그대로", sub(get(), "/root/f")["text"] == "한글 끊김")
        # 머리 줄을 쓰는 중인 새 파일
        h = home / "sessions" / "2026" / "11" / "05" / "rollout-2026-11-05T10-00-00-s-h.jsonl"
        raw = blob([meta("s-h", PARENT["main"], "/root/h")])
        h.write_bytes(raw[:500])
        check("머리 줄 쓰는 중 — 아직 안 나옴", sub(get(), "/root/h") is None)
        append(h, raw[500:])
        check("머리 줄 완성 뒤 나옴 · 줄이 없으면 «대기»", (sub(get(), "/root/h") or {}).get("text") == "대기")
        # 작아진 파일 — 처음부터
        f.write_bytes(blob([meta("s-f", PARENT["main"], "/root/f"), started("g1"), shell("새 내용")]))
        check("파일이 작아짐 — 처음부터 다시", sub(get(), "/root/f")["text"] == "새 내용")
        # 없어진 파일
        f.unlink()
        check("없어진 파일 — 죽지 않고 빠짐", sub(get(), "/root/f") is None)
        # 머리가 망가진 파일
        (home / "sessions" / "2026" / "11" / "05" / "rollout-2026-11-05T10-00-00-bad.jsonl").write_bytes(b"not json\n")
        check("머리가 망가진 파일 — 죽지 않음", isinstance(get()["subs"], list))
    finally:
        codex_hub.SubState.feed, codex_hub.sub_head = feed0, head0

    # 날짜 폴더 — 새로 생긴 날 · 전체 훑기는 처음 한 번
    write_sub(home, "s-new", PARENT["main"], "/root/nextday", [started("n1")], day=("2026", "11", "06"))
    check("다음 날 폴더의 새 서브도 찾음", sub(get(), "/root/nextday") is not None)
    write_sub(home, "s-old", PARENT["main"], "/root/oldday", [started("o1")], day=("2026", "10", "01"))
    codex_hub._SUBS.clear()
    check("처음 훑을 때는 옛 날짜 폴더도 찾음", sub(get(), "/root/oldday") is not None)

    # 비용 — 서브 8개 · 새 데이터 없는 주기 · 한 파일에 한 줄 더한 주기
    many = [write_sub(home, f"s-m{i}", "019b-many", f"/root/m{i}", [started("m"), shell("일")]) for i in range(8)]
    register(root, "many", "019b-many")
    get("many")
    t0 = time.perf_counter()
    for _ in range(100):
        get("many")
    idle = (time.perf_counter() - t0) * 10
    t0 = time.perf_counter()
    for i in range(100):
        append(many[i % 8], blob([shell(f"일 {i}")]))
        get("many")
    busy = (time.perf_counter() - t0) * 10
    check("서브 8개 한 주기 20ms 미만(2초 주기의 1%)", idle < 20 and busy < 20, f"새 줄 없음 {idle:.2f}ms · 새 줄 있음 {busy:.2f}ms")
    os.environ.pop("CODEX_HOME", None)


# 화면 시험용 세계 — MAIN 서브 10개(스크롤) · 2ND 서브 1개 · 서브 없는 세션 doc
# base: 임시 폴더
def make_ui_world(base):
    root, home = base / "proj", base / "codex"
    (root / "docs" / "flowtree").mkdir(parents=True)
    (root / "docs" / "flowtree" / "tree.json").write_text(json.dumps(th.TREE, ensure_ascii=False), encoding="utf-8")
    (root / "app").mkdir()
    (root / "app" / "a.py").write_text("x = 1\n", encoding="utf-8")
    home.mkdir()
    register(root, "main", PARENT["main"])
    register(root, "2nd", PARENT["2nd"])
    register(root, "doc", "019b-doc")
    msgs = []
    for i in range(1, 30):
        msgs += [th.uitem(T + i, f"질문 {i}"), th.amsg(T + i, f"답 {i} — " + "대화 글이 패널 뒤로 얼마나 가려지는지 보는 긴 줄이다. " * 8, "final_answer")]
    th.write_rollout(home, PARENT["main"], msgs)
    th.write_rollout(home, PARENT["2nd"], [th.uitem(T, "2ND 질문")])
    th.write_rollout(home, "019b-doc", [th.uitem(T, "서브 없는 세션")])
    subs = [("/root/impl", [started("a"), shell(LONG_CMD)]),
            ("/root/very_long_agent_path_name_for_truncation_check", [started("b"), shell("pytest -q")]),
            ("/root/verify", [started("c"), done("c", "검증 통과 — 시험 12개")]),
            ("/root/stopped", [started("d"), aborted("d")]),
            ("/root/wide", [started("e"), done("e", "가" * 200)])]
    subs += [(f"/root/worker{i}", [started("w"), done("w", f"작업 {i} 끝")]) for i in range(5)]
    sp = {name: write_sub(home, f"s{i:02d}", PARENT["main"], name, lines) for i, (name, lines) in enumerate(subs)}
    write_sub(home, "s-2nd", PARENT["2nd"], "/root/second", [started("z"), shell("ls")])
    # th.start 가 요구하는 가짜 codex
    fake = base / "fake_codex.py"
    fake.write_text("print('ok')\n", encoding="utf-8")
    return {"root": root, "home": home, "log": base / "q.jsonl", "fake": fake, "base": base, "subs": sp}


# API + 화면
# w: 세계 / base: 서버 주소 / api_only: 화면 시험 건너뜀
def test_server(w, base, api_only):
    code, d = http(base + "/api/hub/subagents?nick=main")
    check("GET /api/hub/subagents — 10줄 · 일함 2", code == 200 and len(d["subs"]) == 10 and d["working"] == 2, (code, d.get("working")))
    code, d = http(base + "/api/hub/subagents?nick=doc")
    check("서브 없는 세션 — 빈 목록", code == 200 and d["subs"] == [], d)
    code, d = http(base + "/api/hub/subagents?nick=" + "%22x")
    check("닉네임 형식 오류 — 400", code == 400, code)
    if api_only:
        return
    from playwright.sync_api import sync_playwright
    th.SHOTS.mkdir(exist_ok=True)
    with sync_playwright() as pw:
        try:
            br = pw.chromium.launch(headless=True)
        except Exception:  # noqa: BLE001
            br = pw.chromium.launch(channel="chrome", headless=True)
        page = br.new_page(viewport={"width": 1600, "height": 960})
        errs = []
        page.on("pageerror", lambda e: errs.append(str(e)))
        page.goto(base + "/")
        page.wait_for_selector("html[data-ready='1']", timeout=30000)
        page.click("#chatTab")
        page.wait_for_selector(".dv-chat-tab[data-nick='main']", timeout=10000)
        page.click(".dv-chat-tab[data-nick='main']")
        panel = page.locator(".dv-subs")
        check("MAIN — 패널 보임 · 줄 10개", wait_for(lambda: panel.is_visible() and page.locator(".dv-sub").count() == 10, 8), page.locator(".dv-sub").count())
        check("머리 — 서브 수 · 일함 수", page.locator(".dv-subs-sum").inner_text() == "서브 10 · 일함 2", page.locator(".dv-subs-sum").inner_text())
        # 위치 — 대화 오른쪽 아래 · 입력창 바로 위 · 스크롤바를 안 가림
        pb = panel.bounding_box()
        lb = page.locator(".dv-chat-list").bounding_box()
        fb = page.locator(".dv-chat-foot").bounding_box()
        check("위치 — 입력창 바로 위(8px) · 오른쪽 18px", abs(fb["y"] - (pb["y"] + pb["height"]) - 8) <= 1 and abs(lb["x"] + lb["width"] - (pb["x"] + pb["width"]) - 18) <= 1, (pb, lb, fb))
        check("크기 — 400px · 머리 포함 8줄 높이 이내", pb["width"] == 400 and pb["height"] <= 22 + 177 + 2, pb)
        m = page.evaluate("(() => { const l = document.querySelector('.dv-subs-list'); const rows = [...l.querySelectorAll('.dv-sub')];"
                          " const box = l.getBoundingClientRect();"
                          " return {seen: rows.filter((r) => r.getBoundingClientRect().bottom <= box.bottom + 1).length, sh: l.scrollHeight, ch: l.clientHeight,"
                          " cut: [...l.querySelectorAll('.dv-sub-mark')].filter((x) => x.scrollWidth > x.clientWidth).length,"
                          " tx: [...l.querySelectorAll('.dv-sub-text, .dv-sub-name')].filter((x) => x.scrollWidth > x.clientWidth && getComputedStyle(x).textOverflow !== 'ellipsis').length,"
                          " head: (() => { const h = document.querySelector('.dv-subs-sum'); return h.scrollWidth > h.clientWidth; })()}; })()")
        check("8줄까지 보이고 나머지는 스크롤", m["seen"] == 8 and m["ch"] >= 176 and m["sh"] > m["ch"], m)
        check("표시 · 머리 글자 안 잘림 · 긴 칸은 말줄임", m["cut"] == 0 and m["tx"] == 0 and not m["head"], m)
        row = lambda i: page.locator(".dv-sub").nth(i)  # noqa: E731
        check("일하는 서브가 위 · 초록 표시", "is-work" in row(0).get_attribute("class") and row(0).locator(".dv-sub-mark").inner_text() == "일함")
        check("이름 앞 /root/ 뺌", row(0).locator(".dv-sub-name").inner_text() == "impl", row(0).inner_text())
        tip = row(0).get_attribute("title")
        check("툴팁 — 전체 이름 · 별명 · 70자까지의 글", "/root/impl (Raman) · 일함" in tip and LONG_CMD[:60] in tip, tip)
        stop = page.locator(".dv-sub.is-stop")
        check("중단 서브 — «중단» 표시 · 이유 글", stop.count() == 1 and stop.locator(".dv-sub-mark").inner_text() == "중단" and "턴 중단됨" in stop.inner_text(), stop.inner_text())
        check("쉼 서브 — 결과 첫 줄", "검증 통과" in page.locator(".dv-sub[data-sub='s02']").inner_text())
        panel.screenshot(path=str(th.SHOTS / "hub_subs_panel.png"))
        page.screenshot(path=str(th.SHOTS / "hub_subs_full.png"))
        # 살아 있는 갱신 — 쉼 → 일함
        append(w["subs"]["/root/verify"], blob([started("c2"), shell("두 번째 검증")]))
        check("기존 갱신 주기로 쉼 → 일함 반영", wait_for(lambda: page.locator(".dv-subs-sum").inner_text() == "서브 10 · 일함 3", 6), page.locator(".dv-subs-sum").inner_text())
        # 접기
        page.click(".dv-subs-fold")
        fbx = panel.bounding_box()
        check("접기 — 줄 숨김 · 머리만 · 오른쪽 아래 그대로", not page.locator(".dv-subs-list").is_visible() and fbx["height"] <= 26 and fbx["width"] < 200
              and abs((fbx["y"] + fbx["height"]) - (pb["y"] + pb["height"])) <= 1, fbx)
        page.screenshot(path=str(th.SHOTS / "hub_subs_folded.png"), clip={"x": fbx["x"] - 120, "y": fbx["y"] - 40, "width": fbx["width"] + 140, "height": fbx["height"] + 70})
        check("접기 뒤 입력칸 포커스 유지", page.evaluate("document.activeElement.className") == "dv-chat-input", page.evaluate("document.activeElement.className"))
        page.reload()
        page.wait_for_selector("html[data-ready='1']", timeout=30000)
        page.click("#chatTab")
        check("접힘 상태 기억", wait_for(lambda: panel.is_visible(), 8) and not page.locator(".dv-subs-list").is_visible())
        page.click(".dv-subs-fold")
        # 끌어 옮기기 — 머리줄을 끌면 자리 이동 · 새로고침 뒤에도 유지 · 더블클릭 = 기본 자리
        b0 = panel.bounding_box()
        hb = page.locator(".dv-subs-sum").bounding_box()
        page.mouse.move(hb["x"] + 5, hb["y"] + 5)
        page.mouse.down()
        page.mouse.move(hb["x"] - 200, hb["y"] - 120, steps=6)
        page.mouse.up()
        b1 = panel.bounding_box()
        check("머리줄 끌기 — 패널 이동", b1["x"] < b0["x"] - 150 and b1["y"] < b0["y"] - 80, (b0, b1))
        page.reload()
        page.wait_for_selector("html[data-ready='1']", timeout=30000)
        page.click("#chatTab")
        wait_for(lambda: panel.is_visible(), 8)
        b2 = panel.bounding_box()
        check("옮긴 자리 기억(새로고침 뒤)", abs(b2["x"] - b1["x"]) < 3 and abs(b2["y"] + b2["height"] - b1["y"] - b1["height"]) < 3, (b1, b2))
        page.locator(".dv-subs-sum").dblclick()
        check("더블클릭 — 기본 자리", wait_for(lambda: abs(panel.bounding_box()["x"] - b0["x"]) < 3, 3), panel.bounding_box())
        # 세션 전환 — 그 세션 서브만 · 없으면 숨김
        page.click(".dv-chat-tab[data-nick='2nd']")
        check("2ND 탭 — 2ND 서브만", wait_for(lambda: page.locator(".dv-sub").count() == 1 and page.locator(".dv-sub-name").first.inner_text() == "second", 6), page.locator(".dv-sub").count())
        page.click(".dv-chat-tab[data-nick='doc']")
        check("서브 없는 세션 — 패널 숨김", wait_for(lambda: not panel.is_visible(), 6))
        page.screenshot(path=str(th.SHOTS / "hub_subs_none.png"))
        page.click(".dv-chat-tab[data-nick='main']")
        check("MAIN 으로 돌아오면 다시 보임", wait_for(lambda: panel.is_visible() and page.locator(".dv-sub").count() == 10, 6))
        # 좁은 화면 — 패널이 대화 폭 안
        page.set_viewport_size({"width": 420, "height": 700})
        nb = panel.bounding_box()
        lb = page.locator(".dv-chat-list").bounding_box()
        check("좁은 화면 — 패널이 대화 폭을 안 넘음", nb["x"] >= lb["x"] and nb["x"] + nb["width"] <= lb["x"] + lb["width"], (nb, lb))
        check("화면 오류 없음", not errs, errs[:3])
        br.close()


def main():
    api_only = "--api-only" in sys.argv
    tmp = Path(tempfile.mkdtemp(prefix="dv_subs_"))
    proc = None
    try:
        (tmp / "a").mkdir()
        test_logic(tmp / "a")
        (tmp / "b").mkdir()
        w = make_ui_world(tmp / "b")
        proc, base = th.start(w)
        test_server(w, base, api_only)
    finally:
        if proc:
            proc.terminate()
            try:
                proc.wait(5)
            except Exception:  # noqa: BLE001
                proc.kill()
        shutil.rmtree(tmp, ignore_errors=True)
    bad = [n for n, ok in th.RESULTS if not ok]
    print(f"결과: {len(th.RESULTS) - len(bad)}/{len(th.RESULTS)} 통과" + (f" · 실패 {bad}" if bad else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
