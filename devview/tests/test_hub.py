"""devview 코덱스 허브 · 대화 탭 시험 — 임시 작업 폴더 + 가짜 Codex 홈(rollout) + 가짜 codex 실행 파일 + 시험 서버(빈 포트) + 헤드리스 크롬

    py -3 tests/test_hub.py              API + 화면 · 결과 PASS/FAIL · 캡처 tests/shots/hub_*.png
    py -3 tests/test_hub.py --api-only   API 만(브라우저 없이 · WSL python3 에서도)
    CC_HEADED=1 py -3 tests/test_hub.py  창을 띄워 눈으로 보기

시험 재료: 시험 안에서 만드는 작은 가상 그래프(TREE · 일반 이름) → 작업 폴더/docs/flowtree/tree.json · 작은 app · .codex-hub 등록(main · 2nd + 추가 5)
rollout 모양은 2026-11-02 WSL Codex 0.163(데몬 0.166) 실측 기록에서 칸 이름을 본떴다 — item_completed UserMessage · phase final_answer
· turn_attribution.turn_trigger(queue) · <environment_context> · <skill> 주입 · task_complete.error
실제 ~/.codex · ~/.devview · 8701 무관(서버의 HOME · USERPROFILE · CODEX_HOME 을 임시 폴더로) · queue 는 가짜 codex(인자를 파일에 적음)
단언 대상은 관측 결과: HTTP 상태 · 요청 파일 · tree.json 노드 · 가짜 codex 가 받은 인자 · 화면 위치 · 보이는 글자 · 클래스
"""
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

# 시험 폴더 · devview 폴더
HERE = Path(__file__).resolve().parent
DEVVIEW = HERE.parent / "devview.py"
# flowtree 폴더 — 키트 devview/flowtree → 로컬 형제 ../flowtree
FLOWTREE = next(d for d in (HERE.parent / "flowtree", HERE.parent.parent / "flowtree") if (d / "server.py").is_file())
# 작은 가상 그래프 — 요구 2 · 세부 · 결정 · 선택지(그래프가 그려졌는지 «노드 10개 넘음» 으로 봄)
TREE = {"version": 2, "rev": 0, "title": "시험 그래프", "code": {"root": "../../app"}, "edges": [], "nodes": [
    {"id": "root", "kind": "root", "title": "시험 시스템"},
    {"id": "g-req", "kind": "group", "parent": "root", "title": "필수 요구"},
    {"id": "r-one", "kind": "req", "parent": "g-req", "title": "요구 하나"},
    *[{"id": f"x-one-{i}", "kind": "detail", "parent": "r-one", "title": f"세부 {i}"} for i in range(1, 5)],
    {"id": "r-two", "kind": "req", "parent": "g-req", "title": "요구 둘"},
    *[{"id": f"x-two-{i}", "kind": "detail", "parent": "r-two", "title": f"세부 {i}"} for i in range(1, 3)],
    {"id": "d-pick", "kind": "decision", "parent": "r-two", "title": "고를 것"},
    {"id": "o-a", "kind": "option", "parent": "d-pick", "title": "선택지 가"},
    {"id": "o-b", "kind": "option", "parent": "d-pick", "title": "선택지 나"}]}
# 작은 app(코드 보기 재료) — 상대 경로 → 줄 목록
APP = {"src/main.py": ["from src.core import calc", "", "", "def main():", "    print(calc.twice(2))"],
       "src/core/calc.py": ["def twice(x):", "    return x * 2"]}
# 설문 도구(있으면 --survey 로 — 설문 보기에서도 허브가 뜨는지)
SURVEY = next((p for p in (HERE.parent.parent / ".agents" / "skills" / "survey" / "survey.py",
                           Path.home() / "OneDrive" / "바탕 화면" / "Hackerton" / ".agents" / "skills" / "survey" / "survey.py")
               if p.is_file()), None)
SHOTS = HERE / "shots"
HEADED = os.environ.get("CC_HEADED") == "1"
RESULTS = []
# 세션 id
TH = {"main": "019a0000-0000-7000-8000-00000000aaaa", "aux": "019a0000-0000-7000-8000-00000000bbbb",
      "2nd": "019a0000-0000-7000-8000-00000000cccc"}
# 기준 시각(에포크 초)
T0 = time.time() - 120
# 긴 상태 줄(툴팁 시험)
LONG_STATUS = ("❇️_1-2 : UI 구현 작업. 운영자 화면 제작 — 표 · 그래프 · 목표선 · 필터 · 내보내기 · 권한 화면 · 로그 화면 · 알림 화면까지 "
               "한 번에 묶어서 끝까지 만든다(넘치는 글 — 툴팁으로 전체가 보여야 함)")
NOTES = "# 메모\n\n첫 문단 글이다.\n둘째 줄도 같은 문단.\n\n| 열 A | 열 B |\n|---|---|\n| 가 | 1 |\n| 나 | 2 |\n\n끝 문단\n"
CODE = "#!/usr/bin/env python3\n# -*- coding: utf-8 -*-\nimport os\n\n\ndef calc(x):\n    return x * 2\n"


# 빈 포트
def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# 결과 한 줄
# name: 항목 / ok: 통과 / detail: 덧붙임
def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'PASS' if ok else 'FAIL'} | {name}{' | ' + str(detail)[:260] if detail else ''}", flush=True)


# 조건이 참이 될 때까지(상한은 멈춤 방지용)
# fn: 조건 / timeout: 상한 초
def wait_for(fn, timeout=8.0, step=0.1):
    end = time.time() + timeout
    while time.time() < end:
        try:
            if fn():
                return True
        except Exception:  # noqa: BLE001
            pass
        time.sleep(step)
    return False


# rollout 줄
# t: 에포크 초 / kind: 줄 종류 / payload: 내용
def ev(t, kind, payload):
    return {"timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(t)) + ".000Z", "type": kind, "payload": payload}


# 유저 역할 글 줄
# t: 시각 / text: 글
def umsg(t, text):
    return ev(t, "response_item", {"type": "message", "role": "user", "content": [{"type": "input_text", "text": text}]})


# 답 줄
# t: 시각 / text: 글 / phase: 단계(final_answer · commentary · None)
def amsg(t, text, phase=None):
    p = {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": text}]}
    if phase:
        p["phase"] = phase
    return ev(t, "response_item", p)


# 실제 유저 글(정본)
# t: 시각 / text: 글
def uitem(t, text):
    return ev(t, "event_msg", {"type": "item_completed", "item": {"type": "UserMessage", "content": [{"type": "text", "text": text}]}})


# rollout 파일 쓰기 — 반환 경로
# home: Codex 홈 / sid: 세션 id / events: 머리 뒤 줄
def write_rollout(home, sid, events):
    p = home / "sessions" / "2026" / "11" / "02" / f"rollout-2026-11-02T00-00-00-{sid}.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    head = ev(T0, "session_meta", {"id": sid, "session_id": sid, "cwd": "/work", "cli_version": "0.163.0"})
    p.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in [head] + events) + "\n", encoding="utf-8")
    return p


# 작업 폴더 · Codex 홈 · 가짜 codex 만들기 — 반환 {root, home, log, rollouts}
# base: 임시 폴더
def make_world(base):
    root = base / "proj"
    for rel, lines in APP.items():
        (root / "app" / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / "app" / rel).write_text("\n".join(lines) + "\n", encoding="utf-8")
    (root / "docs" / "flowtree").mkdir(parents=True)
    (root / "docs" / "notes.md").write_text(NOTES, encoding="utf-8")
    (root / "src").mkdir()
    (root / "src" / "calc.py").write_text(CODE, encoding="utf-8")
    (root / "data.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    (root / "docs" / "flowtree" / "tree.json").write_text(json.dumps(TREE, ensure_ascii=False, indent=1), encoding="utf-8")
    # ADR 작업 노드 · 검증 노드(쓰기 통로로)
    sys.path.insert(0, str(FLOWTREE))
    import flowtree_store as fs  # noqa: E402
    tp = root / "docs" / "flowtree" / "tree.json"
    fs.apply(tp, "main", "add", parent="-", title="ADR 작업 하나", summary="허브 시험", graph="adr", doc="docs/notes.md#1-2")
    fs.apply(tp, "main", "verify-add", target="t1", what="tests/test_x.py")
    # 허브 등록
    hub = root / ".codex-hub"
    regs = {"main": dict(thread=TH["main"], effort="?", effort_src="?", status=LONG_STATUS),
            "aux": dict(thread=TH["aux"], effort="medium", effort_src="인자", status="확인 : 검증 v1"),
            "2nd": dict(thread=TH["2nd"], effort="?", effort_src="?", status="답변 : 왜 판 번호?"),   # effort 없음 → 모델 기본값(low)
            "doc1": dict(thread="019a-doc1", effort="high", effort_src="인자", status="추가 세션 1"),
            "doc2": dict(thread="019a-doc2", effort="xhigh", effort_src="인자", status="추가 세션 2"),
            "doc3": dict(thread="019a-doc3", effort="low", effort_src="인자", status="추가 세션 3"),
            "bad": dict(thread="fail-thread", effort="low", effort_src="인자", status="queue 실패 시험")}
    (hub / "sessions").mkdir(parents=True)
    for i, (nick, d) in enumerate(regs.items()):
        d.update(nick=nick, model="gpt-x", cwd=str(root), registered_at=f"2026-11-02 00:0{i}:00", status_at="2026-11-02 00:10:00")
        (hub / "sessions" / f"{nick}.json").write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    (hub / "logs").mkdir()
    (hub / "logs" / "main.jsonl").write_text("".join(json.dumps({"at": f"2026-11-02 00:1{i}:00", "text": f"❇️_1-{i} 결과 줄 {i} · src/x{i}.py"},
                                                                 ensure_ascii=False) + "\n" for i in range(1, 4)), encoding="utf-8")
    # Codex 기록
    home = base / "codex"
    ro = {}
    ro["main"] = write_rollout(home, TH["main"], [
        ev(T0 + 1, "event_msg", {"type": "task_started", "turn_id": "u0", "model_context_window": 258000,
                                 "turn_attribution": {"turn_trigger": "user"}}),
        ev(T0 + 1, "turn_context", {"turn_id": "u0", "cwd": "/work", "model": "gpt-x", "effort": "high"}),
        umsg(T0 + 2, "<environment_context>\n  <cwd>/work</cwd>\n</environment_context>"),
        umsg(T0 + 3, "안녕 — 시작하자"), uitem(T0 + 3, "안녕 — 시작하자"),
        amsg(T0 + 4, "생각 중 메모", "commentary"), amsg(T0 + 5, "안녕하세요 — 준비됨", "final_answer"),
        ev(T0 + 6, "event_msg", {"type": "task_complete", "turn_id": "u0", "last_agent_message": "안녕하세요 — 준비됨"}),
        ev(T0 + 10, "event_msg", {"type": "task_started", "turn_id": "u1", "model_context_window": 258000,
                                  "turn_attribution": {"turn_trigger": "queue"}}),
        ev(T0 + 10, "turn_context", {"turn_id": "u1", "cwd": "/work", "model": "gpt-x", "effort": "high"}),
        umsg(T0 + 11, "$codex-hub 붙어"), uitem(T0 + 11, "$codex-hub 붙어"),
        umsg(T0 + 12, "<skill>\n<name>codex-hub</name>\n본문\n</skill>"),
        ev(T0 + 13, "event_msg", {"type": "token_count", "info": {"last_token_usage": {"total_tokens": 154000}, "model_context_window": 258000}}),
    ])
    ro["aux"] = write_rollout(home, TH["aux"], [
        ev(T0 + 1, "event_msg", {"type": "task_started", "turn_id": "i1", "model_context_window": 1000,
                                 "turn_attribution": {"turn_trigger": "queue"}}),
        umsg(T0 + 2, "<environment_context>x</environment_context>"), umsg(T0 + 3, "검증 해 줘"),
        amsg(T0 + 4, "검증 끝 — 통과"),
        ev(T0 + 5, "event_msg", {"type": "token_count", "info": {"last_token_usage": {"total_tokens": 250}, "model_context_window": 1000}}),
        ev(T0 + 6, "event_msg", {"type": "task_complete", "turn_id": "i1", "last_agent_message": "검증 끝 — 통과"}),
    ])
    ro["2nd"] = write_rollout(home, TH["2nd"], [
        ev(T0 + 1, "event_msg", {"type": "task_started", "turn_id": "s1", "model_context_window": 1000}),
        uitem(T0 + 2, "OK"),
        ev(T0 + 3, "event_msg", {"type": "task_complete", "turn_id": "s1", "last_agent_message": None,
                                 "error": {"message": "모델 없음 — 시험 오류", "codex_error_info": "model_not_found"}}),
    ])
    # 추가 세션 doc2 — 유저 글 · 다른 세션이 보낸 글(@MAIN · @설문) · 마법봉 글(🪄) 섞임
    ro["doc2"] = write_rollout(home, "019a-doc2", [
        ev(T0 + 1, "event_msg", {"type": "task_started", "turn_id": "d1", "turn_attribution": {"turn_trigger": "user"}}),
        uitem(T0 + 2, "그냥 유저 글"),
        ev(T0 + 3, "event_msg", {"type": "task_complete", "turn_id": "d1", "last_agent_message": None}),
        ev(T0 + 4, "event_msg", {"type": "task_started", "turn_id": "d2", "turn_attribution": {"turn_trigger": "queue"}}),
        uitem(T0 + 5, "@MAIN 검증 결과 받았어"),
        ev(T0 + 6, "event_msg", {"type": "task_complete", "turn_id": "d2", "last_agent_message": None}),
        ev(T0 + 7, "event_msg", {"type": "task_started", "turn_id": "d3", "turn_attribution": {"turn_trigger": "queue"}}),
        uitem(T0 + 8, "🪄 섹션 1 ‹화면›(t1) 구현해 줘\n$main-magic m1103-000000-abcd"),
        ev(T0 + 9, "event_msg", {"type": "task_complete", "turn_id": "d3", "last_agent_message": None}),
        ev(T0 + 10, "event_msg", {"type": "task_started", "turn_id": "d4", "turn_attribution": {"turn_trigger": "queue"}}),
        uitem(T0 + 11, "@설문 ---설문 완료 · s1 · 제목 → python3 ~/.codex/skills/survey/survey.py result s1"),
        ev(T0 + 12, "event_msg", {"type": "task_complete", "turn_id": "d4", "last_agent_message": None}),
    ])
    # 모델 기본 effort — Codex 홈 models_cache.json(실제 모양: models[].slug · default_reasoning_level)
    (home / "models_cache.json").write_text(json.dumps({"models": [{"slug": "gpt-x", "default_reasoning_level": "low"}]}), encoding="utf-8")
    # 가짜 codex — 인자를 줄마다 적음 · fail-thread 면 종료코드 3
    fake = base / "fake_codex.py"
    fake.write_text(
        "import json, os, sys\n"
        "args = sys.argv[1:]\n"
        "with open(os.environ['FAKE_CODEX_LOG'], 'a', encoding='utf-8') as f:\n"
        "    f.write(json.dumps(args, ensure_ascii=False) + '\\n')\n"
        "th = args[args.index('--thread') + 1] if '--thread' in args else ''\n"
        "if th == 'fail-thread':\n"
        "    print(\"Error: No active session found matching 'fail-thread'\", file=sys.stderr)\n"
        "    sys.exit(3)\n"
        "print(f'Queued message m-1 for thread {th}.')\n", encoding="utf-8")
    # git 저장소(Git 보기 마법봉 시험) — 없으면 그 시험만 건너뜀
    try:
        genv = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@e", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@e")
        for args in (["init", "-q"], ["add", "-A"], ["commit", "-q", "-m", "시험 커밋"]):
            subprocess.run(["git", *args], cwd=root, env=genv, check=True, capture_output=True)
    except (OSError, subprocess.CalledProcessError):
        pass
    return {"root": root, "home": home, "log": base / "queue_log.jsonl", "fake": fake, "rollouts": ro, "tree": tp, "base": base}


