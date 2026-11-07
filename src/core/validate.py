# 입력 검증 — if 문으로 확인하고 틀리면 InputError(어느 칸 · 어떤 값인지 문구에)
#   과제의 입력 칸에 맞게 함수를 고르거나 고쳐 씀. 경계값 시험은 tests/test_validate.py
from datetime import datetime

from src.core.errors import InputError


# 빈칸이 아닌 글자 — 앞뒤 공백 뺀 값
# name: 칸 이름(문구용) / value: 입력 / max_len: 최대 글자 수
def require_text(name, value, max_len=100):
    if value is None or not str(value).strip():
        raise InputError("{} 빈칸".format(name))
    # 공백 뺀 값
    text = str(value).strip()
    if len(text) > max_len:
        raise InputError("{} {}자 초과 ({}자)".format(name, max_len, len(text)))
    return text


# 범위 안 정수 — low 이상 high 이하
# name: 칸 이름 / value: 입력(문자열 가능) / low · high: 허용 범위(포함)
def int_in_range(name, value, low, high):
    try:
        # 정수 값
        number = int(str(value).strip())
    # 정수로 못 바꿈(빈칸 · 소수 · 글자)
    except ValueError:
        raise InputError("{} 정수 아님: {!r}".format(name, value))
    if number < low or number > high:
        raise InputError("{} 범위 밖: {} (허용 {} ~ {})".format(name, number, low, high))
    return number


# 날짜 — YYYY-MM-DD 형식만
# name: 칸 이름 / value: 입력
def parse_date(name, value):
    try:
        return datetime.strptime(str(value).strip(), "%Y-%m-%d").date()
    # 형식 · 없는 날짜(2월 30일)
    except ValueError:
        raise InputError("{} 날짜 형식 오류: {!r} (YYYY-MM-DD)".format(name, value))


# 필수 열 — 업로드 표에 빠진 열이 있으면 한 번에 모두 알림
# columns: 받은 열 이름들 / required: 필요한 열 이름들
def require_columns(columns, required):
    # 빠진 열
    missing = [c for c in required if c not in set(columns)]
    if missing:
        raise InputError("필수 열 빠짐: {}".format(", ".join(missing)))
