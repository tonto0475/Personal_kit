# -*- coding: utf-8 -*-
r"""책 스티커 마법봉 시험(헤드리스) — 스티커 접수 → 🪄 → 페이지 서버 POST …/api/notes/<id>/magic → 허브 요청 파일(2ND · note) + 가짜 codex queue
→ magic.py answer-note --title → 새로고침 뒤 스티커는 빠지고 아래 질문 줄 행 · 2ND 미등록이면 «2ND 미연결»

    py -3 devview/tests/test_note_magic.py           → PASS / FAIL (playwright 없으면 SKIP)

- 임시 작업 폴더(시험 책 · bookkit/notes.py 복사 · .codex-hub 등록) · 가짜 codex(인자를 파일에 적음) · 실제 ~/.codex · 8701 무관
- devview 는 빈 포트(페이지 서버 = +100)에 띄우고 끝나면 그 프로세스만 끈다 · 캡처 = tests/shots/note_magic*.png
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
# 키트 · bookkit · 시험 책 이름
KIT = HERE.parents[1]
BK = KIT / "bookkit"
NAME = "_nm"
MAGIC = KIT / ".agents" / "skills" / "codex-hub" / "magic.py"
SHOTS = HERE / "shots"


def free_port():
    """페이지 서버(+100)까지 비어 있는 포트 — 아무 번호나 골라 둘 다 잡히는지(윈도우는 OS 가 주는 번호가 연달아 나와 +100 이 예약 구간에 걸리기 쉬움)"""
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

    # 단언 하나
    def check(ok, what, detail=""):
        print(("  ok   " if ok else "  FAIL ") + what + (f" | {str(detail)[:200]}" if detail and not ok else ""), flush=True)
        if not ok:
            fails.append(what)

    tmp = Path(tempfile.mkdtemp(prefix="note_magic_"))
    root = tmp / "proj"
    book = root / "bookkit" / "books" / NAME
    # 시험 책 — 양식 + 예시 계약 · 1차판
    shutil.copytree(BK / "template", book, ignore=shutil.ignore_patterns("dist", "__pycache__"))
    meta = book / "content" / "meta.py"
    meta.write_text(meta.read_text(encoding="utf-8").replace('"doc": "",', f'"doc": "{NAME}",', 1), encoding="utf-8")
    (book / "contracts").mkdir(exist_ok=True)
    for n in ("facts", "reqs", "steps"):
        shutil.copy(BK / "contracts" / "example" / f"{n}.json", book / "contracts" / f"{n}.json")
    shutil.copy(BK / "notes.py", root / "bookkit" / "notes.py")
    r = subprocess.run([sys.executable, str(BK / "engine" / "build_book.py"), str(book), "--stage", "1"], capture_output=True, text=True,
                       encoding="utf-8")
    check(r.returncode == 0, "시험 책 1차판 빌드", r.stdout[-300:] + r.stderr[-300:])
    # 허브 등록(2ND) · 가짜 codex
    hub = root / ".codex-hub"
    (hub / "sessions").mkdir(parents=True)
    reg = hub / "sessions" / "2nd.json"
    reg.write_text(json.dumps({"nick": "2nd", "thread": "019a-2nd", "registered_at": "2026-11-03 00:00:00"}), encoding="utf-8")
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
    dv = subprocess.Popen([sys.executable, str(HERE.parent / "devview.py"), str(root), "--host", "127.0.0.1", "--port", str(port)],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
    nf = book / "notes.json"

    # 가짜 codex 가 받은 인자 목록
    def queued():
        return [json.loads(x) for x in log.read_text(encoding="utf-8").splitlines()] if log.is_file() else []

    try:
        url = f"http://127.0.0.1:{port + 100}/bookkit/books/{NAME}/dist/{NAME}.html"
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

            # 블록에 스티커 붙이기 → 반환 노트 요소
            def stick(block, text):
                pi = pg.evaluate(f"+document.querySelector('#book [data-id=\"{block}\"]').closest('.page').dataset.pi")
                pg.evaluate(f"window.__book.go({pi})")
                pg.wait_for_timeout(300)
                pg.click("#bMemo")
                box = pg.locator(f'#book [data-id="{block}"]').bounding_box()
                pg.mouse.click(box["x"] + 40, box["y"] + 10)
                note = pg.locator(".note").last
                check(note.locator(".nw").is_hidden(), f"새 메모({block}) — 🪄 숨김(접수 전)")
                note.locator("textarea").fill(text)
                note.locator(".nf button:not(.nw)").click()
                pg.wait_for_selector(".note .nt:has-text('접수')", timeout=5000)
                return pg.locator(".note").last

            note = stick("s3-Q1", "최적 기준을 왜 총거리로 잡나?")
            wb, sb = note.locator(".nw").bounding_box(), note.locator(".nf button:not(.nw)").bounding_box()
            check(note.locator(".nw").is_visible() and wb["x"] + wb["width"] <= sb["x"], "접수된 메모 — 🪄 단추가 «수정» 왼쪽", (wb, sb))
            nid = json.loads(nf.read_text(encoding="utf-8"))[0]["id"]
            note.locator(".nw").click()
            ok = pg.wait_for_function("[...document.querySelectorAll('.note .ne')].some((e) => !e.hidden && e.textContent.includes('보냄'))", timeout=8000)
            check(bool(ok) and "보냄" in note.locator(".ne").inner_text(), "🪄 → «보냄 · 2ND 답 대기»", note.locator(".ne").inner_text())
            q = queued()
            msg = q[-1][-1] if q else ""
            rid = msg.rsplit(" ", 1)[-1]
            check(q and q[-1][:3] == ["queue", "--thread", "019a-2nd"], "가짜 codex — 2ND thread 로 queue", q[-1:])
            check(msg == f"--message=🪄 책 ‹{NAME}› 스티커 질문: 최적 기준을 왜 총거리로 잡나? (블록 s3-Q1)\n"
                         f"스티커 {nid} — 답에 짧은 제목(--title · 20자 안팎)도 달 것\n$2nd-magic {rid}",
                  "queue 글 = 🪄 책 ‹…› 스티커 질문: 원문 (블록 …) + 스티커 id · 짧은 제목 지시 + 끝 줄 $2nd-magic 요청id", msg)
            req = json.loads((hub / "requests" / f"{rid}.json").read_text(encoding="utf-8"))
            t = req["target"]
            check(req["role"] == "2nd" and req["view"] == "book" and t["kind"] == "note" and t["note"] == nid and t["block"] == "s3-Q1"
                  and t["notes_file"] == f"bookkit/books/{NAME}/notes.json", "요청 파일 — 2ND · view book · 답 자리 note(스티커 id · 블록 · notes.json)", t)
            check(json.loads(nf.read_text(encoding="utf-8"))[0].get("magic_rid") == rid, "notes.json 에 magic_rid")
            pg.screenshot(path=str(SHOTS / "note_magic_sent.png"))
            # 답 전 다시 누르면 409 → «이미 보냄»
            note.locator(".nw").click()
            pg.wait_for_function("[...document.querySelectorAll('.note .ne')].some((e) => e.textContent.includes('이미 보냄'))", timeout=5000)
            check(len(queued()) == 1, "답 전 다시 누름 — «이미 보냄» · queue 안 함", len(queued()))
            # 2ND 가 답 넣기(magic.py show · answer-note) → 새로고침 뒤 초록 답 칸
            menv = dict(os.environ, CODEX_HUB_DIR=str(hub), CODEX_THREAD_ID="019a-2nd", PYTHONUTF8="1")
            r = subprocess.run([sys.executable, str(MAGIC), "show", rid], cwd=root, env=menv, capture_output=True, text=True, encoding="utf-8")
            check(r.returncode == 0 and "블록 s3-Q1" in r.stdout and f"answer-note {rid}" in r.stdout, "magic.py show — 책 · 블록 · 답 자리 note", r.stdout + r.stderr)
            r = subprocess.run([sys.executable, str(MAGIC), "answer-note", rid, "README 가 기준을 말하지 않아 총거리를 기본 가정으로 둔다.",
                                "--title", "최적 기준"], cwd=root, env=menv, capture_output=True, text=True, encoding="utf-8")
            check(r.returncode == 0 and "답 달음" in r.stdout and json.loads(nf.read_text(encoding="utf-8"))[0].get("title") == "최적 기준",
                  "magic.py answer-note --title — 답 · 제목", r.stdout + r.stderr)
            pg.reload()
            pg.wait_for_function("window.__book && window.__book.ready", timeout=60000)
            pi = pg.evaluate("+document.querySelector('#book [data-id=\"s3-Q1\"]').closest('.page').dataset.pi")
            pg.evaluate(f"window.__book.go({pi})")
            pg.wait_for_timeout(500)
            row = pg.locator("#spQa .qr")
            check(pg.locator(".note").count() == 0 and row.count() == 1 and row.locator(".qrh").inner_text() == "Q1. 최적 기준",
                  "새로고침 뒤 스티커는 빠지고 아래 질문 줄에 «Q1. 최적 기준»")
            row.locator(".qrh").click()
            check("기본 가정" in row.locator(".qrb").inner_text() and row.locator(".qrb").is_visible(), "행 펼침 — 답 글")
            pg.screenshot(path=str(SHOTS / "note_magic_answer.png"))
            # 2ND 미등록 → «2ND 미연결»
            reg.unlink()
            # 다른 쪽의 블록(같은 블록이면 첫 스티커 위를 눌러 새 메모가 안 생김)
            other = pg.evaluate("(() => { const p0 = document.querySelector('#book [data-id=\"s3-Q1\"]').closest('.page');"
                                " return [...document.querySelectorAll('#book .page [data-id]')].find((b) => b.closest('.page') !== p0"
                                " && b.getBoundingClientRect().height > 20).dataset.id; })()")
            note = stick(other, "두 번째 질문")
            note.locator(".nw").click()
            pg.wait_for_function("[...document.querySelectorAll('.note .ne')].some((e) => e.textContent.includes('2ND 미연결'))", timeout=5000)
            check("2ND 미연결" in note.locator(".ne").inner_text() and len(queued()) == 1, "2ND 미등록 — «2ND 미연결» · queue 안 함")
            pg.screenshot(path=str(SHOTS / "note_magic_offline.png"))
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
