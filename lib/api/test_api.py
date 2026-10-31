# lib/api 시험 — 재시도 규칙 · 결과 3분류 · Retry-After · 페이지 넘김 · 웹훅 서명 · 작업 폴링(네트워크 없이)
import asyncio
import sys
from pathlib import Path

import pytest

# 이 폴더 · 저장소 루트 · 가짜 서버 폴더 — import 경로에 추가
HERE = Path(__file__).resolve().parent
for p in (HERE, HERE.parents[1], HERE.parent / "testing"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from api_client import ApiClient, AsyncApiClient, iter_cursor, iter_pages  # noqa: E402
from api_poll import apoll_job, poll_job  # noqa: E402
from api_webhook import sign, verify_signature  # noqa: E402
from fake_api import FakeApi  # noqa: E402
from src.core.errors import ExternalError, ExternalTimeout, InputError  # noqa: E402


# 가짜 서버 + 대기 기록 클라이언트 — 실제로 자지 않고 대기 초만 모음
@pytest.fixture
def fake():
    # 가짜 서버
    api = FakeApi()
    api.add("GET", "/items", {"ok": 1})
    api.add("POST", "/orders", {"id": 7})
    return api


# 대기 초 목록 · 클라이언트
@pytest.fixture
def client(fake):
    # 대기한 초들
    waits = []
    # 시험 대상
    c = ApiClient("http://fake", timeout_sec=1, max_retry=3, backoff_sec=0.5, sleep=waits.append, transport=fake.transport)
    c.waits = waits
    return c


# 정상 — 한 번에 성공
def test_ok(client, fake):
    assert client.get_json("/items") == {"ok": 1}
    assert len(fake.calls) == 1


# 503 두 번 뒤 성공 — 간격이 0.5 · 1.0 으로 늘어남
def test_retry_backoff(client, fake):
    fake.fail_next(503, times=2)
    assert client.get_json("/items") == {"ok": 1}
    assert client.waits == [0.5, 1.0]


# 429 + Retry-After 5 — 기본 간격보다 큰 서버 값을 지킴
def test_retry_after(client, fake):
    fake.fail_next(429, retry_after=5)
    client.get_json("/items")
    assert client.waits == [5.0]


# 500 · 404 는 재시도하지 않고 바로 실패
@pytest.mark.parametrize("status", [500, 404, 400])
def test_no_retry_status(client, fake, status):
    fake.fail_next(status)
    with pytest.raises(ExternalError, match="HTTP {}".format(status)):
        client.get_json("/items")
    assert len(fake.calls) == 1


# timeout 이 재시도 횟수를 넘으면 «모름» = ExternalTimeout
def test_timeout_unknown(client, fake):
    fake.timeout_next(times=4)
    with pytest.raises(ExternalTimeout, match="결과 모름"):
        client.get_json("/items")
    assert len(fake.calls) == 4


# 지연이 timeout 보다 길면 timeout 으로 처리됨
def test_delay_over_timeout(client, fake):
    fake.delay_next(5)
    assert client.get_json("/items") == {"ok": 1}
    assert len(fake.calls) == 2


# 504 를 끝까지 받으면 «모름»
def test_504_unknown(client, fake):
    fake.fail_next(504, times=4)
    with pytest.raises(ExternalTimeout, match="HTTP 504"):
        client.get_json("/items")


# POST 는 키가 없으면 재시도하지 않음 · 키가 있으면 재시도하고 같은 키를 다시 보냄
def test_post_idempotency(client, fake):
    fake.timeout_next()
    with pytest.raises(ExternalTimeout):
        client.post_json("/orders", {"n": 1})
    assert len(fake.calls) == 1
    fake.timeout_next()
    assert client.post_json("/orders", {"n": 1}, idempotency_key="k-1") == {"id": 7}
    # 키 헤더 값들 — 두 번 다 같은 키
    keys = [h.get("idempotency-key") for _, _, h in fake.calls[1:]]
    assert keys == ["k-1", "k-1"]


# 연결 실패 — 서버에 닿기 전이라 키 없는 POST 도 재시도 · 끝까지 실패면 «실패»(ExternalError)
def test_connect_fail_retried(client, fake):
    fake.connect_fail_next()
    assert client.post_json("/orders", {"n": 1}) == {"id": 7}
    assert len(fake.calls) == 2
    fake.connect_fail_next(times=4)
    with pytest.raises(ExternalError, match="ConnectError"):
        client.get_json("/items")


# 토큰은 환경변수에서 · Authorization 헤더로
def test_token_env(fake, monkeypatch):
    monkeypatch.setenv("FAKE_TOKEN", "abc")
    # 토큰 쓰는 클라이언트
    c = ApiClient("http://fake", token_env="FAKE_TOKEN", transport=fake.transport)
    c.get_json("/items")
    assert fake.calls[0][2]["authorization"] == "Bearer abc"


# 비동기판 — 같은 규칙(502 한 번 뒤 성공)
def test_async_retry(fake):
    # 대기한 초들
    waits = []

    # 대기 기록 함수
    async def fake_sleep(sec):
        waits.append(sec)

    # 시험 본체
    async def main():
        # 비동기 클라이언트
        c = AsyncApiClient("http://fake", timeout_sec=1, sleep=fake_sleep, transport=fake.transport)
        fake.fail_next(502)
        try:
            return await c.get_json("/items")
        finally:
            await c.close()

    assert asyncio.run(main()) == {"ok": 1}
    assert waits == [0.5]


# 페이지 번호 — 2개씩 5개 → 3페이지
def test_iter_pages():
    # 전체 데이터
    data = list(range(5))

    # 가짜 조회 함수
    def get_json(path, params):
        # 시작 위치
        start = (params["page"] - 1) * params["size"]
        return {"items": data[start:start + params["size"]]}

    assert list(iter_pages(get_json, "/x", size=2)) == data


# 커서 — 끝까지 · 같은 커서 반복이면 실패
def test_iter_cursor():
    # 커서 → 응답 표
    pages = {None: {"items": [1, 2], "next_cursor": "a"}, "a": {"items": [3], "next_cursor": None}}
    assert list(iter_cursor(lambda p, q: pages[q.get("cursor")], "/x")) == [1, 2, 3]
    # 끝나지 않는 커서
    loop = {None: {"items": [1], "next_cursor": "a"}, "a": {"items": [2], "next_cursor": "a"}}
    with pytest.raises(ExternalError, match="커서 반복"):
        list(iter_cursor(lambda p, q: loop[q.get("cursor")], "/x"))


# 웹훅 — 맞는 서명 통과 · 본문 바꿈 · 시각 범위 밖 · 헤더 없음 거부
def test_webhook():
    # 본문 · 시각 · 서명
    body, ts = b'{"id":1}', "1000"
    sig = "sha256=" + sign("s3cret", ts, body)
    verify_signature("s3cret", body, sig, ts, now=1100)
    with pytest.raises(InputError, match="서명 불일치"):
        verify_signature("s3cret", b'{"id":2}', sig, ts, now=1100)
    with pytest.raises(InputError, match="범위 밖"):
        verify_signature("s3cret", body, sig, ts, now=2000)
    with pytest.raises(InputError, match="헤더 없음"):
        verify_signature("s3cret", body, "", ts, now=1100)


# 폴링 — 완료 · 실패 · 시간 초과
def test_poll():
    # 상태 순서
    seq = iter([{"status": "running"}, {"status": "done", "result": 3}])
    assert poll_job(lambda: next(seq), interval_sec=1, sleep=lambda s: None)["result"] == 3
    with pytest.raises(ExternalError, match="작업 실패"):
        poll_job(lambda: {"status": "failed"}, sleep=lambda s: None)
    # 가짜 시계 — 대기마다 시간이 흐름
    now = [0.0]
    with pytest.raises(ExternalTimeout, match="10초 안에"):
        poll_job(lambda: {"status": "running"}, interval_sec=2, timeout_sec=10,
                 sleep=lambda s: now.__setitem__(0, now[0] + s), clock=lambda: now[0])


# 비동기 폴링 — 완료
def test_apoll():
    # 상태 순서
    seq = iter([{"status": "queued"}, {"status": "succeeded"}])

    # 비동기 상태 조회
    async def get_status():
        return next(seq)

    # 대기 없음
    async def no_sleep(sec):
        return None

    assert asyncio.run(apoll_job(get_status, sleep=no_sleep))["status"] == "succeeded"
