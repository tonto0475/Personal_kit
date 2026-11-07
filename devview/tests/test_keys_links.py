# -*- coding: utf-8 -*-
r"""md 링크 → 옆 칸 + 자리 옮기기 · 책 iframe 안 단축키(Alt+Q · W · B) · 책 «새로» 막대 시험(헤드리스)

    py -3 devview/tests/test_keys_links.py           → PASS / FAIL (playwright 없으면 SKIP)

- 임시 작업 폴더 · 가짜 codex(인자를 파일에 적음) · 빈 포트(페이지 서버 = +100) · 끝나면 그 프로세스만 끈다
- 단언 대상은 관측 결과: 보이는 칸 · 열린 파일 · 표에 표시된 행 · queue 인자 · 지금 보기 · 계산된 스타일
- 캡처 = tests/shots/book_new_bar.png · md_link_split.png
"""
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
KIT = HERE.parents[1]
BK = KIT / "bookkit"
NAME = "keystest"
SHOTS = HERE / "shots"


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# root: 작업 폴더
def make_docs(root):
    """md · csv · 코드 · 가짜 pdf 시험 문서"""
    (root / "docs").mkdir(parents=True)
    (root / "data").mkdir()
    (root / "src").mkdir()
    (root / "docs" / "a.md").write_text(
        "# 문서 A\n\n본문\n\n[표](../data/t.csv#row=20&col=이름)\n\n[제목](b.md#둘째)\n\n[줄](../src/x.py#L5)\n\n[쪽](../data/p.pdf#page=3)\n\n끝\n", encoding="utf-8")
    (root / "docs" / "b.md").write_text("# 첫째\n\n" + "줄\n\n" * 120 + "## 둘째\n\n여기\n", encoding="utf-8")
    (root / "data" / "t.csv").write_text("번호,이름,값\n" + "".join(f"{i},칸{i},{i * 2}\n" for i in range(1, 41)), encoding="utf-8")
    (root / "data" / "u.csv").write_text("번호,이름\n1,가\n", encoding="utf-8")
    (root / "data" / "v.csv").write_text("번호\n1\n2\n3\n", encoding="utf-8")
    (root / "src" / "x.py").write_text("".join(f"a{i} = {i}\n" for i in range(1, 11)), encoding="utf-8")
    (root / "data" / "p.pdf").write_bytes(b"%PDF-1.4\n%%EOF\n")


