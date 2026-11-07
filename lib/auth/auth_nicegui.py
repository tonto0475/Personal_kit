# NiceGUI 로그인 화면 — 아이디 · 비밀번호 입력 → /auth/login 으로 form 전송(브라우저가 쿠키를 받고 next 로 이동) · 실패 문구 · 로그아웃 버튼
#   역할: 화면 쪽 껍데기만 — 판정 · 쿠키는 auth_web 의 /auth/login 이 한다(웹소켓 이벤트로는 쿠키를 못 심어서 일반 form 전송을 쓴다)
#   어디에: app.py 에서 add_auth(app, store, login_url="/login") 다음 add_login_page() 한 번 · 상단 바에 logout_button()
#   실패하면: 틀린 비밀번호 → /login?error=1 로 돌아와 «로그인 실패 (아이디 또는 비밀번호 불일치)» 표시 · add_auth 를 안 불렀으면 /auth/login 이 404
from nicegui import ui

from lib.auth.auth_core import MSG_LOGIN_FAIL
from lib.auth.auth_web import _safe_next


# 로그인 화면 등록
# path: 화면 주소(add_auth 의 login_url 과 같게) / title: 제목 / action: 로그인 경로 / home: next 가 없을 때 이동
def add_login_page(path="/login", title="로그인", action="/auth/login", home="/"):
    # 로그인 화면 — 주소의 error · next 를 읽어 문구 · 숨은 칸에 넣는다
    @ui.page(path)
    def login_page(error: str = "", next: str = ""):
        with ui.card().classes("absolute-center w-80"):
            ui.label(title).classes("text-lg font-semibold")
            # form — 브라우저 기본 전송(name 속성이 붙은 칸만 보내짐)
            with ui.element("form").props('method=post action="{}"'.format(action)).classes("w-full column gap-2"):
                ui.input("아이디").props("name=id autocomplete=username autofocus").classes("w-full")
                ui.input("비밀번호", password=True).props("name=password autocomplete=current-password").classes("w-full")
                ui.element("input").props('type=hidden name=next value="{}"'.format(_safe_next(next, home)))
                if error:
                    ui.label(MSG_LOGIN_FAIL).classes("text-negative text-sm")
                ui.button("로그인").props("type=submit").classes("w-full")

    return login_page


# 로그아웃 버튼 — /auth/logout(GET) 으로 이동 → 쿠키 삭제 후 로그인 화면
# prefix: 로그인 경로 앞머리
def logout_button(prefix="/auth"):
    return ui.button("로그아웃", on_click=lambda: ui.navigate.to(prefix + "/logout")).props("flat dense")
