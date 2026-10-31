# 화면 색 · 글꼴 토큰 한 장 + NiceGUI 에 입히는 apply_theme — 화면 코드는 여기 이름만 쓰고 색 값을 박지 않음
#   색 기준: DI 프로젝트 — 민트 시그니처 · 검정 바탕 · 검정 모노톤
#   OK 색은 유저 확인 중 → OK 한 줄만 바꾸면 배지 · 그래프 · 표가 같이 바뀜
from pathlib import Path

from nicegui import app, ui

# ===== 바탕 — 검정 모노톤(깊은 것 → 얕은 것) =====
# 페이지 바탕
BG_BASE = "#101014"
# 창 · 상단 바 · 하단 상태바 바탕
BG_WINDOW = "#18181e"
# 카드 · 패널 바탕
BG_PANEL = "#1c1c24"
# 중립 칸(입력 칸 · 표 머리줄)
NEUTRAL = "#28282e"
# 테두리 · 구분선
BORDER = "#3a3a4a"

# ===== 글자 =====
# 기본 글자
TEXT = "#f8f8f2"
# 보조 글자(단위 · 축 이름)
TEXT_DIM = "#8b8b9a"
# 비활성 글자
TEXT_DISABLED = "#5a5a6a"

# ===== 강조 — 민트 시그니처 =====
# 강조(주 버튼 · 선택 · 그래프 첫 계열)
ACCENT = "#2BE88A"
# 강조 위에 마우스
ACCENT_HOVER = "#4DF2A5"
# 강조 눌림 · 옅은 강조
ACCENT_DIM = "#22C273"
# 강조 바탕 위 글자
ON_ACCENT = "#101014"
# 마우스가 올라간 항목 표시
HOVER = "#ffd54f"

# ===== 상태 — 배지 · 램프 · 이탈 점 =====
# 정상(유저 확인 중 — 이 한 줄만 바꾼다)
OK = "#2BE88A"
# 불량 · 실패 · 연결 끊김
NG = "#ff5555"
# 대기 · 진행 중 · 연결 시도 중
WAIT = "#ffb347"
# 불량 행 바탕
ROW_BG_NG = "#4a1f24"
# 대기 행 바탕
ROW_BG_WAIT = "#4a3416"
# 규격선 · 목표선 · 관리 한계선
SPEC_LINE = "#ffb300"

# ===== 글꼴 =====
# 글꼴 이름(CSS font-family)
FONT = "Pretendard"
# 글꼴 파일 — 저장소 루트 assets/fonts(대회장 오프라인 대비 · CDN 쓰지 않음)
FONT_FILE = Path(__file__).resolve().parents[2] / "assets" / "fonts" / "Pretendard-Regular.ttf"
# 글꼴 폴더를 내보낼 주소
FONT_URL = "/fonts"

# 그래프 계열 색 순서 — 계열이 여럿일 때 이 순서로 씀(강조 → 대기 → 보조 글자 → 불량)
SERIES = [ACCENT, WAIT, TEXT_DIM, NG, ACCENT_DIM, SPEC_LINE]

# 글꼴 폴더 등록 여부 — app.add_static_files 는 같은 주소로 두 번 등록하지 않음
_static_added = False


# 페이지 전체 CSS — 바탕 · 글자 · 글꼴 · AG Grid 색 변수 · 상태 배지 · 표 행 색
def _page_css():
    return """
@font-face {{ font-family: '{font}'; src: url('{url}/{file}') format('truetype'); font-display: swap; }}
body, .q-body, .nicegui-content {{ background: {bg}; color: {text}; font-family: '{font}', sans-serif; }}
.q-header, .q-footer {{ background: {win}; color: {text}; border-color: {border}; }}
.q-card {{ background: {panel}; color: {text}; }}
.text-dim {{ color: {dim}; }}
.nicegui-aggrid {{
  --ag-background-color: {panel}; --ag-foreground-color: {text}; --ag-header-background-color: {neutral};
  --ag-border-color: {border}; --ag-accent-color: {accent}; --ag-row-hover-color: {neutral};
  --ag-font-family: '{font}', sans-serif; --ag-header-text-color: {dim};
}}
.badge-ok, .badge-ng, .badge-wait {{ padding: 2px 8px; border-radius: 4px; font-weight: 600; color: {on_accent}; }}
.badge-ok {{ background: {ok}; }}
.badge-ng {{ background: {ng}; }}
.badge-wait {{ background: {wait}; }}
.cell-over {{ color: {ng}; font-weight: 600; }}
.row-ng {{ background: {row_ng} !important; }}
.row-wait {{ background: {row_wait} !important; }}
""".format(font=FONT, url=FONT_URL, file=FONT_FILE.name, bg=BG_BASE, text=TEXT, win=BG_WINDOW,
           border=BORDER, panel=BG_PANEL, dim=TEXT_DIM, neutral=NEUTRAL, accent=ACCENT,
           on_accent=ON_ACCENT, ok=OK, ng=NG, wait=WAIT, row_ng=ROW_BG_NG, row_wait=ROW_BG_WAIT)


# ECharts 공통 바탕 설정 — 그래프 옵션 dict 에 펼쳐 넣음(바탕 · 글자 · 계열 색)
def echart_base():
    return {
        "backgroundColor": "transparent",
        "color": SERIES,
        "textStyle": {"color": TEXT, "fontFamily": FONT},
    }


# 테마 적용 — 페이지 함수 안 첫 줄에서 호출(ui.colors · dark_mode 는 페이지마다 따로 붙음)
def apply_theme():
    global _static_added
    if not _static_added:
        app.add_static_files(FONT_URL, str(FONT_FILE.parent))
        _static_added = True
    ui.colors(primary=ACCENT, secondary=NEUTRAL, accent=ACCENT_DIM, positive=OK, negative=NG,
              warning=WAIT, info=TEXT_DIM, dark=BG_WINDOW, dark_page=BG_BASE)
    ui.dark_mode(True)
    ui.add_css(_page_css())
