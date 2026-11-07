"""키트 devview 시험 — 빈 저장소로 다시 열어도 보던 탭 · 파일 · 보기가 돌아오나 + md 표 칸 편집

    python3 devview/tests/test_restore.py      (키트 루트에서 · 윈도우는 py -3)

- 대회 Browser 도구가 다른 도구에서 돌아올 때 빈 저장소로 페이지를 새로 여는 것을 «새 브라우저 컨텍스트»로 흉내
- 홈 폴더를 임시로 바꿔(~/.devview/state.json) 유저 기록과 안 섞인다
- 단언 대상은 관측 결과: 열린 탭 · 활성 파일 · 보기 · 디스크 바이트 · state.json
"""
import json
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


def wait_for(fn, timeout=8.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            v = fn()
            if v:
                return v
        except Exception:
            pass
        time.sleep(0.1)
    return None


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main():
    tmp = Path(tempfile.mkdtemp(prefix="dv_restore_"))
    root = tmp / "ws"
    root.mkdir()
    (root / "README.md").write_text("# 읽어 보기\n", encoding="utf-8")
    (root / "a.md").write_text("# 가\n\n| 이름 | 판정 |\n|---|---|\n| 가 | **필수** |\n", encoding="utf-8")
    (root / "b.py").write_text("print('b')\n", encoding="utf-8")
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
    state = home / ".devview" / "state.json"
    try:
        with sync_playwright() as pw:
            br = pw.chromium.launch(headless=True)

            def page():
                pg = br.new_context(viewport={"width": 1400, "height": 900}).new_page()   # 새 컨텍스트 = 빈 저장소
                pg.goto(base)
                pg.wait_for_function("document.documentElement.dataset.ready === '1'", timeout=40000)
                return pg

            # ① 첫 방문: 파일 둘을 열고 Git 보기로 바꿈
            pg = page()
            pg.evaluate("p => window.devview.openFile(p, {})", "b.py")
            pg.evaluate("p => window.devview.openFile(p, {})", "a.md")
            pg.evaluate("v => window.devview.showView(v)", "git")
            ok = wait_for(lambda: state.exists() and '"active"' in state.read_text(encoding="utf-8")
                          and "a.md" in state.read_text(encoding="utf-8") and "git" in state.read_text(encoding="utf-8"))
            check("서버에 보던 상태 저장(state.json)", ok, state.read_text(encoding="utf-8")[:160] if state.exists() else "없음")
            pg.context.close()

            # ② 빈 저장소로 다시 열기 = Browser 도구 복귀
            pg = page()
            tabs = pg.evaluate("() => [...document.querySelectorAll('[data-tab], .dv-tab')].map(e => e.dataset.tab || e.title || e.textContent)")
            act = pg.evaluate("() => window.devview.activePath()")
            view = pg.evaluate("() => document.documentElement.dataset.view || document.body.dataset.view || ''")
            check("빈 저장소로 열어도 활성 파일 복원", act == "a.md", act)
            check("열었던 탭 복원(b.py · a.md)", any("b.py" in str(t) for t in tabs) and any("a.md" in str(t) for t in tabs), tabs)
            check("보기(Git) 복원", wait_for(lambda: pg.locator("#gitView").is_visible() or "git" in view), view)

            # ③ md 표 칸 편집(키트 번들)
            pg.evaluate("v => window.devview.showView(v)", "code")
            pg.evaluate("p => window.devview.openFile(p, {})", "a.md")
            tw = ".cm-tablew >> visible=true"
            check("md 표 위젯", wait_for(lambda: pg.locator(tw).count() == 1))
            pg.locator(tw).first.locator("tr").nth(1).locator("td").nth(1).click()
            check("칸 클릭 → 표 유지 · 칸 원문", pg.locator(".cm-cell-edit").inner_text() == "**필수**" and pg.locator(".cm-traw").count() == 0)
            pg.keyboard.press("Control+A")
            pg.keyboard.type("권장")
            pg.keyboard.press("Enter")
            check("칸 확정 → 디스크 그 칸만", wait_for(lambda: (root / "a.md").read_text(encoding="utf-8")
                                                   == "# 가\n\n| 이름 | 판정 |\n|---|---|\n| 가 | 권장 |\n"),
                  (root / "a.md").read_text(encoding="utf-8"))
            br.close()
    finally:
        proc.kill()
        proc.wait(5)
    bad = [n for n, ok in RESULTS if not ok]
    print(f"결과: {'모두 통과' if not bad else '실패 ' + str(len(bad)) + '개'} ({len(RESULTS)}개)")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
