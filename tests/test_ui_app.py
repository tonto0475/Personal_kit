# 화면 테마(src/ui/theme.py) · 앱 기동(src/ui/app.py) 시험 — 토큰 값 · 글꼴 파일 · 서버를 띄워 HTTP 200 · 종료는 그 프로세스만
import os
import re
import socket
import subprocess
import sys
import time

import httpx

from src.ui import theme

# 저장소 루트 — 앱을 python -m 으로 띄울 작업 폴더
ROOT = theme.FONT_FILE.parents[2]
# 색 토큰 이름 전체(공통 지시 고정 목록)
COLOR_TOKENS = ["BG_BASE", "BG_WINDOW", "BG_PANEL", "NEUTRAL", "BORDER", "TEXT", "TEXT_DIM", "TEXT_DISABLED",
                "ACCENT", "ACCENT_HOVER", "ACCENT_DIM", "ON_ACCENT", "HOVER", "OK", "NG", "WAIT",
                "ROW_BG_NG", "ROW_BG_WAIT", "SPEC_LINE"]


# 토큰이 전부 있고 #rrggbb 모양 · 민트 시그니처 · 검정 바탕
def test_theme_tokens():
    # 토큰 이름
    for name in COLOR_TOKENS:
        assert re.fullmatch(r"#[0-9a-fA-F]{6}", getattr(theme, name)), name
    assert theme.ACCENT == "#2BE88A"
    assert theme.BG_BASE == "#101014"
    assert theme.FONT == "Pretendard"


# 글꼴 파일이 저장소 안에 있음(CDN 없이 오프라인) · CSS 가 그 파일과 토큰 색을 씀
def test_theme_font_and_css():
    assert theme.FONT_FILE.is_file()
    # 페이지 CSS
    css = theme._page_css()
    assert "{}/{}".format(theme.FONT_URL, theme.FONT_FILE.name) in css
    assert theme.BG_BASE in css and theme.OK in css and theme.NG in css
    assert "http" not in css


# 앱을 빈 포트로 띄워 메인 · 글꼴 주소가 200 인지. 실패 신호 = 프로세스 종료(로그를 그대로 보여 줌)
def test_app_boots():
    # 빈 포트 — OS 가 골라 줌
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    # 앱 환경 — PORT 지정 · pytest · NiceGUI 시험 표식 제거(남으면 앱이 시험 모드로 떠 PORT 를 무시)
    env = {k: v for k, v in os.environ.items() if not k.startswith(("PYTEST_", "NICEGUI_"))}
    env.update(PORT=str(port), PYTHONUTF8="1")
    # 앱 프로세스
    proc = subprocess.Popen([sys.executable, "-m", "src.ui.app"], cwd=str(ROOT), env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        # 응답 상태 — 뜰 때까지 None
        status = None
        # 기동 대기 상한(무한 대기 방지용 — 판정은 프로세스 종료 · 응답 코드로)
        deadline = time.monotonic() + 60
        while status is None and time.monotonic() < deadline:
            if proc.poll() is not None:
                raise AssertionError("앱 종료 (코드 {}): {}".format(proc.returncode, proc.stdout.read().decode(
                    "utf-8", "replace")))
            try:
                status = httpx.get("http://127.0.0.1:{}/".format(port), timeout=2).status_code
            # 아직 안 뜸
            except httpx.TransportError:
                time.sleep(0.3)
        assert status == 200
        # 메인 페이지 HTML
        html = httpx.get("http://127.0.0.1:{}/".format(port), timeout=5).text
        assert "API" in html
        assert httpx.get("http://127.0.0.1:{}{}/{}".format(port, theme.FONT_URL, theme.FONT_FILE.name),
                         timeout=5).status_code == 200
    finally:
        # 이 시험이 띄운 프로세스만 종료
        proc.terminate()
        proc.wait(timeout=10)
