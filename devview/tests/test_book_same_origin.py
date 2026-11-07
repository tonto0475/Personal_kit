# 책 보기 = devview 와 같은 주소(/pg/) — 대회 브라우저처럼 다른 주소(포트) 요청을 막아도 책 · 스티커 · 🪄 · 책 안 단축키가 동작
#   py -3 tests/test_book_same_origin.py        (헤드리스 · 페이지 안 키만 · 실제 Codex 대신 가짜 codex)
# 2026-11-05 사전 체험: 책 iframe 이 페이지 서버(포트 +100 · 호스트 «8801-…»)를 불러 흰 화면 → 본 서버 /pg/<경로> 로 옮김
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

from playwright.sync_api import sync_playwright

DV = Path(__file__).resolve().parents[1] / "devview.py"
BK = DV.parents[1] / "bookkit"
NAME = "sotest"  # «_» 로 시작하면 책 목록에서 빠짐
R = []


def check(name, ok, detail=""):
    R.append(bool(ok))
    print(f"{'PASS' if ok else 'FAIL'} | {name}{' | ' + str(detail)[:300] if detail else ''}", flush=True)


def wait(fn, t=10):
    t0 = time.time()
    while time.time() - t0 < t:
        try:
            v = fn()
            if v:
                return v
        except Exception:
            pass
        time.sleep(0.2)
    return None


