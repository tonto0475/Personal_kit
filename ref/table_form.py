# 표 기본 폼 — AG Grid(ui.aggrid) 열 정의 함수 + 위 필터 줄 · 상태 배지 · 페이지 넘김 + «칸 안 단추» 예시(ui.table 슬롯) + 데모
#   기본으로 켜는 것 4개: 정렬 · 열 필터(입력식) · 상태 배지 열(OK · NG · 대기) · 빈 상태 문구 «데이터 없음»
#   넣지 않은 것: CSV 내보내기 · 열 폭 저장(요구 있을 때만)
#   숫자 열 규칙: 오른쪽 정렬 · 소수 자리 지정 · 목표 초과 빨강(cellClassRules → theme 의 .cell-over)
#   실행(데모): python3 ref/table_form.py → http://<주소>:<PORT 또는 3000>/
import os
import sys
from pathlib import Path

# 저장소 루트 — 이 파일을 직접 실행해도 src 를 찾게 sys.path 앞에 추가
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.core.errors import InputError  # noqa: E402

# 상태 값 → 배지 class(theme 의 .badge-ok · .badge-ng · .badge-wait)
STATUS_CLASS = {"OK": "badge-ok", "NG": "badge-ng", "대기": "badge-wait"}
# 빈 상태 문구
EMPTY_TEXT = "데이터 없음"
# 한 쪽 행 수 기본값 · 고를 수 있는 값
PAGE_SIZE = 20
PAGE_SIZES = [10, 20, 50, 100]
# 페이지 넘김 줄 한글 — «1 ~ 10 / 25» · «쪽 1 / 3» · «행 수»
LOCALE_TEXT = {"page": "쪽", "to": "~", "of": "/", "pageSizeSelectorLabel": "행 수",
               "firstPage": "처음", "previousPage": "이전", "nextPage": "다음", "lastPage": "끝"}

# 상태 배지 렌더러 JS 문자열 — STATUS_CLASS 를 JS 객체로 박아 넣음 · 글자는 textContent 로(값에 든 HTML 이 실행되지 않게)
def _badge_js():
    # JS 객체 글자 — {'OK': 'badge-ok', ...}
    mapping = "{" + ", ".join("'{}': '{}'".format(k, v) for k, v in STATUS_CLASS.items()) + "}"
    return ("p => { if (p.value == null || p.value === '') return ''; const s = document.createElement('span');"
            " s.className = (" + mapping + "[p.value] || 'badge-wait'); s.textContent = p.value; return s; }")


# ===== 열 정의 =====

# 글자 열 — 정렬 · 입력식 필터
# field: 데이터 키 / header: 머리글 / min_width: 최소 폭(px · 글자 잘림 방지)
def text_col(field, header, min_width=100):
    return {"field": field, "headerName": header, "minWidth": min_width,
            "filter": "agTextColumnFilter", "floatingFilter": True}


# 숫자 열 — 오른쪽 정렬 · 소수 자리 · 목표 초과 빨강
# field · header: 위와 같음 / digits: 소수 자리 / target: 목표 상한 또는 None(빨강 규칙 없음) / unit: 머리글 뒤 단위
def number_col(field, header, *, digits, target, unit=""):
    if not isinstance(digits, int) or digits < 0:
        raise InputError("소수 자리 오류 (digits={})".format(digits))
    # 열 정의
    col = {"field": field, "headerName": "{} ({})".format(header, unit) if unit else header,
           "type": "rightAligned", "minWidth": 110, "filter": "agNumberColumnFilter", "floatingFilter": True,
           ":valueFormatter": "p => p.value == null ? '' : Number(p.value).toFixed({})".format(digits)}
    if target is not None:
        col["cellClassRules"] = {"cell-over": "x != null && x > {}".format(target)}
    return col


# 상태 배지 열 — OK · NG · 대기 토큰 색 배지
# field · header: 위와 같음
def status_col(field, header="상태"):
    return {"field": field, "headerName": header, "minWidth": 100, "filter": "agTextColumnFilter",
            "floatingFilter": True, ":cellRenderer": _badge_js()}


# 표 옵션 — 정렬 · 필터 · 빈 상태 문구 · 페이지 넘김 · 상태 행 바탕(NG · 대기)
# columns: 열 정의 목록 / rows: 행 dict 목록 / status_field: 행 바탕을 칠할 상태 키 또는 None / page_size: 한 쪽 행 수
def grid_options(columns, rows, *, status_field=None, page_size=PAGE_SIZE):
    if not columns:
        raise InputError("표 열 정의 없음")
    # 옵션
    opt = {
        "columnDefs": columns,
        "rowData": rows,
        "defaultColDef": {"sortable": True, "resizable": True, "wrapHeaderText": True, "autoHeaderHeight": True},
        "pagination": True,
        "paginationPageSize": page_size,
        "paginationPageSizeSelector": PAGE_SIZES,
        "overlayNoRowsTemplate": "<span>{}</span>".format(EMPTY_TEXT),
        "localeText": LOCALE_TEXT,
    }
    if status_field is not None:
        opt["rowClassRules"] = {"row-ng": "data && data['{}'] === 'NG'".format(status_field),
                                "row-wait": "data && data['{}'] === '대기'".format(status_field)}
    return opt


