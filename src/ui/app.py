# 앱 시작점 — 빈 페이지 · 상단 바 · 하단 상태바(연결 램프 자리) · 테마 적용. 실행: python3 -m src.ui.app
import os

from nicegui import ui

from src.ui.theme import NG, OK, TEXT_DIM, WAIT, apply_theme

# 앱 제목 — 상단 바 · 브라우저 탭
APP_TITLE = "앱"
# 기본 포트 — 환경변수 PORT 가 있으면 그 값(유저 결정: 0.0.0.0 · 3000)
DEFAULT_PORT = 3000
# 바인딩 주소 — Browser 도구 · 다른 기기에서 보려면 0.0.0.0
HOST = "0.0.0.0"

# 램프 상태 → 색 · 글자
LAMP_STATES = {"ok": (OK, "연결"), "ng": (NG, "끊김"), "wait": (WAIT, "확인 중"), "none": (TEXT_DIM, "미설정")}


# 연결 램프 — 점 + «이름 상태» 글자. 반환한 함수로 상태를 바꿈(외부 연동이 생기면 시작 직후 확인 결과로 호출)
# name: 연결 대상 이름(API · DB)
def lamp(name):
    # 램프 줄
    with ui.row().classes("items-center gap-1 no-wrap"):
        # 색 점
        dot = ui.icon("circle").style("font-size: 10px")
        # 상태 글자
        label = ui.label().classes("whitespace-nowrap")

    # 상태 바꾸기
    # state: "ok" · "ng" · "wait" · "none" / detail: 뒤에 붙일 사유(주소 · timeout 등)
    def set_state(state, detail=""):
        # 점 색 · 상태 글자
        color, word = LAMP_STATES[state]
        dot.style("color: {}".format(color))
        label.set_text("{} {}{}".format(name, word, " (" + detail + ")" if detail else ""))

    set_state("wait")
    return set_state


# 메인 페이지 — 상단 바 · 빈 본문 · 하단 상태바
@ui.page("/")
def index():
    apply_theme()
    # 상단 바
    with ui.header().classes("items-center px-4 py-2 border-b"):
        ui.label(APP_TITLE).classes("text-lg font-semibold")
    # 본문 — 빈 자리
    ui.column().classes("w-full p-4")
    # 하단 상태바 — 연결 램프 자리
    with ui.footer().classes("items-center px-4 py-1 border-t text-sm"):
        # 연결 램프 상태 바꾸는 함수 — 외부 연동이 생기면 시작 직후 확인 결과로 "ok" · "ng"
        set_api = lamp("API")
        set_api("none")
        ui.space()
        ui.label("v0").style("color: {}".format(TEXT_DIM))


# 서버 실행 — reload 끔(대회장에서 파일 감시로 두 번 뜨는 일 방지) · 브라우저 자동 열기 끔
def main():
    # 포트 — 환경변수 PORT 우선
    port = int(os.environ.get("PORT", DEFAULT_PORT))
    ui.run(host=HOST, port=port, title=APP_TITLE, reload=False, show=False, dark=True)


if __name__ == "__main__":
    main()
