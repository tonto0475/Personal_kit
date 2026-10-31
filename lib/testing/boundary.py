# 경계값 표 → pytest parametrize 틀
#   역할: «이름 · 입력 · 기대(값 또는 예외 클래스)» 표 한 장을 시험 여러 개로 펼침 · 범위 경계 네 점을 자동 생성
#   어디에: tests/ 의 검증 · 판정 함수 시험(ref/CHECKSHEET 경계 표를 그대로 옮겨 적음)
#   실패하면: pytest 가 표의 «이름» 으로 어느 줄이 틀렸는지 보여 줌(ids)
import pytest


# 표 → parametrize 인자. 사용: @pytest.mark.parametrize("value, expected", cases(TABLE))
# table: [(이름, 입력, 기대), ...] — 기대가 예외 클래스면 그 예외가 나야 통과
def cases(table):
    return [pytest.param(value, expected, id=name) for name, value, expected in table]


# 기대 확인 — 값이면 같은지 · 예외 클래스면 그 예외가 나는지
# func: 시험 대상 함수(인자 하나) / value: 입력 / expected: 기대 값 또는 예외 클래스
def check(func, value, expected):
    if isinstance(expected, type) and issubclass(expected, BaseException):
        with pytest.raises(expected):
            func(value)
    else:
        assert func(value) == expected


# 범위 경계 네 점 — 아래 밖 · 아래 끝 · 위 끝 · 위 밖. «이상 · 이하» 범위 기준
# low · high: 허용 범위 끝(포함) / step: 한 칸 / error: 범위 밖일 때 기대 예외
def range_table(low, high, step, error):
    return [
        ("아래 밖 {}".format(low - step), low - step, error),
        ("아래 끝 {}".format(low), low, low),
        ("위 끝 {}".format(high), high, high),
        ("위 밖 {}".format(high + step), high + step, error),
    ]