# 가짜 codex 가 받은 인자 목록
# w: 시험 세계
def queued(w):
    if not w["log"].is_file():
        return []
    return [json.loads(x) for x in w["log"].read_text(encoding="utf-8").splitlines() if x.strip()]


# devview 시험 서버 — (프로세스, 주소)
# w: 시험 세계
def start(w, extra=None):
    port = free_port()
    # 임시 홈 — ~/.devview(보던 상태 · 설문 목록)가 실제 홈에 안 쌓이게
    home = w["base"] / "home"
    home.mkdir(exist_ok=True)
    env = dict(os.environ, DEVVIEW_NO_VAULT="1", CODEX_HOME=str(w["home"]), DEVVIEW_CODEX=str(w["fake"]),
               FAKE_CODEX_LOG=str(w["log"]), HOME=str(home), USERPROFILE=str(home), PYTHONUTF8="1")
    env.update(extra or {})
    cmd = [sys.executable, str(DEVVIEW), str(w["root"]), "--host", "127.0.0.1", "--port", str(port)]
    if SURVEY:
        cmd += ["--survey", str(SURVEY)]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env)
    base = f"http://127.0.0.1:{port}"
    for _ in range(100):
        if proc.poll() is not None:
            raise RuntimeError("서버 기동 실패: " + proc.stdout.read().decode("utf-8", "replace"))
        try:
            urllib.request.urlopen(base + "/api/info", timeout=1).read()
            return proc, base
        except OSError:
            time.sleep(0.1)
    proc.kill()
    raise RuntimeError("서버 응답 없음")


# HTTP → (상태, 본문 사전)
# url: 주소 / body: POST 본문 사전(없으면 GET) / hdr: X-Devview 붙임
def http(url, body=None, hdr=True):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method="POST" if data is not None else "GET",
                                 headers={"Content-Type": "application/json", **({"X-Devview": "1"} if hdr else {})})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except ValueError:
            return e.code, {}


# 요청 파일 읽기
# w: 시험 세계 / rid: 요청 id
def request_file(w, rid):
    return json.loads((w["root"] / ".codex-hub" / "requests" / f"{rid}.json").read_text(encoding="utf-8"))


