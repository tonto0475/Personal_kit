# 비동기 작업 상태 폴링 — 완료 · 실패 · 시간 초과 셋으로 끝냄
#   역할: «작업 접수 → id 받음 → 상태 조회 반복» 형 외부 API 에서 끝날 때까지 일정 간격으로 상태를 물음
#   어디에: 작업을 맡기고 기다리는 호출(AI 분석 · 보고서 생성 · 대량 변환). 화면 안에서는 apoll_job(await)
#   실패하면: 작업이 실패 상태 → ExternalError · 제한 시간 안에 안 끝남 → ExternalTimeout(작업은 서버에서 계속 돌 수 있음 = 모름)
import asyncio
import time

from src.core.errors import ExternalError, ExternalTimeout

# 완료 상태 값들
DONE_VALUES = ("done", "succeeded", "completed")
# 실패 상태 값들
FAIL_VALUES = ("failed", "error", "canceled")


# 상태 하나 판정 — 완료면 True · 진행 중이면 False · 실패면 ExternalError
# data: 상태 응답 dict / status_key: 상태가 든 키 / done_values · fail_values: 완료 · 실패 값들
def _check(data, status_key, done_values, fail_values):
    # 상태 값
    status = str(data.get(status_key, "")).lower()
    if status in done_values:
        return True
    if status in fail_values:
        raise ExternalError("작업 실패 — 상태 {} · {}".format(status, data.get("error", "")))
    return False


# 동기 폴링 — 끝난 상태 응답을 돌려줌
# get_status: 인자 없이 상태 dict 를 돌려주는 함수 / interval_sec: 조회 간격 초 / timeout_sec: 전체 제한 초
# status_key · done_values · fail_values: 상태 판정 / sleep · clock: 대기 · 시계 함수(시험에서 바꿔 끼움)
def poll_job(get_status, interval_sec=2, timeout_sec=120, status_key="status",
             done_values=DONE_VALUES, fail_values=FAIL_VALUES, sleep=time.sleep, clock=time.monotonic):
    # 마감 시각
    deadline = clock() + timeout_sec
    while True:
        # 이번 상태 응답
        data = get_status()
        if _check(data, status_key, done_values, fail_values):
            return data
        if clock() + interval_sec > deadline:
            raise ExternalTimeout("작업이 {}초 안에 끝나지 않음 — 마지막 상태 {}".format(timeout_sec, data.get(status_key)))
        sleep(interval_sec)


# 비동기 폴링 — 동기판과 같은 규칙 · get_status 는 async 함수
async def apoll_job(get_status, interval_sec=2, timeout_sec=120, status_key="status",
                    done_values=DONE_VALUES, fail_values=FAIL_VALUES, sleep=asyncio.sleep, clock=time.monotonic):
    # 마감 시각
    deadline = clock() + timeout_sec
    while True:
        # 이번 상태 응답
        data = await get_status()
        if _check(data, status_key, done_values, fail_values):
            return data
        if clock() + interval_sec > deadline:
            raise ExternalTimeout("작업이 {}초 안에 끝나지 않음 — 마지막 상태 {}".format(timeout_sec, data.get(status_key)))
        await sleep(interval_sec)