# ===== 화면 =====

# 표 폼 — 위 필터 줄(검색 · 상태 버튼) + AG Grid. 반환: 표 요소
# columns · rows · status_field · page_size: grid_options 와 같음 / height_px: 표 높이
def table_form(columns, rows, *, status_field=None, page_size=PAGE_SIZE, height_px=480):
    from nicegui import ui
    # 표 요소 — 아래에서 만들고 필터 줄이 참조
    grid = None

    # 전체 검색 — 모든 열에서 글자 찾기
    # e: 입력 변경 이벤트
    def on_search(e):
        grid.run_grid_method("setGridOption", "quickFilterText", e.value or "")

    # 상태 버튼 — 그 상태만 · «전체» 는 필터 해제
    # value: 상태 값 또는 None
    def on_status(value):
        # 필터 모델 — 상태 열 «같음»
        model = None if value is None else {status_field: {"filterType": "text", "type": "equals", "filter": value}}
        grid.run_grid_method("setColumnFilterModel", status_field, model[status_field] if model else None)
        grid.run_grid_method("onFilterChanged")

    with ui.column().classes("w-full gap-2"):
        with ui.row().classes("w-full items-center gap-2"):
            ui.input(placeholder="검색", on_change=on_search).props("dense outlined clearable").classes("w-64")
            if status_field is not None:
                with ui.button_group().props("outline"):
                    ui.button("전체", on_click=lambda: on_status(None)).props("outline no-caps")
                    # 상태 값
                    for s in STATUS_CLASS:
                        ui.button(s, on_click=lambda s=s: on_status(s)).props("outline no-caps")
        grid = ui.aggrid(grid_options(columns, rows, status_field=status_field, page_size=page_size)) \
            .classes("w-full").style("height: {}px".format(height_px))
    return grid


# 칸 안 단추 표 — ui.table 슬롯(NiceGUI table_and_slots 식). 행마다 단추 · 누르면 on_click(행 dict)
# columns: ui.table 열 [{name, label, field}] / rows: 행 dict 목록(row_key 값 필수) / on_click: 단추 처리 함수
# button_label: 단추 글자 / row_key: 행 구별 키
def button_table(columns, rows, *, on_click, button_label, row_key="id"):
    from nicegui import ui
    # 표 — 마지막에 단추 열 추가
    table = ui.table(columns=columns + [{"name": "action", "label": "", "field": "action"}],
                     rows=rows, row_key=row_key).classes("w-full")
    table.add_slot("body-cell-action", """
        <q-td :props="props" auto-width>
            <q-btn dense outline no-caps color="primary" label="%s" @click="() => $parent.$emit('action', props.row)" />
        </q-td>""" % button_label)
    table.on("action", lambda e: on_click(e.args))
    return table


# ===== 데모 =====

# 데모 행 — 로트 25개(쪽 넘김이 보이게 page_size 10)
def demo_rows():
    # 상태 순환 · 두께 · 불량률
    status = ["OK", "OK", "NG", "OK", "대기"]
    return [{"lot": "LOT-{:04d}".format(1000 + i), "line": "L{}".format(i % 4 + 1),
             "thickness": 50 + ((i * 37) % 21 - 10) / 10, "defect": round(((i * 13) % 30) / 10, 2),
             "status": status[i % 5]} for i in range(25)]


# 데모 열
def demo_columns():
    return [text_col("lot", "로트"), text_col("line", "라인", 80),
            number_col("thickness", "두께", digits=2, target=None, unit="µm"),
            number_col("defect", "불량률", digits=1, target=2.0, unit="%"),
            status_col("status")]


# 데모 페이지 — 기본 표 · 빈 표 · 칸 안 단추 표
def build_demo():
    from nicegui import ui
    from src.ui.theme import apply_theme

    @ui.page("/")
    def page():
        apply_theme()
        with ui.column().classes("w-full max-w-5xl mx-auto p-4 gap-4"):
            with ui.card().classes("w-full p-4 table-main"):
                table_form(demo_columns(), demo_rows(), status_field="status", page_size=10, height_px=580)
            with ui.card().classes("w-full p-4 table-empty"):
                ui.aggrid(grid_options(demo_columns(), [])).classes("w-full").style("height: 220px")
            with ui.card().classes("w-full p-4 table-button"):
                # 단추 표 행
                rows = [{"id": r["lot"], "lot": r["lot"], "status": r["status"]} for r in demo_rows()[:3]]
                button_table([{"name": "lot", "label": "로트", "field": "lot", "align": "left"},
                              {"name": "status", "label": "상태", "field": "status", "align": "left"}],
                             rows, on_click=lambda row: ui.notify("재검사 요청 {}".format(row["lot"])),
                             button_label="재검사")


if __name__ in {"__main__", "__mp_main__"}:
    from nicegui import ui
    build_demo()
    ui.run(host="0.0.0.0", port=int(os.environ.get("PORT", 3000)), title="표 기본 폼",
           reload=False, show=False, dark=True)