# ======= API =======
def test_api(w, base):
    code, d = http(base + "/api/info")
    check("info.hub = true", code == 200 and d.get("hub") is True, d.get("hub"))
    code, d = http(base + "/api/hub")
    rows = d.get("rows") or []
    nicks = [r["nick"] for r in rows]
    check("/api/hub 행 순서 — 기본 2(MAIN · 2ND · INSP 행 없음) + 추가(등록 순)", nicks == ["main", "2nd", "aux", "doc1", "doc2", "doc3", "bad"], nicks)
    m = rows[0] if rows else {}
    check("MAIN 작업 중 · effort 기록 high · 맥락 154k/258k", m.get("state") == "working" and m.get("effort") == "high"
          and m.get("effort_src") == "기록" and m.get("context", {}).get("used") == 154000 and m.get("context", {}).get("window") == 258000,
          (m.get("state"), m.get("effort"), m.get("context")))
    i = rows[2] if len(rows) > 2 else {}
    check("aux 대기 · 마지막 턴 id · effort 등록값 medium", i.get("state") == "idle" and (i.get("done") or {}).get("id") == "i1"
          and i.get("effort") == "medium" and not (i.get("done") or {}).get("error"), (i.get("state"), i.get("done"), i.get("effort")))
    s = rows[1] if len(rows) > 1 else {}
    check("2ND 오류 — task_complete.error 글", "시험 오류" in str((s.get("done") or {}).get("error")), s.get("done"))
    check("2ND effort 기록 · 등록 없음 → 모델 기본값 low(기본값)", s.get("effort") == "low" and s.get("effort_src") == "기본값",
          (s.get("effort"), s.get("effort_src")))
    check("추가 세션 — 기록 없음 안내 · role 없음", rows[3].get("role") is None and rows[3].get("note"), rows[3])
    check("queue 준비(가짜 codex)", d.get("queue", {}).get("ok") is True, d.get("queue"))
    code, d = http(base + "/api/hub/log?nick=main")
    check("/api/hub/log — 오래된 것이 위 · 3줄", code == 200 and [x["text"][:6] for x in d["lines"]] == ["❇️_1-1", "❇️_1-2", "❇️_1-3"],
          d.get("lines"))
    code, d = http(base + "/api/hub/log?nick=../x")
    check("/api/hub/log 닉네임 형식 거부", code == 400, code)

    # 대화 — 유저 글(정본) · 최종 답변 · 주입 문서 뺌
    code, d = http(base + "/api/hub/chat?nick=main")
    items = d.get("items") or []
    roles = [(x["role"], x["text"]) for x in items]
    check("대화(main) — 🚹 · 혼잣말(note) · 🤖 · 🚹(주입 없음)", roles == [("user", "안녕 — 시작하자"), ("note", "생각 중 메모"),
                                                                    ("assistant", "안녕하세요 — 준비됨"), ("user", "$codex-hub 붙어")], roles)
    check("대화 — 주입 문서(<environment_context> · <skill>) 없음", not any("<environment_context>" in x["text"] or "<skill>" in x["text"]
                                                                       for x in items))
    check("대화 — queue 로 들어온 글 표시(via)", items and items[-1].get("via") == "queue", items[-1:] and items[-1].get("via"))
    code, d2 = http(base + f"/api/hub/chat?nick=main&after={d.get('total')}")
    check("대화 after=N — 새 항목만(0개)", code == 200 and d2.get("items") == [] and d2.get("total") == d.get("total"), d2)
    code, d = http(base + "/api/hub/chat?nick=aux")
    roles = [(x["role"], x["text"]) for x in d.get("items") or []]
    check("대화(aux, 옛 판) — 유저 역할 글 · 턴 끝 답", roles == [("user", "검증 해 줘"), ("assistant", "검증 끝 — 통과")], roles)
    code, d = http(base + "/api/hub/chat?nick=2nd")
    check("대화(2nd) — 오류 항목", [x["role"] for x in d.get("items") or []] == ["user", "error"], d.get("items"))
    code, d = http(base + "/api/hub/chat?nick=doc2")
    check("대화(doc2) — @MAIN · 🪄 · @설문 글도 유저 글로 그대로(4개)", [x["role"] for x in d.get("items") or []] == ["user"] * 4
          and d["items"][1]["text"] == "@MAIN 검증 결과 받았어" and d["items"][2]["text"].startswith("🪄 "), d.get("items"))
    code, d = http(base + "/api/hub/chat?nick=doc1")
    check("대화 — 기록 없는 세션 404", code == 404, (code, d))
    code, d = http(base + "/api/hub/chat?nick=nobody")
    check("대화 — 미등록 세션 404", code == 404, code)

    # queue
    code, _ = http(base + "/api/hub/queue", {"nick": "main", "text": "x"}, hdr=False)
    check("POST /api/hub/queue — X-Devview 없으면 403", code == 403, code)
    text = '기호 $HOME & | ; "따옴표" %PATH% `백틱`\n둘째 줄 -- --message=가짜'
    code, d = http(base + "/api/hub/queue", {"nick": "main", "text": text})
    q = queued(w)
    check("queue 성공 · 출력 끝 줄", code == 200 and d.get("ok") and "Queued message" in d.get("out", ""), (code, d))
    check("queue 인자 — 셸 없이 그대로(기호 · 줄바꿈 · = 붙임)", q and q[-1] == ["queue", "--thread", TH["main"], f"--message={text}"],
          q[-1:] if q else q)
    code, d = http(base + "/api/hub/queue", {"nick": "bad", "text": "실패해야 함"})
    check("queue 실패 — 종료코드 3 → 502 · 원인 한 줄", code == 502 and "종료코드 3" in d.get("error", "") and "No active session" in d.get("error", ""),
          (code, d))
    code, d = http(base + "/api/hub/queue", {"nick": "ghost", "text": "x"})
    check("queue — 미등록 세션 409", code == 409 and "미연결" in d.get("error", ""), (code, d))
    code, d = http(base + "/api/hub/queue", {"nick": "main", "text": "   "})
    check("queue — 빈 글 400", code == 400, code)

    # magic
    n0 = len(queued(w))
    code, d = http(base + "/api/hub/magic", {"nick": "main", "view": "graph", "selection": {"nodes": []}})
    check("main 마법봉 — 노드 없음 400 · queue 안 함", code == 400 and "노드를 고르지 않음" in d.get("error", "") and len(queued(w)) == n0, (code, d))
    code, d = http(base + "/api/hub/magic", {"nick": "main", "view": "graph", "selection": {
        "nodes": [{"id": "t1", "kind": "task", "graph": "adr", "title": "ADR 작업 하나"}, {"id": "r-one", "kind": "req"}],
        "graph_view": "adr"}})
    rid = d.get("id")
    req = request_file(w, rid) if rid else {}
    want = f"🪄 섹션 1-2 ‹ADR 작업 하나›(t1) 구현해 줘 — 요약: 허브 시험\n맥락: ‹요구 하나›(r-one)\n$main-magic {rid}"
    check("main 마법봉 — 요청 파일(노드 2) · queue «🪄 지시 본문 + 끝 줄 $main-magic 요청id»", code == 200
          and [x["id"] for x in req.get("nodes", [])] == ["t1", "r-one"] and queued(w)[-1][-1] == f"--message={want}", (code, d, queued(w)[-1:]))
    check("요청 파일 message = queue 글", req.get("message") == want, req.get("message"))
    # main 마법봉 — 함수 표(파일 · 함수) · 유저가 고쳐 아직 코드에 반영 안 된 이름(«이름 바뀜»)이 지시 본문에
    sys.path.insert(0, str(FLOWTREE))
    import flowtree_store as fs  # noqa: E402
    ftid = fs.apply(w["tree"], "main", "add", parent="-", title="함수 작업", summary="함수 표", graph="hand_off",
                    funcs=["calc.py | 두배 | 두 배 | ⭐", "calc.py | 세배"])["id"]
    fs.apply(w["tree"], "user", "funcs", task=ftid, row="f2", cells={"name": "세_배"})
    code, d = http(base + "/api/hub/magic", {"nick": "main", "view": "graph", "selection": {
        "nodes": [{"id": ftid, "kind": "task", "graph": "hand_off", "title": "함수 작업"}], "graph_view": "hand_off"}})
    msg = request_file(w, d["id"]).get("message", "") if d.get("id") else ""
    check("main 마법봉 — 함수 표 · «이름 바뀜: 옛 → 새 — 코드 · 시험 · 문서도 새 이름으로» 줄", code == 200
          and f"‹함수 작업›({ftid}) 구현해 줘 — 요약: 함수 표 · 함수: calc.py · 두배 · calc.py · 세_배" in msg
          and f"\n이름 바뀜: calc.py · 세배 → calc.py · 세_배 — 코드 · 시험 · 문서도 새 이름으로 바꾸고 funcs-ack {ftid}\n" in msg, (code, d, msg))
    check("요청 파일 — tree · flowtree 경로 · root", req.get("tree", "").endswith("tree.json") and Path(req.get("flowtree") or "x").is_dir()
          and req.get("root"), (req.get("tree"), req.get("flowtree")))
    # main 마법봉 — 작업 · 검증 · 질문 세 종류를 한 요청으로(MAIN 이 종류로 서브에게 나눈다)
    qid = fs.apply(w["tree"], "user", "ask", text="왜 이렇게?", target="t1")["id"]
    code, d = http(base + "/api/hub/magic", {"nick": "main", "view": "graph", "selection": {
        "nodes": [{"id": "t1", "kind": "task"}, {"id": "v3", "kind": "verify"}, {"id": "v1", "kind": "task"}, {"id": qid, "kind": "question"}]}})
    req = request_file(w, d["id"]) if d.get("id") else {}
    check("main 마법봉 — 작업 · 검증 · 질문 노드 전부 요청에",
          code == 200 and [x["id"] for x in req.get("nodes", [])] == ["t1", "v3", "v1", qid], (code, d, req.get("nodes")))
    msg = queued(w)[-1][-1]
    check("main 마법봉 queue — 작업 «구현해 줘» · 검증 «확인해 줘»(트리 종류로: v1 은 화면이 task 라 해도 verify) · 질문 «답해 줘» · 끝 줄 $main-magic",
          msg.count("구현해 줘") == 1 and msg.count("확인해 줘") == 2 and "(v3)" in msg and f"질문 노드 ‹왜 이렇게?›({qid}) 답해 줘" in msg
          and msg.endswith(f"\n$main-magic {d.get('id')}"), msg)
    code, d = http(base + "/api/hub/magic", {"nick": "main", "view": "graph", "selection": {"nodes": [{"id": "v3", "kind": "verify"}]}})
    msg = queued(w)[-1][-1]
    check("main 마법봉 — 검증 노드만 보내도 됨", code == 200 and msg.startswith("--message=🪄 검증 노드 ‹") and "구현해 줘" not in msg, (code, msg))
    code, d = http(base + "/api/hub/magic", {"nick": "main", "view": "graph", "selection": {"nodes": [{"id": qid, "kind": "question"}]}})
    msg = queued(w)[-1][-1]
    check("main 마법봉 — 질문 노드만 보내도 됨", code == 200 and msg.startswith("--message=🪄 질문 노드 ‹") and msg.endswith(f"\n$main-magic {d.get('id')}"), (code, msg))
    n0 = len(queued(w))
    code, d = http(base + "/api/hub/magic", {"nick": "insp", "view": "graph", "selection": {"nodes": [{"id": "v3", "kind": "verify"}]}})
    check("insp 마법봉 없음 — 거부 · queue 안 함", code >= 400 and len(queued(w)) == n0, (code, d))
    code, d = http(base + "/api/hub/magic", {"nick": "2nd", "view": "graph", "question": "판 번호 방식이 왜 필요해?", "selection": {
        "nodes": [{"id": "r-one"}, {"id": "d-pick"}], "graph_view": "feature"}})
    tree = json.loads(w["tree"].read_text(encoding="utf-8"))
    qn = next((n for n in tree["nodes"] if n.get("id") == d.get("question")), {})
    edges = sorted(e["target"] for e in tree["edges"] if e.get("kind") == "asks" and e.get("source") == d.get("question"))
    check("2nd 그래프 — 질문 노드 즉시 등록(유저 · 미답변 · 대상마다 선)", code == 200 and qn.get("by") == "user" and qn.get("title") == "판 번호 방식이 왜 필요해?"
          and not qn.get("answers") and edges == ["d-pick", "r-one"], (code, d, qn, edges))
    req = request_file(w, d["id"]) if d.get("id") else {}
    check("2nd 그래프 — 요청 답 자리 node + 질문 id · queue «$2nd-magic»", req.get("target", {}).get("kind") == "node"
          and req["target"].get("question") == d.get("question")
          and queued(w)[-1][-1] == f"--message=🪄 질문: 판 번호 방식이 왜 필요해? (대상: 노드 ‹요구 하나›(r-one) · ‹고를 것›(d-pick))\n$2nd-magic {d['id']}",
          (req.get("target"), queued(w)[-1:]))
    # 책 스티커(view=book) — 답 자리 note · 질문 노드 안 만듦 · queue 글 «책 ‹…› 스티커 질문»
    nq = len(json.loads(w["tree"].read_text(encoding="utf-8"))["nodes"])
    code, d = http(base + "/api/hub/magic", {"nick": "2nd", "view": "book", "question": "이 칸 뜻?", "selection": {
        "note": "ab12cd34", "notes_file": "bookkit/books/b1/notes.json", "doc": "b1", "book": "b1", "ctx": "p3 | b=1-개요", "block": "1-개요"}})
    t = request_file(w, d["id"])["target"] if d.get("id") else {}
    check("2nd 책 스티커 — 답 자리 note · 질문 노드 안 만듦 · queue «🪄 책 ‹b1› 스티커 질문 … (블록 …)»", code == 200 and t.get("kind") == "note"
          and t.get("note") == "ab12cd34" and len(json.loads(w["tree"].read_text(encoding="utf-8"))["nodes"]) == nq
          and queued(w)[-1][-1] == (f"--message=🪄 책 ‹b1› 스티커 질문: 이 칸 뜻? (블록 1-개요)\n스티커 ab12cd34 — 답에 짧은 제목(--title · 20자 안팎)도 달 것"
                                    f"\n$2nd-magic {d.get('id')}"), (code, d, t, queued(w)[-1:]))
    code, d = http(base + "/api/hub/magic", {"nick": "2nd", "view": "book", "question": "x", "selection": {"note": "ab12cd34"}})
    check("2nd 책 스티커 — notes.json 없으면 400", code == 400, (code, d))
    code, d = http(base + "/api/hub/magic", {"nick": "2nd", "view": "app", "question": "섬 질문", "selection": {}})
    tree = json.loads(w["tree"].read_text(encoding="utf-8"))
    check("2nd 앱 보기 — 섬 질문 노드(선 없음)", code == 200 and not [e for e in tree["edges"] if e.get("source") == d.get("question")], (code, d))
    code, d = http(base + "/api/hub/magic", {"nick": "2nd", "view": "git", "question": "이 커밋 왜?", "selection": {
        "commit": "abc1234def5678", "git_file": "app/src/main.py", "subject": "첫 커밋"}})
    tree = json.loads(w["tree"].read_text(encoding="utf-8"))
    qn = next((n for n in tree["nodes"] if n.get("id") == d.get("question")), {})
    check("2nd Git — 질문 제목에 [커밋 · 파일] · 요청에 커밋 · 파일", code == 200 and qn.get("title", "").startswith("[abc1234def · app/src/main.py]")
          and request_file(w, d["id"])["target"].get("git_file") == "app/src/main.py", (code, qn.get("title")))
    for view, sel, want in (("code", {"file": "docs/notes.md", "doc_kind": "md", "range": {"start_line": 3, "end_line": 3}, "text": "첫 문단"}, "md"),
                            ("code", {"file": "src/calc.py", "doc_kind": "code", "range": {"start_line": 6, "end_line": 7}, "text": "def calc"}, "code"),
                            ("code", {"file": "src/calc.py", "doc_kind": "code"}, "code"),
                            ("code", {"file": "data.csv", "doc_kind": "code"}, "form"),
                            ("code", {"file": "docs/a.pdf", "doc_kind": "pdf"}, "form"),
                            ("code", {"file": "docs/notes.md", "doc_kind": "md", "readonly": True}, "form")):
        code, d = http(base + "/api/hub/magic", {"nick": "2nd", "view": view, "question": "질문", "selection": sel})
        t = request_file(w, d["id"])["target"] if d.get("id") else {}
        check(f"2nd 코드 탭 {sel['file']}{' (옛 판)' if sel.get('readonly') else ''} → 답 자리 {want}",
              code == 200 and t.get("kind") == want and t.get("file") == sel["file"], (code, d, t.get("kind")))
    t = request_file(w, d["id"])["target"]
    code, d = http(base + "/api/hub/magic", {"nick": "2nd", "view": "code", "question": "질문", "selection": {"file": "docs/notes.md", "doc_kind": "md"}})
    t = request_file(w, d["id"])["target"]
    check("2nd md — 실제 경로(abs) 기록", t.get("abs") and Path(t["abs"]).resolve() == (w["root"] / "docs" / "notes.md").resolve(), t.get("abs"))
    code, d = http(base + "/api/hub/magic", {"nick": "2nd", "view": "code", "selection": {"file": "docs/notes.md"}})
    check("2nd — 질문 없으면 400", code == 400 and "질문 없음" in d.get("error", ""), (code, d))
    code, d = http(base + "/api/hub/magic", {"nick": "doc1", "view": "graph", "question": "x", "selection": {}})
    check("추가 세션 — 마법봉 없음 400", code == 400, (code, d))


