# lib/judge 시험 — 기준값 판정 경계 · 연속 N회 알람 · KST ↔ UTC
from datetime import datetime

import numpy as np
import pytest

from lib.judge.judge import ConsecutiveAlarm, check_threshold, consecutive_alarm_points
from lib.judge.tz_kst import kst_day_range_utc, parse_to_utc, to_kst, to_utc
from src.core.errors import InputError


# 경계값 5 에서 네 방식이 갈리는지 — 이상 · 이하는 참, 초과 · 미만은 거짓
# op: 비교 방식 / at_edge: 값 5 의 결과 / above: 값 5.1 의 결과
@pytest.mark.parametrize("op, at_edge, above", [
    ("이상", True, True), ("초과", False, True), ("이하", True, False), ("미만", False, False)])
def test_check_threshold_edges(op, at_edge, above):
    assert check_threshold(5, 5, op=op)["met"] is at_edge
    assert check_threshold(5.1, 5, op=op)["met"] is above


# 근거 수치 · numpy 숫자 · 잘못된 입력
def test_check_threshold_detail_and_errors():
    # 판정 결과
    res = check_threshold(np.float64(7.5), 5, op="초과")
    assert res["diff"] == pytest.approx(2.5) and res["op"] == "초과"
    assert check_threshold(np.int64(3), 5, op="미만")["met"] is True
    with pytest.raises(TypeError):
        check_threshold(5, 5)
    with pytest.raises(InputError, match="비교 방식"):
        check_threshold(5, 5, op=">=")
    with pytest.raises(InputError, match="숫자"):
        check_threshold(float("nan"), 5, op="이상")
    with pytest.raises(InputError, match="숫자"):
        check_threshold("5", 5, op="이상")


# 연속 3회 — 3번째에서 한 번 울리고, 끊긴 뒤 다시 3번 연속이면 또 울림
def test_consecutive_alarm():
    assert consecutive_alarm_points([1, 1, 1, 1, 0, 1, 1, 0, 1, 1, 1], 3) == [2, 10]
    # 알람 상태
    alarm = ConsecutiveAlarm(2)
    assert alarm.update(True) == {"alarm": False, "streak": 1}
    assert alarm.update(True) == {"alarm": True, "streak": 2}
    assert alarm.update(True) == {"alarm": False, "streak": 3}
    assert alarm.update(False) == {"alarm": False, "streak": 0}
    with pytest.raises(InputError):
        ConsecutiveAlarm(0)


# KST 09:00 = UTC 00:00 · naive 는 assume 필수 · Z 문자열
def test_timezone_conversion():
    # KST 로 본 naive 시각
    naive = datetime(2026, 10, 31, 9, 0)
    # UTC 변환 결과
    utc = to_utc(naive, assume="KST")
    assert utc.isoformat() == "2026-10-31T00:00:00+00:00"
    assert to_kst(utc).hour == 9
    assert to_kst(datetime(2026, 10, 30, 15, 0), assume="UTC").isoformat().startswith("2026-10-31T00:00:00+09:00")
    with pytest.raises(InputError, match="assume"):
        to_utc(naive)
    assert parse_to_utc("2026-10-31T00:00:00Z") == utc
    assert parse_to_utc("2026-10-31 09:00:00", assume="KST") == utc
    with pytest.raises(InputError):
        parse_to_utc("10/31 9시")


# KST 하루 = UTC 전날 15시 ~ 그날 15시
def test_kst_day_range():
    # 시작 / 끝
    start, end = kst_day_range_utc(2026, 10, 31)
    assert start.isoformat() == "2026-10-30T15:00:00+00:00"
    assert end.isoformat() == "2026-10-31T15:00:00+00:00"
