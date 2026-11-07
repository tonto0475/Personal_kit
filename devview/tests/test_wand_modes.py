"""마법봉 경우별 시험 — 2ND(Alt+W) 질문 노드 · 작업 노드 · 설문 노드(메모 있음 · 없음) · 책 스티커 · 설문 폼 «질문» / MAIN(Alt+Q) 설문 결정

    py -3 devview/tests/test_wand_modes.py      PASS/FAIL 줄 + 마지막 «결과: N/M 통과» · 종료코드 0 = 전부 통과

단언 = 관측 결과: «입력창이 뜨나»(#hub .dv-hub-input 보임) · «가짜 codex 가 받은 메시지» · «답이 어느 노드에 저장됐나 · 새 노드 수»
세계 = test_hub.make_world(임시 작업 폴더 · 가짜 codex · 빈 포트 devview) + 이 시험이 쓰기 통로로 더한 질문 · 설문 노드
키는 헤드리스 크롬 안의 Playwright 키 입력(OS 키 아님) · 실제 Codex · 8701 · 8702 무관
"""
import json
import os
import random
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import test_hub as th  # noqa: E402

# 키트 · magic.py · 설문 도구 · bookkit
KIT = HERE.parents[1]
MAGIC = KIT / ".agents" / "skills" / "codex-hub" / "magic.py"
SURVEY_PY = KIT / ".agents" / "skills" / "survey" / "survey.py"
BK = KIT / "bookkit"
check, wait_for, queued, request_file, http = th.check, th.wait_for, th.queued, th.request_file, th.http


# ======= 재료 =======
# 그래프 노드 · 수
def tree(w):
    return json.loads(w["tree"].read_text(encoding="utf-8"))


def node(w, nid):
    return next((n for n in tree(w)["nodes"] if n["id"] == nid), {})


def count(w):
    return len(tree(w)["nodes"])


# magic.py 실행 — (종료코드, 출력) · 등록 2ND 로
def magic(w, *args):
    env = dict(os.environ, CODEX_HUB_DIR=str(w["root"] / ".codex-hub"), CODEX_THREAD_ID=th.TH["2nd"], PYTHONUTF8="1")
    r = subprocess.run([sys.executable, str(MAGIC), *args], cwd=w["root"], env=env, capture_output=True, text=True, encoding="utf-8")
    return r.returncode, r.stdout + r.stderr


# 시험 노드 — 질문 q · 설문 s(메모 있음 · 선택 1) · 설문(메모 없음) · 설문(답 없음)
def seed(w):
    sys.path.insert(0, str(th.FLOWTREE))
    import flowtree_store as fs  # noqa: E402
    tp = w["tree"]
    q = fs.apply(tp, "user", "ask", text="판 번호는 왜 필요해?", target="t1")["id"]
    s_memo = fs.apply(tp, "main", "survey-add", target="t1", question="저장 방식?", options=["파일|한 파일에 저장", "DB|sqlite"], recommend=0)["id"]
    fs.apply(tp, "user", "vote", survey=s_memo, pick=0, memo="파일이면 동시에 쓰면 깨지지 않나?")
    s_empty = fs.apply(tp, "main", "survey-add", target="t1", question="로그 위치?", options=["logs/", "out/"])["id"]
    fs.apply(tp, "user", "vote", survey=s_empty, pick=1)
    s_none = fs.apply(tp, "main", "survey-add", target="t1", question="색 테마?", options=["어둡게", "밝게"])["id"]
    return {"q": q, "s_memo": s_memo, "s_empty": s_empty, "s_none": s_none}


# 그래프 선택 — flowtree iframe 이 devview 에 보내는 선택 알림과 같은 메시지(iframe 안에서 보냄)
def select(page, ids, kinds):
    fr = page.frame(url=lambda u: "/ft/" in u)
    nodes = [{"id": i, "kind": kinds.get(i, ""), "graph": "hand_off", "title": i} for i in ids]
    fr.evaluate("(n) => window.parent.postMessage({ft: 'selection', view: 'hand_off', nodes: n}, '*')", nodes)
    return wait_for(lambda: [x["id"] for x in page.evaluate("window.devview.flowSelection().nodes")] == ids, 3)


# Playwright 이벤트를 돌리며 기다리기 — time.sleep 중에는 sync API 가 프레임 이동 등 이벤트를 처리하지 않는다
def pw_wait(page, fn, timeout=8.0):
    end = time.time() + timeout
    while time.time() < end:
        try:
            if fn():
                return True
        except Exception:  # noqa: BLE001
            pass
        page.wait_for_timeout(100)
    return False


def input_shown(page, t=1.2):
    return wait_for(lambda: page.is_visible("#hub .dv-hub-input"), t)