# ======= 화면 =======
def test_ui(w, base):
    from playwright.sync_api import sync_playwright
    SHOTS.mkdir(exist_ok=True)
    with sync_playwright() as pw:
        try:
            br = pw.chromium.launch(headless=not HEADED)
        except Exception:  # noqa: BLE001
            br = pw.chromium.launch(channel="chrome", headless=not HEADED)
        page = br.new_page(viewport={"width": 1600, "height": 960})
        errs = []
        page.on("pageerror", lambda e: errs.append(str(e)))
        page.goto(base + "/")
        page.wait_for_selector("html[data-ready='1']", timeout=30000)
        ok = wait_for(lambda: page.locator("#hub .dv-hub-row").count() == 7, 8)
        check("허브 행 7개(기본 3 + 추가 4)", ok, page.locator("#hub .dv-hub-row").count())
        # 그래프가 그려질 때까지
        fr = None
        wait_for(lambda: page.frame(url=lambda u: "/ft/" in u) and page.frame(url=lambda u: "/ft/" in u).locator(".react-flow__node").count() > 10, 20)
        fr = page.frame(url=lambda u: "/ft/" in u)
        time.sleep(0.8)
        hb = page.locator("#hub").bounding_box()
        mm = fr.locator(".react-flow__minimap").bounding_box() if fr else None
        main = page.locator(".dv-main").bounding_box()
        check("허브 좌하단 — 왼쪽 --dv-hub-left(알림 종이 있으면 종 오른쪽 60 · 없으면 15) · 안쪽 800 × 150(+ 테두리 1px)", hb and abs(hb["x"] - main["x"] - page.evaluate("parseFloat(getComputedStyle(document.querySelector('#hub')).left)")) <= 1 and page.evaluate("parseFloat(getComputedStyle(document.querySelector('#hub')).left)") in (15, 60) and abs(hb["width"] - 802) <= 1
              and abs(hb["height"] - 152) <= 1, hb)
        check("허브 아래 끝 = 그래프 미니맵 아래 끝(±2px)", hb and mm and abs((hb["y"] + hb["height"]) - (mm["y"] + mm["height"])) <= 2, (hb, mm))
        check("flowtree 좌하단 Controls(+ · − · 전체 화면) 없음", fr.locator(".react-flow__controls").count() == 0)
        # 5행 · 스크롤
        sc = page.evaluate("(() => { const r = document.querySelector('#hub .dv-hub-rows'); const row = r.querySelector('.dv-hub-row');"
                           " return {ch: r.clientHeight, sh: r.scrollHeight, rh: row.getBoundingClientRect().height,"
                           " gap: r.children[1].getBoundingClientRect().top - r.children[0].getBoundingClientRect().top}; })()")
        check("행 간격 30px · 보이는 칸 150px(5행이 꽉) · 7행이라 세로 스크롤", sc["gap"] == 30 and sc["ch"] == 150 and sc["sh"] > sc["ch"] + 50, sc)
        # 행 내용 · 테두리
        row = lambda n: page.locator(f'#hub .dv-hub-row[data-nick="{n}"]')  # noqa: E731
        txt = row("main").inner_text()
        check("MAIN 행 — 닉네임 · effort ● · 맥락 154k/258k (60%)", "MAIN" in txt and "●" in txt and "154k/258k (60%)" in txt, txt[:80])
        check("aux effort ◐(등록값) · 2ND ○", "◐" in row("aux").inner_text() and "○" in row("2nd").inner_text())
        check("행 테두리 — MAIN 작업 중 빙글 · aux 턴 끝 녹색 점멸 · 2ND 오류 빨강 점멸",
              "m-spin" in row("main").get_attribute("class") and "m-blink" in row("aux").get_attribute("class")
              and "m-err" in row("2nd").get_attribute("class"), [row(n).get_attribute("class") for n in ("main", "aux", "2nd")])
        spin = page.evaluate("getComputedStyle(document.querySelector('#hub .dv-hub-row[data-nick=main]'), '::before').animationName")
        check("빙글 = 회전 애니메이션(::before)", spin == "dv-hub-spin", spin)
        # 진행 색 — 빙글 노랑(그래프 진행 중 빙글과 같은 #f4d35e) · 턴 끝 점멸 녹색 · 오류 빨강
        hs = page.evaluate("Object.fromEntries(['main', 'aux', '2nd'].map((n) => { const r = document.querySelector(`#hub .dv-hub-row[data-nick=\"${n}\"]`);"
                           " return [n, [getComputedStyle(r).getPropertyValue('--hs').trim(), getComputedStyle(r, '::before').backgroundImage]]; }))")
        check("진행 색 — 빙글 노랑 #f4d35e(::before 그라디언트 rgb(244, 211, 94)) · 점멸 녹색 #5fcf73 · 오류 #ff5c5c",
              hs["main"][0] == "#f4d35e" and "rgb(244, 211, 94)" in hs["main"][1] and hs["aux"][0] == "#5fcf73" and hs["2nd"][0] == "#ff5c5c", hs)
        page.evaluate("document.querySelector('#hub .dv-hub-rows').scrollTop = 0")
        time.sleep(0.3)
        page.locator("#hub").screenshot(path=str(SHOTS / "hub_spin_colors.png"))
        # 캡처에서 MAIN 행 둘레에 노랑 화소가 실제로 그려졌나(::before 회전 테두리)
        rb = row("main").bounding_box()
        hb = page.locator("#hub").bounding_box()
        from PIL import Image
        im = Image.open(SHOTS / "hub_spin_colors.png").convert("RGB")
        x0, y0 = int(rb["x"] - hb["x"]) - 2, int(rb["y"] - hb["y"]) - 2
        px = [im.getpixel((x, y)) for x in range(max(0, x0), min(im.width, x0 + int(rb["width"]) + 4))
              for y in range(max(0, y0), min(im.height, y0 + int(rb["height"]) + 4))]
        yellow = sum(1 for r, g, b in px if r > 200 and g > 170 and b < 140)
        check("캡처 — MAIN 행 둘레에 노랑 빙글 화소 보임", yellow > 20, yellow)
        # 즉시 툴팁
        st = row("main").locator(".dv-hub-st")
        b = st.bounding_box()
        page.mouse.move(b["x"] + 40, b["y"] + 10)
        t0 = time.time()
        shown = wait_for(lambda: page.is_visible(".dv-hub-tip"), 1.0, 0.02)
        check("넘친 지금 작업 — 올리자마자 툴팁(0.3초 안) · 전체 글", shown and time.time() - t0 < 0.3
              and page.inner_text(".dv-hub-tip") == LONG_STATUS, (round(time.time() - t0, 3), page.inner_text(".dv-hub-tip")[:40] if shown else ""))
        page.mouse.move(5, 5)
        check("마우스가 나가면 툴팁 숨김", wait_for(lambda: not page.is_visible(".dv-hub-tip"), 1))
        page.screenshot(path=str(SHOTS / "hub_graph.png"))

        # 행 클릭 — 점멸 꺼짐 · 누적창 · 트레이
        row("aux").click()
        check("aux 클릭 → 선택 · 점멸 테두리 사라짐", wait_for(lambda: "is-sel" in row("aux").get_attribute("class")
                                                       and "m-blink" not in row("aux").get_attribute("class"), 2), row("aux").get_attribute("class"))
        page.reload()
        page.wait_for_selector("html[data-ready='1']", timeout=30000)
        wait_for(lambda: page.locator("#hub .dv-hub-row").count() == 7, 8)
        check("확인 기록 유지(새로 열어도 aux 점멸 없음)", "m-blink" not in row("aux").get_attribute("class"), row("aux").get_attribute("class"))
        wait_for(lambda: page.frame(url=lambda u: "/ft/" in u) and page.frame(url=lambda u: "/ft/" in u).locator(".react-flow__node").count() > 10, 20)
        fr = page.frame(url=lambda u: "/ft/" in u)
        row("main").click()
        ok = wait_for(lambda: page.is_visible("#hub .dv-hub-acc") and page.locator("#hub .dv-hub-line").count() == 3, 3)
        ab = page.locator("#hub .dv-hub-acc").bounding_box()
        hb = page.locator("#hub").bounding_box()
        check("MAIN 클릭 → 누적창(허브 바로 위 · 같은 크기 · 3줄)", ok and ab and abs(ab["width"] - hb["width"]) <= 1 and abs(ab["height"] - hb["height"]) <= 1
              and abs((ab["y"] + ab["height"]) - (hb["y"] - 8)) <= 2, (ab, hb))
        acc = page.evaluate("(() => { const b = document.querySelector('#hub .dv-hub-acc-body'); const l = b.querySelectorAll('.dv-hub-line');"
                            " return {oy: getComputedStyle(b).overflowY, ox: getComputedStyle(b).overflowX, dot: getComputedStyle(b.querySelector('.dv-hub-dot')).backgroundColor,"
                            " h: l[0].getBoundingClientRect().height, end: b.scrollTop + b.clientHeight >= b.scrollHeight - 2}; })()")
        check("누적창 — 세로 스크롤 늘 보임 · 가로 스크롤 · 녹색 점 · 줄 간격 넉넉(≥26px) · 맨 아래", acc["oy"] == "scroll" and acc["ox"] == "auto"
              and acc["dot"] == "rgb(95, 184, 101)" and acc["h"] >= 26 and acc["end"], acc)
        tb = page.locator("#hub .dv-hub-tray").bounding_box()
        rb = row("main").bounding_box()
        check("아이콘 트레이 — 고른 행 오른쪽 허브 밖 · 문서 · 마법봉", tb and tb["x"] >= hb["x"] + hb["width"] and abs(tb["y"] - rb["y"]) <= 4
              and page.locator('#hub .dv-hub-tray [data-act="doc"]').is_visible() and page.locator('#hub .dv-hub-tray [data-act="wand"]').is_visible(), (tb, rb))
        check("트레이 아이콘 = 선 그림 svg(굵기 2)", page.locator('#hub .dv-hub-tray [data-act="wand"] svg[stroke-width="2"]').count() == 1)
        page.screenshot(path=str(SHOTS / "hub_acc.png"))
        page.keyboard.press("Escape")
        check("Esc → 행 선택 해제 · 누적창 닫힘 · 트레이 숨김", wait_for(lambda: not page.is_visible("#hub .dv-hub-acc")
                                                            and not page.is_visible("#hub .dv-hub-tray"), 2))
        # 추가 세션 — 문서 아이콘만
        page.locator("#hub .dv-hub-rows").evaluate("(r) => r.scrollTop = r.scrollHeight")
        row("doc3").click()
        check("추가 세션 행 — 트레이에 문서 아이콘만", wait_for(lambda: page.is_visible('#hub .dv-hub-tray [data-act="doc"]'), 2)
              and not page.is_visible('#hub .dv-hub-tray [data-act="wand"]'))
        row("doc3").click()
        page.locator("#hub .dv-hub-rows").evaluate("(r) => r.scrollTop = 0")

        # 입력창 — 문서 아이콘 · Enter 줄바꿈 · Esc 로 안 닫힘 · ✈ 전송
        row("main").click()
        page.click('#hub .dv-hub-tray [data-act="doc"]')
        ok = wait_for(lambda: page.is_visible("#hub .dv-hub-input") and not page.is_visible("#hub .dv-hub-acc"), 2)
        ib = page.locator("#hub .dv-hub-input").bounding_box()
        check("문서 아이콘 → 입력창(누적창 자리 · 같은 크기)", ok and ib and abs(ib["width"] - 802) <= 1 and abs(ib["height"] - 152) <= 1, ib)
        actb = page.locator("#hub .dv-hub-acts").bounding_box()
        check("✕ · ✈ — 입력창 밖 오른쪽 · 아래 끝 맞춤", actb and actb["x"] >= ib["x"] + ib["width"] and abs((actb["y"] + actb["height"]) - (ib["y"] + ib["height"])) <= 2,
              (actb, ib))
        page.keyboard.type("첫 줄")
        page.keyboard.press("Enter")
        page.keyboard.type("둘째 줄 $HOME & %PATH%")
        check("Enter = 줄바꿈(전송 아님)", page.input_value("#hub .dv-hub-input textarea") == "첫 줄\n둘째 줄 $HOME & %PATH%" and len(queued(w)) >= 0)
        n0 = len(queued(w))
        page.keyboard.press("Escape")
        check("Esc 로 입력창 안 닫힘 · 글 그대로", page.is_visible("#hub .dv-hub-input") and "둘째 줄" in page.input_value("#hub .dv-hub-input textarea")
              and len(queued(w)) == n0)
        page.screenshot(path=str(SHOTS / "hub_input.png"))
        page.click('#hub .dv-hub-acts [data-act="send"]')
        ok = wait_for(lambda: len(queued(w)) == n0 + 1 and not page.is_visible("#hub .dv-hub-input"), 5)
        check("✈ → queue(글 그대로) · 성공하면 닫힘", ok and queued(w)[-1] == ["queue", "--thread", TH["main"], "--message=첫 줄\n둘째 줄 $HOME & %PATH%"],
              queued(w)[-1:])
        # 실패 — 글 남김
        page.keyboard.press("Escape")
        page.locator("#hub .dv-hub-rows").evaluate("(r) => r.scrollTop = r.scrollHeight")
        row("bad").click()
        page.click('#hub .dv-hub-tray [data-act="doc"]')
        page.keyboard.type("실패할 글")
        page.click('#hub .dv-hub-acts [data-act="send"]')
        ok = wait_for(lambda: page.locator(".dv-toast.is-bad").count() > 0, 5)
        check("queue 실패 → 빨간 알림 · 입력창 · 글 남음", ok and page.is_visible("#hub .dv-hub-input")
              and page.input_value("#hub .dv-hub-input textarea") == "실패할 글", page.locator(".dv-toast").all_inner_texts()[-1:])
        page.click('#hub .dv-hub-acts [data-act="cancel"]')
        check("✕ → 글 지우고 닫힘 · 누적창으로", wait_for(lambda: not page.is_visible("#hub .dv-hub-input") and page.is_visible("#hub .dv-hub-acc"), 2))
        page.keyboard.press("Escape")
        page.locator("#hub .dv-hub-rows").evaluate("(r) => r.scrollTop = 0")

        # 접기
        page.click("#hub .dv-hub-fold")
        fb = page.locator("#hub").bounding_box()
        check("접기 단추 → 한 줄(높이 30) · 아래 끝 그대로", abs(fb["height"] - 32) <= 1 and abs((fb["y"] + fb["height"]) - (hb["y"] + hb["height"])) <= 1
              and page.locator("#hub .dv-hub-chip").count() >= 3, fb)
        page.click("#hub .dv-hub-fold")
        check("다시 펼침 → 150", abs(page.locator("#hub").bounding_box()["height"] - 152) <= 1)

        # 최소화(−) · 펼치기(+) — 접기 단추 옆 · 최소화 = 이름 칩만 · 화면(.dv-main) 좌하단(왼쪽 12 · 아래 32)
        check("− 단추가 접기 단추 바로 왼쪽", page.evaluate("(() => { const f = document.querySelector('#hub .dv-hub-fold').getBoundingClientRect();"
              " const m = document.querySelector('#hub .dv-hub-min').getBoundingClientRect(); return m.right <= f.left && f.left - m.right <= 4 && m.top === f.top; })()"))
        row("main").click()
        wait_for(lambda: page.is_visible("#hub .dv-hub-acc"), 2)
        page.click("#hub .dv-hub-min")
        mb = page.locator("#hub").bounding_box()
        check("− → 좌하단(왼쪽 --dv-hub-min-left — 알림 종이 있으면 종 오른쪽 60 · 아래 32 = 그래프 아래 막대 26 위) · 높이 30 · 폭 400 미만",
              abs(mb["x"] - main["x"] - page.evaluate("parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--dv-hub-min-left'))")) <= 1 and abs((main["y"] + main["height"]) - (mb["y"] + mb["height"]) - 32) <= 1
              and abs(mb["height"] - 30) <= 1 and mb["width"] < 400, mb)
        check("최소화 — 행 · 누적창 · 트레이 · 접기 단추 안 보임 · 칩 3개 이상",
              page.locator("#hub .dv-hub-row").count() == 0 and not page.is_visible("#hub .dv-hub-acc") and not page.is_visible("#hub .dv-hub-tray")
              and not page.is_visible("#hub .dv-hub-fold") and page.locator("#hub .dv-hub-chip").count() >= 3)
        # 글자 범위 폭 ≤ 칩 폭 · 칩 오른쪽 끝 ≤ + 단추 왼쪽(빙글 테두리 ::before 가 scrollWidth 를 1px 늘려서 글자 범위로 잼)
        check("최소화 — 칩 글자 안 잘림 · + 단추와 안 겹침", page.evaluate("[...document.querySelectorAll('#hub .dv-hub-chip')].every((c) => {"
              " const g = document.createRange(); g.selectNodeContents(c); const b = c.getBoundingClientRect();"
              " return g.getBoundingClientRect().width <= b.width && b.right <= document.querySelector('#hub .dv-hub-min').getBoundingClientRect().left; })"))
        check("최소화 — 단추 제목 «펼치기» · 저장 hub.min", page.get_attribute("#hub .dv-hub-min", "title") == "펼치기"
              and page.evaluate("Object.keys(localStorage).some((k) => k.endsWith('hub.min') && localStorage[k] === 'true')"))
        page.click("#hub .dv-hub-min")
        pb = page.locator("#hub").bounding_box()
        check("+ → 가장 펼친 상태(원래 자리 · 800 × 150)", abs(pb["x"] - hb["x"]) <= 1 and abs(pb["y"] - hb["y"]) <= 1 and abs(pb["height"] - 152) <= 1
              and abs(pb["width"] - 802) <= 1 and page.locator("#hub .dv-hub-row").count() == 7, pb)
        page.click("#hub .dv-hub-fold")
        check("+ 뒤 접기 → 기존 접힘(높이 30 · 아래 끝 그대로)", abs(page.locator("#hub").bounding_box()["height"] - 32) <= 1
              and abs(sum(page.locator("#hub").bounding_box()[k] for k in ("y", "height")) - (hb["y"] + hb["height"])) <= 1)
        page.click("#hub .dv-hub-min")
        page.click("#hub .dv-hub-min")
        check("접힘 + 최소화 → + = 접힘도 풀림(150)", abs(page.locator("#hub").bounding_box()["height"] - 152) <= 1
              and page.evaluate("Object.keys(localStorage).some((k) => k.endsWith('hub.folded') && localStorage[k] === 'false')"))

        # 그래프 Ctrl+클릭 복수 선택 → devview 가 앎 → MAIN 마법봉
        fr.evaluate("window.__flowtree.center('r-one', 0.9)")
        time.sleep(0.4)
        fr.locator('.react-flow__node[data-id="r-one"]').click(position={"x": 30, "y": 12})
        fr.evaluate("window.__flowtree.center('d-pick', 0.9)")
        time.sleep(0.4)
        fr.locator('.react-flow__node[data-id="d-pick"]').click(position={"x": 30, "y": 12}, modifiers=["Control"])
        ok = wait_for(lambda: [n["id"] for n in page.evaluate("window.devview.flowSelection().nodes")] == ["r-one", "d-pick"], 3)
        check("Ctrl+클릭 복수 선택 → devview 선택 알림(2개 · 순서)", ok, page.evaluate("window.devview.flowSelection()"))
        check("복수 선택 둘 다 선택 표시", fr.locator('.react-flow__node.selected').count() >= 2, fr.locator('.react-flow__node.selected').count())
        n0 = len(queued(w))
        row("main").click()
        page.click('#hub .dv-hub-tray [data-act="wand"]')
        ok = wait_for(lambda: len(queued(w)) == n0 + 1 and "$main-magic" in queued(w)[-1][-1], 5)
        rid = queued(w)[-1][-1].split()[-1] if ok else ""
        check("MAIN 마법봉 → 고른 노드 2개로 요청 · queue", ok and [x["id"] for x in request_file(w, rid)["nodes"]] == ["r-one", "d-pick"],
              queued(w)[-1:])
        fr.locator('.react-flow__node[data-id="d-pick"]').click(position={"x": 30, "y": 12}, modifiers=["Control"])
        check("Ctrl+클릭 한 번 더 → 빠짐", wait_for(lambda: [n["id"] for n in page.evaluate("window.devview.flowSelection().nodes")] == ["r-one"], 3),
              page.evaluate("window.devview.flowSelection()"))
        # Alt+W — 그래프 iframe 안에 포커스가 있어도 2ND 마법봉 단추와 같음
        page.keyboard.press("Alt+KeyW")
        ok = wait_for(lambda: page.is_visible("#hub .dv-hub-input"), 2)
        head = page.inner_text("#hub .dv-hub-input-head")
        check("그래프 iframe 안 Alt+W → 질문 입력창 · 대상 노드", ok and "2ND" in head and "요구 하나" in head, head)
        page.click('#hub .dv-hub-acts [data-act="cancel"]')
        page.evaluate("document.querySelector('#ftView iframe').focus()")
        # 그래프 iframe 안 Esc — 노드 선택 해제와 같이 허브 행 선택도 해제
        check("그래프 안에 포커스 · 허브 행 고름", page.evaluate("document.activeElement.tagName") == "IFRAME" and page.is_visible("#hub .dv-hub-acc"))
        page.keyboard.press("Escape")
        check("그래프 안 Esc → 허브 행 선택 해제 · 노드 선택 해제", wait_for(lambda: not page.is_visible("#hub .dv-hub-acc"), 2)
              and wait_for(lambda: page.evaluate("window.devview.flowSelection().nodes.length") == 0, 2))

        # 코드 탭 — Monaco 선택 → 2ND 마법봉(포커스 안 빼앗김 · 덧칠) → 질문 전송
        page.evaluate("window.devview.showView('code')")
        page.evaluate("window.devview.openFile('src/calc.py')")
        wait_for(lambda: page.evaluate("window.devview.activePath()") == "src/calc.py", 5)
        page.evaluate("(() => { const ed = window.devview.editor(); ed.setSelection({startLineNumber: 6, startColumn: 1, endLineNumber: 7, endColumn: 21}); ed.focus(); })()")
        check("허브는 코드 보기에도 같은 자리", page.is_visible("#hub") and abs(page.locator("#hub").bounding_box()["x"] - hb["x"]) <= 1)
        # Alt+W — 편집기 안에서 2ND 마법봉 단추와 같음(행을 안 골라도) · 글자가 안 들어감
        text0 = page.evaluate("window.devview.editor().getValue()")
        page.keyboard.press("Alt+KeyW")
        ok = wait_for(lambda: page.is_visible("#hub .dv-hub-input"), 2)
        head = page.inner_text("#hub .dv-hub-input-head")
        check("편집기 안 Alt+W → 질문 입력창 · 대상(파일 · 줄)", ok and "src/calc.py 6–7줄" in head and "2ND" in head, head)
        check("Alt+W 가 편집기에 글자를 넣지 않음", page.evaluate("window.devview.editor().getValue()") == text0)
        page.keyboard.press("Alt+KeyW")
        check("입력창에서 Alt+W 다시 → 그대로 · 글자 안 들어감", wait_for(lambda: page.evaluate("document.activeElement.tagName") == "TEXTAREA", 2)
              and page.input_value("#hub .dv-hub-input textarea") == "")
        page.click('#hub .dv-hub-acts [data-act="cancel"]')
        page.evaluate("window.devview.editor().focus()")
        # 최소화 상태에서도 Alt+W 가 입력창을 보인다
        page.click("#hub .dv-hub-min")
        page.evaluate("window.devview.editor().focus()")
        page.keyboard.press("Alt+KeyW")
        check("최소화 중 Alt+W → 풀리고 입력창 보임", wait_for(lambda: page.is_visible("#hub .dv-hub-input"), 2))
        page.click('#hub .dv-hub-acts [data-act="cancel"]')
        # 접힘 상태에서도
        page.click("#hub .dv-hub-fold")
        page.evaluate("window.devview.editor().focus()")
        page.keyboard.press("Alt+KeyW")
        ok = wait_for(lambda: page.is_visible("#hub .dv-hub-input"), 2)
        ib = page.locator("#hub .dv-hub-input").bounding_box() if ok else None
        check("접힘 중 Alt+W → 입력창이 화면 안에 보임", ok and ib["height"] > 40 and ib["y"] >= 0 and ib["y"] + ib["height"] <= 1000, ib)
        page.click('#hub .dv-hub-acts [data-act="cancel"]')
        page.click("#hub .dv-hub-fold")
        page.evaluate("window.devview.editor().focus()")
        row("2nd").click()
        check("행 클릭이 편집기 포커스를 안 빼앗음", page.evaluate("window.devview.editor().hasTextFocus()"))
        page.click('#hub .dv-hub-tray [data-act="wand"]')
        ok = wait_for(lambda: page.is_visible("#hub .dv-hub-input"), 2)
        head = page.inner_text("#hub .dv-hub-input-head")
        check("2ND 마법봉 → 질문 입력창 · 머리 줄에 대상(파일 · 줄)", ok and "src/calc.py 6–7줄" in head and "2ND" in head, head)
        check("입력 중에도 고른 범위 덧칠(Monaco 장식) · 선택 유지", page.evaluate("window.devview.markCount()") == 1
              and not page.evaluate("window.devview.editor().getSelection().isEmpty()"), page.evaluate("window.devview.markCount()"))
        page.screenshot(path=str(SHOTS / "hub_code_magic.png"))
        n0 = len(queued(w))
        page.keyboard.type("이 함수는 왜 두 배?")
        page.click('#hub .dv-hub-acts [data-act="send"]')
        ok = wait_for(lambda: len(queued(w)) == n0 + 1, 5)
        rid = queued(w)[-1][-1].split()[-1] if ok else ""
        t = request_file(w, rid)["target"] if ok else {}
        check("2ND 질문 → 요청(code · 6–7줄 · 고른 글자) · queue «$2nd-magic»", ok and t.get("kind") == "code" and t.get("range", {}).get("start_line") == 6
              and t.get("range", {}).get("end_line") == 7 and "def calc" in t.get("text", ""), t)
        check("전송 뒤 덧칠 지움", wait_for(lambda: page.evaluate("window.devview.markCount()") == 0, 2))
        # md 표 행 고르기 → 표 정보
        page.evaluate("window.devview.openFile('docs/notes.md')")
        wait_for(lambda: page.evaluate("window.devview.activePath()") == "docs/notes.md", 5)
        time.sleep(0.5)
        line = page.locator("#codeView .cm-line", has_text="첫 문단 글이다").first
        line.click()
        page.keyboard.press("Home")
        page.keyboard.press("Shift+End")
        info = page.evaluate("window.devview.selectionInfo()")
        check("md 편집기 선택 → 원문 줄 번호(3) · 고른 글자", info and info["range"] and info["range"]["start_line"] == 3 and "첫 문단" in info["text"], info)
        page.click('#hub .dv-hub-tray [data-act="wand"]')
        ok = wait_for(lambda: page.is_visible("#hub .dv-hub-input"), 2)
        check("md — 2ND 마법봉 입력 중 덧칠(.cm-hub-mark) · 머리 줄 docs/notes.md 3줄", ok and wait_for(lambda: page.locator("#codeView .cm-hub-mark").count() >= 1, 2)
              and "docs/notes.md 3줄" in page.inner_text("#hub .dv-hub-input-head"), page.inner_text("#hub .dv-hub-input-head"))
        page.click('#hub .dv-hub-acts [data-act="cancel"]')
        check("✕ → md 덧칠 지움", wait_for(lambda: page.locator("#codeView .cm-hub-mark").count() == 0, 2))
        # 그린 표의 칸 누르기(칸 편집) → 표 원문 행 9 · 열 0 · 마법봉 덧칠은 그 칸 테두리
        page.locator("#codeView .cm-tablew td", has_text="나").first.click()
        info = page.evaluate("window.devview.selectionInfo()")
        check("md 표 칸 → table{line 9, col 0} · 칸 글자", info and info.get("table") == {"line": 9, "col": 0} and info["text"] == "나", info)
        page.click('#hub .dv-hub-tray [data-act="wand"]')
        check("표 칸 — 마법봉 입력 중 그 칸 덧칠", wait_for(lambda: page.is_visible("#hub .dv-hub-input"), 2)
              and page.evaluate("window.devview.markCount()") >= 1, page.evaluate("window.devview.markCount()"))
        page.click('#hub .dv-hub-acts [data-act="cancel"]')
        page.screenshot(path=str(SHOTS / "hub_code.png"))
        page.keyboard.press("Escape")

        # Git 보기 — 고른 커밋 · 파일이 2ND 대상
        page.evaluate("window.devview.showView('git')")
        if wait_for(lambda: page.locator("#gLog .dv-gr:not(.is-local)").count() > 0, 6):
            page.locator("#gLog .dv-gr:not(.is-local)").first.click()
            time.sleep(0.8)
            row("2nd").click()
            page.click('#hub .dv-hub-tray [data-act="wand"]')
            wait_for(lambda: page.is_visible("#hub .dv-hub-input"), 2)
            snap = page.evaluate("window.devview.hub().inputCtx.snap")
            check("Git 보기 2ND 마법봉 — 고른 커밋 해시 · 파일이 대상", snap["view"] == "git" and len(snap["selection"]["commit"]) == 40
                  and snap["selection"]["git_file"] and snap["selection"]["commit"][:8] in page.inner_text("#hub .dv-hub-input-head"), snap)
            page.click('#hub .dv-hub-acts [data-act="cancel"]')
            page.keyboard.press("Escape")
        else:
            check("Git 보기 — 커밋 줄(git 없음이면 건너뜀)", True, "git 없음")
        # 모든 보기에 허브 · 대화 보기에서는 숨김
        views = ["graph", "code", "git", "app"] + (["survey"] if page.is_visible("#svTab") else [])
        vis = {}
        for v in views:
            page.evaluate(f"window.devview.showView('{v}')")
            time.sleep(0.15)
            vis[v] = page.is_visible("#hub")
        check(f"허브 — 모든 보기({' · '.join(views)})에 보임", all(vis.values()), vis)
        page.click('#views [data-view="chat"]')
        check("대화 탭 → 허브 숨김", wait_for(lambda: page.evaluate("window.devview.view()") == "chat" and not page.is_visible("#hub"), 2))
        # 대화 탭 순서 — 그래프와 코드 사이
        order = page.evaluate("[...document.querySelectorAll('#views .dv-view')].filter((b) => !b.hidden).map((b) => b.dataset.view)")
        check("대화 탭 자리 = 그래프와 코드 사이", order[:3] == ["graph", "chat", "code"], order)
        ok = wait_for(lambda: page.locator(".dv-chat-tab").count() == 7, 4)
        check("세션 탭 = 등록 세션(thread 있음) 7개", ok, page.locator(".dv-chat-tab").count())
        page.click('.dv-chat-tab[data-nick="main"]')
        ok = wait_for(lambda: page.locator(".dv-msg").count() == 4, 4)
        msgs = page.locator(".dv-msg").all_inner_texts()
        check("대화 — 🚹 유저 · 혼잣말 · 🤖 최종 답변(주입 없음)", ok and msgs[0].startswith("🚹") and "안녕 — 시작하자" in msgs[0]
              and "생각 중 메모" in msgs[1] and msgs[2].startswith("🤖") and "준비됨" in msgs[2]
              and not any("environment_context" in m for m in msgs), msgs)
        nc = page.evaluate("(() => { const n = document.querySelectorAll('.dv-msg')[1]; const a = getComputedStyle(n.querySelector('.dv-msg-txt')); "
                           "const b = getComputedStyle(document.querySelectorAll('.dv-msg')[2].querySelector('.dv-msg-txt')); "
                           "return [n.classList.contains('is-note'), a.color !== b.color, parseFloat(a.fontSize) < parseFloat(b.fontSize)]; })()")
        check("혼잣말 = 흐린 작은 줄(is-note · 답과 색 · 크기 다름)", all(nc), nc)
        bg = page.evaluate("[getComputedStyle(document.querySelectorAll('.dv-msg')[0]).backgroundColor, getComputedStyle(document.querySelectorAll('.dv-msg')[2]).backgroundColor]")
        check("유저 메시지 = 줄 전체 하이라이트(답은 배경 없음)", bg[0] not in ("rgba(0, 0, 0, 0)", "transparent") and bg[1] in ("rgba(0, 0, 0, 0)", "transparent"), bg)
        meta = page.inner_text(".dv-chat-meta")
        check("입력창 아래 — 맥락 · 모델 · effort", "154k/258k (60%)" in meta and "gpt-x" in meta and "high" in meta, meta)
        page.screenshot(path=str(SHOTS / "hub_chat.png"))
        # 세션끼리 보낸 글(«@MAIN ») = 🔁 · 연녹색 · 이름 칩(본문에서 @MAIN 뗌) · 마법봉 글(🪄) = 마법봉 칩 · 유저 글과 다른 표시
        page.click('.dv-chat-tab[data-nick="doc2"]')
        ok = wait_for(lambda: page.locator(".dv-msg").count() == 4, 4)
        rl = page.evaluate("(() => { const m = [...document.querySelectorAll('.dv-msg')]; const r = m.find((x) => x.classList.contains('is-relay'));"
                           " const g = m.find((x) => x.classList.contains('is-magic')); const u = m.find((x) => x.classList.contains('is-user')"
                           " && !x.classList.contains('is-relay') && !x.classList.contains('is-magic'));"
                           " const bg = (x) => x ? getComputedStyle(x).backgroundColor : '';"
                           " return {who: r && r.querySelector('.dv-msg-who').textContent, chip: r && r.querySelector('.dv-msg-chip').textContent,"
                           " txt: r && r.querySelector('.dv-msg-txt').textContent, rbg: bg(r), ubg: bg(u), gwho: g && g.querySelector('.dv-msg-who').textContent,"
                           " gchip: g && g.querySelector('.dv-msg-chip.is-magic') && g.querySelector('.dv-msg-chip').textContent,"
                           " gtxt: g && g.querySelector('.dv-msg-txt').textContent, gbar: g && getComputedStyle(g).boxShadow}; })()")
        check("@MAIN 글 — 🔁 · 칩 MAIN · 본문에서 @MAIN 뗌 · 연녹색 배경(유저 글과 다름)", ok and rl["who"] == "🔁" and rl["chip"] == "MAIN"
              and rl["txt"] == "MAIN검증 결과 받았어" and rl["rbg"] != rl["ubg"] and rl["rbg"] not in ("rgba(0, 0, 0, 0)", ""), rl)
        check("🪄 글 — 🚹 · 마법봉 칩 · 본문(첫 🪄 뗌) · 왼쪽 띠", rl["gwho"] == "🚹" and rl["gchip"] == "🪄 마법봉"
              and rl["gtxt"].startswith("🪄 마법봉섹션 1 ‹화면›(t1) 구현해 줘") and "$main-magic" in rl["gtxt"] and "inset" in (rl["gbar"] or ""), rl)
        page.screenshot(path=str(SHOTS / "hub_chat_relay.png"))
        page.click('.dv-chat-tab[data-nick="main"]')
        wait_for(lambda: page.locator(".dv-msg").count() == 4 and "안녕 — 시작하자" in page.locator(".dv-msg").first.inner_text(), 4)
        # 답 하나 접기 · 펴기 — 펼친 답의 «접기» 단추 → 한 줄 · 그 줄 클릭 → 다시 펼침(11/03 유저: 펼친 것을 하나씩 접을 수 없었음)
        ans = page.locator(".dv-msg.is-assistant").first
        check("펼친 답에 접기 단추", ans.locator(".dv-cm-close").is_visible())
        ans.locator(".dv-cm-close").click()
        ans = page.locator(".dv-msg.is-assistant").first
        check("접기 단추 → 한 줄(▸ … 접힘) · 단추 사라짐", wait_for(lambda: ans.locator(".dv-cm-fold").count() == 1, 2)
              and ans.locator(".dv-cm-close").count() == 0, ans.inner_text())
        ans.locator(".dv-cm-fold").click()
        check("접힌 줄 클릭 → 다시 펼침 · 접기 단추 다시", wait_for(lambda: page.locator(".dv-msg.is-assistant").first.locator(".dv-cm-close").count() == 1, 2)
              and page.locator(".dv-msg.is-assistant").first.locator(".dv-cm-fold").count() == 0)
        page.locator(".dv-msg.is-assistant .dv-msg-who").first.click()
        check("🤖 클릭도 접힘(종전 동작)", wait_for(lambda: page.locator(".dv-msg.is-assistant").first.locator(".dv-cm-fold").count() == 1, 2))
        page.locator(".dv-msg.is-assistant .dv-msg-who").first.click()
        # 보내기 키
        ta = page.locator(".dv-chat-input")
        ta.click()
        n0 = len(queued(w))
        page.keyboard.type("한 줄")
        page.keyboard.press("Enter")
        time.sleep(0.45)
        page.keyboard.type("두 줄")
        check("Enter 한 번 = 줄바꿈(안 보냄)", ta.input_value() == "한 줄\n두 줄" and len(queued(w)) == n0, ta.input_value())
        page.keyboard.press("Control+Enter")
        ok = wait_for(lambda: len(queued(w)) == n0 + 1, 4)
        check("Ctrl+Enter = 보내기(글 그대로) · 입력 비움", ok and queued(w)[-1][-1] == "--message=한 줄\n두 줄" and wait_for(lambda: ta.input_value() == "", 2),
              queued(w)[-1:])
        pend = lambda: page.locator(".dv-msg.is-pending").all_inner_texts()
        busy = page.evaluate("window.devview.hub().rows.find((r) => r.nick === 'main').state") == "spin"
        check(f"보낸 직후 대기 줄 «{'대기열' if busy else '보냄'}»(기록에 들어오기 전 · MAIN 작업 중={busy})",
              wait_for(lambda: len(pend()) == 1 and "한 줄" in pend()[0] and ("대기열" if busy else "보냄") in pend()[0], 2), pend())
        with open(w["rollouts"]["main"], "a", encoding="utf-8") as f:
            f.write(json.dumps(uitem(time.time(), "한 줄\n두 줄"), ensure_ascii=False) + "\n")
        check("기록에 들어오면 대기 줄 사라지고 🚹 줄로", wait_for(lambda: not pend() and any("두 줄" in m for m in page.locator(".dv-msg.is-user").all_inner_texts()), 5), pend())
        page.keyboard.type("빠른 두 번")
        page.keyboard.press("Enter")
        page.keyboard.press("Enter")
        time.sleep(0.6)
        check("Enter 빠르게 두 번 = 줄바꿈 둘(안 보냄)", ta.input_value() == "빠른 두 번\n\n" and len(queued(w)) == n0 + 1, (ta.input_value(), len(queued(w))))
        ta.fill("")
        page.keyboard.type("x")
        page.keyboard.press("Control+Backspace")
        check("Ctrl+Backspace = 단어 지우기(가로채지 않음)", ta.input_value() == "", ta.input_value())
        page.keyboard.press("Control+Backquote")
        check("대화 입력 — 기호 단축키(Ctrl+` 🚹) 그대로", ta.input_value() == "🚹", ta.input_value())
        ta.fill("")
        # Alt+←→ 세션 탭
        page.keyboard.press("Alt+ArrowRight")
        check("Alt+→ → 다음 세션 탭(2ND)", wait_for(lambda: page.evaluate("window.devview.chat().cur") == "2nd", 2), page.evaluate("window.devview.chat()"))
        page.keyboard.press("Alt+ArrowLeft")
        check("Alt+← → 이전 세션 탭(MAIN)", wait_for(lambda: page.evaluate("window.devview.chat().cur") == "main", 2))
        # 답변 마크다운 — 표 · 굵게(빨강) · 제목 크기 · 코드 · HTML 주입 없음
        md_ans = "# 큰 제목\n\n### 작은 제목\n\n**굵게** 와 `코드`\n\n| 칸 | 값 |\n|---|---:|\n| a | 1 |\n| b | 2 |\n\n- [x] 끝\n- 둘\n\n<b>주입</b>"
        with open(w["rollouts"]["main"], "a", encoding="utf-8") as f:
            for x in (ev(time.time(), "event_msg", {"type": "task_started", "turn_id": "u9"}), uitem(time.time(), "표 보여 줘"),
                      amsg(time.time(), md_ans, "final_answer"), ev(time.time(), "event_msg", {"type": "task_complete", "turn_id": "u9", "last_agent_message": md_ans})):
                f.write(json.dumps(x, ensure_ascii=False) + "\n")
        last = ".dv-msg.is-assistant >> nth=-1"
        ok = wait_for(lambda: page.locator(".dv-msg.is-assistant .dv-cm-tbl").count() == 1, 5)
        md = page.evaluate("(() => { const a = [...document.querySelectorAll('.dv-msg.is-assistant')].pop(); const t = a.querySelector('.dv-msg-txt');"
                           " const fs = (s) => parseFloat(getComputedStyle(t.querySelector(s)).fontSize);"
                           " return { cls: t.className, rows: t.querySelectorAll('.dv-cm-tbl tbody tr').length, th: [...t.querySelectorAll('.dv-cm-tbl th')].map((x) => x.textContent),"
                           " right: getComputedStyle(t.querySelector('.dv-cm-tbl td:nth-child(2)')).textAlign, b: getComputedStyle(t.querySelector('.dv-cm-b')).color,"
                           " body: parseFloat(getComputedStyle(t).fontSize), h1: fs('.dv-cm-h1'), h3: fs('.dv-cm-h3'), code: !!t.querySelector('code'),"
                           " task: t.querySelectorAll('.dv-cm-box.on').length, inj: !!t.querySelector('p b:not(.dv-cm-b)'), txt: t.textContent }; })()")
        check("답변 표 — 머리 2칸 · 행 2 · 오른쪽 정렬", ok and md["rows"] == 2 and md["th"] == ["칸", "값"] and md["right"] == "right" and "dv-cmd" in md["cls"], md)
        check("답변 굵게 = 빨강(#ff6b6b)", md["b"] == "rgb(255, 107, 107)", md["b"])
        check("답변 제목 크기 h1 > h3 > 본문 · 코드 · 할 일", md["h1"] > md["h3"] > md["body"] and md["code"] and md["task"] == 1, md)
        check("답변 속 HTML = 글자 그대로(주입 없음)", not md["inj"] and "<b>주입</b>" in md["txt"], md["txt"][-30:])
        page.screenshot(path=str(SHOTS / "hub_chat_md.png"))
        # 접기 — Ctrl+Shift+, 전부 접기 · Ctrl+Shift+. 전부 펴기 · 🤖 클릭 하나
        n_ans = page.locator(".dv-msg.is-assistant").count()
        page.locator(".dv-chat-input").click()
        page.keyboard.press("Control+Shift+Comma")
        check(f"Ctrl+Shift+, → 답 {n_ans}개 전부 접힘 · 첫 글 줄 미리보기", wait_for(lambda: page.locator(".dv-cm-fold").count() == n_ans and page.locator(".dv-cmd").count() == 0, 2)
              and "큰 제목" in page.locator(last).inner_text() and "접힘" in page.locator(last).inner_text(), page.locator(last).inner_text())
        page.keyboard.press("Control+Shift+Period")
        check("Ctrl+Shift+. → 전부 펼침", wait_for(lambda: page.locator(".dv-cm-fold").count() == 0 and page.locator(".dv-cmd").count() == n_ans, 2))
        page.locator(".dv-msg.is-assistant .dv-msg-who").last.click()
        check("🤖 클릭 → 그 답 하나만 접힘", wait_for(lambda: page.locator(".dv-cm-fold").count() == 1 and page.locator(".dv-cmd").count() == n_ans - 1, 2))
        page.locator(".dv-cm-fold").click()
        check("접힘 줄 클릭 → 다시 펼침", wait_for(lambda: page.locator(".dv-cm-fold").count() == 0, 2))
        # 2ND 탭 열기 → 오류 점멸 꺼짐
        page.click('.dv-chat-tab[data-nick="2nd"]')
        ok = wait_for(lambda: "m-err" not in (page.get_attribute('.dv-chat-tab[data-nick="2nd"]', "class") or ""), 3)
        check("그 탭을 열면 점멸 꺼짐(2ND 오류) · 허브 행도", ok and wait_for(lambda: page.evaluate(
            "window.devview.hub().rows.find((r) => r.nick === '2nd').state") == "", 2), page.get_attribute('.dv-chat-tab[data-nick="2nd"]', "class"))
        # 새 최종 답변 → 허브 행 점멸(열려 있지 않은 세션)
        with open(w["rollouts"]["aux"], "a", encoding="utf-8") as f:
            for x in (ev(time.time(), "event_msg", {"type": "task_started", "turn_id": "i2"}), uitem(time.time(), "다시"),
                      amsg(time.time(), "새 답", "final_answer"), ev(time.time(), "event_msg", {"type": "task_complete", "turn_id": "i2", "last_agent_message": "새 답"})):
                f.write(json.dumps(x, ensure_ascii=False) + "\n")
        page.click('#views [data-view="graph"]')
        ok = wait_for(lambda: "m-blink" in (page.get_attribute('#hub .dv-hub-row[data-nick="aux"]', "class") or ""), 5)
        check("새 최종 답변 → 허브 행 점멸 · 대화 탭도", ok and "m-blink" in (page.get_attribute('.dv-chat-tab[data-nick="aux"]', "class") or ""),
              page.get_attribute('#hub .dv-hub-row[data-nick="aux"]', "class"))
        # Alt+A · S · D — 다른 보기(그래프)에서도 대화 보기로 가서 그 번호 세션(탭 순서 MAIN · 2ND · aux)
        tabs = page.evaluate("[...document.querySelectorAll('.dv-chat-tab')].map((t) => t.dataset.nick)")
        page.keyboard.press("Alt+KeyD")
        check("그래프에서 Alt+D → 대화 보기 · 3번 세션", wait_for(lambda: page.locator("#chatView").is_visible()
              and page.evaluate("window.devview.chat().cur") == tabs[2], 3), (tabs, page.evaluate("window.devview.chat()")))
        check("Alt+D 뒤 입력칸에 커서", wait_for(lambda: page.evaluate("document.activeElement.classList.contains('dv-chat-input')"), 2))
        page.keyboard.press("Alt+KeyA")
        check("입력칸에서 Alt+A → 1번 세션(글자 안 들어감)", wait_for(lambda: page.evaluate("window.devview.chat().cur") == tabs[0], 2)
              and page.locator(".dv-chat-input").input_value() == "", page.evaluate("window.devview.chat()"))
        page.keyboard.press("Alt+KeyS")
        check("Alt+S → 2번 세션", wait_for(lambda: page.evaluate("window.devview.chat().cur") == tabs[1], 2))
        page.keyboard.press("Alt+KeyF")
        check("Alt+F → 4번 세션", wait_for(lambda: page.evaluate("window.devview.chat().cur") == tabs[3], 2))
        page.keyboard.press("Alt+KeyG")
        check("Alt+G → 5번 세션", wait_for(lambda: page.evaluate("window.devview.chat().cur") == tabs[4], 2), (tabs, page.evaluate("window.devview.chat()")))
        page.keyboard.type("!@#$%")
        check("Shift+숫자 기호는 입력칸에 그대로", page.locator(".dv-chat-input").input_value() == "!@#$%", page.locator(".dv-chat-input").input_value())
        page.locator(".dv-chat-input").fill("")
        # 보던 보기가 저장돼 새 페이지가 대화 보기(허브 숨김)로 열리지 않게 그래프로 되돌림
        page.click('#views [data-view="graph"]')
        time.sleep(1.2)
        # 좁은 화면(대회 미리보기 칸) — 허브 · 트레이가 화면 안 · 가로 넘침 없음
        narrow = br.new_page(viewport={"width": 680, "height": 620})
        narrow.goto(base + "/")
        narrow.wait_for_selector("html[data-ready='1']", timeout=30000)
        wait_for(lambda: narrow.locator("#hub .dv-hub-row").count() == 7, 8)
        narrow.locator('#hub .dv-hub-row[data-nick="main"]').click()
        nb = narrow.locator("#hub").bounding_box()
        tb = narrow.locator("#hub .dv-hub-tray").bounding_box()
        check("좁은 화면 680 — 허브 폭 줄어듦 · 트레이 화면 안 · 가로 넘침 없음", nb["width"] < 680 - 200 and tb and tb["x"] + tb["width"] <= 680
              and narrow.evaluate("document.documentElement.scrollWidth <= innerWidth"), (nb, tb))
        narrow.close()
        check("페이지 예외 없음", not errs, errs[:3])
        br.close()


