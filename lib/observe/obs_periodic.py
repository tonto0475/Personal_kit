# 비동기 주기 작업 — N초마다 한 번 · 정상 종료 · 취소
#   역할: 연결 재확인 · 주기 동기화 같은 반복 일을 asyncio 작업 하나로 돌리고, stop() 으로 깔끔히 끝냄
#   어디에: NiceGUI app.on_startup(task.start) · app.on_shutdown(task.stop) — 화면 스레드를 막지 않음
#   실패하면: 한 회차 예외는 로그만 남기고 다음 회차 계속(한 번 실패로 주기 전체가 죽지 않음) · 취소는 바로 끝남
import asyncio
import inspect
import logging

# 이 모듈 로거
logger = logging.getLogger("periodic")


# 주기 작업
class PeriodicTask:
    # func: 매 회차 부를 함수(동기 · 비동기) / interval_sec: 간격 초 / name: 로그 이름 / run_first: 시작 즉시 1회
    def __init__(self, func, interval_sec, name="주기 작업", run_first=True):
        # 부를 함수
        self.func = func
        # 간격 초
        self.interval_sec = interval_sec
        # 로그 이름
        self.name = name
        # 시작 즉시 1회
        self.run_first = run_first
        # asyncio 작업(시작 전 None)
        self.task = None
        # 실행 회차 · 실패 회차
        self.runs, self.failures = 0, 0
        # 멈춤 신호 — 대기 중에도 바로 깨어남
        self._stop = None

    # 한 회차
    async def _once(self):
        self.runs += 1
        try:
            # 함수 결과
            result = self.func()
            if inspect.isawaitable(result):
                await result
        # 취소는 그대로 올림(정상 종료 경로)
        except asyncio.CancelledError:
            raise
        # 회차 안 예외 — 기록 후 계속
        except Exception as err:
            self.failures += 1
            logger.error("%s 회차 %d 실패: %s", self.name, self.runs, err)

    # 반복 본체
    async def _loop(self):
        if self.run_first:
            await self._once()
        while not self._stop.is_set():
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.interval_sec)
            # 간격이 지남 — 다음 회차
            except asyncio.TimeoutError:
                await self._once()

    # 시작 — 이미 돌고 있으면 그대로
    def start(self):
        if self.task is None or self.task.done():
            self._stop = asyncio.Event()
            self.task = asyncio.get_running_loop().create_task(self._loop())
        return self.task

    # 정상 종료 — 지금 회차가 끝나길 기다림 · wait_sec 을 넘기면 취소
    # wait_sec: 기다릴 최대 초
    async def stop(self, wait_sec=5):
        if self.task is None:
            return
        self._stop.set()
        try:
            await asyncio.wait_for(self.task, timeout=wait_sec)
        # 회차가 너무 오래 걸림 — wait_for 가 이미 작업을 취소함
        except asyncio.TimeoutError:
            logger.warning("%s 종료 대기 %s초 초과 — 취소", self.name, wait_sec)
        # 밖에서 취소된 작업
        except asyncio.CancelledError:
            pass
