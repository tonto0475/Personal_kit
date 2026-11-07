"""마법봉 실제 경로 시험 — 그래프 노드를 마우스로 고르고 · 메모 · 제목 칸에 실제로 타이핑하고 · 칸을 벗어나지 않은 채 키

    py -3 devview/tests/test_wand_real.py      PASS/FAIL 줄 + 마지막 «결과: N/M 통과» · 종료코드 0 = 전부 통과

test_wand_modes 는 선택을 가짜 알림으로 · 메모를 쓰기 통로로 넣어서 «저장 전 전송» 같은 결함을 못 잡았다(2026-11-05 독립 검증).
여기서는 선택 = 그래프 iframe 노드 클릭(Ctrl+클릭 여럿) · 메모 · 제목 = 패널 입력 칸에 keyboard.type · 키 = 그 칸에 포커스가 있는 채 Alt+…
단언 = 가짜 codex 가 받은 글 · 요청 파일 · tree.json(메모 · 답 · 노드 수) · notes.json(magic_rid · 꼬리) · 화면 알림 · 입력창
세계 = test_hub.make_world(임시 작업 폴더 · 가짜 codex · 빈 포트 devview) · 키는 헤드리스 크롬 안 키(OS 키 아님) · 실제 Codex · 8701 무관
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import test_hub as th  # noqa: E402
import test_wand_modes as tm  # noqa: E402

check, queued, request_file = th.check, th.queued, th.request_file
pw_wait, last_msg, node, count, magic = tm.pw_wait, tm.last_msg, tm.node, tm.count, tm.magic


# ======= 재료 =======
# 시험 노드 — 질문 셋(하나는 닫힘) · 설문(빈 메모 · 옛 메모 · 답 없음 둘 · 보류 · 이미 반영)
def seed(w):
    sys.path.insert(0, str(th.FLOWTREE))
    import flowtree_store as fs  # noqa: E402
    tp = w["tree"]
    ask = lambda t: fs.apply(tp, "user", "ask", text=t, target="t1")["id"]  # noqa: E731
    sv = lambda t: fs.apply(tp, "main", "survey-add", target="t1", question=t, options=["가|가 설명", "나"])["id"]  # noqa: E731
    ids = {"q1": ask("첫 질문?"), "q2": ask("둘째 질문?"), "q3": ask("셋째 질문?"),
           "s_type": sv("메모 칠 설문?"), "s_old": sv("옛 메모 설문?"), "s_q": sv("메모만 칠 설문?"), "s_none": sv("답 없는 설문?"),
           "s_hold": sv("보류 설문?"), "s_acked": sv("반영한 설문?")}
    fs.apply(tp, "user", "vote", survey=ids["s_old"], memo="옛 메모")
    fs.apply(tp, "user", "vote", survey=ids["s_hold"], hold=True)
    fs.apply(tp, "user", "vote", survey=ids["s_acked"], pick=0)
    fs.apply(tp, "main", "survey-ack", survey=ids["s_acked"], note="반영함")
    return ids


def ftf(page):
    return page.frame(url=lambda u: "/ft/" in u)


# 노드로 화면 이동(devview → 그래프 {ft:'focus'} — 알림 종 · 바로 가기와 같은 길) 후 마우스 클릭 · ctrl = Ctrl+클릭(여럿)
def click_node(page, nid, ctrl=False):
    if not ctrl:
        page.evaluate("(id) => document.querySelector('#ftView iframe').contentWindow.postMessage({ft: 'focus', node: id}, '*')", nid)
    else:
        ftf(page).evaluate(f"window.__flowtree.center({json.dumps(nid)}, 1)")
    loc = lambda: ftf(page).locator(f'.react-flow__node[data-id="{nid}"]')  # noqa: E731
    pw_wait(page, lambda: loc().count() == 1, 5)
    page.wait_for_timeout(500)
    loc().click(position={"x": 30, "y": 12}, modifiers=["Control"] if ctrl else [])
    page.wait_for_timeout(400)
    return [x["id"] for x in page.evaluate("window.devview.flowSelection().nodes")]


def toasts(page):
    return page.inner_text("#toasts") if page.locator("#toasts").count() else ""


# 키 하나 → (보낸 수, 입력창 보임)
def press(page, w, key, wait=3.0):
    n0 = len(queued(w))
    page.keyboard.press(key)
    pw_wait(page, lambda: len(queued(w)) > n0, wait)
    page.wait_for_timeout(400)
    return len(queued(w)) - n0, page.is_visible("#hub .dv-hub-input")


def cancel(page):
    if page.is_visible("#hub .dv-hub-input"):
        page.click('#hub .dv-hub-acts [data-act="cancel"]')


# ======= 그래프 =======
def test_graph(w, base, ids):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        br = pw.chromium.launch(headless=True)
        page = br.new_page(viewport={"width": 1600, "height": 960})
        errs = []
        page.on("pageerror", lambda e: errs.append(str(e)))
        page.goto(base + "/")
        page.wait_for_selector("html[data-ready='1']", timeout=30000)
        pw_wait(page, lambda: ftf(page) and ftf(page).locator(".react-flow__node").count() > 3, 20)
        pw_wait(page, lambda: page.locator("#hub .dv-hub-row").count() >= 2, 8)
        memo = lambda: ftf(page).locator('textarea[data-edit="memo"]').first  # noqa: E731

        # 결함 1 — 빈 메모 설문: 메모를 치고 칸을 벗어나지 않은 채 Alt+W → 친 글로 바로(입력창 없음)
        check("R1 실제 클릭으로 설문 고름", click_node(page, ids["s_type"]) == [ids["s_type"]])
        memo().click()
        page.keyboard.type("이거 왜 필요해?")
        n, inp = press(page, w, "Alt+KeyW")
        check("R1 메모 치고 바로 Alt+W → 입력창 없이 친 메모로 2ND · 트리 메모 저장됨",
              n == 1 and not inp and last_msg(w).startswith("🪄 질문: 이거 왜 필요해? (설문 노드")
              and (node(w, ids["s_type"]).get("votes") or [{}])[-1].get("memo") == "이거 왜 필요해?", (n, inp, last_msg(w)[:120]))
        cancel(page)

        # 결함 1 — 옛 메모를 고치고 바로 Alt+W → 새 메모로
        click_node(page, ids["s_old"])
        memo().click()
        page.keyboard.press("Control+A")
        page.keyboard.type("새 메모 질문?")
        n, inp = press(page, w, "Alt+KeyW")
        check("R2 옛 메모 고치고 바로 Alt+W → 새 메모로(옛 메모 아님)", n == 1 and last_msg(w).startswith("🪄 질문: 새 메모 질문?"), last_msg(w)[:120])

        # 결함 1 — 답 없는 설문에 메모만 치고 바로 Alt+Q → «답 없음» 으로 빠지지 않고 결정으로 MAIN
        click_node(page, ids["s_q"])
        memo().click()
        page.keyboard.type("가로 하되 로그 남겨")
        n, inp = press(page, w, "Alt+KeyQ")
        check("R3 메모 치고 바로 Alt+Q → MAIN «설문 … 결정 · 메모 가로 하되 로그 남겨»", n == 1 and "메모 가로 하되 로그 남겨" in last_msg(w)
              and f"({ids['s_q']}) 결정" in last_msg(w) and "$main-magic" in last_msg(w), (n, last_msg(w)[:200], toasts(page)[-80:]))

        # 결함 1 — 질문 제목 고치고 바로 Alt+W → 고친 제목으로
        click_node(page, ids["q2"])
        ta = ftf(page).locator("textarea.p-input").first
        ta.click()
        page.keyboard.press("Control+A")
        page.keyboard.type("고친 둘째 질문?")
        n, inp = press(page, w, "Alt+KeyW")
        rid_q2 = last_msg(w).rsplit(" ", 1)[-1]
        check("R4 질문 제목 고치고 바로 Alt+W → 고친 제목으로 그 질문 노드에", n == 1 and last_msg(w).startswith(f"🪄 질문: 고친 둘째 질문? (질문 노드 ‹고친 둘째 질문?›({ids['q2']})"),
              last_msg(w)[:160])

        # 결함 6 — 답 대기 중 같은 질문 Alt+W 연타 → 안 보냄 · «이미 보냄» · 답이 달린 뒤엔 다시 보내지고 show 에 앞 답
        page.evaluate("document.activeElement && document.activeElement.blur()")
        n, inp = press(page, w, "Alt+KeyW", 1.5)
        check("R5 답 대기 중 Alt+W 다시 → 안 보냄 · «이미 보냄» 알림", n == 0 and "이미 보냄" in toasts(page), toasts(page)[-120:])
        code, out = magic(w, "answer-node", rid_q2, "--short", "첫 답", "본문")
        n, inp = press(page, w, "Alt+KeyW")
        code, out = magic(w, "show", last_msg(w).rsplit(" ", 1)[-1])
        check("R5 답 달린 뒤 Alt+W → 보냄 · show 에 «앞 답 1 … 첫 답»", n == 1 and code == 0 and "앞 답 1" in out and "첫 답" in out, out[-300:])

        # 결정 A — 질문 둘 Ctrl+클릭 → Alt+W → 질문마다 요청 따로 · 각각 그 노드 · 새 노드 0
        c0 = count(w)
        click_node(page, ids["q1"])
        sel = click_node(page, ids["q3"], ctrl=True)
        check("A 실제 Ctrl+클릭 — 질문 둘 고름", sel == [ids["q1"], ids["q3"]], sel)
        n, inp = press(page, w, "Alt+KeyW")
        pw_wait(page, lambda: len(queued(w)) >= 2, 2)
        got = [request_file(w, m[-1].rsplit(" ", 1)[-1])["target"].get("question") for m in queued(w)[-2:]]
        check("A 질문 둘 Alt+W → 요청 2개 · 각각 q1 · q3 노드 안 · 새 노드 0 · 입력창 없음", n == 2 and sorted(got) == sorted([ids["q1"], ids["q3"]])
              and count(w) == c0 and not inp, (n, got, count(w) - c0))

        # 결함 4 — 답 없는 설문 + Alt+E → 설문은 맥락으로 남음(«대상 없음» 아님)
        click_node(page, ids["s_none"])
        page.evaluate("document.activeElement && document.activeElement.blur()")
        page.keyboard.press("Alt+KeyE")
        head = page.inner_text("#hub .dv-hub-input-head") if pw_wait(page, lambda: page.is_visible("#hub .dv-hub-input"), 3) else ""
        page.keyboard.type("이 설문부터 채워")
        n0 = len(queued(w))
        page.click('#hub .dv-hub-acts [data-act="send"]')
        pw_wait(page, lambda: len(queued(w)) == n0 + 1, 4)
        msg = last_msg(w)
        check("R7 답 없는 설문 Alt+E → 머리 줄 대상 = 그 설문 · 글에 «맥락: ‹…›(s…)» + 지시 · «대상 없음» 없음",
              "답 없는 설문?" in head and f"({ids['s_none']})" in msg and "지시: 이 설문부터 채워" in msg and "대상 없음" not in msg, (head, msg[:200]))

        # 결정 B — 보류 설문 Alt+Q → 안 보냄 · «보류 설문» / 보류 + 작업 → 작업만 · 알림
        click_node(page, ids["s_hold"])
        n, inp = press(page, w, "Alt+KeyQ", 1.5)
        check("B 보류 설문만 Alt+Q → 안 보냄 · «보류 설문» 알림", n == 0 and "보류 설문" in toasts(page), toasts(page)[-120:])
        # 같은 화면의 검증 노드 v1(t1 의 검증)을 Ctrl+클릭으로 더함 — t1 은 이 섹션 화면에 안 보임
        click_node(page, ids["s_hold"])
        click_node(page, "v1", ctrl=True)
        n, inp = press(page, w, "Alt+KeyQ")
        check("B 보류 설문 + 검증 Alt+Q → 검증만 보냄 · 보류 설문 빠짐 · 알림", n == 1 and ids["s_hold"] not in last_msg(w) and "(v1) 확인해 줘" in last_msg(w)
              and "보류 설문" in toasts(page), (last_msg(w)[:160], toasts(page)[-80:]))

        # 결함 6 — 이미 반영한 설문 Alt+Q → 다시 시작 안 함 · 알림
        click_node(page, ids["s_acked"])
        n, inp = press(page, w, "Alt+KeyQ", 1.5)
        check("R9 이미 반영한 설문 Alt+Q → 안 보냄 · «이미 반영한 설문» 알림", n == 0 and "이미 반영한 설문" in toasts(page), toasts(page)[-120:])

        # 결정 C — 그래프에서 고른 뒤 코드 보기에서 Alt+Q → 마지막 그래프 선택을 보내지 않음
        click_node(page, "t1")
        page.evaluate("window.devview.showView('code')")
        page.wait_for_timeout(400)
        n, inp = press(page, w, "Alt+KeyQ", 1.5)
        check("C 코드 보기 Alt+Q → 안 보냄 · «그래프 보기에서» 알림", n == 0 and "그래프 보기에서" in toasts(page), toasts(page)[-120:])
        # 예비 키 — Alt+[ · ] 즉시 · Alt+; · ' 입력창
        page.evaluate("window.devview.showView('graph')")
        page.wait_for_timeout(400)
        click_node(page, "t1")
        n, inp = press(page, w, "Alt+BracketLeft")
        check("예비 Alt+[ → MAIN 바로 전송(Alt+Q 와 같음)", n == 1 and not inp and "(t1)" in last_msg(w), (n, inp, last_msg(w)[:120]))
        n, inp = press(page, w, "Alt+BracketRight", 1.5)
        check("예비 Alt+] → 2ND 마법봉(작업 노드는 입력창)", n == 0 and inp, (n, inp))
        cancel(page)
        n, inp = press(page, w, "Alt+Semicolon", 1.5)
        check("예비 Alt+; → MAIN 입력창", n == 0 and inp, (n, inp))
        cancel(page)
        n, inp = press(page, w, "Alt+Quote", 1.5)
        check("예비 Alt+' → 2ND 입력창", n == 0 and inp, (n, inp))
        cancel(page)
        check("화면 오류(pageerror) 없음", not errs, errs[:3])
        br.close()


# ======= 책 — 결함 2 · 3 =======
def test_book():
    from playwright.sync_api import sync_playwright
    name = "wrbook"
    tmp = Path(tempfile.mkdtemp(prefix="wand_real_book_"))
    root = tmp / "proj"
    book = root / "bookkit" / "books" / name
    shutil.copytree(tm.BK / "template", book, ignore=shutil.ignore_patterns("dist", "__pycache__"))
    meta = book / "content" / "meta.py"
    meta.write_text(meta.read_text(encoding="utf-8").replace('"doc": "",', f'"doc": "{name}",', 1), encoding="utf-8")
    (book / "contracts").mkdir(exist_ok=True)
    for n in ("facts", "reqs", "steps"):
        shutil.copy(tm.BK / "contracts" / "example" / f"{n}.json", book / "contracts" / f"{n}.json")
    shutil.copy(tm.BK / "notes.py", root / "bookkit" / "notes.py")
    r = subprocess.run([sys.executable, str(tm.BK / "engine" / "build_book.py"), str(book), "--stage", "1"], capture_output=True, text=True, encoding="utf-8")
    check("책 — 시험 책 빌드", r.returncode == 0, r.stderr[-200:])
    hub = root / ".codex-hub"
    (hub / "sessions").mkdir(parents=True)
    for nick in ("main", "2nd"):
        (hub / "sessions" / f"{nick}.json").write_text(json.dumps({"nick": nick, "thread": f"019a-{nick}", "registered_at": "2026-11-05 00:00:00"}),
                                                     encoding="utf-8")
    log = tmp / "queue.jsonl"
    fake = tmp / "fake_codex.py"
    fake.write_text("import json, os, sys\nopen(os.environ['FAKE_CODEX_LOG'], 'a', encoding='utf-8').write(json.dumps(sys.argv[1:], ensure_ascii=False) + '\\n')\n"
                    "print('Queued message m-1.')\n", encoding="utf-8")
    home = tmp / "home"
    home.mkdir()
    port = tm.free_port2()
    env = dict(os.environ, DEVVIEW_NO_VAULT="1", CODEX_HOME=str(tmp / "codex"), DEVVIEW_CODEX=str(fake), FAKE_CODEX_LOG=str(log),
               HOME=str(home), USERPROFILE=str(home), PYTHONUTF8="1")
    dv = subprocess.Popen([sys.executable, str(th.DEVVIEW), str(root), "--host", "127.0.0.1", "--port", str(port)],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
    q = lambda: [json.loads(x) for x in log.read_text(encoding="utf-8").splitlines()] if log.is_file() else []  # noqa: E731
    try:
        base = f"http://127.0.0.1:{port}"
        th.wait_for(lambda: urllib.request.urlopen(base + "/api/info", timeout=1).read(), 20)
        with sync_playwright() as pw:
            br = pw.chromium.launch(headless=True)
            page = br.new_page(viewport={"width": 1600, "height": 1000})
            page.goto(base + "/")
            page.wait_for_selector("html[data-ready='1']", timeout=30000)
            page.evaluate("window.devview.showView('book')")
            bf = lambda: page.frame(url=lambda u: f"/{name}/dist/" in u)  # noqa: E731
            ok = pw_wait(page, lambda: bf() is not None and bf().evaluate("!!(window.__book && window.__book.ready)"), 60)
            check("책 — Book 보기에 시험 책", ok)
            if not ok:
                br.close()
                return
            fr = bf()

            # 결함 3 — 스티커를 안 고르고 Alt+R → 노드 · 스티커 없이 지시 글만 2ND(실패 아님)
            page.evaluate("document.activeElement && document.activeElement.blur()")
            page.keyboard.press("Alt+KeyR")
            shown = pw_wait(page, lambda: page.is_visible("#hub .dv-hub-input"), 3)
            head = page.inner_text("#hub .dv-hub-input-head") if shown else ""
            page.keyboard.type("책 전체 요약해 줘")
            n0 = len(q())
            page.click('#hub .dv-hub-acts [data-act="send"]')
            sent = pw_wait(page, lambda: len(q()) == n0 + 1, 4)
            m = q()[-1] if sent else []
            rid = m[-1].rsplit(" ", 1)[-1] if m else ""
            t = json.loads((hub / "requests" / f"{rid}.json").read_text(encoding="utf-8")).get("target", {}) if sent else {}
            check("R11 책 · 스티커 안 고름 Alt+R → «대상 없음» · 지시 글만 2ND(답 자리 chat · 실패 알림 없음)",
                  shown and "대상 없음" in head and sent and m[2] == "019a-2nd" and "지시: 책 전체 요약해 줘" in m[-1] and t.get("kind") == "chat",
                  (head, m[-1:], t, page.inner_text("#toasts")[-100:]))

            # 결함 2 — 새 스티커 + Alt+R ✈ → 스티커 마법봉 길(magic_rid 남음) → 뒤이은 Alt+W 는 409 «이미 보냄»
            blk = "s3-Q1"
            pi = fr.evaluate(f"+document.querySelector('#book [data-id=\"{blk}\"]').closest('.page').dataset.pi")
            fr.evaluate(f"window.__book.go({pi})")
            page.wait_for_timeout(400)
            fr.click("#bMemo")
            fr.locator(f'#book [data-id="{blk}"]').click(position={"x": 40, "y": 10})
            note = fr.locator(".note").last
            note.locator("textarea").fill("이 칸 기준은?")
            note.locator(".nf button:not(.nw)").click()
            fr.wait_for_selector(".note .nt:has-text('접수')", timeout=5000)
            fr.locator(".note").last.locator(".nb").click()
            nid = json.loads((book / "notes.json").read_text(encoding="utf-8"))[0]["id"]
            fr.locator(".note").last.locator(".nb").press("Alt+KeyR")
            pw_wait(page, lambda: page.is_visible("#hub .dv-hub-input"), 3)
            page.fill("#hub .dv-hub-input textarea", "예시도 들어 줘")
            n0 = len(q())
            page.click('#hub .dv-hub-acts [data-act="send"]')
            sent = pw_wait(page, lambda: len(q()) == n0 + 1, 4)
            m = q()[-1] if sent else []
            nt = json.loads((book / "notes.json").read_text(encoding="utf-8"))[0]
            check("R12 새 스티커 Alt+R ✈ → 스티커 질문 + 지시 · notes.json magic_rid(답 대기 표시 근거)",
                  sent and "스티커 질문: 이 칸 기준은?" in m[-1] and "지시: 예시도 들어 줘" in m[-1] and nt.get("magic_rid") == m[-1].rsplit(" ", 1)[-1],
                  (m[-1:], nt.get("magic_rid")))
            fr.locator(".note").last.locator(".nb").click()
            n0 = len(q())
            fr.locator(".note").last.locator(".nb").press("Alt+KeyW")
            page.wait_for_timeout(1500)
            check("R12 뒤이은 Alt+W → 중복 전송 없음(«이미 보냄»)", len(q()) == n0 and "이미 보냄" in fr.locator(".note").last.inner_text(),
                  (len(q()) - n0, fr.locator(".note").last.inner_text()[-60:]))
            br.close()
    finally:
        dv.terminate()
        try:
            dv.wait(timeout=5)
        except subprocess.TimeoutExpired:
            dv.kill()
        shutil.rmtree(tmp, ignore_errors=True)


# ======= 설문 폼 — 결함 5 =======
def test_survey_form():
    from playwright.sync_api import sync_playwright
    tmp = Path(tempfile.mkdtemp(prefix="wand_real_sv_"))
    try:
        (tmp / "devview").mkdir()
        for nm in ("codex_hub.py", "codex_sessions.py"):
            shutil.copyfile(tm.KIT / "devview" / nm, tmp / "devview" / nm)
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
        spec.write_text(json.dumps({"title": "빈 질문 시험", "questions": [{"id": "1", "question": "q1", "options": ["A", "B"]}]}, ensure_ascii=False),
                        encoding="utf-8")
        r = subprocess.run([sys.executable, str(tm.SURVEY_PY), "--dir", str(store), "new", str(spec), "--project", "시험", "--thread", "T-REG"],
                           capture_output=True, text=True, encoding="utf-8", env=env, timeout=30)
        info = json.loads(r.stdout)
        port = th.free_port()
        server = subprocess.Popen([sys.executable, str(tm.SURVEY_PY), "--dir", str(store), "serve", "--host", "127.0.0.1", "--port", str(port)],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
        try:
            base = f"http://127.0.0.1:{port}"
            th.wait_for(lambda: urllib.request.urlopen(base + "/api/state?probe=1", timeout=1).read(), 10)
            res_file = Path(info["file"]).with_suffix("").with_suffix(".result.json")
            with sync_playwright() as pw:
                br = pw.chromium.launch(headless=True)
                page = br.new_page()
                page.goto(base + info["path"])
                page.locator(".seg label", has_text="질문").first.click()
                page.locator("button.ok").click()
                shown = pw_wait(page, lambda: page.locator("#askErr").is_visible(), 3)
                text = page.locator("#askErr").inner_text() if shown else ""
                br.close()
            calls = out.read_text(encoding="utf-8").splitlines() if out.is_file() else []
            check("R13 설문 폼 «질문» + 메모 비움 → 제출 막힘 · 이유 표시 · 결과 파일 · 전송 없음",
                  shown and "질문 글(메모)이 비었음" in text and not res_file.exists() and not calls, (text, res_file.exists(), calls))
            data = urllib.parse.urlencode({"q1": "질문", "q1_memo": "", "_act": "submit"}).encode("utf-8")
            try:
                code = urllib.request.urlopen(urllib.request.Request(base + info["path"], data=data), timeout=20).status
            except urllib.error.HTTPError as e:
                code = e.code
            check("R13 서버도 빈 질문 제출 거부(400) · 결과 파일 없음", code == 400 and not res_file.exists(), code)
        finally:
            server.terminate()
            server.wait(timeout=10)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    tmp = Path(tempfile.mkdtemp(prefix="wand_real_"))
    proc = None
    try:
        w = th.make_world(tmp)
        ids = seed(w)
        proc, base = th.start(w)
        test_graph(w, base, ids)
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