# ======= Claude 세션(kind claude) — 기록 읽기 · tmux 보내기 · 마법봉 «/역할-magic» =======
# Claude 세션 id · 가짜 claude 프로세스 번호
CSID = "5e81db89-0000-4000-8000-00000000cccc"
CSID2 = "5e81db89-0000-4000-8000-00000000dddd"
CPID = 4242


# Claude 기록 한 줄
# t: 에포크 초 / kind: user · assistant · system / **kw: 줄 칸
def cline(t, kind, **kw):
    return {"type": kind, "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(t)), "sessionId": CSID,
            "isSidechain": False, **kw}


# 가짜 Claude 홈 + 등록(main = Claude · tmux %5 / doc1 = Claude · tmux 없음) + 가짜 tmux — 반환 서버 환경 덧붙임
# w: 시험 세계
def claude_world(w):
    ch = w["base"] / "claude"
    proj = ch / "projects" / re.sub(r"[^A-Za-z0-9]", "-", str(w["root"]))
    proj.mkdir(parents=True)
    # 2026-11-03 WSL claude 2.1.302 실측 칸 이름 — 블록 하나가 한 줄 · 혼잣말 = stop_reason tool_use · 최종 답 = end_turn
    lines = [
        cline(T0 + 1, "user", isMeta=True, message={"role": "user", "content": "<local-command-caveat>무시</local-command-caveat>"}),
        cline(T0 + 1, "user", message={"role": "user", "content": "<command-name>/login</command-name>\n<command-message>login</command-message>"}),
        cline(T0 + 1, "user", message={"role": "user", "content": "<local-command-stdout>Login successful</local-command-stdout>"}),
        cline(T0 + 2, "user", promptId="p1", message={"role": "user", "content": "<command-message>main</command-message>\n<command-name>/main</command-name>\n<command-args>A</command-args>"}),
        cline(T0 + 2, "user", isMeta=True, promptId="p1", message={"role": "user", "content": [{"type": "text", "text": "Base directory for this skill: /x\n본문"}]}),
        cline(T0 + 3, "assistant", message={"model": "claude-sonnet-5-5", "stop_reason": "tool_use", "content": [{"type": "thinking", "thinking": "속생각"}]}),
        cline(T0 + 3, "assistant", message={"model": "claude-sonnet-5-5", "stop_reason": "tool_use", "content": [{"type": "text", "text": "확인할게"}]}),
        cline(T0 + 3, "assistant", message={"model": "claude-sonnet-5-5", "stop_reason": "tool_use", "content": [{"type": "tool_use", "name": "Bash", "input": {}}]}),
        cline(T0 + 4, "user", message={"role": "user", "content": [{"type": "tool_result", "content": "도구 결과"}]}),
        cline(T0 + 5, "assistant", message={"model": "claude-sonnet-5-5", "stop_reason": "end_turn", "content": [{"type": "text", "text": "끝났어"}],
                                           "usage": {"input_tokens": 2, "cache_creation_input_tokens": 1000, "cache_read_input_tokens": 49000, "output_tokens": 50}}),
        cline(T0 + 6, "system", subtype="turn_duration", uuid="td-1", durationMs=4000),
        cline(T0 + 7, "user", isSidechain=True, message={"role": "user", "content": "서브 글(안 보임)"}),
        cline(T0 + 8, "user", promptId="p2", message={"role": "user", "content": "여러 줄 글\n둘째 줄"}),
    ]
    (proj / f"{CSID}.jsonl").write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in lines), encoding="utf-8")
    # /clear 뒤 새 세션 — 프로세스 기록이 가리키면 그것을 따라감(doc1 시험)
    (proj / f"{CSID2}.jsonl").write_text(json.dumps(cline(T0 + 9, "user", message={"role": "user", "content": "clear 뒤 글"})) + "\n", encoding="utf-8")
    (ch / "sessions").mkdir()
    (ch / "sessions" / f"{CPID}.json").write_text(json.dumps({"pid": CPID, "sessionId": CSID2, "cwd": str(w["root"]), "procStart": "77",
                                                              "status": "idle"}), encoding="utf-8")
    hub = w["root"] / ".codex-hub" / "sessions"
    base = dict(model="claude-sonnet-5-5", cwd=str(w["root"]), effort="?", effort_src="?", status="", status_at="")
    (hub / "main.json").write_text(json.dumps(dict(base, nick="main", kind="claude", thread=CSID, tmux="%5", tmux_socket="/tmp/s",
                                                   registered_at="2026-11-02 00:00:00")), encoding="utf-8")
    (hub / "doc1.json").write_text(json.dumps(dict(base, nick="doc1", kind="claude", thread=CSID, claude_pid=CPID, claude_proc="77",
                                                   tmux=None, registered_at="2026-11-02 00:03:00")), encoding="utf-8")
    # 가짜 tmux — 인자 · 표준 입력을 줄마다 적음
    log = w["base"] / "tmux_log.jsonl"
    fake = w["base"] / "fake_tmux.py"
    fake.write_text("import json, os, sys\nargs = sys.argv[1:]\ndata = sys.stdin.buffer.read().decode('utf-8')\n"
                    "open(os.environ['FAKE_TMUX_LOG'], 'a', encoding='utf-8').write(json.dumps([args, data], ensure_ascii=False) + '\\n')\n"
                    "if 'display-message' in args:\n    print(args[args.index('-t') + 1])\n", encoding="utf-8")
    w["tmux_log"] = log
    return {"CLAUDE_CONFIG_DIR": str(ch), "DEVVIEW_TMUX": str(fake), "FAKE_TMUX_LOG": str(log)}


