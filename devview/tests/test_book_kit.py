"""devview Book 탭 · 키트 폴더(KIT) 시험 — 임시 폴더 + 시험 서버(빈 포트 · 페이지 서버 +100) + 헤드리스 크롬

    py -3 tests/test_book_kit.py              API + 화면 · 결과 PASS/FAIL · 캡처 tests/shots/book_*.png
    py -3 tests/test_book_kit.py --api-only   API 만(브라우저 없이)
    CC_HEADED=1 py -3 tests/test_book_kit.py  창을 띄워 눈으로 보기

세계 1(옛 방식 — 작업 폴더 = 키트): 01_oht = versions.json 판 2개(v1 · v2 + 최신 복사본) · 02_shift = 판 목록 없는 옛 빌드 html 1
         · 시험용 «_» 책 · _partial · book_example(벤치마크)은 목록에 안 나온다 — 줄 = 판 하나 · 최신이 위 · 그룹 없음
세계 2(과제 루트 + kit/): README · uploads · kit/AGENTS.md · kit/docs/hand_off.md · kit/bookkit · kit/.codex-hub
세계 3(책 없음): «만든 책 없음» 한 줄
실제 ~/.devview · 8701 무관(서버의 HOME · USERPROFILE 을 임시 폴더로)
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
sys.path.insert(0, str(HERE))
import test_hub as th  # noqa: E402 — check · wait_for · http · RESULTS 를 같이 씀

DEVVIEW = HERE.parent / "devview.py"
SHOTS = HERE / "shots"
HEADED = os.environ.get("CC_HEADED") == "1"
check, wait_for, http = th.check, th.wait_for, th.http


# 책 html 하나 — 제목 글자로 iframe 안 내용을 확인
# p: 경로 / title: 제목
# 책 안 «노트 목록» 단추(#bHome) — bookkit 책 book.js 와 같은 동작(iframe 안이면 부모에 {book:'toggle-list'})
HOME_BTN = ("<a id='bHome' href='/no-home' title='노트 목록'>노트 목록</a><script>(()=>{const h=document.getElementById('bHome');"
            "if(window.parent===window)return;h.title='책 목록 보이기 · 숨기기';h.addEventListener('click',e=>{e.preventDefault();"
            "window.parent.postMessage({book:'toggle-list'},'*');});})();</script>")


def book_html(p, title):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"<!doctype html><html><head><meta charset='utf-8'><title>{title}</title></head>"
                 f"<body style='font:20px sans-serif;padding:30px'><h1 id='bt'>{title}</h1><p>시험 책 본문</p>{HOME_BTN}</body></html>", encoding="utf-8")


# 북키트 재료 — kit: 키트 폴더 / 반환 없음
#   01_oht: 판 목록(versions.json) v1 1차판(20분 전) · v2 2차판(1분 전) / 02_shift: 판 목록 없음 · html 1(10분 전)
def make_books(kit):
    bk = kit / "bookkit"
    dist = bk / "books" / "01_oht" / "dist"
    now = time.time()
    book_html(dist / "01_oht__v1_1차판.html", "OHT 책 1차판")
    book_html(dist / "01_oht__v2_2차판.html", "OHT 책 2차판")
    book_html(dist / "01_oht.html", "OHT 책 2차판")  # 최신 복사본 — 목록에 따로 나오지 않는다
    book_html(dist / "_partial" / "01_oht__s3.html", "부분")
    at = lambda t: time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(t))  # noqa: E731
    (dist / "versions.json").write_text(json.dumps({"doc": "01_oht", "title": "OHT 반송", "latest": "01_oht__v2_2차판.html", "versions": [
        {"n": 1, "name": "1차판", "label": "", "stage": 1, "file": "01_oht__v1_1차판.html", "at": at(now - 1200), "blocks": 90, "blanks": 0, "new": None, "base": None},
        {"n": 2, "name": "2차판", "label": "", "stage": 2, "file": "01_oht__v2_2차판.html", "at": at(now - 60), "blocks": 183, "blanks": 0, "new": 12, "base": 1},
    ]}, ensure_ascii=False), encoding="utf-8")
    book_html(bk / "books" / "02_shift" / "dist" / "02_shift_2차판.html", "근무 책 2차판")
    os.utime(bk / "books" / "02_shift" / "dist" / "02_shift_2차판.html", (now - 600, now - 600))
    book_html(bk / "books" / "_selftest" / "dist" / "_selftest.html", "시험용")
    book_html(bk / "book_example" / "task09" / "task09_kit.html", "벤치 9")


# 빈 포트 — 페이지 서버(+100)도 비어 있는 것
def free_port():
    import random
    for _ in range(200):
        p = random.randint(20000, 40000)
        try:
            with socket.socket() as a, socket.socket() as b:
                a.bind(("127.0.0.1", p))
                b.bind(("127.0.0.1", p + 100))
            return p
        except OSError:
            continue
    raise RuntimeError("빈 포트 없음")


# 시험 서버 — (프로세스, 주소, 포트)
# root: 작업 폴더 / base: 임시 폴더 / args: 덧붙일 인자
def start(root, base, args=()):
    port = free_port()
    home = base / "home"
    home.mkdir(exist_ok=True)
    env = dict(os.environ, DEVVIEW_NO_VAULT="1", HOME=str(home), USERPROFILE=str(home), PYTHONUTF8="1",
               CODEX_HOME=str(base / "codex"), CLAUDE_CONFIG_DIR=str(base / "claude"))
    proc = subprocess.Popen([sys.executable, str(DEVVIEW), str(root), "--host", "127.0.0.1", "--port", str(port), "--start-view", "code", *args],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env)
    url = f"http://127.0.0.1:{port}"
    for _ in range(100):
        if proc.poll() is not None:
            raise RuntimeError("서버 기동 실패: " + proc.stdout.read().decode("utf-8", "replace"))
        try:
            urllib.request.urlopen(url + "/api/info", timeout=1).read()
            return proc, url, port
        except OSError:
            time.sleep(0.1)
    proc.kill()
    raise RuntimeError("서버 응답 없음")


def stop(proc):
    proc.terminate()
    try:
        proc.wait(5)
    except Exception:  # noqa: BLE001
        proc.kill()


# ======= 세계 1 — 작업 폴더 = 키트(옛 방식) · Book 목록 =======
# 판 줄 경로(작업 폴더 기준)
V2 = "bookkit/books/01_oht/dist/01_oht__v2_2차판.html"
V1 = "bookkit/books/01_oht/dist/01_oht__v1_1차판.html"
SHIFT = "bookkit/books/02_shift/dist/02_shift_2차판.html"


def test_books_api(url):
    code, d = http(url + "/api/books")
    books = d.get("books") or []
    check("Book 목록 — 판 하나가 한 줄 · 최신이 위(OHT v2 → 근무 → OHT v1) · 최신 복사본 · «_» · _partial 뺌",
          code == 200 and [b["path"] for b in books] == [V2, SHIFT, V1], [b.get("path") for b in books])
    check("판 줄 — 제목 «<책 제목> · v<N> · <판 이름>» · 부가 줄 «시각 · 블록 · 새로»",
          len(books) == 3 and books[0]["title"] == "OHT 반송 · v2 · 2차판" and books[0]["sub"].endswith("· 블록 183 · 새로 12")
          and books[2]["title"] == "OHT 반송 · v1 · 1차판" and "새로" not in books[2]["sub"], [(b.get("title"), b.get("sub")) for b in books])
    check("책마다 마지막 판만 latest(OHT v2 · 근무) · 앞 판(OHT v1)은 아님", [b.get("latest") for b in books] == [True, True, False],
          [b.get("latest") for b in books])
    check("판 목록 없는 책 — html 하나가 한 줄 · 판 표시(파일 이름의 2차판)",
          len(books) == 3 and books[1]["edition"] == "2차판" and books[1]["title"] == "02_shift · 02_shift_2차판", books[1:2])
    check("벤치마크 묶음 없음(응답에 examples 없음)", "examples" not in d, list(d))
    code, d = http(url + "/api/info")
    check("info.kit — 작업 폴더 = 키트면 빈 글자", code == 200 and d.get("kit") == "", d.get("kit"))


def test_books_ui(url, port):
    from playwright.sync_api import sync_playwright
    SHOTS.mkdir(exist_ok=True)
    with sync_playwright() as pw:
        try:
            br = pw.chromium.launch(headless=not HEADED)
        except Exception:  # noqa: BLE001
            br = pw.chromium.launch(channel="chrome", headless=not HEADED)
        ctx = br.new_context(viewport={"width": 1500, "height": 900})
        page = ctx.new_page()
        errs = []
        page.on("pageerror", lambda e: errs.append(str(e)))
        page.goto(url + "/")
        page.wait_for_selector("html[data-ready='1']", timeout=30000)
        tab = page.locator("#bookTab")
        check("Book 탭 — 위쪽 탭 줄 · 툴팁 «Book (Alt+B)»", tab.is_visible() and tab.get_attribute("title") == "Book (Alt+B)"
              and tab.inner_text().strip() == "Book", tab.get_attribute("title"))
        page.keyboard.press("Alt+b")
        ok = wait_for(lambda: page.locator("#bookView").is_visible() and page.locator(".dv-book-item").count() == 3, 8)
        check("Alt+B → Book 보기 · 목록 3줄(판 하나 = 한 줄)", ok, page.locator(".dv-book-item").count())
        check("그룹 머리 없음(벤치마크 묶음 뺌)", page.locator(".dv-book-group").count() == 0)
        check("Book 보기 — 허브 숨김(책 목록을 가리지 않게)", not page.locator("#hub").is_visible())
        items = page.locator(".dv-book-item")
        check("목록 순서 = 최신이 위", [items.nth(i).get_attribute("data-book") for i in range(3)] == [V2, SHIFT, V1])
        first = items.nth(0)
        check("줄 = 제목 + 회색 부가 줄(설문 목록 모양)", first.locator(".dv-book-name").inner_text() == "OHT 반송 · v2 · 2차판"
              and "블록 183 · 새로 12" in first.locator(".dv-book-sub").inner_text()
              and first.locator(".dv-book-sub").evaluate("e => getComputedStyle(e).color") == "rgb(134, 138, 145)",
              first.inner_text())
        cls = [items.nth(i).get_attribute("class") for i in range(3)]
        check("마지막 판 = 파랑(pend) · 앞 판 = 회색(done) · 맨 위 줄 고름(is-on)",
              "pend" in cls[0] and "is-on" in cls[0] and "pend" in cls[1] and "done" in cls[2], cls)
        check("앞 판 줄 배경 = 설문 완료 회색(#2b2d31)", items.nth(2).evaluate("e => getComputedStyle(e).backgroundColor") == "rgb(43, 45, 49)")
        want = f"http://127.0.0.1:{port}/pg/bookkit/books/01_oht/dist/01_oht__v2_2%EC%B0%A8%ED%8C%90.html"
        src = page.locator(".dv-book-frame").get_attribute("src")
        check("iframe 주소 — 같은 주소 /pg/ 의 맨 위 판(2026-11-05 — 다른 포트는 대회 브라우저에서 막힘)", src == want, src)
        ok = wait_for(lambda: page.frame(url=lambda u: "01_oht__v2" in u) is not None
                      and page.frame(url=lambda u: "01_oht__v2" in u).locator("#bt").count() == 1, 8)
        check("iframe 안 책이 실제로 열림(제목 글자)", ok and page.frame(url=lambda u: "01_oht__v2" in u).locator("#bt").inner_text() == "OHT 책 2차판")
        page.locator(f'.dv-book-item[data-book="{V1}"]').click()
        ok = wait_for(lambda: "01_oht__v1" in (page.locator(".dv-book-frame").get_attribute("src") or ""), 5)
        check("앞 판 줄 클릭 → 그 판 · 고른 줄 강조(하나만)", ok and "is-on" in page.locator(f'.dv-book-item[data-book="{V1}"]').get_attribute("class")
              and page.locator(".dv-book-item.is-on").count() == 1)
        # frame_locator — iframe 주소가 바뀌는 중에도 스스로 기다린다(page.frame 목록은 sleep 중 갱신이 늦어 흔들렸다)
        bt = page.frame_locator(".dv-book-frame").locator("#bt", has_text="OHT 책 1차판")
        try:
            bt.wait_for(timeout=8000)
            ok = True
        except Exception:  # noqa: BLE001
            ok = False
        check("앞 판 html 이 그대로 열림", ok)
        time.sleep(0.5)
        page.screenshot(path=str(SHOTS / "book_tab.png"))
        with ctx.expect_page() as pop:
            page.locator(".dv-book-open").click()
        newp = pop.value
        check("«새 탭으로 열기» → 같은 주소 새 탭", "01_oht__v1" in newp.url, newp.url)
        newp.wait_for_load_state()
        check("iframe 밖(새 탭) — «노트 목록» 단추는 원래 링크 · 툴팁 그대로",
              newp.locator("#bHome").get_attribute("title") == "노트 목록", newp.locator("#bHome").get_attribute("title"))
        newp.close()
        # 책 안 «노트 목록» → 왼쪽 목록 자리째 숨김 ↔ 보임 · 새로고침 뒤에도 유지
        home = page.frame_locator(".dv-book-frame").locator("#bHome")
        check("iframe 안 — 툴팁 «책 목록 보이기 · 숨기기»", home.get_attribute("title") == "책 목록 보이기 · 숨기기", home.get_attribute("title"))
        w0 = page.locator(".dv-book-frame").bounding_box()["width"]
        home.click()
        ok = wait_for(lambda: not page.locator(".dv-book-side").is_visible(), 5)
        w1 = page.locator(".dv-book-frame").bounding_box()["width"]
        check("«노트 목록» 클릭 → 왼쪽 목록 사라짐 · 책이 그 자리만큼 넓어짐", ok and w1 >= w0 + 290, (w0, w1))
        check("iframe 주소 그대로(링크로 넘어가지 않음)", "01_oht__v1" in (page.locator(".dv-book-frame").get_attribute("src") or ""))
        time.sleep(0.5)
        page.screenshot(path=str(SHOTS / "book_tab_hidden.png"))
        home.click()
        check("다시 클릭 → 목록 보임", wait_for(lambda: page.locator(".dv-book-side").is_visible(), 5))
        home.click()
        wait_for(lambda: not page.locator(".dv-book-side").is_visible(), 5)
        time.sleep(1.2)  # 상태 저장(0.8초 묶음) 뒤 새로고침
        page.reload()
        page.wait_for_selector("html[data-ready='1']", timeout=30000)
        if not page.locator("#bookView").is_visible():
            page.keyboard.press("Alt+b")
        ok = wait_for(lambda: page.locator("#bookView").is_visible() and page.locator(".dv-book-frame").get_attribute("src"), 8)
        check("새로고침 뒤에도 숨김 유지", ok and not page.locator(".dv-book-side").is_visible())
        page.frame_locator(".dv-book-frame").locator("#bHome").click()
        check("새로고침 뒤 다시 클릭 → 보임", wait_for(lambda: page.locator(".dv-book-side").is_visible(), 5))
        page.locator(".dv-book-head > span").first.click()  # 키 입력이 iframe 이 아니라 devview 로 가게
        page.keyboard.press("Alt+b")
        ok = wait_for(lambda: page.locator("#codeView").is_visible() and not page.locator("#bookView").is_visible(), 5)
        check("Alt+B 다시 → 코드 보기", ok)
        check("화면 오류 없음", not errs, errs[:3])
        br.close()


# ======= 세계 2 — 작업 폴더 = 과제 루트 · 키트 = kit/ =======
def make_task(base):
    root = base / "task"
    (root / "uploads").mkdir(parents=True)
    (root / "README.md").write_text("# 과제\n", encoding="utf-8")
    (root / "HOW_TO_RUN.md").write_text("# 실행\n", encoding="utf-8")
    (root / "uploads" / "data.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    kit = root / "kit"
    (kit / "docs").mkdir(parents=True)
    (kit / "AGENTS.md").write_text("# 키트\n", encoding="utf-8")
    (kit / "docs" / "hand_off.md").write_text("# hand_off — 키트 문서\n", encoding="utf-8")
    (kit / "docs" / "ADR.md").write_text("# ADR — 키트 문서(옛 이름 · 로컬 판 단축키)\n", encoding="utf-8")
    (kit / "docs" / "surveys").mkdir()
    make_books(kit)
    hub = kit / ".codex-hub" / "sessions"
    hub.mkdir(parents=True)
    (hub / "main.json").write_text(json.dumps({"nick": "main", "thread": "t-1", "status": "키트 허브", "registered_at": "2026-11-04 00:00:00"}),
                                   encoding="utf-8")
    return root


def test_kit_api(url):
    code, d = http(url + "/api/info")
    check("info.kit = kit · 작업 폴더 = 과제 루트", code == 200 and d.get("kit") == "kit" and d.get("name") == "task", (d.get("kit"), d.get("name")))
    check("그래프 기본 tree = kit/docs/flowtree/tree.json", str((d.get("flowtree") or {}).get("tree", "")).replace("\\", "/").endswith("task/kit/docs/flowtree/tree.json")
          or not (d.get("flowtree") or {}).get("ok"), d.get("flowtree"))
    code, d = http(url + "/api/tree")
    paths = {x["p"] for x in d.get("entries") or []}
    check("코드 트리 — 과제 원본(README · HOW_TO_RUN · uploads)과 kit/ 가 같이 보임",
          {"README.md", "HOW_TO_RUN.md", "uploads", "uploads/data.csv", "kit", "kit/docs/hand_off.md"} <= paths, sorted(paths)[:20])
    code, d = http(url + "/api/books")
    check("Book 목록 — 키트 bookkit 기준 · 경로는 작업 폴더 기준(kit/…)",
          code == 200 and [b["path"] for b in d.get("books") or []][:1] == ["kit/" + V2], d.get("books"))
    code, d = http(url + "/api/hub")
    m = next((r for r in d.get("rows") or [] if r["nick"] == "main"), {})
    check("허브 — 키트의 .codex-hub 를 읽음", code == 200 and m.get("status") == "키트 허브"
          and str(d.get("dir", "")).replace("\\", "/").endswith("task/kit/.codex-hub"), (m.get("status"), d.get("dir")))


def test_kit_ui(url, port):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        try:
            br = pw.chromium.launch(headless=not HEADED)
        except Exception:  # noqa: BLE001
            br = pw.chromium.launch(channel="chrome", headless=not HEADED)
        page = br.new_page(viewport={"width": 1400, "height": 860})
        page.goto(url + "/")
        page.wait_for_selector("html[data-ready='1']", timeout=30000)
        page.keyboard.press("Control+Alt+1")
        ok = wait_for(lambda: page.evaluate("window.devview.activePath()") in ("kit/docs/hand_off.md", "kit/docs/ADR.md"), 8)
        check("문서 단축키 Ctrl+Alt+1 → 키트 문서 kit/docs/hand_off.md(로컬 판은 ADR.md)", ok, page.evaluate("window.devview.activePath()"))
        page.keyboard.press("Alt+b")
        wait_for(lambda: page.locator(".dv-book-frame").get_attribute("src") is not None, 5)
        src = page.locator(".dv-book-frame").get_attribute("src") or ""
        check("Book iframe — 같은 주소 /pg/kit/bookkit/… 주소", src.startswith(f"http://127.0.0.1:{port}/pg/kit/bookkit/books/01_oht/"), src)
        br.close()


# ======= 세계 3 — 책 없음 =======
def test_empty_ui(url):
    code, d = http(url + "/api/books")
    check("책 없음 — 목록 빈 배열", code == 200 and d.get("books") == [], d)
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        try:
            br = pw.chromium.launch(headless=not HEADED)
        except Exception:  # noqa: BLE001
            br = pw.chromium.launch(channel="chrome", headless=not HEADED)
        page = br.new_page(viewport={"width": 1200, "height": 700})
        page.goto(url + "/")
        page.wait_for_selector("html[data-ready='1']", timeout=30000)
        page.locator("#bookTab").click()
        ok = wait_for(lambda: page.locator(".dv-book-none").count() == 1, 5)
        txt = page.locator(".dv-book-none").inner_text() if ok else ""
        check("책 없음 — «만든 책 없음 — $ontology 로 1차판을 만들면 여기에»", txt == "만든 책 없음 — $ontology 로 1차판을 만들면 여기에", txt)
        check("책 없음 — 새 탭 단추 꺼짐", page.locator(".dv-book-open").is_disabled())
        br.close()


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    api_only = "--api-only" in sys.argv
    tmp = Path(tempfile.mkdtemp(prefix="dv_book_"))
    try:
        # 세계 1
        w1 = tmp / "w1"
        (w1 / "kit").mkdir(parents=True)
        (w1 / "kit" / "AGENTS.md").write_text("# 키트\n", encoding="utf-8")
        make_books(w1 / "kit")
        proc, url, port = start(w1 / "kit", w1)
        try:
            test_books_api(url)
            if not api_only:
                test_books_ui(url, port)
        finally:
            stop(proc)
        # 세계 2
        w2 = tmp / "w2"
        root = make_task(w2)
        proc, url, port = start(root, w2)
        try:
            test_kit_api(url)
            if not api_only:
                test_kit_ui(url, port)
        finally:
            stop(proc)
        # 세계 2 — --kit 로 지정(같은 결과) · 밖이면 거부
        proc, url, port = start(root, w2, ["--kit", str(root / "kit")])
        try:
            code, d = http(url + "/api/info")
            check("--kit 지정 — info.kit = kit", d.get("kit") == "kit", d.get("kit"))
        finally:
            stop(proc)
        r = subprocess.run([sys.executable, str(DEVVIEW), str(root / "kit"), "--port", "1", "--kit", str(root)], capture_output=True,
                           text=True, encoding="utf-8", errors="replace", env=dict(os.environ, PYTHONUTF8="1"))
        check("--kit 가 작업 폴더 밖이면 시작 거부", r.returncode != 0 and "작업 폴더 밖" in (r.stdout + r.stderr), (r.returncode, r.stderr[-200:]))
        # 세계 3
        w3 = tmp / "w3"
        w3.mkdir()
        (w3 / "README.md").write_text("# 빈\n", encoding="utf-8")
        proc, url, port = start(w3, w3)
        try:
            if api_only:
                code, d = http(url + "/api/books")
                check("책 없음 — 목록 빈 배열", code == 200 and d.get("books") == [], d)
            else:
                test_empty_ui(url)
        finally:
            stop(proc)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    bad = [n for n, ok in th.RESULTS if not ok]
    print(f"결과: {len(th.RESULTS) - len(bad)}/{len(th.RESULTS)} 통과" + (f" · 실패 {bad}" if bad else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