def last_msg(w):
    q = queued(w)
    return q[-1][-1][len("--message="):] if q and q[-1][-1].startswith("--message=") else ""


# ======= 그래프 — 2ND · MAIN =======
def test_graph(w, base, ids):
    from playwright.sync_api import sync_playwright
    kinds = {ids["q"]: "question", ids["s_memo"]: "survey", ids["s_empty"]: "survey", ids["s_none"]: "survey", "t1": "task"}
    with sync_playwright() as pw:
        br = pw.chromium.launch(headless=True)
        page = br.new_page(viewport={"width": 1600, "height": 960})
        errs = []
        page.on("pageerror", lambda e: errs.append(str(e)))
        page.goto(base + "/")
        page.wait_for_selector("html[data-ready='1']", timeout=30000)
        wait_for(lambda: page.frame(url=lambda u: "/ft/" in u) and page.frame(url=lambda u: "/ft/" in u).locator(".react-flow__node").count() > 3, 20)
        wait_for(lambda: page.locator("#hub .dv-hub-row").count() >= 2, 8)

        # ① 질문 노드 — 입력창 없이 · 질문 = 노드 제목 · 답 = 그 질문 노드
        n0, c0 = len(queued(w)), count(w)
        check("① 선택 = 질문 노드", select(page, [ids["q"]], kinds))
        page.evaluate("document.activeElement && document.activeElement.blur()")
        page.keyboard.press("Alt+KeyW")
        sent = wait_for(lambda: len(queued(w)) == n0 + 1, 5)
        check("① 질문 노드 Alt+W — 입력창 안 뜸", sent and not input_shown(page, 0.5))
        msg = last_msg(w)
        rid = msg.rsplit(" ", 1)[-1]
        check("① 가짜 codex 메시지 = 노드 제목 · «질문 노드 … 안에 답» · $2nd-magic",
              msg.startswith(f"🪄 질문: 판 번호는 왜 필요해? (질문 노드 ‹판 번호는 왜 필요해?›({ids['q']}) 안에 답 · 대상: 노드 ‹ADR 작업 하나›(t1))")
              and msg.endswith(f"\n$2nd-magic {rid}"), msg)
        t = request_file(w, rid).get("target", {}) if sent else {}
        check("① 요청 답 자리 = node · 그 질문 id · 대상 t1", t.get("kind") == "node" and t.get("question") == ids["q"] and "t1" in (t.get("targets") or []), t)
        code, out = magic(w, "show", rid)
        check("① magic.py show — 답변 준비 중 · answer-node 자리", code == 0 and f"{ids['q']} 답변 준비 중" in out and f"answer-node {rid}" in out, out)
        code, out = magic(w, "answer-node", rid, "--short", "충돌 감지용", "본문 근거")
        check("① answer-node → 그 질문 노드 answers 1 · 새 노드 0", code == 0 and len(node(w, ids["q"]).get("answers") or []) == 1
              and count(w) == c0, (out, count(w) - c0))

        # ② 작업 노드만 — 입력창(지금처럼) · 보낸 글로 새 질문 노드
        n0, c0 = len(queued(w)), count(w)
        check("② 선택 = 작업 노드", select(page, ["t1"], kinds))
        page.keyboard.press("Alt+KeyW")
        check("② 작업 노드 Alt+W — 입력창 뜸 · 아직 안 보냄", input_shown(page, 3) and len(queued(w)) == n0)
        page.keyboard.type("이 작업 범위는?")
        page.click('#hub .dv-hub-acts [data-act="send"]')
        sent = wait_for(lambda: len(queued(w)) == n0 + 1, 5)
        check("② 보냄 → 새 질문 노드 1 · 메시지 «질문: 이 작업 범위는?»", sent and count(w) == c0 + 1 and last_msg(w).startswith("🪄 질문: 이 작업 범위는?"),
              last_msg(w))

        # ③ 설문 노드(메모 있음) — 입력창 없이 · 질문 = 메모 · 답 = 그 설문 노드 «질문 · 답»
        n0, c0 = len(queued(w)), count(w)
        votes0 = node(w, ids["s_memo"]).get("votes")
        check("③ 선택 = 설문(메모 있음)", select(page, [ids["s_memo"]], kinds))
        page.keyboard.press("Alt+KeyW")
        sent = wait_for(lambda: len(queued(w)) == n0 + 1, 5)
        check("③ 설문(메모) Alt+W — 입력창 안 뜸", sent and not input_shown(page, 0.5))
        msg = last_msg(w)
        rid = msg.rsplit(" ", 1)[-1]
        check("③ 메시지 = 메모 · «설문 노드 ‹저장 방식?› 안에 답» · 대상 t1",
              msg.startswith(f"🪄 질문: 파일이면 동시에 쓰면 깨지지 않나? (설문 노드 ‹저장 방식?›({ids['s_memo']}) 안에 답 · 대상: 노드 ‹ADR 작업 하나›(t1))"), msg)
        code, out = magic(w, "show", rid)
        check("③ magic.py show — «설문 노드» · answer-node 자리", code == 0 and f"설문 노드 {ids['s_memo']}" in out and f"answer-node {rid}" in out, out)
        code, out = magic(w, "answer-node", rid, "--short", "잠금 파일로 막음", "flowtree_store 잠금")
        sv = node(w, ids["s_memo"])
        a = (sv.get("answers") or [{}])[-1]
        check("③ answer-node → 설문 answers 1(q = 메모) · votes 그대로 · 새 노드 0",
              code == 0 and len(sv.get("answers") or []) == 1 and a.get("q") == "파일이면 동시에 쓰면 깨지지 않나?" and a.get("short") == "잠금 파일로 막음"
              and sv.get("votes") == votes0 and count(w) == c0, (out, a, count(w) - c0))
        # 화면 — 설문 노드 세부 보기에 «질문 · 답»
        fr = page.frame(url=lambda u: "/ft/" in u)
        # devview → 그래프 {ft:'focus'}(알림 종 · 바로 가기와 같은 길) — 그 노드가 든 화면으로 가서 가운데
        page.evaluate("(id) => document.querySelector('#ftView iframe').contentWindow.postMessage({ft: 'focus', node: id}, '*')", ids["s_memo"])
        shown = wait_for(lambda: fr.locator(f'.react-flow__node[data-id="{ids["s_memo"]}"]').count() == 1, 5)
        if shown:
            time.sleep(0.6)
            if not fr.locator("[data-sv-qa]").count():
                fr.locator(f'.react-flow__node[data-id="{ids["s_memo"]}"]').click(position={"x": 30, "y": 12})
            ok = wait_for(lambda: fr.locator("[data-sv-qa]").count() >= 1, 4)
            txt = fr.locator("[data-sv-qa]").first.inner_text() if ok else ""
            check("③ 화면 — 설문 세부 «질문 · 답» 에 🚹 메모 · 🤖 결론", ok and "파일이면 동시에" in txt and "잠금 파일로 막음" in txt, txt)
            th.SHOTS.mkdir(exist_ok=True)
            page.screenshot(path=str(th.SHOTS / "wand_survey_qa.png"))
        else:
            check("③ 화면 — 설문 노드가 지금 그래프 화면에 있음(세부 보기 확인)", False, "center 실패")

        # ④ 설문 노드(메모 없음) — 입력창 · 보낸 글이 질문 · 답 = 그 설문 노드
        n0, c0 = len(queued(w)), count(w)
        check("④ 선택 = 설문(메모 없음)", select(page, [ids["s_empty"]], kinds))
        page.keyboard.press("Alt+KeyW")
        check("④ 설문(메모 없음) Alt+W — 입력창 뜸 · 아직 안 보냄", input_shown(page, 3) and len(queued(w)) == n0)
        page.keyboard.type("logs 와 out 차이?")
        page.click('#hub .dv-hub-acts [data-act="send"]')
        sent = wait_for(lambda: len(queued(w)) == n0 + 1, 5)
        msg = last_msg(w)
        rid = msg.rsplit(" ", 1)[-1]
        check("④ 메시지 = 입력 글 · «설문 노드 … 안에 답» · 새 노드 0", sent and msg.startswith(f"🪄 질문: logs 와 out 차이? (설문 노드 ‹로그 위치?›({ids['s_empty']}) 안에 답")
              and count(w) == c0, msg)
        code, out = magic(w, "answer-node", rid, "--short", "out 은 결과물", "")
        a = (node(w, ids["s_empty"]).get("answers") or [{}])[-1]
        check("④ answer-node → 설문 answers(q = 입력 글)", code == 0 and a.get("q") == "logs 와 out 차이?", (out, a))

        # ⑤ MAIN — 답한 설문(결정) + 답 없는 설문 + 작업 → 답 없는 설문만 빠지고 «결정 … 반영하고 이어진 작업 시작»
        n0, c0 = len(queued(w)), count(w)
        check("⑤ 선택 = 설문(답) · 설문(답 없음) · 작업", select(page, [ids["s_memo"], ids["s_none"], "t1"], kinds))
        page.keyboard.press("Alt+KeyQ")
        sent = wait_for(lambda: len(queued(w)) == n0 + 1, 5)
        msg = last_msg(w)
        rid = msg.rsplit(" ", 1)[-1]
        check("⑤ MAIN 메시지 — «설문 ‹저장 방식?› 결정: ‹1. 파일 — 한 파일에 저장› · 메모 … — 반영하고 이어진 작업 ‹ADR 작업 하나›(t1) 시작»",
              sent and f"설문 ‹저장 방식?›({ids['s_memo']}) 결정: ‹1. 파일 — 한 파일에 저장› · 메모 파일이면 동시에 쓰면 깨지지 않나?"
              " — 반영하고 이어진 작업 ‹ADR 작업 하나›(t1) 시작" in msg and msg.endswith(f"\n$main-magic {rid}"), msg)
        check("⑤ 답 없는 설문은 메시지 · 요청에서 빠짐 · 작업은 그대로", ids["s_none"] not in msg and "(t1) 구현해 줘" in msg
              and [x["id"] for x in request_file(w, rid)["nodes"]] == [ids["s_memo"], "t1"], msg)
        toast = wait_for(lambda: page.locator(".dv-toast, #toast, [class*=toast]").filter(has_text="답 없음").count() > 0, 3)
        check("⑤ 화면 알림 «답 없음 — s… 뺌»", toast, page.evaluate("document.body.innerText.match(/답 없음[^\\n]*/)?.[0] || ''"))
        check("⑤ 입력창 안 뜸 · 새 노드 0", not input_shown(page, 0.3) and count(w) == c0)
        code, out = magic(w, "show", rid)
        check("⑤ magic.py show — «설문 할 일» · survey-ack · 카드 P", code == 0 and f"설문 할 일: {ids['s_memo']}" in out and f"survey-ack {ids['s_memo']}" in out
              and "카드 P" in out, out)
        # 답 없는 설문만 → 보내지 않음 · 알림
        n0 = len(queued(w))
        select(page, [ids["s_none"]], kinds)
        page.keyboard.press("Alt+KeyQ")
        toast = wait_for(lambda: page.locator("[class*=toast]").filter(has_text="보낼 노드 없음 — 답 없음").count() > 0, 3)
        check("⑤ 답 없는 설문만 → 안 보냄 · «보낼 노드 없음 — 답 없음» 알림", toast and len(queued(w)) == n0)
        check("화면 오류(pageerror) 없음", not errs, errs[:3])
        br.close()