# root: 작업 폴더
def make_book(root):
    """시험 책 — 1차판(reqs 만) → 2차판(«새로» 블록이 생김)"""
    book = root / "bookkit" / "books" / NAME
    shutil.copytree(BK / "template", book, ignore=shutil.ignore_patterns("dist", "__pycache__"))
    meta = book / "content" / "meta.py"
    meta.write_text(meta.read_text(encoding="utf-8").replace('"doc": "",', f'"doc": "{NAME}",', 1), encoding="utf-8")
    con = book / "contracts"
    con.mkdir(exist_ok=True)
    shutil.copy(BK / "contracts" / "example" / "reqs.json", con / "reqs.json")
    shutil.copy(BK / "notes.py", root / "bookkit" / "notes.py")
    # stage: 판 번호
    for stage in ("1", "2"):
        r = subprocess.run([sys.executable, str(BK / "engine" / "build_book.py"), str(book), "--stage", stage], capture_output=True, text=True, encoding="utf-8")
        assert r.returncode == 0, r.stdout[-400:] + r.stderr[-400:]
        for n in ("facts", "steps"):
            shutil.copy(BK / "contracts" / "example" / f"{n}.json", con / f"{n}.json")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("SKIP — playwright 없음(PASS 아님)")
        return 0
    fails = []

    # 단언 하나
    def check(ok, what, detail=""):
        print(("  ok   " if ok else "  FAIL ") + what + (f" | {str(detail)[:200]}" if detail and not ok else ""), flush=True)
        if not ok:
            fails.append(what)

    # 조건이 참이 될 때까지 — 실패 판정은 호출한 쪽 단언이 한다
    def wait_for(fn, timeout=6.0):
        end = time.time() + timeout
        while time.time() < end:
            if fn():
                return True
            time.sleep(0.1)
        return bool(fn())

    tmp = Path(tempfile.mkdtemp(prefix="keys_links_"))
    root = tmp / "proj"
    root.mkdir()
    make_docs(root)
    make_book(root)
    # 허브 등록 · 가짜 codex
    hub = root / ".codex-hub" / "sessions"
    hub.mkdir(parents=True)
    (hub / "2nd.json").write_text(json.dumps({"nick": "2nd", "thread": "019a-2nd", "registered_at": "2026-11-05 00:00:00"}), encoding="utf-8")
    (hub / "main.json").write_text(json.dumps({"nick": "main", "thread": "019a-main", "registered_at": "2026-11-05 00:00:00"}), encoding="utf-8")
    log = tmp / "queue.jsonl"
    fake = tmp / "fake_codex.py"
    fake.write_text("import json, os, sys\nopen(os.environ['FAKE_CODEX_LOG'], 'a', encoding='utf-8').write(json.dumps(sys.argv[1:], ensure_ascii=False) + chr(10))\n"
                    "print('Queued message m-1.')\n", encoding="utf-8")
    home = tmp / "home"
    home.mkdir()
    port = free_port()
    env = dict(os.environ, DEVVIEW_NO_VAULT="1", CODEX_HOME=str(tmp / "codex"), DEVVIEW_CODEX=str(fake), FAKE_CODEX_LOG=str(log),
               HOME=str(home), USERPROFILE=str(home), PYTHONUTF8="1")
    dv = subprocess.Popen([sys.executable, str(HERE.parent / "devview.py"), str(root), "--kit", str(root), "--host", "127.0.0.1", "--port", str(port)],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)

    # 가짜 codex 가 받은 인자 목록
    def queued():
        return [json.loads(x) for x in log.read_text(encoding="utf-8").splitlines()] if log.is_file() else []

    try:
        base = f"http://127.0.0.1:{port}"
        for _ in range(100):
            try:
                urllib.request.urlopen(base + "/", timeout=1).read(10)
                break
            except OSError:
                time.sleep(0.2)
        with sync_playwright() as pw:
            br = pw.chromium.launch(headless=True)
            pg = br.new_page(viewport={"width": 1600, "height": 1000})
            errs = []
            pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto(base + "/")
            pg.wait_for_selector("html[data-ready='1']", timeout=30000)
            pg.evaluate("window.devview.showView('code')")

            print("md 링크 → 옆 칸 + 자리")
            pg.evaluate("window.devview.openFile('docs/a.md')")
            pg.wait_for_selector("[data-href]", timeout=8000)
            # 보이는 칸 수 · 지금 파일
            panes = lambda: pg.evaluate("[...document.querySelectorAll('#panes > *')].filter((e) => !e.hidden && e.offsetWidth > 100).length")  # noqa: E731
            act = lambda: pg.evaluate("window.devview.activePath()")  # noqa: E731

            # href 로 시작하는 링크 Ctrl+클릭
            def link(start):
                pg.locator(f'.dv-md:visible [data-href^="{start}"]').first.click(modifiers=["Control"])

            check(panes() == 1, "시작 = 한 칸", panes())
            link("../data/t.csv")
            check(wait_for(lambda: act() == "data/t.csv") and panes() == 2, "CSV 링크 → 오른쪽 칸이 펼쳐져 열림", (act(), panes()))
            check(pg.locator(".dv-md:visible").count() == 1, "md 는 왼쪽에 그대로 보인다")
            row = pg.locator(".dv-table tr.is-hit td").all_inner_texts() if wait_for(lambda: pg.locator(".dv-table tr.is-hit").count() == 1) else []
            check(row[:3] == ["20", "20", "칸20"], "CSV #row=20 → 표의 20행 표시", row)
            cell = pg.locator(".dv-table td.is-hit")
            check(cell.count() == 1 and cell.inner_text() == "칸20", "CSV col=이름 → 그 칸 표시(열 이름)")
            check(pg.evaluate("(() => { const r = document.querySelector('.dv-table tr.is-hit').getBoundingClientRect(), w = document.querySelector('.dv-table-wrap').getBoundingClientRect();"
                              " return r.top >= w.top && r.bottom <= w.bottom; })()"), "그 행이 화면 안")
            SHOTS.mkdir(exist_ok=True)
            pg.screenshot(path=str(SHOTS / "md_link_split.png"))
            link("b.md")
            check(wait_for(lambda: act() == "docs/b.md") and panes() == 2, "MD 링크 → 있는 오른쪽 칸을 다시 씀(칸 2개)", (act(), panes()))
            check(wait_for(lambda: pg.locator(".cm-content:visible").get_by_text("여기", exact=True).count() >= 1
                           and pg.evaluate("[...document.querySelectorAll('.dv-md:not([hidden]) .cm-scroller')].some((e) => e.scrollTop > 200)")),
                  "MD #제목 → 그 제목까지 내려감")
            link("../src/x.py")
            check(wait_for(lambda: act() == "src/x.py") and panes() == 2, "코드 링크 → 오른쪽 칸")
            check(wait_for(lambda: pg.evaluate("window.devview.editor().getPosition().lineNumber") == 5), "#L5 → 5줄", pg.evaluate("window.devview.editor().getPosition()"))
            link("../data/p.pdf")
            check(wait_for(lambda: act() == "data/p.pdf"), "PDF 링크 → 오른쪽 칸")
            check(wait_for(lambda: (pg.evaluate("document.querySelector('iframe.dv-pdf')?.src") or "").endswith("#page=3")), "PDF #page=3 → 보기 주소에 쪽 번호")

            print("CSV 기본 표")
            pg.evaluate("window.devview.openFile('data/u.csv')")
            check(wait_for(lambda: act() == "data/u.csv" and pg.locator(".dv-table:visible").count() == 1), "CSV 를 그냥 열면 표로 뜬다")
            tb = pg.locator('[data-cb="table"]:visible')
            check(tb.count() == 1 and tb.inner_text().strip() == "원문 보기", "단추 = 원문 보기(표가 켜진 상태)")
            tb.click()
            check(wait_for(lambda: pg.locator(".dv-table:visible").count() == 0), "원문 보기 → 원문으로")
            pg.evaluate("window.devview.openFile('data/v.csv', { line: 3 })")
            check(wait_for(lambda: act() == "data/v.csv" and pg.evaluate("window.devview.editor().getPosition().lineNumber") == 3)
                  and pg.locator(".dv-table:visible").count() == 0, "줄을 찍어 열면 원문 그 줄")

            print("책 iframe 안 단축키")
            pg.keyboard.press("Alt+KeyB")
            check(wait_for(lambda: pg.evaluate("window.devview.view()") == "book"), "Alt+B → Book 보기")
            # sync 판은 time.sleep 중 프레임 이벤트를 처리하지 않아 wait_for_timeout 으로 기다린다
            fr = None
            for _ in range(300):
                fr = pg.frame(url=lambda u: NAME in u)
                if fr:
                    break
                pg.wait_for_timeout(100)
            check(fr is not None, "책 iframe 읽힘", [f.url for f in pg.frames])
            fr.wait_for_function("window.__book && window.__book.ready", timeout=60000)

            # «새로» 표식 — 글자표 없음 · 왼쪽 막대
            new = fr.evaluate("(() => { const b = [...document.querySelectorAll('#book .blk[data-new]')]; const s = b[0] && getComputedStyle(b[0]);"
                              " return { n: b.length, tag: b[0] && getComputedStyle(b[0], '::before').content, bar: s && s.backgroundImage }; })()")
            check(new["n"] > 0 and new["tag"] == "none" and "linear-gradient" in (new["bar"] or ""), "«새로» 블록 = 글자표 없음 · 왼쪽 막대", new)
            pi = fr.evaluate("+document.querySelector('#book .blk[data-new]').closest('.page').dataset.pi")
            fr.evaluate(f"window.__book.go({pi})")
            pg.wait_for_timeout(500)
            pg.screenshot(path=str(SHOTS / "book_new_bar.png"))

            # 책 안 포커스 — 메모 없음
            toast = lambda: fr.evaluate("document.getElementById('toast').textContent")  # noqa: E731
            fr.evaluate("window.focus(); document.body.focus()")
            pg.keyboard.press("Alt+KeyW")
            check(wait_for(lambda: toast() == "메모를 고르지 않음"), "고른 메모 없이 Alt+W → 알림 · 보내지 않음", toast())
            check(not queued(), "queue 비어 있음", queued())
            # 메모 붙이기
            blk = fr.evaluate("document.querySelector('#book .page.on .blk, #book .page .blk').dataset.id")
            bpi = fr.evaluate(f"+document.querySelector('#book [data-id=\"{blk}\"]').closest('.page').dataset.pi")
            fr.evaluate(f"window.__book.go({bpi})")
            pg.wait_for_timeout(300)
            fr.locator("#bMemo").click()
            fr.locator(f'#book [data-id="{blk}"]').click(position={"x": 40, "y": 10})
            note = fr.locator(".note").last
            note.locator("textarea").fill("이 칸 뜻?")
            pg.keyboard.press("Alt+KeyW")
            check(wait_for(lambda: toast() == "접수 뒤 보낼 수 있음"), "접수 전 메모에서 Alt+W → 알림", toast())
            check("W" not in note.locator("textarea").input_value() and "w" not in note.locator("textarea").input_value(), "입력 칸에 글자가 안 들어감")
            note.locator(".nf button:not(.nw)").click()
            fr.wait_for_selector(".note .nt:has-text('접수')", timeout=5000)
            fr.locator(".note").last.locator(".nh .nt").click()
            pg.keyboard.press("Alt+KeyW")
            ok = wait_for(lambda: len(queued()) == 1 and "$2nd-magic" in queued()[-1][-1])
            check(ok and "이 칸 뜻?" in queued()[-1][-1], "메모를 고르고 Alt+W → 🪄 와 같이 2ND queue", queued()[-1:])
            # 책 안 포커스에서 보기 전환
            pg.keyboard.press("Alt+KeyB")
            check(wait_for(lambda: pg.evaluate("window.devview.view()") == "code"), "책 안 Alt+B → 코드", pg.evaluate("window.devview.view()"))
            pg.keyboard.press("Alt+KeyB")
            check(wait_for(lambda: pg.evaluate("window.devview.view()") == "book"), "devview 문서 Alt+B → Book")
            # 포커스가 devview 문서에 있어도 책의 고른 메모로
            pg.evaluate("document.activeElement.blur(); window.focus()")
            # 판정 = 페이지 서버 응답 — 답 대기 폴링이 메모를 다시 그려 글자 표시는 금방 사라진다
            with pg.expect_response(lambda r: r.url.endswith("/magic"), timeout=8000) as res:
                pg.keyboard.press("Alt+KeyW")
            check(res.value.status == 409, "포커스가 책 밖이어도 Alt+W → 책의 고른 메모로 요청(이미 보냄 409)", res.value.status)
            # 책 안 Alt+Q — MAIN 마법봉은 그래프 보기에서만(2026-11-05 유저 결정) → 알림 · 보내지 않음
            n0 = len(queued())
            fr.locator(".note").last.locator(".nh .nt").click()
            pg.keyboard.press("Alt+KeyQ")
            check(wait_for(lambda: "그래프 보기에서" in pg.inner_text("#toasts")) and len(queued()) == n0 and pg.evaluate("window.devview.view()") == "book",
                  "고른 노드 없이 책 안 Alt+Q → 알림 · 보내지 않음 · 보기 그대로", (queued()[n0:], pg.evaluate("window.devview.view()")))
            # 그래프에서 노드를 고르고 책으로 돌아옴
            pg.evaluate("window.devview.showView('graph')")
            gf = None
            for _ in range(300):
                gf = pg.frame(url=lambda u: "/ft/" in u)
                if gf and gf.locator(".screens button").count() > 0:
                    break
                pg.wait_for_timeout(100)
            gf.locator('.screens button[data-screen="1"]').click()
            gf.wait_for_selector('.react-flow__node[data-id="s1-t1"]', timeout=8000)
            gf.evaluate("window.__flowtree.center('s1-t1', 1.2)")
            pg.wait_for_timeout(400)
            gf.locator('.react-flow__node[data-id="s1-t1"]').click(position={"x": 30, "y": 12})
            check(wait_for(lambda: [n["id"] for n in pg.evaluate("window.devview.flowSelection().nodes")] == ["s1-t1"]), "그래프에서 노드 고름", pg.evaluate("window.devview.flowSelection()"))
            pg.evaluate("window.devview.showView('book')")
            fr.locator(".note").last.locator(".nh .nt").click()
            pg.keyboard.press("Alt+KeyQ")
            # 그래프에서 고른 노드가 있어도 책 안 Alt+Q 는 보내지 않음(마지막 그래프 선택을 다른 보기에서 보내지 않음)
            pg.wait_for_timeout(1200)
            check(len(queued()) == n0 and "그래프 보기에서" in pg.inner_text("#toasts"),
                  "그래프 선택이 남아 있어도 책 안 Alt+Q → 보내지 않음 · 알림", queued()[n0:])
            check(pg.evaluate("window.devview.view()") == "book", "책 안 Alt+Q → 보기 그대로", pg.evaluate("window.devview.view()"))
            check(not errs, "페이지 오류 없음", errs[:3])
            br.close()
    finally:
        dv.terminate()
        dv.wait(timeout=10)
        shutil.rmtree(tmp, ignore_errors=True)
    print("PASS" if not fails else f"FAIL — {len(fails)}개")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
