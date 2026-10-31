# lib/testing 시험 — 가짜 서버 장애 주입 4종 · 경계값 표 틀
import sys
from pathlib import Path

import httpx
import pytest

# 이 폴더 — import 경로에 추가
HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from boundary import cases, check, range_table  # noqa: E402
from fake_api import FakeApi, body_json  # noqa: E402


# 가짜 서버 + 클라이언트
@pytest.fixture
def fake():
    # 가짜 서버
    api = FakeApi()
    api.add("GET", "/n", {"n": 1})
    api.add("POST", "/echo", lambda req: {"got": body_json(req)})
    return api


# 등록 경로 · 요청 본문 · 없는 경로 404
def test_routes(fake):
    with httpx.Client(base_url="http://f", transport=fake.transport) as c:
        assert c.get("/n").json() == {"n": 1}
        assert c.post("/echo", json={"a": "한글"}).json() == {"got": {"a": "한글"}}
        assert c.get("/none").status_code == 404


# 장애 주입 — 5xx · timeout · 지연 · 같은 응답 두 번
def test_faults(fake):
    with httpx.Client(base_url="http://f", transport=fake.transport, timeout=1) as c:
        fake.fail_next(503, retry_after=3)
        # 장애 응답
        r = c.get("/n")
        assert (r.status_code, r.headers["Retry-After"]) == (503, "3")
        fake.timeout_next()
        with pytest.raises(httpx.ReadTimeout):
            c.get("/n")
        fake.delay_next(2)
        with pytest.raises(httpx.ReadTimeout):
            c.get("/n")
        fake.delay_next(0.01)
        assert c.get("/n").json() == {"n": 1}
        c.post("/echo", json={"x": 1})
        fake.repeat_last()
        assert c.get("/n").json() == {"got": {"x": 1}}
    assert len(fake.calls) == 6


# 경계값 표 → parametrize 예시(0 이상 100 이하 정수)
# value: 입력
def _percent(value):
    if not 0 <= value <= 100:
        raise ValueError(value)
    return value


@pytest.mark.parametrize("value, expected", cases(range_table(0, 100, 1, ValueError) + [("가운데", 50, 50)]))
def test_boundary(value, expected):
    check(_percent, value, expected)
