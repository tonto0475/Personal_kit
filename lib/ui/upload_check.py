# 파일 업로드 → 미리보기(앞 20행) → 검증 결과(행 · 사유 표) → CSV 내려받기(utf-8-sig) 화면 조각
#   역할: 올린 CSV · 엑셀을 표로 읽어 앞부분을 보여 주고, 필수 열 · 행 규칙을 검사해 실패 행을 «행 · 열 · 사유» 표로 보여 줌
#   어디에: 입력 파일을 사람이 올리는 화면(데이터 반입 · 일괄 등록) — 순수 함수(read_upload · validate_rows · to_csv_bytes)만 따로 복사해 써도 됨
#   실패하면: 지원하지 않는 확장자 · 읽기 실패 · 필수 열 없음은 InputError → 화면에 «[입력 오류] …» 한 줄(조용히 빈 표로 넘어가지 않음)
import io
from pathlib import Path

import pandas as pd

from src.core.errors import AppError, InputError

# 미리보기 행 수
PREVIEW_ROWS = 20
# CSV 읽기 인코딩 시도 순서 — BOM 있는 utf-8 먼저, cp949 는 마지막(utf-8 한글이 cp949 로 «성공» 하는 것 방지)
CSV_ENCODINGS = ("utf-8-sig", "cp949")
# 받는 확장자
CSV_EXT = ".csv"
EXCEL_EXT = (".xlsx", ".xls")
# 표 머리줄 1행 — 사람이 보는 행 번호 = 데이터 번호 + 이 값(엑셀에서 연 행 번호와 같게)
HEADER_ROWS = 1


# ===== 순수 함수 =====

# 올린 파일 바이트 → 표. CSV 는 인코딩을 차례로 시도
# name: 파일 이름(확장자로 형식 판별) / data: 파일 내용 바이트
def read_upload(name, data):
    # 확장자 소문자
    ext = Path(name).suffix.lower()
    if not data:
        raise InputError("빈 파일 ({})".format(name))
    if ext == CSV_EXT:
        # 인코딩 후보
        for enc in CSV_ENCODINGS:
            try:
                return pd.read_csv(io.BytesIO(data), encoding=enc)
            # 이 인코딩으로 못 읽음 — 다음 후보
            except UnicodeDecodeError:
                continue
            # 형식 자체가 깨짐(따옴표 · 열 수)
            except pd.errors.ParserError as err:
                raise InputError("CSV 형식 오류 ({}: {})".format(name, err))
        raise InputError("CSV 인코딩 판별 실패 ({} · 시도 {})".format(name, " · ".join(CSV_ENCODINGS)))
    if ext in EXCEL_EXT:
        try:
            return pd.read_excel(io.BytesIO(data))
        # 엑셀 아님 · 깨진 파일
        except Exception as err:
            raise InputError("엑셀 읽기 실패 ({}: {})".format(name, err))
    raise InputError("지원하지 않는 형식 ({} · csv · xlsx 만)".format(name))


# 표 → 화면 행 목록(앞 n 행). 결측은 빈 칸
# df: 표 / n: 행 수
def preview_rows(df, n=PREVIEW_ROWS):
    return df.head(n).astype(object).where(df.head(n).notna(), "").to_dict("records")


# 행 검사 — 필수 열의 빈 값 · 열별 규칙 위반을 «행 · 열 · 사유» 목록으로
# df: 표 / required: 필수 열 이름 목록 / rules: {열 이름: (검사 함수(값) → 참이면 통과, 실패 사유)}
def validate_rows(df, required, rules):
    # 없는 필수 열 — 파일 전체가 틀린 것이라 행 검사 전에 입력 오류
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise InputError("필수 열 없음 ({})".format(" · ".join(missing)))
    # 실패 목록
    fails = []
    # 데이터 번호 · 행
    for i, row in enumerate(df.to_dict("records")):
        # 사람이 보는 행 번호
        line = i + 1 + HEADER_ROWS
        # 필수 열 이름
        for col in required:
            if pd.isna(row[col]) or str(row[col]).strip() == "":
                fails.append({"행": line, "열": col, "사유": "빈 값"})
        # 규칙 열 · 검사 함수 · 사유
        for col, (check, reason) in rules.items():
            if col not in row or pd.isna(row[col]):
                continue
            try:
                # 검사 결과
                ok = check(row[col])
            # 검사 함수가 값 형식 때문에 터짐(숫자 자리에 글자 등) — 실패로 기록
            except (TypeError, ValueError):
                ok = False
            if not ok:
                fails.append({"행": line, "열": col, "사유": "{} (값 {})".format(reason, row[col])})
    return fails


