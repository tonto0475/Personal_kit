# lib/ui 시험 — 업로드 읽기 · 행 검사 · CSV 바이트(순수 함수) + 화면 조각(NiceGUI 가상 사용자 · 네트워크 없음)
import asyncio

import pandas as pd
import pytest
from nicegui import ui
from nicegui.testing.user_simulation import user_simulation

from lib.ui.progress_confirm import confirm, progress_bar, run_with_progress
from lib.ui.upload_check import UploadCheckPanel, preview_rows, read_upload, to_csv_bytes, validate_rows
from src.core.errors import InputError

# 한글 · 빈 값 · 범위 밖 값이 섞인 CSV 본문
CSV_TEXT = "로트,두께\nA,10.5\n,11.0\nC,99\nD,abc\n"
# 검사 규칙 — 두께 0 ~ 20
RULES = {"두께": (lambda v: 0 <= float(v) <= 20, "두께 범위 밖 (0~20)")}


# CSV 를 utf-8-sig · cp949 둘 다 같은 표로 읽는지
# enc: 저장 인코딩
@pytest.mark.parametrize("enc", ["utf-8-sig", "cp949"])
def test_read_upload_csv_encodings(enc):
    # 읽은 표
    df = read_upload("입력.csv", CSV_TEXT.encode(enc))
    assert list(df.columns) == ["로트", "두께"]
    assert len(df) == 4


# 엑셀 바이트도 읽는지(openpyxl)
def test_read_upload_excel(tmp_path):
    # 엑셀 파일 경로
    path = tmp_path / "입력.xlsx"
    pd.DataFrame({"로트": ["A", "B"], "두께": [1.0, 2.0]}).to_excel(path, index=False)
    assert read_upload("입력.xlsx", path.read_bytes())["로트"].tolist() == ["A", "B"]


# 지원하지 않는 형식 · 빈 파일은 입력 오류
def test_read_upload_rejects():
    with pytest.raises(InputError, match="지원하지 않는 형식"):
        read_upload("a.txt", b"x")
    with pytest.raises(InputError, match="빈 파일"):
        read_upload("a.csv", b"")


# 미리보기는 앞 20행 · 결측은 빈 칸
def test_preview_rows():
    # 25행 표 — 첫 행 결측
    df = pd.DataFrame({"x": [None] + list(range(24))})
    rows = preview_rows(df)
    assert len(rows) == 20
    assert rows[0]["x"] == ""


# 행 검사 — 빈 값 · 범위 밖 · 형식 오류를 «행 · 열 · 사유» 로(행 번호는 머리줄 포함 엑셀 행 번호)
def test_validate_rows():
    # 검사 결과
    fails = validate_rows(read_upload("a.csv", CSV_TEXT.encode("utf-8")), ["로트", "두께"], RULES)
    assert [(f["행"], f["열"]) for f in fails] == [(3, "로트"), (4, "두께"), (5, "두께")]
    assert fails[0]["사유"] == "빈 값"
    assert "값 99" in fails[1]["사유"]


# 필수 열이 없으면 행 검사 전에 입력 오류
def test_validate_missing_column():
    with pytest.raises(InputError, match="필수 열 없음 \\(무게\\)"):
        validate_rows(pd.DataFrame({"로트": ["A"]}), ["로트", "무게"], {})


# CSV 바이트는 BOM 이 붙은 utf-8(엑셀 한글)
def test_to_csv_bytes():
    # CSV 바이트
    data = to_csv_bytes([{"행": 3, "사유": "빈 값"}])
    assert data.startswith(b"\xef\xbb\xbf")
    assert data.decode("utf-8-sig").splitlines() == ["행,사유", "3,빈 값"]


# 가상 사용자로 페이지를 열고 시험 본문 실행
# build: 페이지 내용을 만드는 함수 / body: (user) 를 받아 확인하는 비동기 함수
def _simulate(build, body):
    async def main():
        async with user_simulation(build) as user:
            await user.open("/")
            await body(user)
    asyncio.run(main())


# 업로드 패널 — load 하면 상태 줄 · 미리보기 · 결과 표 · 내려받기 단추가 바뀜 · 형식 오류는 «[입력 오류]»
def test_upload_panel():
    # 만든 패널 — 페이지 함수 밖에서 확인하려고 담아 둠
    holder = {}

    def build():
        holder["panel"] = UploadCheckPanel(["로트", "두께"], RULES)

    async def body(user):
        # 패널
        panel = holder["panel"]
        panel.load("입력.csv", CSV_TEXT.encode("utf-8"))
        await user.should_see("입력.csv · 입력 4행 · 통과 1 · 실패 3")
        assert len(panel.preview.options["rowData"]) == 4
        assert len(panel.result.options["rowData"]) == 3
        assert panel.download.enabled
        panel.load("a.txt", b"x")
        await user.should_see("[입력 오류] 지원하지 않는 형식")
        assert not panel.download.enabled

    _simulate(build, body)


# 진행률 — 끝나면 바 1 · «처리 3 / 3» / 중간 AppError 면 멈추고 처리 건수 표시
def test_run_with_progress():
    # 바 · 글자
    parts = {}

    def build():
        parts["bar"], parts["text"] = progress_bar()

    # 항목 처리 — 3 이면 입력 오류
    # x: 항목
    def work(x):
        if x == 3:
            raise InputError("항목 3 형식 오류")
        return x * 10

    async def body(user):
        assert await run_with_progress([1, 2], work, parts["bar"], parts["text"]) == [10, 20]
        assert parts["bar"].value == 1
        await user.should_see("처리 2 / 2")
        assert await run_with_progress([1, 3, 4], work, parts["bar"], parts["text"]) == [10]
        await user.should_see("[입력 오류] 항목 3 형식 오류 · 처리 1 / 3")

    _simulate(build, body)


# 확인 대화상자 — 확인 단추면 True · 취소면 False
# label: 누를 단추 / expected: 기대 결과
@pytest.mark.parametrize("label, expected", [("삭제", True), ("취소", False)])
def test_confirm(label, expected):
    # 결과 담는 곳
    got = {}

    def build():
        async def ask():
            got["result"] = await confirm("로트 삭제", "LOT-1001 삭제", ok_label="삭제")
        ui.button("열기", on_click=ask)

    async def body(user):
        user.find("열기").click()
        await user.should_see("LOT-1001 삭제")
        user.find(content=label, kind=ui.button).click()
        # 대화상자 결과가 들어올 때까지 이벤트 루프 양보
        for _ in range(50):
            if "result" in got:
                break
            await asyncio.sleep(0.01)
        assert got.get("result") is expected

    _simulate(build, body)
