# 페이지 서버(포트 +100) 맨 위(/) = 가장 최근 책 — 대회 미리보기 칸은 PORT 숫자만 바꿀 수 있고 경로는 못 친다(2026-11-05)
#   py -3 tests/test_book_page_root.py        (헤드리스 · 페이지 안 키만 · 실제 Codex 대신 가짜 codex)
# 확인: / 에서 책 뜸 · 쪽 넘김 · 스티커 저장(그 책 notes.json) · 🪄 · 프록시 접두어 아래 <base> · 책 없음 한 줄
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
NAME = "roottest"
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


def free_port():
    while True:
        s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close()
        if p + 100 < 65536:
            return p


# devview 띄우기 → (프로세스, 포트)
def start(root, env):
    port = free_port()
    proc = subprocess.Popen([sys.executable, str(DV), str(root), "--host", "127.0.0.1", "--port", str(port), "--start-view", "code"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
    wait(lambda: urllib.request.urlopen(f"http://127.0.0.1:{port + 100}/", timeout=1).status == 200, 15)
    return proc, port


def main():
    tmp = Path(tempfile.mkdtemp(prefix="book_root_"))
    home = tmp / "home"
    home.mkdir()
    log = tmp / "queue.jsonl"
    fake = tmp / "fake_codex.py"
    fake.write_text("import json, os, sys\nopen(os.environ['FAKE_CODEX_LOG'], 'a', encoding='utf-8').write(json.dumps(sys.argv[1:], ensure_ascii=False) + '\\n')\n"
                    "print('Queued message m-1.')\n", encoding="utf-8")
    env = dict(os.environ, DEVVIEW_NO_VAULT="1", CODEX_HOME=str(tmp / "codex"), DEVVIEW_CODEX=str(fake), FAKE_CODEX_LOG=str(log),
               HOME=str(home), USERPROFILE=str(home), PYTHONUTF8="1")
    procs = []
    try:
        # ① 책 없음
        empty = tmp / "empty"
        empty.mkdir()
        p0, port0 = start(empty, env)
        procs.append(p0)
        body = urllib.request.urlopen(f"http://127.0.0.1:{port0 + 100}/", timeout=5).read().decode("utf-8")
        check("① 책 없음 — / 에 «만든 책 없음» 한 줄", "만든 책 없음" in body, body[:120])
        # ② 책 하나
        root = tmp / "proj"
        book = root / "bookkit" / "books" / NAME
        shutil.copytree(BK / "template", book, ignore=shutil.ignore_patterns("dist", "__pycache__"))
        meta = book / "content" / "meta.py"
        meta.write_text(meta.read_text(encoding="utf-8").replace('"doc": "",', f'"doc": "{NAME}",', 1), encoding="utf-8")
        (book / "contracts").mkdir(exist_ok=True)
        for n in ("facts", "reqs", "steps"):
            shutil.copy(BK / "contracts" / "example" / f"{n}.json", book / "contracts" / f"{n}.json")
        r = subprocess.run([sys.executable, str(BK / "engine" / "build_book.py"), str(book), "--stage", "1"], capture_output=True, text=True, encoding="utf-8")
        check("② 시험 책 빌드(임시 폴더)", r.returncode == 0, r.stderr[-200:])
        hub = root / ".codex-hub"
        (hub / "sessions").mkdir(parents=True)
        (hub / "sessions" / "2nd.json").write_text(json.dumps({"nick": "2nd", "thread": "019a-2nd", "registered_at": "2026-11-05 00:00:00"}), encoding="utf-8")
        p1, port = start(root, env)
        procs.append(p1)
        page = f"http://127.0.0.1:{port + 100}"
        # 프록시 접두어 아래에서도 <base> 에 접두어
        px = urllib.request.urlopen(f"{page}/absproxy/{port + 100}/", timeout=5).read().decode("utf-8")
        check("② 프록시 접두어(/absproxy/N/) 아래 / — <base> 에 접두어 + 책 폴더", f'<base href="/absproxy/{port + 100}/bookkit/books/{NAME}/dist/">' in px, px[:200])
        nf = book / "notes.json"
        with sync_playwright() as pw:
            br = pw.chromium.launch(channel="chrome", headless=True)
            ctx = br.new_context(viewport={"width": 1600, "height": 1000})
            other = []

            # 이 페이지 서버 밖 주소는 막음(대회 칸 흉내)
            def guard(route):
                u = route.request.url
                if u.startswith(page + "/") or u == page:
                    return route.continue_()
                other.append(u)
                return route.abort()
            ctx.route("**/*", guard)
            pg = ctx.new_page()
            errs = []
            pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto(page + "/")
            check("② / 에서 책이 뜸(주소 그대로)", wait(lambda: pg.evaluate("!!(window.__book && window.__book.ready)"), 30) and pg.url.rstrip("/") == page, pg.url)
            pg.evaluate("window.__book.go(2)")
            time.sleep(0.3)
            vis = pg.evaluate("[...document.querySelectorAll('#book .page.on')].map((e) => +e.dataset.pi)")
            check("② 쪽 넘김", 2 in vis or 3 in vis, vis)
            block = "s3-Q1"
            pg.evaluate(f"window.__book.go(+document.querySelector('#book [data-id=\"{block}\"]').closest('.page').dataset.pi)")
            time.sleep(0.3)
            if pg.locator("#bMemo").get_attribute("aria-pressed") != "true":
                pg.locator("#bMemo").click()
            box = pg.locator(f'#book [data-id="{block}"]').bounding_box()
            pg.mouse.click(box["x"] + 40, box["y"] + 10)
            note = pg.locator(".note").last
            note.locator("textarea").fill("맨 위 주소 스티커 시험")
            note.locator(".nf button:not(.nw)").click()
            saved = wait(lambda: nf.is_file() and [n for n in json.loads(nf.read_text(encoding="utf-8")) if n["text"] == "맨 위 주소 스티커 시험"], 8)
            check("② 스티커 저장 → 그 책 폴더 notes.json", saved)
            nid = saved[0]["id"] if saved else "?"
            pg.locator(".note .nw").last.click()
            q = wait(lambda: log.is_file() and [x for x in log.read_text(encoding="utf-8").splitlines() if nid in x], 10)
            check("② 스티커 🪄 → 2ND 큐(가짜 codex)에 스티커 id", q, log.read_text(encoding="utf-8")[-200:] if log.is_file() else "로그 없음")
            check("② 밖 주소 요청 없음", not other, other[:3])
            check("② 페이지 예외 없음", not errs, errs[:3])
            br.close()
    finally:
        for p in procs:
            p.terminate()
            p.wait(5)
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"결과: {sum(R)}/{len(R)}")
    return all(R)


def test_book_page_root():
    assert main()


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