# 표 → 엑셀에서 한글이 안 깨지는 CSV 바이트(utf-8-sig)
# df: 표 또는 행 dict 목록
def to_csv_bytes(df):
    if not isinstance(df, pd.DataFrame):
        df = pd.DataFrame(df)
    return df.to_csv(index=False).encode("utf-8-sig")


# ===== 화면 =====

# 업로드 패널 — 업로드 칸 · 상태 한 줄 · 미리보기 표 · 검증 결과 표 · 내려받기 단추
#   load(name, data) 를 직접 불러도 같은 동작(시험 · 다른 입력 경로용)
class UploadCheckPanel:
    # required · rules: validate_rows 와 같음 / result_name: 검증 결과 CSV 파일 이름
    def __init__(self, required, rules, result_name="검증결과.csv"):
        from nicegui import ui
        # 검사 기준
        self.required = list(required)
        self.rules = dict(rules)
        self.result_name = result_name
        # 마지막으로 읽은 표 · 실패 목록
        self.df = None
        self.fails = []
        with ui.column().classes("w-full gap-2"):
            ui.upload(label="CSV · 엑셀", auto_upload=True, on_upload=self._on_upload, max_files=1) \
                .props("accept=.csv,.xlsx,.xls flat bordered").classes("w-full")
            # 상태 한 줄 — 길이를 모르는 글이라 줄바꿈
            self.status = ui.label("").classes("whitespace-normal break-all")
            # 미리보기 표
            self.preview = ui.aggrid({"columnDefs": [], "rowData": [],
                                      "overlayNoRowsTemplate": "<span>데이터 없음</span>"}).classes("w-full") \
                .style("height: 300px")
            # 검증 결과 표
            self.result = ui.aggrid({"columnDefs": [{"field": "행", "type": "rightAligned", "maxWidth": 90},
                                                    {"field": "열", "maxWidth": 160}, {"field": "사유"}],
                                     "rowData": [], "overlayNoRowsTemplate": "<span>데이터 없음</span>"}) \
                .classes("w-full").style("height: 220px")
            self.download = ui.button("검증 결과 CSV", on_click=self._on_download).props("outline no-caps")
            self.download.disable()

    # 업로드 이벤트 → load
    # e: 업로드 이벤트(e.file.name · await e.file.read())
    async def _on_upload(self, e):
        self.load(e.file.name, await e.file.read())

    # 파일 읽기 → 미리보기 · 검증 · 상태 줄
    # name: 파일 이름 / data: 내용 바이트
    def load(self, name, data):
        try:
            self.df = read_upload(name, data)
            self.fails = validate_rows(self.df, self.required, self.rules)
        # 입력 오류 · 그 밖 앱 에러 — 화면에 종류와 함께
        except AppError as err:
            self.df, self.fails = None, []
            self.status.set_text(err.screen_text())
            self._fill(self.preview, [])
            self._fill(self.result, [])
            self.download.disable()
            return
        # 실패 행 수 — 한 행에 사유가 여럿일 수 있어 행 번호로 셈
        bad = len({f["행"] for f in self.fails})
        self.status.set_text("{} · 입력 {}행 · 통과 {} · 실패 {}".format(name, len(self.df), len(self.df) - bad, bad))
        self._fill(self.preview, preview_rows(self.df), list(self.df.columns))
        self._fill(self.result, self.fails)
        self.download.enable()

    # 표 내용 바꾸기
    # grid: AG Grid 요소 / rows: 행 목록 / columns: 열 이름 목록(None 이면 열 정의 유지)
    @staticmethod
    def _fill(grid, rows, columns=None):
        if columns is not None:
            grid.options["columnDefs"] = [{"field": str(c), "minWidth": 90} for c in columns]
        grid.options["rowData"] = rows
        grid.update()

    # 검증 결과 내려받기
    def _on_download(self):
        from nicegui import ui
        ui.download.content(to_csv_bytes(self.fails or [{"행": "", "열": "", "사유": ""}]), self.result_name,
                            media_type="text/csv")
