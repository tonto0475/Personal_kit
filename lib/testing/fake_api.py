# 가짜 API 서버 + 장애 주입 — httpx.MockTransport 기반(네트워크 없이 · 포트 없이)
#   역할: 경로별 응답을 등록하고, 다음 요청 N번에 지연 · 5xx · timeout · 같은 응답 두 번을 끼워 넣음
#   어디에: tests/ 의 API 시험(재시도 · 실패 분류 · 중복 수신). ApiClient(transport=fake.transport) 처럼 넘김
#   실패하면: 등록 안 된 경로는 404 · 시험이 기대와 다르면 fake.calls(받은 요청 목록)로 몇 번 왔는지 확인
import json
import time

import httpx


# 가짜 API — 동기 · 비동기 httpx 클라이언트 둘 다에 붙음
class FakeApi:
    def __init__(self):
        # 경로 표 — (메서드, 경로) → 처리 함수(request → httpx.Response)
        self.routes = {}
        # 장애 주입 줄 — 앞에서부터 하나씩 꺼내 다음 요청에 적용
        self.faults = []
        # 받은 요청 목록 — (메서드, 경로, 헤더 dict)
        self.calls = []
        # 마지막으로 보낸 응답 — «같은 응답 두 번» 용
        self.last = None

    # 경로 등록 — body 가 함수면 request 를 받아 dict · Response 를 돌려줌, 아니면 고정 JSON
    # method: HTTP 메서드 / path: 경로 / body: 응답 JSON 또는 함수 / status: 상태 코드
    def add(self, method, path, body=None, status=200):
        # 처리 함수
        def handler(request):
            # 응답 내용
            out = body(request) if callable(body) else body
            if isinstance(out, httpx.Response):
                return out
            return httpx.Response(status, json=out)
        self.routes[(method.upper(), path)] = handler

    # 다음 요청 times 번을 5xx 로
    # status: 상태 코드 / times: 횟수 / retry_after: Retry-After 헤더 값(None 이면 안 붙임)
    def fail_next(self, status=503, times=1, retry_after=None):
        self.faults += [("status", status, retry_after)] * times

    # 다음 요청 times 번을 timeout 으로(서버가 답하지 않음)
    def timeout_next(self, times=1):
        self.faults += [("timeout", None, None)] * times

    # 다음 요청 times 번을 연결 실패로(서버에 닿지 못함)
    def connect_fail_next(self, times=1):
        self.faults += [("connect", None, None)] * times

    # 다음 요청을 sec 초 늦게 — 클라이언트 timeout 보다 길면 실제로 기다리지 않고 timeout 예외
    def delay_next(self, sec, times=1):
        self.faults += [("delay", sec, None)] * times

    # 다음 요청에 직전 응답을 그대로 한 번 더(재전송 · 같은 페이지 두 번)
    def repeat_last(self, times=1):
        self.faults += [("repeat", None, None)] * times

    # 요청 하나 처리 — MockTransport 가 부름
    # request: httpx 요청
    def _handle(self, request):
        # 경로
        path = request.url.path
        self.calls.append((request.method, path, dict(request.headers)))
        # 이번에 적용할 장애
        fault = self.faults.pop(0) if self.faults else None
        if fault and fault[0] == "timeout":
            raise httpx.ReadTimeout("가짜 timeout", request=request)
        if fault and fault[0] == "connect":
            raise httpx.ConnectError("가짜 연결 실패", request=request)
        if fault and fault[0] == "delay":
            # 클라이언트 읽기 제한 초
            read_limit = (request.extensions.get("timeout") or {}).get("read")
            if read_limit is not None and fault[1] >= read_limit:
                raise httpx.ReadTimeout("가짜 지연 {}초 ≥ timeout {}초".format(fault[1], read_limit), request=request)
            time.sleep(fault[1])
        if fault and fault[0] == "status":
            # 장애 응답 헤더
            headers = {"Retry-After": str(fault[2])} if fault[2] is not None else {}
            return httpx.Response(fault[1], json={"error": "가짜 장애"}, headers=headers)
        if fault and fault[0] == "repeat" and self.last is not None:
            return httpx.Response(self.last[0], content=self.last[1], headers={"content-type": "application/json"})
        # 처리 함수
        handler = self.routes.get((request.method, path))
        # 응답
        response = handler(request) if handler else httpx.Response(404, json={"error": "없는 경로 " + path})
        # 본문 바이트
        content = response.read()
        self.last = (response.status_code, content)
        return httpx.Response(response.status_code, content=content, headers=response.headers)

    # httpx 에 넘길 가짜 전송 계층
    @property
    def transport(self):
        return httpx.MockTransport(self._handle)


# 요청 본문 JSON 읽기 — 처리 함수 안에서
# request: httpx 요청
def body_json(request):
    return json.loads(request.content.decode("utf-8")) if request.content else None
