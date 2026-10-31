# 견본 앱 ① 현황판 — Tabler 세로 메뉴형(O2): 상단 바 · 왼쪽 세로 메뉴(접기) · 숫자 카드 줄 · 그래프 카드 · 표 · 하단 상태바 램프 · 빈 상태 · 오류 띠
#   실행: python3 -m ref.sample_apps.dashboard → http://<주소>:<PORT 또는 3000>/   (?demo=empty 빈 상태 · ?demo=fail 오류 띠)
#   대회장에서 바꿀 곳: «⭐ 바꿀 곳» 표시 — APP_TITLE · MENU · load_data · 표 열(table_columns)
import os
import sys
import time
from pathlib import Path

# 저장소 루트 — 파일을 직접 실행해도 src · ref 를 찾게 sys.path 앞에 추가
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from nicegui import ui  # noqa: E402

from ref.gallery.charts import bar_target_option, chart_card, line_option, summary  # noqa: E402
from ref.table_form import number_col, status_col, table_form, text_col  # noqa: E402
from src.core.errors import AppError, ExternalError, InternalError  # noqa: E402
from src.ui.app import lamp  # noqa: E402
from src.ui.theme import (  # noqa: E402
    ACCENT, BG_WINDOW, BORDER, NEUTRAL, NG, ROW_BG_NG, TEXT, TEXT_DIM, apply_theme)

# ⭐ 바꿀 곳 — 앱 제목(상단 바 · 브라우저 탭)
APP_TITLE = "생산 현황"
# ⭐ 바꿀 곳 — 왼쪽 메뉴 [(이름, 아이콘, 이동할 구역 id)] — 아이콘은 Material Icons 이름
MENU = [("현황", "dashboard", "sec-kpi"), ("추이", "show_chart", "sec-chart"), ("로트", "table_rows", "sec-table")]
# 기본 포트 — 환경변수 PORT 가 있으면 그 값
DEFAULT_PORT = 3000
# 바인딩 주소 — IDE Browser 도구 · 다른 기기에서 보려면 0.0.0.0
HOST = "0.0.0.0"
# 왼쪽 메뉴 폭 · 접었을 때 폭(px)
DRAWER_WIDTH_PX = 220
DRAWER_MINI_PX = 60
# 빈 상태 문구
EMPTY_TEXT = "데이터 없음"


# 레이아웃 CSS — 메뉴 · 숫자 카드 · 오류 띠 · 빈 상태(색은 theme 토큰)
def _layout_css():
    return """
.side-menu {{ background: {win}; border-right: 1px solid {border}; }}
.side-menu .menu-item {{ color: {dim}; border-radius: 6px; margin: 2px 8px; min-height: 40px; }}
.side-menu .menu-item:hover {{ background: {neutral}; color: {text}; }}
.side-menu .menu-item.menu-active {{ background: {neutral}; color: {accent}; }}
.menu-head {{ color: {dim}; letter-spacing: .06em; }}
.page-pre {{ color: {dim}; letter-spacing: .06em; }}
.kpi-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 16px; width: 100%; }}
.chart-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(440px, 1fr)); gap: 16px; width: 100%; }}
.q-card {{ border: 1px solid {border}; box-shadow: none; }}
.err-band {{ background: {row_ng}; border-left: 4px solid {ng}; border-radius: 4px; color: {text}; }}
.err-band .err-icon {{ color: {ng}; }}
.err-band .err-text {{ word-break: break-all; white-space: normal; }}
.empty-box {{ color: {dim}; }}
""".format(win=BG_WINDOW, border=BORDER, dim=TEXT_DIM, neutral=NEUTRAL, text=TEXT, accent=ACCENT,
           row_ng=ROW_BG_NG, ng=NG)


# ===== 데이터 =====

