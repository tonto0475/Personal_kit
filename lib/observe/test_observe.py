# lib/observe 시험 — 설정 덮어쓰기 · 필수값 · 로그 칸 · 비밀값 가림 · /health · 주기 작업 종료
import asyncio
import logging
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# 이 폴더 · 저장소 루트 — import 경로에 추가
HERE = Path(__file__).resolve().parent
for p in (HERE, HERE.parents[1]):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from obs_config import load_config  # noqa: E402
from obs_health import add_health  # noqa: E402
from obs_log import log_error, log_event, setup_logging  # noqa: E402
from obs_periodic import PeriodicTask  # noqa: E402
from src.core.errors import ExternalTimeout, InputError  # noqa: E402


# 환경변수가 파일 값을 형 그대로 덮어씀 · 필수값 빠지면 InputError
def test_config(tmp_path, monkeypatch):
    # 설정 파일
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("api:\n  base_url: http://a\n  timeout_sec: 10\ndebug: false\n", encoding="utf-8")
    monkeypatch.setenv("APP_API__TIMEOUT_SEC", "30")
    monkeypatch.setenv("APP_DEBUG", "true")
    # 읽은 설정
    cfg = load_config(cfg_file, required=["api.base_url"], dotenv_path=tmp_path / "none.env")
    assert cfg["api"] == {"base_url": "http://a", "timeout_sec": 30} and cfg["debug"] is True
    with pytest.raises(InputError, match="db.path"):
        load_config(cfg_file, required=["db.path"], dotenv_path=tmp_path / "none.env")
    monkeypatch.setenv("APP_API__TIMEOUT_SEC", "열")
    with pytest.raises(InputError, match="형식 오류"):
        load_config(cfg_file, dotenv_path=tmp_path / "none.env")


# 칸 고정 · 종류 칸 · 비밀값 가림 · debug.log 는 켰을 때만
def test_logging(tmp_path):
    # 로거
    log = setup_logging(tmp_path, debug=False, name="t_obs")
    log_event(log, "통신", "주문 조회 120건 token=abc123")
    log_error(log, "통신", ExternalTimeout("API 연결 실패 (timeout 10초)"))
    log.debug("안 남아야 함")
    for h in log.handlers:
        h.flush()
    # app.log 줄들
    lines = (tmp_path / "app.log").read_text(encoding="utf-8").splitlines()
    assert [ln.split(" | ")[2:5] for ln in lines] == [["-", "INFO", "통신"], ["timeout", "ERROR", "통신"]]
    assert "abc123" not in lines[0] and "token=***" in lines[0]
    assert not (tmp_path / "debug.log").exists()
    setup_logging(tmp_path, debug=True, name="t_obs").debug("디버그")
    assert (tmp_path / "debug.log").exists()
    for h in list(logging.getLogger("t_obs").handlers):
        h.close()


# /health — 모두 통과 200 · 하나 실패(예외 포함) 503 + 사유
def test_health():
    # 앱
    app = FastAPI()

    # 실패하는 비동기 검사
    async def api_ok():
        raise ConnectionError("거부")

    add_health(app, {"db": lambda: True})
    add_health(app, {"db": lambda: True, "api": api_ok}, path="/health2")
    # 시험 클라이언트
    client = TestClient(app)
    assert client.get("/health").json()["status"] == "ok"
    # 실패 응답
    r = client.get("/health2")
    assert r.status_code == 503 and r.json()["checks"]["api"]["detail"].startswith("ConnectionError")


# 주기 작업 — 여러 번 돎 · 회차 예외에도 계속 · stop 으로 끝남
def test_periodic():
    # 회차 기록
    seen = []

    # 두 번째 회차만 실패
    def tick():
        seen.append(1)
        if len(seen) == 2:
            raise RuntimeError("한 번 실패")

    # 시험 본체
    async def main():
        # 주기 작업
        task = PeriodicTask(tick, interval_sec=0.01)
        task.start()
        await asyncio.sleep(0.1)
        await task.stop()
        return task

    # 끝난 작업
    task = asyncio.run(main())
    assert task.task.done() and task.runs >= 3 and task.failures == 1
