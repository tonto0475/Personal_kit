# -*- coding: utf-8 -*-
r"""책 아래 «질문 줄» 화면 시험(헤드리스) — 답 없는 스티커는 화면에 · 답이 달리면 스티커가 빠지고 그 쪽 질문 줄 «Q1. 제목» 행
→ 다른 쪽에선 안 보임 → 행 펼침(질문 · 답) → 꼬리 질문 + 🪄(가짜 codex) → 꼬리 답이 같은 행 안 → #note=<id>&t=<꼬리> 로 열기 · hashchange

    py -3 bookkit/engine/book/tests/test_note_rows_ui.py      → PASS / FAIL (playwright 없으면 SKIP)

- 임시 작업 폴더에 엔진 양식 책을 빌드(실제 책 · notes.json 무관) · 가짜 codex · devview 는 빈 포트(페이지 서버 = +100) · 끝나면 그 PID 만 끈다
- 캡처 = 이 폴더 shots/note_rows_*.png
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
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
# 키트 · bookkit · 시험 책 이름 · 캡처 폴더
ROOT = HERE.parents[3]
BK = ROOT / "bookkit"
NAME = "_nr"
SHOTS = HERE / "shots"
HEADED = os.environ.get("CC_HEADED") == "1"


def free_port():
    """페이지 서버(+100)까지 비어 있는 포트"""
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


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("SKIP — playwright 없음(PASS 아님)")
        return 0
    fails = []
    SHOTS.mkdir(exist_ok=True)

    # 단언 하나
    def check(ok, what, detail=""):
        print(("  ok   " if ok else "  FAIL ") + what + (f" | {str(detail)[:300]}" if detail and not ok else ""), flush=True)
        if not ok:
            fails.append(what)

    tmp = Path(tempfile.mkdtemp(prefix="note_rows_"))
    root = tmp / "proj"
    book = root / "bookkit" / "books" / NAME
    shutil.copytree(BK / "template", book, ignore=shutil.ignore_patterns("dist", "__pycache__"))
    meta = book / "content" / "meta.py"
    meta.write_text(meta.read_text(encoding="utf-8").replace('"doc": "",', f'"doc": "{NAME}",', 1), encoding="utf-8")
    (book / "contracts").mkdir(exist_ok=True)
    for n in ("facts", "reqs", "steps"):
        shutil.copy(BK / "contracts" / "example" / f"{n}.json", book / "contracts" / f"{n}.json")
    shutil.copy(BK / "notes.py", root / "bookkit" / "notes.py")
    r = subprocess.run([sys.executable, str(BK / "engine" / "build_book.py"), str(book), "--stage", "1"], capture_output=True, text=True, encoding="utf-8")
    check(r.returncode == 0, "시험 책 1차판 빌드(임시 폴더)", r.stdout[-300:] + r.stderr[-300:])
    hub = root / ".codex-hub"
    (hub / "sessions").mkdir(parents=True)
    (hub / "sessions" / "2nd.json").write_text(json.dumps({"nick": "2nd", "thread": "019a-2nd", "registered_at": "2026-11-03 00:00:00"}), encoding="utf-8")
    log = tmp / "queue.jsonl"
    fake = tmp / "fake_codex.py"
    fake.write_text("import json, os, sys\nargs = sys.argv[1:]\n"
                    "open(os.environ['FAKE_CODEX_LOG'], 'a', encoding='utf-8').write(json.dumps(args, ensure_ascii=False) + '\\n')\n"
                    "print('Queued message m-1.')\n", encoding="utf-8")
    home = tmp / "home"
    home.mkdir()
    port = free_port()
    env = dict(os.environ, DEVVIEW_NO_VAULT="1", CODEX_HOME=str(tmp / "codex"), DEVVIEW_CODEX=str(fake), FAKE_CODEX_LOG=str(log),
               HOME=str(home), USERPROFILE=str(home), PYTHONUTF8="1")
    dv = subprocess.Popen([sys.executable, str(ROOT / "devview" / "devview.py"), str(root), "--host", "127.0.0.1", "--port", str(port)],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
    nf = book / "notes.json"
    notes_py = root / "bookkit" / "notes.py"

    def queued():
        return [json.loads(x)[-1] for x in log.read_text(encoding="utf-8").splitlines()] if log.is_file() else []

    def disk():
        return {n["id"]: n for n in json.loads(nf.read_text(encoding="utf-8"))}

    def answer(*args):
        return subprocess.run([sys.executable, str(notes_py), "answer", *args, "--book", str(book)], capture_output=True, text=True, encoding="utf-8")

    try:
        url = f"http://127.0.0.1:{port + 100}/bookkit/books/{NAME}/dist/{NAME}.html"
        for _ in range(100):
            try:
                urllib.request.urlopen(url, timeout=1).read(10)
                break
            except OSError:
                time.sleep(0.2)
        with sync_playwright() as pw:
            br = pw.chromium.launch(headless=not HEADED)
            pg = br.new_page(viewport={"width": 1600, "height": 1000})
            errs = []
            pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto(url)
            pg.wait_for_function("window.__book && window.__book.ready", timeout=60000)

            def page_of(block):
                return pg.evaluate(f"+document.querySelector('#book [data-id=\"{block}\"]').closest('.page').dataset.pi")

            def go(pi):
                pg.evaluate(f"window.__book.go({pi})")
                pg.wait_for_timeout(300)

            # 블록에 스티커 붙이기 → 스티커 id
            def stick(block, text):
                go(page_of(block))
                pg.click("#bMemo")
                box = pg.locator(f'#book [data-id="{block}"]').bounding_box()
                pg.mouse.click(box["x"] + 40, box["y"] + 10)
                note = pg.locator(".note").last
                note.locator("textarea").fill(text)
                note.locator(".nf button:not(.nw)").click()
                pg.wait_for_selector(".note .nt:has-text('접수')", timeout=5000)
                return [n for n in disk().values() if n["text"] == text][0]["id"]

            # 다른 펼침의 블록(첫 블록 쪽과 다른 펼침 · 높이 있는 것)
            def other_block(block):
                return pg.evaluate("(b0) => { const s0 = Math.floor(+document.querySelector('#book [data-id=\"' + b0 + '\"]').closest('.page').dataset.pi / 2);"
                                   " return [...document.querySelectorAll('#book .page .pin > [data-id]')].find((b) =>"
                                   " Math.floor(+b.closest('.page').dataset.pi / 2) !== s0 && !['cover', 'part', 'chapter', 'matter'].includes(b.dataset.k) && !b.closest('.full') && b.textContent.trim().length > 20).dataset.id; }",
                                   block)

            Q1 = "DB 트랜잭션은 여러 쓰기를 왜 한 단위로 묶어야 하나? 하나만 실패하면 나머지는 어떻게 되나?"
            nid = stick("s3-Q1", Q1)
            sp = page_of("s3-Q1")
            check(pg.locator(".note").count() == 1 and pg.locator(".note").first.is_visible() and pg.locator("#spQa").is_hidden(),
                  "답 없는 스티커 — 화면에 보임 · 질문 줄 숨김")
            pg.locator(".note .nw").click()
            pg.wait_for_function("[...document.querySelectorAll('.note .ne')].some((e) => !e.hidden && e.textContent.includes('보냄'))", timeout=8000)
            check(disk()[nid].get("magic_rid") and nid in queued()[-1], "스티커 🪄 — magic_rid · queue 글에 스티커 id", queued()[-1:])
            # 답 + 제목 → (새로고침 없이) 4초 다시 읽기로 스티커가 빠지고 질문 줄 행
            r = answer(nid, "한 단위로 묶어야 중간 실패 때 앞의 쓰기까지 되돌린다(롤백).", "--title", "DB 트랜잭션 관련 질문")
            check(r.returncode == 0, "notes.py answer --title", r.stdout + r.stderr)
            moved = True
            try:
                pg.wait_for_function("document.querySelectorAll('.note').length === 0 && document.querySelectorAll('#spQa .qr').length === 1", timeout=12000)
            except Exception:  # noqa: BLE001
                moved = False
            row = pg.locator("#spQa .qr")
            check(moved and row.locator(".qrh").inner_text() == "Q1. DB 트랜잭션 관련 질문" and pg.locator("#spQa").is_visible(),
                  "답이 달리면 — 스티커 사라짐 · 그 쪽 질문 줄 «Q1. DB 트랜잭션 관련 질문»(새로고침 없이)", row.all_inner_texts())
            check(row.locator(".qrb").is_hidden(), "행은 처음엔 접힘")
            pg.screenshot(path=str(SHOTS / "note_rows_row.png"))

            # 다른 펼침 → 그 행 안 보임(패널 숨김)
            ob = other_block("s3-Q1")
            go(page_of(ob))
            check(pg.locator("#spQa").is_hidden() and pg.locator("#spQa .qr").count() == 0, f"다른 쪽({ob}) — 질문 줄 숨김")
            go(sp)
            row = pg.locator("#spQa .qr")
            check(row.count() == 1, "원래 쪽으로 돌아오면 행 다시")
            row.locator(".qrh").click()
            body = row.locator(".qrb")
            check(body.is_visible() and Q1 in body.inner_text() and "롤백" in body.inner_text(), "행 클릭 — 아래로 펼쳐 질문 · 답 글")
            check(pg.evaluate("[...document.querySelectorAll('#spQa .qr, #spQa .qx')].every((e) => e.scrollWidth <= e.clientWidth + 1)"),
                  "긴 질문 · 답 — 가로 넘침 없음(줄바꿈)")

            # 꼬리 질문 + 🪄
            body.locator(".qf textarea").fill("롤백하면 이미 보낸 응답은?")
            body.locator(".qf .nw").click()
            pg.wait_for_function("[...document.querySelectorAll('#spQa .qe')].some((e) => !e.hidden && e.textContent.includes('보냄'))", timeout=8000)
            th = disk()[nid].get("thread") or []
            check(len(th) == 1 and th[0]["id"] == "t1" and th[0]["q"] == "롤백하면 이미 보낸 응답은?" and th[0].get("magic_rid"),
                  "notes.json thread[t1] — q · magic_rid", th)
            m = queued()[-1]
            check(f"스티커 {nid} · 꼬리 t1" in m and "꼬리 질문: 롤백하면 이미 보낸 응답은?" in m and "앞 답: 한 단위로" in m,
                  "가짜 codex 메시지 — 스티커 id + 꼬리 id · 앞 답 · 꼬리 질문", m)
            row = pg.locator("#spQa .qr")
            check(row.count() == 1 and row.locator(".qt[data-t='t1'] .qwait").inner_text() == "2ND 답 대기" and row.locator(".qrb").is_visible(),
                  "꼬리는 같은 행 안(행 수 1 · «2ND 답 대기» · 펼침 유지)")
            r = answer(nid, "--thread", "t1", "응답은 커밋 뒤에 보내야 한다.")
            check(r.returncode == 0, "notes.py answer --thread t1", r.stdout + r.stderr)
            got = True
            try:
                pg.wait_for_function("(() => { const q = document.querySelector('#spQa .qt[data-t=\"t1\"]'); return q && q.textContent.includes('커밋 뒤'); })()",
                                     timeout=12000)
            except Exception:  # noqa: BLE001
                got = False
            check(got and pg.locator("#spQa .qr").count() == 1 and pg.locator("#spQa .qt").count() == 1, "꼬리 답 — 같은 행 안에 이어 달림 · 행 수 그대로")
            pg.screenshot(path=str(SHOTS / "note_rows_thread.png"))

            # 다른 쪽 질문(옛 형식처럼 제목 없음) → 그 쪽에서만 Q1 = 질문 앞부분
            nid2 = stick(ob, "API 테스트는 상태 코드부터 보나?")
            answer(nid2, "그렇다. 상태 코드 → 본문 순서.")
            pg.reload()
            pg.wait_for_function("window.__book && window.__book.ready", timeout=60000)
            go(page_of(ob))
            pg.wait_for_timeout(300)
            rows = pg.locator("#spQa .qr .qrh").all_inner_texts()
            check(rows == ["Q1. API 테스트는 상태 코드부터 보나?"] and pg.locator(".note").count() == 0, "제목 없는 항목 — 행 제목 = 질문 앞부분 · 그 쪽 것만", rows)

            # #note=<id>&t=t1 로 새로 열기 — 그 쪽 · 그 행 펼침 · 꼬리 답 보임
            pg.goto(url + f"#note={nid}&t=t1")
            pg.wait_for_function("window.__book && window.__book.ready", timeout=60000)
            ok = True
            try:
                pg.wait_for_function(f"!!document.querySelector('#spQa .qr.open[data-id=\"{nid}\"]')", timeout=8000)
            except Exception:  # noqa: BLE001
                ok = False
            pg.wait_for_timeout(400)
            qt = pg.locator(f"#spQa .qr[data-id='{nid}'] .qt[data-t='t1']")
            inview = pg.evaluate("(() => { const r = document.querySelector('#spQa .qt[data-t=\"t1\"]').getBoundingClientRect(); return r.top >= 0 && r.bottom <= innerHeight; })()") if ok else False
            check(ok and pg.evaluate("window.__book.cur()") // 2 == sp // 2 and qt.is_visible() and "커밋 뒤" in qt.inner_text() and inview,
                  "#note=<id>&t=t1 로 열기 — 그 쪽 · 행 펼침 · 꼬리 답이 화면 안")
            pg.screenshot(path=str(SHOTS / "note_rows_hash.png"))
            # 열린 책에서 hash 만 바꿈 → 다른 스티커 쪽 · 그 행 펼침
            pg.evaluate(f"location.hash = 'note={nid2}'")
            ok = True
            try:
                pg.wait_for_function(f"!!document.querySelector('#spQa .qr.open[data-id=\"{nid2}\"]')", timeout=8000)
            except Exception:  # noqa: BLE001
                ok = False
            check(ok and pg.evaluate("window.__book.cur()") // 2 == page_of(ob) // 2, "hashchange #note=<id2> — 그 쪽으로 넘기고 그 행 펼침")

            # 한 페이지 보기 — 그 쪽 아래 질문 줄(.qa1)에 행
            pg.evaluate("window.__book.setMode(1)")
            pg.wait_for_timeout(600)
            q1 = pg.locator(f"#book .qa1:not([hidden]) .qr[data-id='{nid}']")
            check(pg.locator("#spQa").is_hidden() and q1.count() == 1 and q1.locator(".qrh").inner_text() == "Q1. DB 트랜잭션 관련 질문",
                  "한 페이지 보기 — 그 쪽 아래 질문 줄 · 두 페이지 패널 숨김")
            check(pg.locator("#book .qa1:not([hidden])").count() == 2, "한 페이지 — 질문 있는 쪽 2개만 질문 줄", pg.locator("#book .qa1:not([hidden])").count())
            pg.evaluate("window.__book.setMode(2)")
            check(not errs, "페이지 예외 없음", errs)
            br.close()
    finally:
        dv.terminate()
        try:
            dv.wait(timeout=5)
        except subprocess.TimeoutExpired:
            dv.kill()
        shutil.rmtree(tmp, ignore_errors=True)
    print("PASS" if not fails else f"FAIL {len(fails)}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