# ⭐ 바꿀 곳 — 현황 데이터(가짜). 대회장에서는 src/api 조회 함수 결과로 같은 모양 dict 를 채움
#   kpis: 숫자 카드 [{name 이름 · value 값 · unit 단위 · target 목표 · higher 클수록 좋음 여부 · digits 소수 자리}]
#   days · trend · trend_unit · trend_ref: 선 그래프 / lines · defect · defect_target: 막대+목표선 / rows: 표 행
def load_data():
    # 날짜 14개
    days = ["10/{:02d}".format(d) for d in range(17, 31)]
    # 일별 생산량 · 계획
    output = [962, 1004, 1011, 987, 1032, 1046, 998, 1021, 1050, 1018, 976, 1039, 1062, 1032]
    plan = [1000] * len(days)
    # 라인 이름 · 라인별 불량률
    lines = ["L1", "L2", "L3", "L4", "L5", "L6"]
    defect = [1.2, 0.8, 2.6, 0.5, 2.3, 0.9]
    # 표 행 상태 순환
    status = ["OK", "OK", "NG", "OK", "대기"]
    # 표 행 — 로트 18개
    rows = [{"lot": "LOT-{:04d}".format(2400 + i), "line": lines[i % 6],
             "thickness": round(50 + ((i * 37) % 21 - 10) / 10, 2), "defect": round(((i * 13) % 30) / 10, 1),
             "status": status[i % 5]} for i in range(18)]
    return {
        "kpis": [
            {"name": "생산량", "value": output[-1], "unit": "개", "target": 1000, "higher": True, "digits": 0},
            {"name": "수율", "value": 98.4, "unit": "%", "target": 98.0, "higher": True, "digits": 1},
            {"name": "불량률", "value": 2.3, "unit": "%", "target": 2.0, "higher": False, "digits": 1},
            {"name": "대기 로트", "value": 3, "unit": "건", "target": 5, "higher": False, "digits": 0},
        ],
        "days": days, "trend": {"생산량": output, "계획": plan}, "trend_unit": "개", "trend_ref": 1000,
        "lines": lines, "defect": defect, "defect_target": 2.0,
        "rows": rows,
    }


# 빈 데이터 — load_data 와 같은 모양 · 목록이 전부 비어 있음
def empty_data():
    return {"kpis": [], "days": [], "trend": {}, "trend_unit": "", "trend_ref": None,
            "lines": [], "defect": [], "defect_target": None, "rows": []}


# 데이터 가져오기 — demo 값으로 빈 상태 · 외부 실패를 흉내(그림 · 시험용)
# demo: "" 정상 · "empty" 빈 데이터 · "fail" 외부 실패
def fetch(demo=""):
    if demo == "fail":
        raise ExternalError("현황 API 연결 실패 (api.example.com:443 · HTTP 503)")
    if demo == "empty":
        return empty_data()
    return load_data()


# 숫자 카드 판정 — 목표 대비 «달성 · 미달» + 차이 수치(참거짓만 돌려주지 않음)
# value: 값 / target: 목표 / higher: 클수록 좋음 여부
def judge_kpi(value, target, higher):
    # 차이 — 값 - 목표
    diff = value - target
    # 달성 여부
    ok = diff >= 0 if higher else diff <= 0
    return {"state": "ok" if ok else "ng", "word": "달성" if ok else "미달", "diff": diff}


# ⭐ 바꿀 곳 — 표 열 정의(table_form 열 함수)
def table_columns():
    return [text_col("lot", "로트"), text_col("line", "라인", 80),
            number_col("thickness", "두께", digits=2, target=None, unit="µm"),
            number_col("defect", "불량률", digits=1, target=2.0, unit="%"),
            status_col("status")]


# ===== 화면 조각 =====

# 빈 상태 — 가운데 아이콘 + 문구 한 줄
# text: 문구
def empty_state(text=EMPTY_TEXT):
    with ui.column().classes("empty-box w-full items-center justify-center gap-2 py-16") as box:
        ui.icon("inbox").style("font-size: 40px")
        ui.label(text).classes("text-base")
    return box


# 오류 띠 — 본문 맨 위 한 줄(«[종류] 메시지») · 닫기 단추. 반환: 띄우는 함수 show(err) · 숨기는 함수 hide()
def error_band():
    with ui.row().classes("err-band w-full items-center no-wrap gap-2 px-3 py-2") as band:
        ui.icon("error").classes("err-icon")
        # 문구
        text = ui.label("").classes("err-text grow")
        ui.button(icon="close", on_click=lambda: band.set_visibility(False)).props("flat dense round size=sm")
    band.set_visibility(False)

    # 띄우기 — AppError 면 screen_text(), 그 밖의 예외는 내부 오류로 감쌈
    # err: 예외
    def show(err):
        if not isinstance(err, AppError):
            err = InternalError("{}: {}".format(type(err).__name__, err))
        text.set_text(err.screen_text())
        band.set_visibility(True)

    # 숨기기
    def hide():
        band.set_visibility(False)

    return show, hide


