# 그래프 화면 단축키 — Alt+` = Main · Alt+1~8 = 섹션1~8 · Alt+0 = 섹션0(어느 보기 · 입력 칸 · 그래프 iframe 안에서도)
# + 기호 Alt+Z · X · C · V(입력 칸) · 파일 트리 Alt+Shift+1 — 빈 포트 · 임시 폴더 devview + 헤드리스 크롬(페이지 안 키만 · 실제 키 없음)
#   py -3 tests/test_screen_keys.py
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

DV = Path(__file__).resolve().parents[1] / "devview.py"
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


# 그래프 iframe 의 지금 화면 단추 글(Main · 섹션N) — aria-pressed · 활성 class 중 있는 것
ACTIVE_JS = """() => {
  const bs = [...document.querySelectorAll('button')].filter(b => /^(Main|섹션\\d)$/.test(b.textContent.trim()));
  const on = bs.filter(b => b.getAttribute('aria-pressed') === 'true' || b.getAttribute('aria-selected') === 'true'
    || /(^|\\s)(on|is-on|active|sel|cur)(\\s|$)/.test(b.className));
  return on.length === 1 ? on[0].textContent.trim() : (bs.length ? '?' + bs.map(b => b.className).join('|') : '');
}"""


def main():
    root = Path(tempfile.mkdtemp(prefix="scrkeys_"))
    (root / "a.txt").write_text("hello\n", encoding="utf-8")
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    env = dict(os.environ, DEVVIEW_NO_VAULT="1", HOME=str(root), USERPROFILE=str(root))
    proc = subprocess.Popen([sys.executable, str(DV), str(root), "--host", "127.0.0.1", "--port", str(port), "--page-port", "0",
                             "--start-view", "code"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
    base = f"http://127.0.0.1:{port}"
    try:
        wait(lambda: urllib.request.urlopen(base + "/api/info", timeout=1).read(), 15)
        with sync_playwright() as pw:
            br = pw.chromium.launch(channel="chrome", headless=True)
            pg = br.new_page(viewport={"width": 1500, "height": 900})
            errs = []
            pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto(base + "/")
            pg.wait_for_function("() => typeof document !== 'undefined' && document.querySelector('#bell')", timeout=15000)
            view = lambda: pg.evaluate("() => document.querySelector('.dv-view.is-on, .dv-view[aria-pressed=\"true\"]')?.dataset.view || ''")  # noqa: E731
            ft = lambda: next((f for f in pg.frames if f.locator(".react-flow").count()), None)  # noqa: E731
            active = lambda: (ft() or pg).evaluate(ACTIVE_JS) if ft() else ""  # noqa: E731

            # ① 코드 보기에서 Alt+2 → 그래프 · 섹션2
            pg.mouse.click(700, 450)
            pg.keyboard.press("Alt+Digit2")
            check("① 코드 보기 Alt+2 → 그래프 보기", wait(lambda: view() == "graph"), view())
            check("① 섹션2 화면", wait(lambda: active() == "섹션2", 15), active())
            # ② 그래프 iframe 안에서 Alt+` → Main · Alt+0 → 섹션0 · Alt+8 → 섹션8
            fr = ft()
            fr.locator(".react-flow__pane").click(position={"x": 30, "y": 30})
            fr.locator("body").press("Alt+Backquote")
            check("② 그래프 안 Alt+` → Main", wait(lambda: active() == "Main"), active())
            fr.locator("body").press("Alt+Digit0")
            check("② 그래프 안 Alt+0 → 섹션0", wait(lambda: active() == "섹션0"), active())
            fr.locator("body").press("Alt+Digit8")
            check("② 그래프 안 Alt+8 → 섹션8(설문 탭으로 안 감)", wait(lambda: active() == "섹션8") and view() == "graph", (active(), view()))
            # ③ 입력 칸 안에서도 이동 · 기호는 Alt+Z · X · C · V
            pg.evaluate("() => { const t = document.createElement('textarea'); t.id = 'kt'; t.style.cssText = 'position:fixed;left:200px;top:200px;z-index:99999'; document.body.appendChild(t); }")
            pg.click("#kt")
            for k in ("KeyZ", "KeyX", "KeyC", "KeyV"):
                pg.keyboard.press(f"Alt+{k}")
            val = pg.input_value("#kt")
            check("③ 입력 칸 Alt+Z · X · C · V → ❇️🔎💭📌", val == "❇️🔎💭📌", repr(val))
            pg.keyboard.press("Alt+Digit1")
            check("③ 입력 칸 Alt+1 → 기호 대신 그래프 섹션1", wait(lambda: active() == "섹션1") and pg.input_value("#kt") == val, (active(), pg.input_value("#kt")))
            pg.evaluate("() => document.querySelector('#kt').remove()")
            # ④ 다른 보기(Git)에서도
            pg.keyboard.press("Alt+Digit9")
            check("④ Alt+9 → Git 보기(그대로)", wait(lambda: view() == "git"), view())
            pg.keyboard.press("Alt+Digit5")
            check("④ Git 보기 Alt+5 → 그래프 섹션5", wait(lambda: view() == "graph" and active() == "섹션5"), (view(), active()))
            # ⑤ 파일 트리 = Alt+Shift+1 (코드 보기로 가며 트리 토글)
            tree_on = lambda: pg.evaluate("() => !document.querySelector('#codeView').classList.contains('is-notree')")  # noqa: E731
            pg.keyboard.press("Alt+Shift+Digit1")
            v1, t1 = wait(lambda: view() == "code") and view(), tree_on()
            pg.keyboard.press("Alt+Shift+Digit1")
            time.sleep(0.4)
            t2 = tree_on()
            check("⑤ Alt+Shift+1 → 코드 보기 · 트리 토글", v1 == "code" and t1 != t2, (v1, t1, t2))
            check("페이지 예외 없음", not errs, errs[:3])
            br.close()
    finally:
        proc.terminate()
        proc.wait(5)
    print(f"결과: {sum(R)}/{len(R)}")
    return all(R)


def test_screen_keys():
    assert main()


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