def main():
    tmp = Path(tempfile.mkdtemp(prefix="book_so_"))
    root = tmp / "proj"
    book = root / "bookkit" / "books" / NAME
    shutil.copytree(BK / "template", book, ignore=shutil.ignore_patterns("dist", "__pycache__"))
    meta = book / "content" / "meta.py"
    meta.write_text(meta.read_text(encoding="utf-8").replace('"doc": "",', f'"doc": "{NAME}",', 1), encoding="utf-8")
    (book / "contracts").mkdir(exist_ok=True)
    for n in ("facts", "reqs", "steps"):
        shutil.copy(BK / "contracts" / "example" / f"{n}.json", book / "contracts" / f"{n}.json")
    r = subprocess.run([sys.executable, str(BK / "engine" / "build_book.py"), str(book), "--stage", "1"], capture_output=True, text=True, encoding="utf-8")
    check("시험 책 빌드(임시 폴더)", r.returncode == 0, r.stdout[-200:] + r.stderr[-200:])
    hub = root / ".codex-hub"
    (hub / "sessions").mkdir(parents=True)
    (hub / "sessions" / "2nd.json").write_text(json.dumps({"nick": "2nd", "thread": "019a-2nd", "registered_at": "2026-11-05 00:00:00"}), encoding="utf-8")
    log = tmp / "queue.jsonl"
    fake = tmp / "fake_codex.py"
    fake.write_text("import json, os, sys\nopen(os.environ['FAKE_CODEX_LOG'], 'a', encoding='utf-8').write(json.dumps(sys.argv[1:], ensure_ascii=False) + '\\n')\n"
                    "print('Queued message m-1.')\n", encoding="utf-8")
    home = tmp / "home"
    home.mkdir()
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    env = dict(os.environ, DEVVIEW_NO_VAULT="1", CODEX_HOME=str(tmp / "codex"), DEVVIEW_CODEX=str(fake), FAKE_CODEX_LOG=str(log),
               HOME=str(home), USERPROFILE=str(home), PYTHONUTF8="1")
    proc = subprocess.Popen([sys.executable, str(DV), str(root), "--host", "127.0.0.1", "--port", str(port), "--start-view", "code"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
    base = f"http://127.0.0.1:{port}"
    nf = book / "notes.json"
    try:
        wait(lambda: urllib.request.urlopen(base + "/api/info", timeout=1).read(), 15)
        with sync_playwright() as pw:
            br = pw.chromium.launch(channel="chrome", headless=True)
            ctx = br.new_context(viewport={"width": 1600, "height": 1000})
            blocked = []

            # 대회 브라우저 흉내 — devview 주소(호스트:포트) 밖 요청은 막음
            def guard(route):
                u = route.request.url
                if u.startswith(base + "/") or u == base:
                    return route.continue_()
                blocked.append(u)
                return route.abort()
            ctx.route("**/*", guard)
            pg = ctx.new_page()
            errs = []
            pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto(base + "/")
            pg.wait_for_selector("#bell", timeout=15000)
            # 옛 주소(페이지 서버 포트 +100)는 이 브라우저에서 막힘 — 흰 화면의 원인 재현
            old = f"http://127.0.0.1:{port + 100}/bookkit/books/{NAME}/dist/{NAME}.html"
            p2 = ctx.new_page()
            try:
                p2.goto(old, timeout=5000)
                old_ok = p2.evaluate("!!(window.__book && window.__book.ready)")
            except Exception:
                old_ok = False
            p2.close()
            check("재현 — 옛 페이지 서버 주소(포트 +100)는 막혀 책이 안 뜸", not old_ok and any(str(port + 100) in u for u in blocked), blocked[-1:])
            # Book 보기(Alt+B) → iframe 주소 = 같은 주소의 /pg/
            pg.keyboard.press("Alt+KeyB")
            src = wait(lambda: pg.evaluate("document.querySelector('#bookView iframe')?.getAttribute('src') || ''"), 10) or ""
            check("A 주소(/pg/) — 책 iframe 주소 = 같은 주소의 /pg/…", src.startswith(base + "/pg/") and src.endswith(".html"), src)
            view = lambda: pg.evaluate("() => document.querySelector('.dv-view.is-on, .dv-view[aria-pressed=\"true\"]')?.dataset.view || ''")  # noqa: E731
            nid = "?"
            for mode in ("A 주소(/pg/)", "A' 글 넣기(srcdoc)"):
                if mode.startswith("A'"):
                    pg.locator(".dv-book-mode").click()
                    doc = wait(lambda: pg.evaluate("(() => { const f = document.querySelector('#bookView iframe'); return f.hasAttribute('srcdoc') && !f.hasAttribute('src') && f.srcdoc.includes('<base href=\"' + location.origin + '/pg/'); })()"), 10)
                    check(f"{mode} — 단추 → srcdoc(주소 이동 없음 · <base> = 같은 주소 /pg/ 책 폴더)", doc)
                time.sleep(0.5)
                fr = wait(lambda: pg.locator("#bookView iframe").element_handle().content_frame(), 10)
                ready = fr and wait(lambda: fr.evaluate("!!(window.__book && window.__book.ready)"), 30)
                check(f"{mode} — 책이 뜸(흰 화면 아님) · window.__book.ready", ready)
                # 쪽 넘김
                p0 = fr.evaluate("window.__book.cur !== undefined ? window.__book.cur : -1")
                fr.evaluate("window.__book.go(2)")
                time.sleep(0.3)
                vis = fr.evaluate("[...document.querySelectorAll('#book .page.on')].map((e) => +e.dataset.pi)")
                check(f"{mode} — 쪽 넘김(go 2 → 보이는 쪽)", 2 in vis or 3 in vis, (p0, vis))
                # 스티커 붙이기 → notes.json(같은 주소 /pg/…/api/notes)
                block = "s3-Q1"
                text = f"같은 주소 스티커 시험 {mode}"
                fr.evaluate(f"window.__book.go(+document.querySelector('#book [data-id=\"{block}\"]').closest('.page').dataset.pi)")
                time.sleep(0.3)
                if fr.locator("#bMemo").get_attribute("aria-pressed") != "true":  # 메모 모드 켜기(앞 방식에서 켠 상태가 저장돼 있을 수 있음)
                    fr.locator("#bMemo").click()
                if not mode.startswith("A "):
                    # 앞 방식 스티커가 왼쪽 쪽을 덮음 — 같은 펼침의 오른쪽 쪽 블록에
                    block = fr.evaluate("[...document.querySelectorAll('#book .page.on .pin > [data-id]')].find((b) => b.closest('.page').dataset.side === 'r' && b.textContent.trim().length > 10)?.dataset.id")
                box = fr.locator(f'#book [data-id="{block}"]').bounding_box()
                pg.mouse.click(box["x"] + 40, box["y"] + 10)
                note = fr.locator(".note").last
                note.locator("textarea").fill(text)
                note.locator(".nf button:not(.nw)").click()
                saved = wait(lambda: nf.is_file() and [n for n in json.loads(nf.read_text(encoding="utf-8")) if n["text"] == text], 8)
                check(f"{mode} — 스티커 저장 → notes.json", saved)
                if fr.locator("#bMemo[aria-pressed=\"true\"]").count():
                    fr.locator("#bMemo").click()
                # 🪄 → 가짜 codex 에 그 스티커 id
                nid = saved[0]["id"] if saved else "?"
                fr.locator(".note .nw").last.click()
                q = wait(lambda: log.is_file() and [x for x in log.read_text(encoding="utf-8").splitlines() if nid in x], 10)
                check(f"{mode} — 스티커 🪄 → 2ND 큐(가짜 codex)에 스티커 id", q, (log.read_text(encoding="utf-8")[-200:] if log.is_file() else "로그 없음"))
                # 책 안 단축키 — Alt+B 는 devview 로 넘어가 코드 보기로 → 다시 Book
                fr.locator("body").press("Alt+KeyB")
                check(f"{mode} — 책 안 Alt+B → devview 코드 보기(메시지 출처 검사 통과)", wait(lambda: view() == "code", 5), view())
                pg.keyboard.press("Alt+KeyB")
                wait(lambda: view() == "book", 5)
            # A' 에서 알림 종 → 책 스티커(#note=) — srcdoc 문서의 hash 로 넘김
            r = subprocess.run([sys.executable, str(DV.parent / "notify.py"), "--kit", str(root), "add", "--kind", "note", "--title", "스티커 이동 시험",
                                "--to", f"book:{NAME}:{nid}"], capture_output=True, text=True, env=env)
            check("알림 등록", r.returncode == 0, r.stdout + r.stderr)
            pg.keyboard.press("Alt+KeyB")
            wait(lambda: view() == "code", 5)
            wait(lambda: pg.evaluate("(() => { const b = document.querySelector('#bell .dv-bell-badge'); return !b.hidden; })()"), 12)
            pg.click("#bell .dv-bell-btn")
            pg.locator("#notifyPanel .dv-notify-item", has_text="스티커 이동 시험").first.click()
            got = wait(lambda: pg.locator("#bookView iframe").element_handle().content_frame().evaluate("location.hash"), 15)
            check("A' — 알림 → 책 · srcdoc 문서 hash = #note=<스티커>", view() == "book" and got and nid in got, (view(), got))
            check("devview 밖 주소 요청 없음(막힌 것은 재현용 한 건뿐)", all(str(port + 100) in u for u in blocked), blocked)
            check("페이지 예외 없음", not errs, errs[:3])
            br.close()
    finally:
        proc.terminate()
        proc.wait(5)
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"결과: {sum(R)}/{len(R)}")
    return all(R)


def test_book_same_origin():
    assert main()


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
