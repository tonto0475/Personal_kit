# lib/auth NiceGUI 시험 — 실제 NiceGUI 서버(빈 포트 · 자식 프로세스)에 로그인 화면 · 역할 페이지 · 남의 것 403 을 붙여 확인
#   nicegui 가 없으면 건너뜀 · 브라우저 로그인 흐름(form 전송 → 쿠키 → 이동)은 playwright 가 있을 때만(헤드리스)
import os
import socket
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

pytest.importorskip("nicegui")
httpx = pytest.importorskip("httpx")

# 저장소 루트
ROOT = Path(__file__).resolve().parents[2]
# 시험 비밀번호
PW = "test1234"

# 시험 앱 원문 — 운영자 페이지 · 사원 자기 행 페이지 · 행 하나(소유자 확인)
APP_SRC = textwrap.dedent('''
    import sys
    sys.path.insert(0, {root!r})
    from fastapi import Request
    from nicegui import app, ui
    from lib.auth.auth_core import make_test_store, own_rows
    from lib.auth.auth_web import add_auth, deny_if_not_owner, require_role
    from lib.auth.auth_nicegui import add_login_page, logout_button

    ROWS = [{{"no": 1, "owner_id": "E1001"}}, {{"no": 2, "owner_id": "E1002"}}]
    add_auth(app, make_test_store({pw!r}, rounds=1000), login_url="/login")
    add_login_page()

    @ui.page("/")
    @require_role()
    def home(request: Request):
        ui.label("홈 " + request.state.user["id"]).classes("who")
        for r in own_rows(ROWS, request.state.user):
            ui.label("행 {{}}".format(r["no"])).classes("row-item")
        logout_button()

    @ui.page("/admin")
    @require_role("운영자")
    def admin(request: Request):
        ui.label("운영자 화면")

    @ui.page("/rows/{{no}}")
    def row(no: int, request: Request):
        found = next(r for r in ROWS if r["no"] == no)
        deny = deny_if_not_owner(request, found["owner_id"])
        if deny:
            return deny
        ui.label("행 {{}}".format(no))

    ui.run(port={port}, reload=False, show=False)
''')


# 빈 포트 하나
def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# 시험 서버 — 자식 프로세스로 띄우고 /login 이 응답하면 넘겨줌 · 끝나면 그 PID 만 종료
@pytest.fixture(scope="module")
def server(tmp_path_factory):
    # 포트
    port = _free_port()
    # 앱 파일
    app_file = tmp_path_factory.mktemp("auth_ng") / "app_auth_demo.py"
    app_file.write_text(APP_SRC.format(root=str(ROOT), pw=PW, port=port), encoding="utf-8")
    # 환경 — pytest 표시 변수 제거(NiceGUI 가 시험 모드로 착각) · 시험 비밀키(실제 값 아님)
    env = {k: v for k, v in os.environ.items() if not k.startswith("PYTEST")}
    env.update(AUTH_SECRET="test-secret-0123456789", PYTHONUTF8="1")
    # 서버 프로세스
    proc = subprocess.Popen([sys.executable, str(app_file)], env=env, cwd=str(app_file.parent),
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    # 기본 주소
    base = "http://127.0.0.1:{}".format(port)
    try:
        while True:
            if proc.poll() is not None:
                pytest.fail("시험 서버 종료: " + proc.stdout.read().decode("utf-8", "replace")[-2000:])
            try:
                if httpx.get(base + "/login", timeout=2).status_code == 200:
                    break
            except httpx.TransportError:
                time.sleep(0.3)
        yield base
    finally:
        proc.terminate()
        proc.wait(timeout=10)


# 로그인한 httpx 클라이언트
def _client(base, login_id):
    # 클라이언트
    c = httpx.Client(base_url=base, follow_redirects=False)
    assert c.post("/auth/login", json={"id": login_id, "password": PW}).status_code == 200
    return c


# 로그인 전 — 페이지는 /login?next=… 로 이동
def test_redirect_to_login(server):
    # 응답
    r = httpx.get(server + "/admin", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login?next=%2Fadmin"


# 역할 — 사원은 운영자 화면 403 · 운영자는 200
def test_role_page(server):
    assert _client(server, "E1001").get("/admin").status_code == 403
    assert _client(server, "admin").get("/admin").status_code == 200


# 남의 것 보기 403 · 내 것 200
def test_owner_page(server):
    # 사원 클라이언트
    c = _client(server, "E1001")
    assert c.get("/rows/1").status_code == 200
    assert c.get("/rows/2").status_code == 403


# form 실패 — 로그인 화면으로 돌아오며 next 유지
def test_form_fail(server):
    # 응답
    r = httpx.post(server + "/auth/login", data={"id": "E1001", "password": "x", "next": "/admin"})
    assert r.status_code == 303 and r.headers["location"] == "/login?error=1&next=%2Fadmin"


# 브라우저 — /admin 접속 → 로그인 화면 → 틀린 비밀번호 문구 → 사원 로그인 → 홈에 자기 행만 → 로그아웃 → 로그인 화면
def test_browser_flow(server):
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as p:
        # 헤드리스 브라우저
        browser = p.chromium.launch(headless=True)
        # 탭
        page = browser.new_page()
        page.goto(server + "/admin")
        page.wait_for_url("**/login?next=%2Fadmin")
        page.fill("input[name=id]", "E1001")
        page.fill("input[name=password]", "x")
        page.click("button[type=submit]")
        page.wait_for_url("**/login?error=1*")
        assert page.get_by_text("로그인 실패 (아이디 또는 비밀번호 불일치)").is_visible()
        page.goto(server + "/login")
        page.fill("input[name=id]", "E1001")
        page.fill("input[name=password]", PW)
        page.click("button[type=submit]")
        page.wait_for_selector(".who")
        assert page.inner_text(".who") == "홈 E1001"
        assert page.locator(".row-item").all_inner_texts() == ["행 1"]
        page.get_by_text("로그아웃").click()
        page.wait_for_url("**/login")
        browser.close()