# 가짜 tmux 가 받은 [인자, 표준 입력] 목록
# w: 시험 세계
def tmuxed(w):
    p = w["tmux_log"]
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()] if p.is_file() else []


def test_claude(w, base):
    code, d = http(base + "/api/hub")
    rows = {r["nick"]: r for r in d.get("rows") or []}
    m, c1 = rows.get("main") or {}, rows.get("doc1") or {}
    check("Claude 행 — kind · 모델 · 맥락(input + cache) · 마지막 턴 turn_duration · 작업 중(유저 글 뒤 턴 끝 없음)",
          m.get("kind") == "claude" and m.get("model") == "claude-sonnet-5-5" and (m.get("context") or {}).get("used") == 50002
          and (m.get("done") or {}).get("id") == "td-1" and m.get("state") == "working", m)
    check("Claude 행 — 프로세스 기록이 있으면 그 세션 id(/clear 뒤) · 상태 idle · tmux 없음 안내",
          c1.get("thread") == CSID2 and c1.get("state") == "idle" and "tmux 밖" in str(c1.get("note")), c1)
    check("queue 준비 — Claude 등록 + tmux 있음", (d.get("queue") or {}).get("ok") is True, d.get("queue"))
    code, d = http(base + "/api/hub/chat?nick=main&after=0")
    got = [(x["role"], x["text"]) for x in d.get("items") or []]
    check("Claude 대화 — /명령 · 혼잣말(note) · 최종 답 · 여러 줄 유저 글 (주입 · 도구 · 생각 · 서브 뺌)",
          got == [("user", "/login"), ("user", "/main A"), ("note", "확인할게"), ("assistant", "끝났어"), ("user", "여러 줄 글\n둘째 줄")], got)
    code, d = http(base + "/api/hub/chat?nick=doc1&after=0")
    check("Claude 대화 — /clear 뒤 새 기록을 따라감", [x["text"] for x in d.get("items") or []] == ["clear 뒤 글"] and d.get("thread") == CSID2, d)
    text = '기호 $HOME "따옴표" `x` -- --x\n둘째 줄'
    code, d = http(base + "/api/hub/queue", {"nick": "main", "text": text})
    calls = tmuxed(w)
    check("Claude 보내기 — tmux 확인 → load-buffer(표준 입력 = 글 그대로) → paste-buffer -p → Enter · 소켓 -S",
          code == 200 and [c[0][2] for c in calls] == ["display-message", "load-buffer", "paste-buffer", "send-keys"]
          and calls[1][1] == text and "-p" in calls[2][0] and calls[3][0][-1] == "Enter" and all(c[0][:2] == ["-S", "/tmp/s"] for c in calls),
          (code, d, calls))
    code, d = http(base + "/api/hub/queue", {"nick": "doc1", "text": "x"})
    check("Claude 보내기 — tmux 밖 세션은 409 · 원인 한 줄", code == 409 and "tmux" in d.get("error", ""), (code, d))
    code, d = http(base + "/api/hub/magic", {"nick": "main", "view": "graph", "selection": {
        "nodes": [{"id": "t1", "kind": "task", "graph": "adr", "title": "ADR 작업 하나"}], "graph_view": "adr"}})
    rid = d.get("id")
    sent = tmuxed(w)[-3][1] if len(tmuxed(w)) >= 3 else ""
    check("Claude 마법봉 — 🪄 본문 + 끝 줄 «/main-magic 요청id»(tmux 로)", code == 200 and sent.startswith("🪄 ")
          and sent.endswith(f"\n/main-magic {rid}") and request_file(w, rid).get("message") == sent, (code, d, sent[-60:]))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    api_only = "--api-only" in sys.argv
    tmp = Path(tempfile.mkdtemp(prefix="dv_hub_"))
    proc = None
    try:
        w = make_world(tmp)
        proc, base = start(w)
        test_api(w, base)
        # Claude 세션 — 깨끗한 세계 + 가짜 Claude 홈 · 가짜 tmux(서버 따로)
        proc.terminate()
        proc.wait(5)
        tmpc = Path(tempfile.mkdtemp(prefix="dv_hubcl_"))
        try:
            wc = make_world(tmpc)
            proc, base = start(wc, claude_world(wc))
            test_claude(wc, base)
        finally:
            proc.terminate()
            try:
                proc.wait(5)
            except Exception:  # noqa: BLE001
                proc.kill()
            shutil.rmtree(tmpc, ignore_errors=True)
        if not api_only:
            # 화면 시험은 깨끗한 세계로(API 시험이 만든 질문 노드 · 요청과 안 섞이게)
            proc.terminate()
            proc.wait(5)
            tmp2 = Path(tempfile.mkdtemp(prefix="dv_hubui_"))
            try:
                w2 = make_world(tmp2)
                proc, base = start(w2)
                test_ui(w2, base)
            finally:
                proc.terminate()
                try:
                    proc.wait(5)
                except Exception:  # noqa: BLE001
                    proc.kill()
                proc = None
                shutil.rmtree(tmp2, ignore_errors=True)
    finally:
        if proc:
            proc.terminate()
            try:
                proc.wait(5)
            except Exception:  # noqa: BLE001
                proc.kill()
        shutil.rmtree(tmp, ignore_errors=True)
    bad = [n for n, ok in RESULTS if not ok]
    print(f"결과: {len(RESULTS) - len(bad)}/{len(RESULTS)} 통과" + (f" · 실패 {bad}" if bad else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
