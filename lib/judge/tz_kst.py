# 시간대 처리 — KST ↔ UTC
#   역할: 시각을 UTC 로 바꿔 저장 · 화면에는 KST 로 표시 · 시간대 없는 시각(naive)을 어느 시간대로 볼지 인자로 명시
#   어디에: DB · 로그 · API 로 보내는 시각(UTC 저장 규칙) · 화면 · 보고서 표시(KST) · «오늘» 범위 계산
#   실패하면: 시간대 없는 시각에 assume 인자 누락 · 형식이 틀린 문자열이면 InputError(9시간 어긋난 값을 조용히 저장하지 않음)
#   규칙: 서버 · DB 에 저장하는 시각은 항상 UTC(ISO 8601 · 끝에 +00:00). KST 는 표시할 때만 변환
from datetime import datetime, timedelta, timezone

from src.core.errors import InputError

try:
    from zoneinfo import ZoneInfo
    # 한국 표준시
    KST = ZoneInfo("Asia/Seoul")
# 시간대 DB 없는 환경(윈도우에 tzdata 없음) — 한국은 서머타임이 없어 +9 고정과 같음
except Exception:
    KST = timezone(timedelta(hours=9), "KST")

# 협정 세계시
UTC = timezone.utc
# naive 시각을 볼 시간대 이름 → 시간대
ASSUME = {"KST": KST, "UTC": UTC}


# 지금 시각(UTC · 시간대 있음) — 저장용
def now_utc():
    return datetime.now(UTC)


# 시각에 시간대를 붙임. 이미 있으면 그대로, 없으면 assume 으로 봄
# dt: 시각 / assume: «KST» · «UTC» — naive 일 때만 쓰임
def _aware(dt, assume):
    if not isinstance(dt, datetime):
        raise InputError("시각이 datetime 이 아님: {!r}".format(dt))
    if dt.tzinfo is not None:
        return dt
    if assume not in ASSUME:
        raise InputError("시간대 없는 시각 — assume 을 KST · UTC 로 명시: {}".format(dt.isoformat()))
    return dt.replace(tzinfo=ASSUME[assume])


# 시각 → UTC(저장용). 시간대 없는 시각은 assume 필수
# dt: 시각 / assume: naive 시각을 볼 시간대
def to_utc(dt, assume=None):
    return _aware(dt, assume).astimezone(UTC)


# 시각 → KST(표시용). 시간대 없는 시각은 assume 필수
# dt: 시각 / assume: naive 시각을 볼 시간대
def to_kst(dt, assume=None):
    return _aware(dt, assume).astimezone(KST)


# ISO 8601 문자열 → UTC 시각. «Z» 끝도 받음(3.10 의 fromisoformat 은 Z 를 못 읽음)
# text: 시각 문자열 / assume: 문자열에 시간대가 없을 때 볼 시간대
def parse_to_utc(text, assume=None):
    # Z 를 +00:00 으로 바꾼 문자열
    norm = text.strip()
    if norm.endswith("Z"):
        norm = norm[:-1] + "+00:00"
    try:
        # 읽은 시각
        dt = datetime.fromisoformat(norm)
    # 형식 오류
    except ValueError:
        raise InputError("시각 형식 오류 (ISO 8601 아님): {}".format(text))
    return to_utc(dt, assume)


# KST 날짜 하루의 UTC 범위 [시작, 끝) — «오늘 데이터» 를 UTC 로 저장된 DB 에서 고를 때
# year · month · day: KST 기준 날짜
def kst_day_range_utc(year, month, day):
    # KST 그날 0시
    start = datetime(year, month, day, tzinfo=KST)
    return start.astimezone(UTC), (start + timedelta(days=1)).astimezone(UTC)
