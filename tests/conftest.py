# 여러 시험이 같이 쓰는 준비물(픽스처) — 저장소 루트 경로 · 가짜 업무 서비스
import sys
from pathlib import Path

import httpx
import pytest

# 저장소 루트 — 어느 폴더에서 pytest 를 돌려도 src 를 찾게 sys.path 앞에 추가
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# 가짜 업무 서비스 — httpx.MockTransport(네트워크 · 포트 없이). 경로 표는 과제 API 에 맞게 고침
#   service.mode 로 다음 요청들의 장애를 고름: "ok" · "timeout" · "connect" · "500" · "503"
#   service.calls 에 받은 요청 경로가 쌓임(몇 번 왔는지 확인용)
class FakeService:
    def __init__(self):
        # 장애 모드
        self.mode = "ok"
        # 받은 요청 경로들
        self.calls = []
        # 경로 → 정상 응답 JSON
        self.routes = {"/items": {"items": [{"id": 1, "name": "A"}]}}

    # 요청 하나 처리
    # request: httpx 요청
    def handle(self, request):
        self.calls.append(request.url.path)
        if self.mode == "timeout":
            raise httpx.ReadTimeout("가짜 timeout", request=request)
        if self.mode == "connect":
            raise httpx.ConnectError("가짜 연결 실패", request=request)
        if self.mode in ("500", "503"):
            return httpx.Response(int(self.mode), json={"error": "가짜 장애"})
        if request.url.path not in self.routes:
            return httpx.Response(404, json={"error": "없는 경로"})
        return httpx.Response(200, json=self.routes[request.url.path])

    # httpx 에 넘길 가짜 전송 계층
    @property
    def transport(self):
        return httpx.MockTransport(self.handle)


# 시험마다 새 가짜 서비스
@pytest.fixture
def fake_service():
    return FakeService()