# 숫자 카드 하나 — 이름 · 값 + 단위 · 목표 대비 배지 + «목표 · 차이»
# kpi: load_data 의 kpis 항목
def kpi_card(kpi):
    # 판정
    j = judge_kpi(kpi["value"], kpi["target"], kpi["higher"])
    # 숫자 → 글자 형식
    fmt = "{:,." + str(kpi["digits"]) + "f}"
    with ui.card().classes("p-4 gap-1 kpi-card"):
        ui.label(kpi["name"]).classes("text-sm text-dim")
        with ui.row().classes("items-baseline gap-1 no-wrap"):
            ui.label(fmt.format(kpi["value"])).classes("text-3xl font-semibold whitespace-nowrap")
            ui.label(kpi["unit"]).classes("text-sm text-dim")
        # 배지 · 목표 줄 — 칸이 좁으면 목표 글자가 다음 줄로(잘림 대신)
        with ui.row().classes("items-center gap-x-2 gap-y-1"):
            ui.label(j["word"]).classes("badge-{} text-xs whitespace-nowrap".format(j["state"]))
            ui.label("목표 {} {} · 차이 {}".format(fmt.format(kpi["target"]), kpi["unit"],
                                                ("+" if j["diff"] > 0 else "") + fmt.format(j["diff"]))) \
                .classes("text-xs text-dim whitespace-nowrap")


# 구역 제목 — 구역 id(메뉴 이동 대상) + 제목 글자
# anchor: 구역 id / title: 제목
def section_title(anchor, title):
    ui.label(title).classes("text-base font-semibold mt-2").props("id={}".format(anchor))


# 현황 본문 — 숫자 카드 줄 · 그래프 카드 2개 · 표. 데이터가 비면 빈 상태
# data: load_data 모양 dict
def dashboard_body(data):
    if not data["kpis"] and not data["rows"]:
        with ui.card().classes("w-full"):
            empty_state()
        return
    section_title("sec-kpi", "오늘")
    with ui.element("div").classes("kpi-grid"):
        # 숫자 카드 항목
        for kpi in data["kpis"]:
            kpi_card(kpi)
    section_title("sec-chart", "추이")
    with ui.element("div").classes("chart-grid"):
        # 선 그래프 옵션 — 세로축을 0 부터가 아니라 값 범위로(추이가 납작해지지 않게)
        trend_opt = line_option(data["days"], data["trend"], title="일별 생산량", unit=data["trend_unit"],
                                ref_line=data["trend_ref"])
        trend_opt["yAxis"]["scale"] = True
        chart_card(trend_opt, summary(data["trend"]["생산량"], data["trend_unit"], 0), height_px=260)
        # 목표 초과 라인 수
        over = sum(v > data["defect_target"] for v in data["defect"])
        chart_card(bar_target_option(data["lines"], data["defect"], title="라인별 불량률", unit="%",
                                     ref_line=data["defect_target"]),
                   [("목표", "{} %".format(data["defect_target"])), ("초과", "{} 라인".format(over))], height_px=260)
    section_title("sec-table", "로트")
    with ui.card().classes("w-full p-4"):
        table_form(table_columns(), data["rows"], status_field="status", page_size=10, height_px=520)


