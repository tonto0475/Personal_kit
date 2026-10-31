# 표 기본 폼 시험 — 열 정의(정렬 · 입력식 필터 · 숫자 열 규칙 · 상태 배지) · 표 옵션(빈 상태 문구 · 페이지 넘김 · 상태 행 바탕)
import sys
from pathlib import Path

import pytest

# 이 폴더 — table_form 을 바로 import
sys.path.insert(0, str(Path(__file__).resolve().parent))

import table_form as tf  # noqa: E402
from src.core.errors import InputError  # noqa: E402


# 글자 열 — 입력식 필터
def test_text_col():
    # 열 정의
    col = tf.text_col("lot", "로트")
    assert col["filter"] == "agTextColumnFilter" and col["floatingFilter"] is True


# 숫자 열 — 오른쪽 정렬 · 소수 자리 · 목표 초과 빨강 · 단위는 머리글에
def test_number_col():
    # 목표 있는 열
    col = tf.number_col("defect", "불량률", digits=1, target=2.0, unit="%")
    assert col["type"] == "rightAligned"
    assert "toFixed(1)" in col[":valueFormatter"]
    assert col["cellClassRules"] == {"cell-over": "x != null && x > 2.0"}
    assert col["headerName"] == "불량률 (%)"
    assert "cellClassRules" not in tf.number_col("t", "두께", digits=2, target=None)
    with pytest.raises(InputError, match="소수 자리 오류"):
        tf.number_col("t", "두께", digits=-1, target=None)


# 상태 배지 열 — 세 상태 class 가 렌더러에 다 들어감 · 글자는 textContent(HTML 실행 안 됨)
def test_status_col():
    # 렌더러 JS
    js = tf.status_col("status")[":cellRenderer"]
    for cls in ("badge-ok", "badge-ng", "badge-wait"):
        assert cls in js
    assert "textContent" in js and "innerHTML" not in js


# 표 옵션 — 정렬 기본 · 빈 상태 문구 · 페이지 넘김 · 상태 행 바탕 · CSV 내보내기는 없음
def test_grid_options():
    # 옵션
    opt = tf.grid_options(tf.demo_columns(), tf.demo_rows(), status_field="status", page_size=10)
    assert opt["defaultColDef"]["sortable"] is True
    assert "데이터 없음" in opt["overlayNoRowsTemplate"]
    assert opt["pagination"] is True and opt["paginationPageSize"] == 10
    assert opt["rowClassRules"]["row-ng"] == "data && data['status'] === 'NG'"
    assert not any("csv" in k.lower() or "export" in k.lower() for k in opt)
    assert "rowClassRules" not in tf.grid_options(tf.demo_columns(), [])
    with pytest.raises(InputError, match="표 열 정의 없음"):
        tf.grid_options([], [])
