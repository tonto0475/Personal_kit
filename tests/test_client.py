# 외부 API 클라이언트(src/api/client.py) 시험 — 정상 · timeout · 5xx(가짜 업무 서비스 · 네트워크 없이)
import pytest

from src.api.client import ApiClient
from src.core.errors import ExternalError, ExternalTimeout


# 시험 대상 클라이언트 만들기
# service: 가짜 업무 서비스
def make_client(service):
    return ApiClient("http://fake", timeout_sec=10, max_retry=1, transport=service.transport)


# 정상 — 한 번에 JSON
def test_ok(fake_service):
    assert make_client(fake_service).get_json("/items") == {"items": [{"id": 1, "name": "A"}]}
    assert fake_service.calls == ["/items"]


# timeout — 1번 재시도 후 ExternalTimeout · 문구에 제한 시간
def test_timeout(fake_service):
    fake_service.mode = "timeout"
    with pytest.raises(ExternalTimeout, match="timeout 10초 · 2회 시도"):
        make_client(fake_service).get_json("/items")
    assert len(fake_service.calls) == 2


# 503 — 재시도 대상 · 끝까지 실패면 ExternalError
def test_503_retried(fake_service):
    fake_service.mode = "503"
    with pytest.raises(ExternalError, match="HTTP 503"):
        make_client(fake_service).get_json("/items")
    assert len(fake_service.calls) == 2


# 연결 실패 — 서버에 닿기 전이라 재시도 · 끝까지 실패면 ExternalError
def test_connect_fail_retried(fake_service):
    fake_service.mode = "connect"
    with pytest.raises(ExternalError, match="연결 실패 · 2회 시도"):
        make_client(fake_service).get_json("/items")
    assert len(fake_service.calls) == 2


# 500 — 다시 보내도 같은 답이라 재시도 없이 ExternalError
def test_500_no_retry(fake_service):
    fake_service.mode = "500"
    with pytest.raises(ExternalError, match="HTTP 500"):
        make_client(fake_service).get_json("/items")
    assert len(fake_service.calls) == 1


# timeout 한 번 뒤 회복 — 재시도로 성공
def test_timeout_then_ok(fake_service):
    # 원래 처리 함수
    original = fake_service.handle

    # 첫 요청만 timeout
    def flaky(request):
        fake_service.mode = "timeout" if not fake_service.calls else "ok"
        return original(request)

    fake_service.handle = flaky
    assert make_client(fake_service).get_json("/items")["items"][0]["id"] == 1
    assert len(fake_service.calls) == 2
