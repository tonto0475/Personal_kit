# 판정 · 규칙 — 기준값 비교 · 연속 N회 알람
#   역할: 값 하나를 기준값과 «이상 · 초과 · 이하 · 미만» 중 명시한 방식으로 비교해 결과 + 근거 수치(차이)를 돌려줌 · 나쁜 값이 N번 연속이면 알람
#   어디에: 측정값 → 합격/불합격 · 경고 표시 · «3회 연속 기준 초과 시 알람» 같은 요구
#   실패하면: 비교 방식 누락 · 오타 · 값이 숫자가 아님 · N < 1 이면 InputError(경계값을 추측해서 판정하지 않음)
import math
import numbers

from src.core.errors import InputError

# 비교 방식 → 조건 함수. 기본값을 두지 않음 — «5% 이상» 과 «5% 초과» 는 경계값 5 에서 판정이 갈림
OPS = {
    "이상": lambda v, t: v >= t,
    "초과": lambda v, t: v > t,
    "이하": lambda v, t: v <= t,
    "미만": lambda v, t: v < t,
}


# 값이 «기준값 op» 조건을 만족하는지. 만족이 합격인지 불합격인지는 부르는 쪽이 정함
# value: 측정값 / threshold: 기준값 / op: «이상 · 초과 · 이하 · 미만» 중 하나(필수 · 키워드로만)
def check_threshold(value, threshold, *, op):
    if op not in OPS:
        raise InputError("비교 방식 오류: {} (이상 · 초과 · 이하 · 미만 중 하나)".format(op))
    # 숫자 확인 대상 — 이름 / 값
    for name, x in (("value", value), ("threshold", threshold)):
        if isinstance(x, bool) or not isinstance(x, numbers.Real) or math.isnan(x):
            raise InputError("판정 값이 숫자가 아님: {}={!r}".format(name, x))
    return {
        "met": bool(OPS[op](value, threshold)),
        "value": value,
        "threshold": threshold,
        "op": op,
        "diff": value - threshold,
    }


# 연속 N회 알람 — 나쁜 값이 N번 연속 들어온 순간 알람 1번(같은 연속 구간에서 다시 울리지 않음)
class ConsecutiveAlarm:
    # n: 연속 횟수 기준
    def __init__(self, n):
        if not isinstance(n, int) or n < 1:
            raise InputError("연속 횟수 n 은 1 이상 정수 (현재 {!r})".format(n))
        # 연속 횟수 기준
        self.n = n
        # 지금까지 이어진 나쁜 값 개수
        self.streak = 0

    # 판정 결과 하나 넣기 — 돌려줌: {alarm: 이번에 울림, streak: 현재 연속 개수}
    # is_bad: 이번 값이 나쁜 값인가
    def update(self, is_bad):
        self.streak = self.streak + 1 if is_bad else 0
        return {"alarm": self.streak == self.n, "streak": self.streak}


# 판정 목록 전체에서 알람이 울리는 위치(0부터) — 배치 처리 · 시험용
# flags: 나쁜 값 여부 목록 / n: 연속 횟수 기준
def consecutive_alarm_points(flags, n):
    # 알람 상태
    alarm = ConsecutiveAlarm(n)
    return [i for i, bad in enumerate(flags) if alarm.update(bad)["alarm"]]