# ======= 지시 붙은 마법봉(Alt+E MAIN · Alt+R 2ND) — 노드 없음 · 코드 줄 · 대상 없음 =======
def test_note_keys(w, base):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        br = pw.chromium.launch(headless=True)
        page = br.new_page(viewport={"width": 1600, "height": 960})
        errs = []
        page.on("pageerror", lambda e: errs.append(str(e)))
        page.goto(base + "/")
        page.wait_for_selector("html[data-ready='1']", timeout=30000)
        pw_wait(page, lambda: page.locator("#hub .dv-hub-row").count() >= 2, 8)

        # 한 경우 — 키 → 입력창 · 머리 줄 · 자동 전송 없음 → 지시 ✈ → 가짜 codex 글
        def run(case, key, role, want_head, want_msg):
            n0, c0 = len(queued(w)), count(w)
            page.keyboard.press(f"Alt+{key}")
            shown = pw_wait(page, lambda: page.is_visible("#hub .dv-hub-input"), 3)
            head = page.inner_text("#hub .dv-hub-input-head") if shown else ""
            page.wait_for_timeout(600)
            check(f"{case} Alt+{key[-1]} — {role.upper()} 지시 입력창 · 머리 «{want_head}» · 자동 전송 없음",
                  shown and want_head in head and f"→ {role.upper()}" in head and len(queued(w)) == n0, (head, len(queued(w)) - n0))
            text = f"{case} 지시 {role}"
            page.keyboard.type(text)
            page.click('#hub .dv-hub-acts [data-act="send"]')
            sent = pw_wait(page, lambda: len(queued(w)) == n0 + 1, 6)
            msg = last_msg(w)
            ok = sent and all(x in msg for x in want_msg) and f"지시: {text}" in msg and f"${role}-magic" in msg
            check(f"{case} Alt+{key[-1]} ✈ — 가짜 codex 글에 대상 · 지시 둘 다 · 새 노드 {'1(2ND 섬 질문)' if role == '2nd' and case != '코드 줄' else '0'}", ok, msg)
            rid = msg.rsplit(" ", 1)[-1] if sent else ""
            return rid, count(w) - c0

        # 노드 없음(그래프 · 아무것도 안 고름)
        select(page, [], {})
        page.evaluate("document.activeElement && document.activeElement.blur()")
        rid, _ = run("노드 없음", "KeyE", "main", "대상 없음", ["대상 없음(보기 graph)"])
        code, out = magic(w, "show", rid)
        check("노드 없음 MAIN — magic.py show «대상 없음 · 지시 · 할 일»(멈춤 아님)", code == 0 and "지시: 노드 없음 지시 main" in out
              and "할 일: 대상 + 지시대로" in out and "멈춤" not in out, out)
        rid, made = run("노드 없음", "KeyR", "2nd", "대상 없음", ["지시: 노드 없음 지시 2nd"])
        t = request_file(w, rid)["target"] if rid else {}
        qn = node(w, t.get("question") or "")
        check("그래프 보기 대상 없음 2ND → 새 질문 노드 1(섬 · 제목 = 지시 글)", made == 1 and t.get("kind") == "node"
              and qn.get("kind") == "question" and qn.get("title") == "노드 없음 지시 2nd", (made, t, qn))

        # 코드 보기 · 연 파일 없음(대상 없음) — 2ND 는 노드를 만들지 않고 지시 글만
        page.evaluate("window.devview.showView('code')")
        page.evaluate("window.devview.closeAll && window.devview.closeAll()")
        page.wait_for_timeout(300)
        page.evaluate("document.activeElement && document.activeElement.blur()")
        if page.evaluate("!!(window.devview.activePath && window.devview.activePath())"):
            check("코드 보기 대상 없음 — 열린 파일 없음(시험 전제)", False, page.evaluate("window.devview.activePath()"))
        rid, made = run("코드 빈", "KeyR", "2nd", "대상 없음", ["지시: 코드 빈 지시 2nd (대상: 없음(보기 app) — 답은 대화로)"])
        t = request_file(w, rid)["target"] if rid else {}
        check("코드 보기 대상 없음 2ND → 새 노드 0 · 답 자리 chat", made == 0 and t.get("kind") == "chat", (made, t))
        code, out = magic(w, "show", rid)
        check("코드 보기 대상 없음 2ND — show «답 자리 없음 — 대화로 답»", code == 0 and "답 자리 없음 — 대화로 답" in out, out)

        # 코드 줄 선택
        page.evaluate("window.devview.showView('code')")
        page.evaluate("window.devview.openFile('src/calc.py')")
        pw_wait(page, lambda: page.evaluate("window.devview.activePath()") == "src/calc.py", 5)
        sel_code = ("(() => { const ed = window.devview.editor(); ed.setSelection({startLineNumber: 6, startColumn: 1, endLineNumber: 7, endColumn: 21});"
                    " ed.focus(); })()")
        page.evaluate(sel_code)
        rid, made = run("코드 줄", "KeyE", "main", "src/calc.py 6–7줄", ["대상: 파일 src/calc.py 6–7줄", "def calc"])
        code, out = magic(w, "show", rid)
        check("코드 줄 MAIN — 요청 target.ref(code · 6–7줄) · show «대상 파일 · 지시»", code == 0 and "대상 파일: src/calc.py · 줄 6–7" in out
              and "지시: 코드 줄 지시 main" in out and request_file(w, rid)["target"]["ref"]["kind"] == "code", out)
        page.evaluate(sel_code)
        rid, made = run("코드 줄", "KeyR", "2nd", "src/calc.py 6–7줄", ["지시: 코드 줄 지시 2nd (대상: src/calc.py 6–7줄)"])
        t = request_file(w, rid)["target"] if rid else {}
        check("코드 줄 2ND — 답 자리 code(그 파일 · 줄) · 새 노드 0", t.get("kind") == "code" and (t.get("range") or {}).get("start_line") == 6 and made == 0, (t, made))

        # 대상 없음(앱 보기)
        page.evaluate("window.devview.showView('app')")
        page.wait_for_timeout(300)
        page.evaluate("document.activeElement && document.activeElement.blur()")
        run("대상 없음", "KeyE", "main", "대상 없음", ["대상 없음(보기 app)"])
        rid, made = run("대상 없음", "KeyR", "2nd", "대상 없음", ["지시: 대상 없음 지시 2nd"])
        check("앱 보기 대상 없음 2ND → 새 노드 0", made == 0 and request_file(w, rid)["target"].get("kind") == "chat", made)
        check("지시 마법봉 — 화면 오류(pageerror) 없음", not errs, errs[:3])
        br.close()


