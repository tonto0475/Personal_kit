# -*- coding: utf-8 -*-
r"""책 스티커 시험(devview 페이지 서버 · 헤드리스) — 책 열기 → 스티커 붙이기 → notes.json 저장 → notes.py answer → 새로고침 뒤 답이 보인다

    python3 bookkit/engine/test_notes.py            → PASS / FAIL (playwright 가 없으면 SKIP)

- 시험 책 = bookkit/books/_notes_selftest(양식 + 예시 계약 · 2차판) — 끝나면 그 폴더만 지운다
- devview 는 빈 포트에 새로 띄우고(페이지 서버 = 포트 + 100) 끝나면 그 PID 만 끈다
"""
import json
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
# 키트 bookkit 폴더 · 키트 폴더 · 시험 책 이름 · 시험 책 폴더
KIT = HERE.parent
ROOT = KIT.parent
NAME = "_notes_selftest"
BOOK = KIT / "books" / NAME


def free_port():
    """페이지 서버(+100)까지 비어 있는 포트"""
    for _ in range(50):
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        p = s.getsockname()[1]
        s.close()
        if p + 100 < 65535:
            t = socket.socket()
            try:
                t.bind(("127.0.0.1", p + 100))
                return p
            except OSError:
                pass
            finally:
                t.close()
    raise RuntimeError("빈 포트 없음")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("SKIP — playwright 없음(PASS 아님)")
        return 0
    fails = []

    # 단언 하나
    def check(ok, what):
        print(("  ok   " if ok else "  FAIL ") + what)
        if not ok:
            fails.append(what)

    if BOOK.exists():
        shutil.rmtree(BOOK)
    shutil.copytree(KIT / "template", BOOK, ignore=shutil.ignore_patterns("dist", "__pycache__"))
    meta = BOOK / "content" / "meta.py"
    meta.write_text(meta.read_text(encoding="utf-8").replace('"doc": "",', f'"doc": "{NAME}",', 1), encoding="utf-8")
    (BOOK / "contracts").mkdir(exist_ok=True)
    for n in ("facts", "reqs", "steps"):
        shutil.copy(KIT / "contracts" / "example" / f"{n}.json", BOOK / "contracts" / f"{n}.json")
    r = subprocess.run([sys.executable, str(HERE / "build_book.py"), str(BOOK), "--stage", "1"], capture_output=True, text=True, encoding="utf-8")
    check(r.returncode == 0, "시험 책 1차판 빌드")
    port = free_port()
    dv = subprocess.Popen([sys.executable, str(ROOT / "devview" / "devview.py"), str(ROOT), "--host", "127.0.0.1", "--port", str(port)],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        base = f"http://127.0.0.1:{port + 100}"
        url = f"{base}/bookkit/books/{NAME}/dist/{NAME}.html"
        for _ in range(100):
            try:
                urllib.request.urlopen(url, timeout=1).read(10)
                break
            except OSError:
                time.sleep(0.2)
        with sync_playwright() as pw:
            br = pw.chromium.launch(headless=True)
            pg = br.new_page(viewport={"width": 1600, "height": 1000})
            pg.goto(url)
            pg.wait_for_function("window.__book && window.__book.ready", timeout=60000)
            # 3장 질문 1 블록(s3-Q1)으로 가서 메모 붙이기
            pi = pg.evaluate("(() => { const b = document.querySelector('#book [data-id=\"s3-Q1\"]'); const pg = b.closest('.page'); return +pg.dataset.pi; })()")
            pg.evaluate(f"window.__book.go({pi})")
            pg.wait_for_timeout(300)
            pg.click("#bMemo")
            box = pg.locator('#book [data-id="s3-Q1"]').bounding_box()
            pg.mouse.click(box["x"] + 40, box["y"] + 10)
            pg.locator(".note textarea").fill("최적 기준을 왜 총거리로 잡나?")
            pg.locator(".note .nf button:not(.nw)").click()
            pg.wait_for_selector(".note .nt:has-text('접수')", timeout=5000)
            nf = BOOK / "notes.json"
            notes = json.loads(nf.read_text(encoding="utf-8")) if nf.is_file() else []
            check(len(notes) == 1 and notes[0]["doc"] == NAME, f"notes.json 저장 — {nf}")
            check(bool(notes) and "b=s3-Q1" in notes[0]["ctx"], "스티커 자리 = 블록 s3-Q1")
            nid = notes[0]["id"] if notes else "x"
            r = subprocess.run([sys.executable, str(KIT / "notes.py"), "list"], capture_output=True, text=True, encoding="utf-8")
            check(nid in r.stdout and "s3-Q1" in r.stdout, "notes.py list 에 보임")
            r = subprocess.run([sys.executable, str(KIT / "notes.py"), "answer", nid, "README 가 기준을 말하지 않아 기본 가정으로 둔다."],
                               capture_output=True, text=True, encoding="utf-8")
            check(r.returncode == 0, "notes.py answer")
            # 2차판으로 다시 빌드 — 블록 ID 가 고정이라 스티커가 같은 블록에 붙어야 한다
            r = subprocess.run([sys.executable, str(HERE / "build_book.py"), str(BOOK), "--stage", "2"], capture_output=True, text=True, encoding="utf-8")
            check(r.returncode == 0, "2차판 다시 빌드")
            pg.reload()
            pg.wait_for_function("window.__book && window.__book.ready", timeout=60000)
            pi = pg.evaluate("+document.querySelector('#book [data-id=\"s3-Q1\"]').closest('.page').dataset.pi")
            pg.evaluate(f"window.__book.go({pi})")
            pg.wait_for_timeout(500)
            na = pg.locator("#spQa .qr")
            check(na.count() == 1 and pg.locator(".note").count() == 0, "새로고침(2차판) 뒤 답 달린 스티커는 빠지고 아래 질문 줄 행")
            na.locator(".qrh").click()
            check("기본 가정" in na.inner_text() and na.locator(".qrb").is_visible(), "행 펼침 — 답이 보인다(같은 블록 쪽)")
            # 판 파일(dist/<doc>__v<N>_<판>.html) — 1차판 · 2차판 두 파일 모두에서 같은 스티커(책 폴더의 notes.json 하나)
            vs = json.loads((BOOK / "dist" / "versions.json").read_text(encoding="utf-8"))["versions"]
            check([v["name"] for v in vs] == ["1차판", "2차판"], f"판 목록 {[v['file'] for v in vs]}")
            for v in vs:
                pg.goto(f"{base}/bookkit/books/{NAME}/dist/{v['file']}")
                pg.wait_for_function("window.__book && window.__book.ready", timeout=60000)
                pi = pg.evaluate("+document.querySelector('#book [data-id=\"s3-Q1\"]').closest('.page').dataset.pi")
                pg.evaluate(f"window.__book.go({pi})")
                pg.wait_for_timeout(500)
                na = pg.locator("#spQa .qr")
                if na.count() == 1:
                    na.locator(".qrh").click()
                check(na.count() == 1 and "기본 가정" in na.inner_text() and na.locator(".qrb").is_visible(), f"판 파일 {v['file']} 에서도 같은 질문 줄 행 · 답")
            # «노트 목록» 단추 — 밖(새 탭)이면 원래 링크 · iframe 안이면 부모에 {book:'toggle-list'}(devview 가 왼쪽 책 목록을 숨김 ↔ 보임)
            check(pg.locator("#bHome").get_attribute("title") == "노트 목록" and pg.locator("#bHome").get_attribute("href"),
                  "iframe 밖 — «노트 목록» 링크 · 툴팁 그대로")
            wrap = BOOK / "dist" / "_wrap.html"
            wrap.write_text("<!doctype html><meta charset='utf-8'><script>window.msgs=[];addEventListener('message',e=>msgs.push(e.data));</script>"
                            f"<iframe id='f' src='{NAME}.html' style='width:1500px;height:900px'></iframe>", encoding="utf-8")
            pg.goto(f"{base}/bookkit/books/{NAME}/dist/_wrap.html")
            fr = pg.frame_locator("#f")
            fr.locator("#bHome").wait_for(timeout=60000)
            check(fr.locator("#bHome").get_attribute("title") == "책 목록 보이기 · 숨기기", "iframe 안 — 툴팁 «책 목록 보이기 · 숨기기»")
            fr.locator("#bHome").click()
            pg.wait_for_timeout(300)
            check(pg.evaluate("window.msgs") == [{"book": "toggle-list"}] and pg.url.endswith("_wrap.html")
                  and pg.locator("#f").get_attribute("src") == f"{NAME}.html", f"iframe 안 클릭 → 부모에 toggle-list · 링크로 안 넘어감 {pg.evaluate('window.msgs')}")
            r = subprocess.run([sys.executable, str(KIT / "notes.py"), "list"], capture_output=True, text=True, encoding="utf-8")
            check("답할 스티커 없음" in r.stdout, "답한 뒤 list = 답할 스티커 없음")
            # 지우기(질문 줄 행 «지우기» → DELETE) — 지금 페이지는 iframe 감싼 쪽이라 책(iframe) 안을 누른다
            fpi = pg.frame_locator("#f").locator('#book [data-id="s3-Q1"]').evaluate("b => +b.closest('.page').dataset.pi")
            fr.locator("body").evaluate(f"() => window.__book.go({fpi})")
            fr.locator("#spQa .qrh").click()
            fr.locator("#spQa .qdel").click()
            pg.wait_for_timeout(300)
            check(json.loads(nf.read_text(encoding="utf-8")) == [] and fr.locator("#spQa .qr").count() == 0, "행 «지우기» 면 notes.json 에서 빠지고 행도 사라진다")
            # 페이지 서버의 다른 경로는 그대로 읽기 전용
            req = urllib.request.Request(url, data=b"x", method="POST")
            try:
                urllib.request.urlopen(req, timeout=3)
                check(False, "책 html 에 POST = 405")
            except urllib.error.HTTPError as e:
                check(e.code == 405, f"책 html 에 POST = 405({e.code})")
            br.close()
    finally:
        dv.terminate()
        try:
            dv.wait(timeout=5)
        except subprocess.TimeoutExpired:
            dv.kill()
        shutil.rmtree(BOOK, ignore_errors=True)
    print("PASS" if not fails else f"FAIL {len(fails)}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
