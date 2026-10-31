"""키트 devview 시험 — 문서 바로 가기(Alt+A · Alt+D)는 작업 폴더 docs/ 만 연다(kit/docs 원본 양식은 안 연다)

    python3 devview/tests/test_doc_keys.py      (키트 루트에서 · 윈도우는 py -3)

- 임시 작업 폴더: docs/ONTOLOGY.md 는 있음 · ADR.md 는 kit/docs 에만 있음
- 단언 대상은 관측 결과: 열린 파일 경로 · 알림 글자
"""
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

DEVVIEW = Path(__file__).resolve().parent.parent / "devview.py"
RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'PASS' if ok else 'FAIL'} | {name}{' | ' + str(detail)[:200] if detail else ''}", flush=True)


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main():
    tmp = Path(tempfile.mkdtemp(prefix="dv_dockeys_"))
    root = tmp / "ws"
    (root / "docs").mkdir(parents=True)
    (root / "kit" / "docs").mkdir(parents=True)
    (root / "docs" / "ONTOLOGY.md").write_text("# 루트 지도\n", encoding="utf-8")
    (root / "kit" / "docs" / "ONTOLOGY.md").write_text("# 키트 양식\n", encoding="utf-8")
    (root / "kit" / "docs" / "ADR.md").write_text("# 키트 양식 ADR\n", encoding="utf-8")
    home = tmp / "home"
    home.mkdir()
    env = dict(os.environ, HOME=str(home), USERPROFILE=str(home))
    port = free_port()
    proc = subprocess.Popen([sys.executable, str(DEVVIEW), str(root), "--host", "127.0.0.1", "--port", str(port)],
                            env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}/"
    while proc.poll() is None:
        try:
            urllib.request.urlopen(base + "api/info", timeout=1).read()
            break
        except OSError:
            time.sleep(0.1)
    try:
        with sync_playwright() as pw:
            br = pw.chromium.launch(headless=True)
            pg = br.new_context(viewport={"width": 1400, "height": 900}).new_page()
            pg.goto(base)
            pg.wait_for_function("document.documentElement.dataset.ready === '1'", timeout=40000)

            pg.keyboard.press("Alt+d")
            pg.wait_for_timeout(1500)
            act = pg.evaluate("() => window.devview.activePath()")
            check("Alt+D → 루트 docs/ONTOLOGY.md", act == "docs/ONTOLOGY.md", act)

            pg.keyboard.press("Alt+a")
            pg.wait_for_timeout(1500)
            act = pg.evaluate("() => window.devview.activePath()")
            body = pg.inner_text("body")
            check("Alt+A → kit/docs/ADR.md 를 열지 않음", act != "kit/docs/ADR.md", act)
            check("Alt+A → «docs/ADR.md 없음» 알림", "docs/ADR.md 없음" in body)
            br.close()
    finally:
        proc.kill()
        proc.wait(5)
    bad = [n for n, ok in RESULTS if not ok]
    print(f"결과: {'모두 통과' if not bad else '실패 ' + str(len(bad)) + '개'} ({len(RESULTS)}개)")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