# ======= 책 스티커 — devview Book 보기 안 Alt+W =======
def free_port2():
    for _ in range(200):
        p = random.randint(20000, 40000)
        try:
            with socket.socket() as s, socket.socket() as t:
                s.bind(("127.0.0.1", p))
                t.bind(("127.0.0.1", p + 100))
            return p
        except OSError:
            pass
    raise RuntimeError("빈 포트 없음")


def test_book():
    from playwright.sync_api import sync_playwright
    name = "wmbook"
    tmp = Path(tempfile.mkdtemp(prefix="wand_book_"))
    root = tmp / "proj"
    book = root / "bookkit" / "books" / name
    shutil.copytree(BK / "template", book, ignore=shutil.ignore_patterns("dist", "__pycache__"))
    meta = book / "content" / "meta.py"
    meta.write_text(meta.read_text(encoding="utf-8").replace('"doc": "",', f'"doc": "{name}",', 1), encoding="utf-8")
    (book / "contracts").mkdir(exist_ok=True)
    for n in ("facts", "reqs", "steps"):
        shutil.copy(BK / "contracts" / "example" / f"{n}.json", book / "contracts" / f"{n}.json")
    shutil.copy(BK / "notes.py", root / "bookkit" / "notes.py")
    r = subprocess.run([sys.executable, str(BK / "engine" / "build_book.py"), str(book), "--stage", "1"], capture_output=True, text=True, encoding="utf-8")
    check("책 — 시험 책 1차판 빌드", r.returncode == 0, r.stdout[-200:] + r.stderr[-200:])
    hub = root / ".codex-hub"
    (hub / "sessions").mkdir(parents=True)
    (hub / "sessions" / "2nd.json").write_text(json.dumps({"nick": "2nd", "thread": "019a-2nd", "registered_at": "2026-11-05 00:00:00"}), encoding="utf-8")
    (hub / "sessions" / "main.json").write_text(json.dumps({"nick": "main", "thread": "019a-main", "registered_at": "2026-11-05 00:00:00"}), encoding="utf-8")
    log = tmp / "queue.jsonl"
    fake = tmp / "fake_codex.py"
    fake.write_text("import json, os, sys\nopen(os.environ['FAKE_CODEX_LOG'], 'a', encoding='utf-8').write(json.dumps(sys.argv[1:], ensure_ascii=False) + '\\n')\n"
                    "print('Queued message m-1.')\n", encoding="utf-8")
    home = tmp / "home"
    home.mkdir()
    port = free_port2()
    env = dict(os.environ, DEVVIEW_NO_VAULT="1", CODEX_HOME=str(tmp / "codex"), DEVVIEW_CODEX=str(fake), FAKE_CODEX_LOG=str(log),
               HOME=str(home), USERPROFILE=str(home), PYTHONUTF8="1")
    dv = subprocess.Popen([sys.executable, str(th.DEVVIEW), str(root), "--host", "127.0.0.1", "--port", str(port)],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
    q = lambda: [json.loads(x) for x in log.read_text(encoding="utf-8").splitlines()] if log.is_file() else []  # noqa: E731
    try:
        base = f"http://127.0.0.1:{port}"
        wait_for(lambda: urllib.request.urlopen(base + "/api/info", timeout=1).read(), 20)
        with sync_playwright() as pw:
            br = pw.chromium.launch(headless=True)
            page = br.new_page(viewport={"width": 1600, "height": 1000})
            # 책 주소 응답 · 실패(못 열 때 원인)
            pg_log = []
            page.on("response", lambda r: pg_log.append((r.status, r.url[-60:])) if "/pg/" in r.url else None)
            page.on("requestfailed", lambda r: pg_log.append(("failed", r.url[-60:], r.failure)) if "/pg/" in r.url else None)
            page.goto(base + "/")
            page.wait_for_selector("html[data-ready='1']", timeout=30000)
            page.evaluate("window.devview.showView('book')")
            ok = pw_wait(page, lambda: page.frame(url=lambda u: f"/{name}/dist/" in u) is not None, 20)
            bf = lambda: page.frame(url=lambda u: f"/{name}/dist/" in u)  # noqa: E731 — 책 프레임(다시 붙어도 새로 찾음)
            ok = ok and pw_wait(page, lambda: bf().evaluate("!!(window.__book && window.__book.ready)"), 60)
            fr = bf()
            check("책 — devview Book 보기에 시험 책", ok, (pg_log[:4], [f.url[-50:] for f in page.frames],
                                                       fr.evaluate("typeof window.__book + ' ' + JSON.stringify(window.__book && window.__book.ready)") if fr else None))
            if not ok:
                br.close()
                return
            # 스티커 하나 접수
            blk = "s3-Q1"
            pi = fr.evaluate(f"+document.querySelector('#book [data-id=\"{blk}\"]').closest('.page').dataset.pi")
            fr.evaluate(f"window.__book.go({pi})")
            time.sleep(0.4)
            fr.click("#bMemo")
            box = fr.locator(f'#book [data-id="{blk}"]').bounding_box()
            fr.locator(f'#book [data-id="{blk}"]').click(position={"x": 40, "y": 10})
            note = fr.locator(".note").last
            note.locator("textarea").fill("총거리 기준 이유?")
            note.locator(".nf button:not(.nw)").click()
            fr.wait_for_selector(".note .nt:has-text('접수')", timeout=5000)
            note = fr.locator(".note").last
            note.locator(".nb").click()
            n0 = len(q())
            page.keyboard.press("Alt+KeyW")
            sent = wait_for(lambda: len(q()) == n0 + 1, 6)
            check("책 스티커 Alt+W — 입력창 안 뜸(허브 입력창 · 책 안 입력 칸 둘 다)", sent and not input_shown(page, 0.5), (sent, box))
            msg = q()[-1][-1] if sent else ""
            check("책 스티커 Alt+W — 가짜 codex «🪄 책 ‹…› 스티커 질문: 총거리 기준 이유?» · $2nd-magic",
                  "스티커 질문: 총거리 기준 이유?" in msg and "$2nd-magic" in msg, msg)
            nid = json.loads((book / "notes.json").read_text(encoding="utf-8"))[0]["id"]
            # 지시 붙은 마법봉 — 책 안(스티커를 누른 채) Alt+E · Alt+R → 허브 입력창(대상 = 스티커) · 자동 전송 없음 → ✈ 뒤 대상 + 지시
            # 스티커를 누른 채 키 → 입력창(대상 = 스티커 · 자동 전송 없음) → 지시 → ✈ — 반환 (보냈나, 받은 인자)
            def note_key(key, role, text):
                fr.locator(".qr, .note").first.dispatch_event("pointerdown")
                fr.evaluate("document.activeElement && document.activeElement.blur && document.activeElement.blur()")
                n0 = len(q())
                fr.locator("body").press(f"Alt+{key}")
                shown = pw_wait(page, lambda: page.is_visible("#hub .dv-hub-input"), 3)
                head = page.inner_text("#hub .dv-hub-input-head") if shown else ""
                page.wait_for_timeout(600)
                check(f"책 스티커 Alt+{key[-1]} — {role.upper()} 지시 입력창 · 대상 스티커 · 자동 전송 없음",
                      shown and nid in head and role.upper() in head and len(q()) == n0, (head, len(q()) - n0))
                page.fill("#hub .dv-hub-input textarea", text)
                page.click('#hub .dv-hub-acts [data-act="send"]')
                sent = pw_wait(page, lambda: len(q()) == n0 + 1, 4)
                return sent, (q()[-1] if sent else [])

            sent, m = note_key("KeyE", "main", "main 스티커 지시")
            check("책 스티커 Alt+E ✈ — 가짜 codex(main) 글에 스티커 id · 지시",
                  sent and m[2] == "019a-main" and nid in m[-1] and "지시: main 스티커 지시" in m[-1] and "$main-magic" in m[-1], m[-1:])
            check("책 스티커 Alt+E ✈ 뒤 — 입력창 닫히고 Book 보기에서 허브 다시 숨음", pw_wait(page, lambda: not page.is_visible("#hub"), 3))
            # 답 대기 중(Alt+W 로 보냄) Alt+R → 스티커 마법봉 길의 409 — 안 보냄 · 알림
            sent, m = note_key("KeyR", "2nd", "2nd 스티커 지시")
            toast = pw_wait(page, lambda: "이미 보냄" in page.inner_text("#toasts"), 3)
            check("답 대기 스티커 Alt+R → «이미 보냄» · 안 보냄(중복 전송 없음)", not sent and toast, m[-1:] if m else None)
            page.click('#hub .dv-hub-acts [data-act="cancel"]')
            # 2ND 가 답을 단 뒤 Alt+R → 꼬리 질문으로(원 답 그대로) · magic_rid 남음
            rid_w = msg.rsplit(" ", 1)[-1]
            menv = dict(os.environ, CODEX_HUB_DIR=str(hub), CODEX_THREAD_ID="019a-2nd", PYTHONUTF8="1")
            r = subprocess.run([sys.executable, str(MAGIC), "answer-note", rid_w, "원 답이다", "--title", "총거리"], cwd=root, env=menv,
                               capture_output=True, text=True, encoding="utf-8")
            check("책 — 2ND 원 답 달기(answer-note)", r.returncode == 0, r.stdout + r.stderr)
            sent, m = note_key("KeyR", "2nd", "2nd 꼬리 지시")
            nt = json.loads((book / "notes.json").read_text(encoding="utf-8"))[0]
            tl = (nt.get("thread") or [{}])[-1]
            check("답 달린 스티커 Alt+R ✈ → 꼬리 질문(thread q = 지시) · 원 답 그대로 · 꼬리 magic_rid · 가짜 codex «꼬리 질문»",
                  sent and m[2] == "019a-2nd" and "꼬리 질문" in m[-1] and "2nd 꼬리 지시" in m[-1] and nt.get("answer") == "원 답이다"
                  and tl.get("q") == "2nd 꼬리 지시" and tl.get("magic_rid") == m[-1].rsplit(" ", 1)[-1], (m[-1:], nt))
            br.close()
    finally:
        dv.terminate()
        try:
            dv.wait(timeout=5)
        except subprocess.TimeoutExpired:
            dv.kill()
        shutil.rmtree(tmp, ignore_errors=True)


# ======= 설문 폼 — 문항에서 «질문» + 메모 → 제출 → 2ND 로 바로 =======
def test_survey_form():
    from playwright.sync_api import sync_playwright
    tmp = Path(tempfile.mkdtemp(prefix="wand_sv_"))
    try:
        (tmp / "devview").mkdir()
        for nm in ("codex_hub.py", "codex_sessions.py"):
            shutil.copyfile(KIT / "devview" / nm, tmp / "devview" / nm)
        for nick, thr in (("main", "T-MAIN"), ("2nd", "T-2ND")):
            p = tmp / ".codex-hub" / "sessions" / f"{nick}.json"
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps({"nick": nick, "thread": thr}), encoding="utf-8")
        fake = tmp / "fake_codex.py"
        fake.write_text("import json, os, sys\nopen(os.environ['FAKE_OUT'], 'a', encoding='utf-8').write(json.dumps(sys.argv[1:], ensure_ascii=False) + '\\n')\n"
                        "print('queued')\n", encoding="utf-8")
        out = tmp / "calls.jsonl"
        env = dict(os.environ, SURVEY_REGISTRY=str(tmp / "_registry.json"), FAKE_OUT=str(out), DEVVIEW_CODEX=str(fake), PYTHONUTF8="1")
        for k in ("SURVEY_NO_QUEUE", "CODEX_HUB_DIR", "CODEX_THREAD_ID"):
            env.pop(k, None)
        store = tmp / "docs" / "surveys"
        spec = tmp / "q.json"
        spec.write_text(json.dumps({"title": "폼 시험", "questions": [{"id": "1", "question": "q1", "options": ["A", "B"]}]}, ensure_ascii=False), encoding="utf-8")
        r = subprocess.run([sys.executable, str(SURVEY_PY), "--dir", str(store), "new", str(spec), "--project", "시험", "--thread", "T-REG"],
                           capture_output=True, text=True, encoding="utf-8", env=env, timeout=30)
        info = json.loads(r.stdout) if r.returncode == 0 else {}
        check("설문 폼 — 설문 등록", r.returncode == 0, r.stderr[-200:])
        port = th.free_port()
        server = subprocess.Popen([sys.executable, str(SURVEY_PY), "--dir", str(store), "serve", "--host", "127.0.0.1", "--port", str(port)],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
        try:
            base = f"http://127.0.0.1:{port}"
            wait_for(lambda: urllib.request.urlopen(base + "/api/state?probe=1", timeout=1).read(), 10)
            with sync_playwright() as pw:
                br = pw.chromium.launch(headless=True)
                page = br.new_page()
                page.goto(base + info["path"])
                page.locator(".seg label", has_text="질문").first.click()
                page.locator("textarea[name='q1_memo']").fill("A 와 B 의 차이?")
                page.locator("button.ok").click()
                page.wait_for_selector("#route", timeout=30000)
                text = page.locator("#route").inner_text()
                br.close()
            calls = [json.loads(x) for x in out.read_text(encoding="utf-8").splitlines()] if out.is_file() else []
            m = [c for c in calls if c[:3] == ["queue", "--thread", "T-2ND"]]
            check("설문 폼 «질문» + 메모 제출 → 2ND 로 바로(🪄 … 질문 1개 · A 와 B 의 차이? · $2nd-magic) · 화면 «2ND 전송»",
                  len(m) == 1 and "질문 1개" in m[0][3] and "A 와 B 의 차이?" in m[0][3] and "$2nd-magic" in m[0][3] and "2ND 전송" in text,
                  (calls, text))
        finally:
            server.terminate()
            server.wait(timeout=10)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    tmp = Path(tempfile.mkdtemp(prefix="wand_modes_"))
    proc = None
    try:
        w = th.make_world(tmp)
        ids = seed(w)
        proc, base = th.start(w)
        test_graph(w, base, ids)
        test_note_keys(w, base)
    finally:
        if proc:
            proc.terminate()
            try:
                proc.wait(5)
            except Exception:  # noqa: BLE001
                proc.kill()
        shutil.rmtree(tmp, ignore_errors=True)
    test_book()
    test_survey_form()
    bad = [n for n, ok in th.RESULTS if not ok]
    print(f"결과: {len(th.RESULTS) - len(bad)}/{len(th.RESULTS)} 통과" + (f" · 실패 {bad}" if bad else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