# 틀 — 상단 바 · 왼쪽 세로 메뉴(접기) · 하단 상태바(램프). 반환 dict:
#   header_right: 상단 바 오른쪽 자리 / lamps: 상태바 램프 줄 / set_api: API 램프 함수 / stamp: 갱신 시각 글자
# title: 앱 제목 / menu: [(이름, 아이콘, 구역 id)]
def shell(title=APP_TITLE, menu=MENU):
    apply_theme()
    ui.add_css(_layout_css())
    # 메뉴 접힘 여부 — 목록 한 칸(안쪽 함수에서 바꿈)
    mini = [False]
    with ui.left_drawer(value=True, fixed=True).props(
            "width={} mini-width={} :breakpoint=0".format(DRAWER_WIDTH_PX, DRAWER_MINI_PX)) \
            .classes("side-menu p-0") as drawer:
        ui.label("메뉴").classes("menu-head text-xs px-5 pt-4 pb-2 q-mini-drawer-hide")
        with ui.list().classes("w-full"):
            # 메뉴 항목 요소 목록
            items = []
            # 메뉴 이름 · 아이콘 · 구역 id
            for name, icon, anchor in menu:
                # 항목 — 누르면 그 구역으로 스크롤 · 선택 표시
                with ui.item(on_click=lambda a=anchor, n=name: _go(a, n)).classes("menu-item") as item:
                    with ui.item_section().props("avatar").style("min-width: 36px"):
                        ui.icon(icon).style("font-size: 20px")
                    with ui.item_section().classes("q-mini-drawer-hide"):
                        ui.label(name).classes("whitespace-nowrap")
                item.props("data-name={}".format(name))
                items.append((name, item))
            items[0][1].classes("menu-active")

    # 메뉴 이동 — 구역으로 부드럽게 스크롤 · 선택 표시 옮김
    # anchor: 구역 id / name: 메뉴 이름
    def _go(anchor, name):
        ui.run_javascript("document.getElementById('{}')?.scrollIntoView({{behavior: 'smooth'}})".format(anchor))
        # 항목 이름 · 요소
        for n, it in items:
            if n == name:
                it.classes("menu-active")
            else:
                it.classes(remove="menu-active")

    # 메뉴 접기 · 펴기 — Quasar mini 모드(아이콘만)
    def toggle_menu():
        mini[0] = not mini[0]
        if mini[0]:
            drawer.props("mini")
        else:
            drawer.props(remove="mini")

    with ui.header().classes("items-center px-3 py-2 border-b no-wrap"):
        ui.button(icon="menu", on_click=toggle_menu).props("flat dense round").tooltip("메뉴 접기")
        ui.label(title).classes("text-lg font-semibold whitespace-nowrap")
        ui.space()
        # 상단 바 오른쪽 자리
        header_right = ui.row().classes("items-center gap-2 no-wrap")
    with ui.footer().classes("items-center px-4 py-1 border-t text-sm no-wrap"):
        # 램프 줄
        lamps = ui.row().classes("items-center gap-4 no-wrap")
        with lamps:
            # API 램프 함수
            set_api = lamp("API")
        ui.space()
        # 갱신 시각
        stamp = ui.label("").classes("text-dim whitespace-nowrap")
    return {"header_right": header_right, "lamps": lamps, "set_api": set_api, "stamp": stamp}


# 현황판 페이지 내용 — 틀 + 페이지 제목 + 오류 띠 + 본문(새로고침 가능). 반환: shell 결과 dict + show_error · data
# demo: fetch 로 넘길 흉내 값 / title: 앱 제목
def build(demo="", title=APP_TITLE):
    # 틀 부품
    parts = shell(title)
    # 마지막으로 가져온 데이터 — 대화창이 문맥으로 읽음(목록 한 칸)
    holder = [empty_data()]
    with ui.column().classes("w-full gap-3 p-4"):
        # 오류 띠 띄우기 · 숨기기
        show_error, hide_error = error_band()
        with ui.row().classes("w-full items-end no-wrap"):
            with ui.column().classes("gap-0"):
                ui.label("개요").classes("page-pre text-xs")
                ui.label(title).classes("text-xl font-semibold whitespace-nowrap")
            ui.space()
            ui.button("새로고침", icon="refresh", on_click=lambda: body.refresh()) \
                .props("outline no-caps dense").classes("px-3")

        # 본문 — 가져오기 성공이면 현황, 실패면 오류 띠 + 빈 상태
        @ui.refreshable
        def body():
            try:
                # 현황 데이터
                data = fetch(demo)
            # 외부 실패 · timeout 등
            except AppError as err:
                show_error(err)
                parts["set_api"]("ng", err.kind)
                holder[0] = empty_data()
                with ui.card().classes("w-full"):
                    empty_state()
                return
            hide_error()
            holder[0] = data
            parts["set_api"]("ok", "{}건".format(len(data["rows"])))
            parts["stamp"].set_text("갱신 {}".format(time.strftime("%H:%M:%S")))
            dashboard_body(data)

        body()
    parts.update({"show_error": show_error, "data": holder})
    return parts


# 페이지 — 주소 «/». 쿼리 ?demo=empty · ?demo=fail
# demo: 흉내 값
def index(demo: str = ""):
    build(demo)


# 서버 실행 — reload 끔 · 브라우저 자동 열기 끔
def main():
    ui.page("/")(index)
    ui.run(host=HOST, port=int(os.environ.get("PORT", DEFAULT_PORT)), title=APP_TITLE,
           reload=False, show=False, dark=True)


if __name__ in {"__main__", "__mp_main__"}:
    main()
