# 입력 검증(src/core/validate.py) 시험 — 경계값 표
import datetime

import pytest

from src.core.errors import InputError
from src.core.validate import int_in_range, parse_date, require_columns, require_text


# 범위 1 ~ 100 경계 — (입력, 기대: 값 또는 InputError)
@pytest.mark.parametrize("value, expected", [
    ("0", InputError), ("1", 1), ("100", 100), ("101", InputError),
    (" 7 ", 7), ("", InputError), ("1.5", InputError), ("열", InputError)])
def test_int_in_range(value, expected):
    if expected is InputError:
        with pytest.raises(InputError, match="수량"):
            int_in_range("수량", value, 1, 100)
    else:
        assert int_in_range("수량", value, 1, 100) == expected


# 글자 — 빈칸 · 공백만 · 최대 길이 경계
@pytest.mark.parametrize("value, expected", [
    (None, InputError), ("   ", InputError), (" 가 ", "가"), ("a" * 5, "a" * 5), ("a" * 6, InputError)])
def test_require_text(value, expected):
    if expected is InputError:
        with pytest.raises(InputError, match="이름"):
            require_text("이름", value, max_len=5)
    else:
        assert require_text("이름", value, max_len=5) == expected


# 날짜 — 형식 · 없는 날짜
def test_parse_date():
    assert parse_date("측정일", "2026-10-31") == datetime.date(2026, 10, 31)
    for bad in ("2026/10/31", "2026-02-30", ""):
        with pytest.raises(InputError, match="측정일 날짜 형식 오류"):
            parse_date("측정일", bad)


# 필수 열 — 빠진 열을 모두 문구에
def test_require_columns():
    require_columns(["lot", "value", "extra"], ["lot", "value"])
    with pytest.raises(InputError, match="필수 열 빠짐: lot, value"):
        require_columns(["extra"], ["lot", "value"])
