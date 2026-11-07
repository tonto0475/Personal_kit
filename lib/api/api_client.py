# 외부 API 공통 클라이언트 — 동기판 · 비동기판 · for 문 재시도 · 결과 3분류 · 페이지 넘김
#   역할: 기본 주소 · timeout · 토큰(환경변수) · 요청 로그를 한 곳에 묶고, 재시도 규칙과 실패 종류 구분을 통일
#   어디에: src/api/ 의 외부 호출 전부(화면 NiceGUI 안에서는 AsyncApiClient — 화면 멈춤 방지)
#   실패하면: 성공 외에는 errors.py 예외로 올라감 — 실패(ExternalError) · 모름(ExternalTimeout, 서버가 처리했는지 알 수 없음)
#
# 재시도 규칙(유저 지정 · 설문 #5)
#   - 대상: 429 · 502 · 503 · 504 · timeout · 연결 실패 만(400 · 401 · 404 · 500 등은 다시 보내도 같은 답이라 바로 실패)
#   - 간격: backoff_sec × 2^(시도-1), backoff_max_sec 상한 · 응답에 Retry-After 가 있으면 그 값과 큰 쪽
#   - POST · PATCH 는 Idempotency-Key 헤더가 있을 때만 재시도(키가 없으면 두 번 처리될 수 있음) · 단 연결 실패는 서버에 닿기 전이라 키 없이도 재시도
import asyncio
import email.utils
import logging
import os
import time

import httpx

from src.core.errors import ExternalError, ExternalTimeout

# 이 모듈 로거 — 요청 로그(관련 로직 칸 «통신»)
logger = logging.getLogger("api")

# 재시도할 응답 상태 코드
RETRY_STATUS = (429, 502, 503, 504)
# 결과를 «모름» 으로 보는 상태 코드 — 게이트웨이 timeout(뒤 서버는 처리했을 수도 있음)
UNKNOWN_STATUS = (504,)
# 키 없이도 재시도해도 되는 메서드 — 같은 요청을 여러 번 보내도 결과가 같음
IDEMPOTENT_METHODS = ("GET", "HEAD", "OPTIONS", "PUT", "DELETE")
# 결과 3분류 값
SUCCESS, FAIL, UNKNOWN = "성공", "실패", "모름"


# 결과 3분류 — 응답 또는 예외를 성공 · 실패 · 모름 중 하나로
# response: httpx 응답(없으면 None) / exc: 요청 중 난 예외(없으면 None)
def classify(response=None, exc=None):
    if exc is not None:
        # timeout · 보낸 뒤 연결 끊김 — 서버가 받았는지 알 수 없음
        if isinstance(exc, (httpx.TimeoutException, httpx.RemoteProtocolError, httpx.ReadError)):
            return UNKNOWN
        # 연결 실패 등 — 보내지 못함
        return FAIL
    if response.status_code in UNKNOWN_STATUS:
        return UNKNOWN
    if 200 <= response.status_code < 300:
        return SUCCESS
    return FAIL


# 재시도 여부 — 메서드 · 헤더 · 결과로 판단
# method: HTTP 메서드 / headers: 보낸 요청 헤더 / response: 응답(없으면 None) / exc: 예외(없으면 None)
def should_retry(method, headers, response=None, exc=None):
    # 연결 실패 — 요청이 서버에 닿기 전이라 메서드와 상관없이 다시 보내도 두 번 처리되지 않음(CODE_RULE 5절)
    if isinstance(exc, httpx.ConnectError):
        return True
    # 재시도해도 두 번 처리되지 않는 요청인가
    safe = method.upper() in IDEMPOTENT_METHODS or "idempotency-key" in {k.lower() for k in headers}
    if not safe:
        return False
    if exc is not None:
        return isinstance(exc, httpx.TimeoutException)
    return response.status_code in RETRY_STATUS


# Retry-After 헤더 → 기다릴 초(없거나 못 읽으면 None). 초 숫자 · HTTP 날짜 둘 다
# response: 응답(없으면 None)
def retry_after_sec(response):
    if response is None:
        return None
    # 헤더 원문
    raw = response.headers.get("Retry-After")
    if not raw:
        return None
    if raw.strip().isdigit():
        return float(raw.strip())
    try:
        # HTTP 날짜 → 지금부터 남은 초
        when = email.utils.parsedate_to_datetime(raw)
        return max(0.0, when.timestamp() - time.time())
    # 형식이 틀린 헤더 — 무시하고 기본 간격
    except (TypeError, ValueError):
        return None


# 이번 재시도 전 기다릴 초 — 점점 늘리는 간격과 Retry-After 중 큰 쪽
# attempt: 방금 끝난 시도 번호(1 부터) / response: 응답 / backoff_sec: 첫 간격 초 / backoff_max_sec: 간격 상한 초
def wait_sec(attempt, response, backoff_sec, backoff_max_sec):
    # 점점 늘리는 간격
    base = min(backoff_sec * (2 ** (attempt - 1)), backoff_max_sec)
    # 서버가 요청한 대기
    server = retry_after_sec(response)
    return base if server is None else max(base, server)


# 최종 결과를 예외로 — 성공이면 응답 그대로, 실패 · 모름이면 errors.py 예외
# method · url: 요청 / response: 마지막 응답 / exc: 마지막 예외 / timeout_sec: 제한 시간 초(문구용) / attempts: 시도 횟수
def raise_for_result(method, url, response, exc, timeout_sec, attempts):
    # 3분류 결과
    result = classify(response, exc)
    if result == SUCCESS:
        return response
    # 문구 앞부분
    head = "{} {} ({}회 시도)".format(method, url, attempts)
    if result == UNKNOWN:
        if exc is not None:
            raise ExternalTimeout("{} 결과 모름 — {} (timeout {}초)".format(head, type(exc).__name__, timeout_sec)) from exc
        raise ExternalTimeout("{} 결과 모름 — HTTP {}".format(head, response.status_code))
    if exc is not None:
        raise ExternalError("{} 실패 — {}".format(head, type(exc).__name__)) from exc
    raise ExternalError("{} 실패 — HTTP {}".format(head, response.status_code))


# 공통 설정 — 동기판 · 비동기판이 같이 씀
# base_url: 기본 주소 / timeout_sec: 제한 시간 초 / max_retry: 재시도 횟수(첫 시도 제외)
# backoff_sec: 첫 재시도 간격 초 / backoff_max_sec: 간격 상한 초 / token_env: 토큰이 든 환경변수 이름(None 이면 토큰 없음)
def _client_kwargs(base_url, timeout_sec, token_env, transport):
    # 기본 헤더
    headers = {}
    if token_env:
        # 토큰 값 — 로그에 찍지 않음
        token = os.environ.get(token_env, "")
        if token:
            headers["Authorization"] = "Bearer " + token
    # httpx 클라이언트 인자
    kwargs = {"base_url": base_url, "timeout": timeout_sec, "headers": headers}
    if transport is not None:
        kwargs["transport"] = transport
    return kwargs


# 동기 API 클라이언트 — 스크립트 · 배치 · 테스트용
class ApiClient:
    # base_url: 기본 주소 / timeout_sec: 제한 시간 초 / max_retry: 재시도 횟수 / backoff_sec: 첫 간격 초
    # backoff_max_sec: 간격 상한 초 / token_env: 토큰 환경변수 이름 / transport: 가짜 서버(시험용) / sleep: 대기 함수(시험에서 바꿔 끼움)
    def __init__(self, base_url, timeout_sec=10, max_retry=3, backoff_sec=0.5, backoff_max_sec=8,
                 token_env=None, transport=None, sleep=time.sleep):
        # 제한 시간 초
        self.timeout_sec = timeout_sec
        # 재시도 횟수
        self.max_retry = max_retry
        # 첫 간격 · 상한 초
        self.backoff_sec, self.backoff_max_sec = backoff_sec, backoff_max_sec
        # 대기 함수
        self.sleep = sleep
        # httpx 클라이언트 — 연결 재사용
        self.http = httpx.Client(**_client_kwargs(base_url, timeout_sec, token_env, transport))

    # 요청 1건 — 재시도 포함 · 성공 응답만 돌려줌
    # method: HTTP 메서드 / path: 기본 주소 뒤 경로 / kwargs: httpx 인자(params · json · headers)
    def request(self, method, path, **kwargs):
        # 보낼 헤더 — 재시도 판단에 씀
        headers = kwargs.get("headers") or {}
        # 마지막 응답 · 예외
        response, exc = None, None
        # 시도 번호 — 1 부터
        for attempt in range(1, self.max_retry + 2):
            # 시작 시각
            started = time.monotonic()
            response, exc = None, None
            try:
                response = self.http.request(method, path, **kwargs)
            # 요청 중 예외 — 분류는 classify
            except httpx.HTTPError as err:
                exc = err
            # 걸린 밀리초
            took_ms = (time.monotonic() - started) * 1000
            logger.info("%s %s → %s (%.0fms, 시도 %d)", method, path,
                        response.status_code if response is not None else type(exc).__name__, took_ms, attempt)
            if attempt > self.max_retry or not should_retry(method, headers, response, exc):
                break
            self.sleep(wait_sec(attempt, response, self.backoff_sec, self.backoff_max_sec))
        return raise_for_result(method, path, response, exc, self.timeout_sec, attempt)

    # GET → JSON
    # path: 경로 / params: 쿼리 인자
    def get_json(self, path, params=None):
        return self.request("GET", path, params=params).json()

    # POST → JSON. idempotency_key 를 주면 재시도 가능
    # path: 경로 / body: 보낼 JSON / idempotency_key: 중복 실행 방지 키(None 이면 재시도 안 함)
    def post_json(self, path, body, idempotency_key=None):
        # 요청 헤더
        headers = {"Idempotency-Key": idempotency_key} if idempotency_key else {}
        return self.request("POST", path, json=body, headers=headers).json()

    # 연결 닫기
    def close(self):
        self.http.close()


# 비동기 API 클라이언트 — NiceGUI 화면 안에서(await 동안 화면이 멈추지 않음)
class AsyncApiClient:
    # 인자는 ApiClient 와 같음 / sleep: 비동기 대기 함수
    def __init__(self, base_url, timeout_sec=10, max_retry=3, backoff_sec=0.5, backoff_max_sec=8,
                 token_env=None, transport=None, sleep=asyncio.sleep):
        # 제한 시간 초
        self.timeout_sec = timeout_sec
        # 재시도 횟수
        self.max_retry = max_retry
        # 첫 간격 · 상한 초
        self.backoff_sec, self.backoff_max_sec = backoff_sec, backoff_max_sec
        # 비동기 대기 함수
        self.sleep = sleep
        # httpx 비동기 클라이언트
        self.http = httpx.AsyncClient(**_client_kwargs(base_url, timeout_sec, token_env, transport))

    # 요청 1건 — 재시도 포함 · 성공 응답만 돌려줌(동기판과 같은 규칙)
    # method: HTTP 메서드 / path: 경로 / kwargs: httpx 인자
    async def request(self, method, path, **kwargs):
        # 보낼 헤더
        headers = kwargs.get("headers") or {}
        # 마지막 응답 · 예외
        response, exc = None, None
        # 시도 번호
        for attempt in range(1, self.max_retry + 2):
            # 시작 시각
            started = time.monotonic()
            response, exc = None, None
            try:
                response = await self.http.request(method, path, **kwargs)
            # 요청 중 예외
            except httpx.HTTPError as err:
                exc = err
            # 걸린 밀리초
            took_ms = (time.monotonic() - started) * 1000
            logger.info("%s %s → %s (%.0fms, 시도 %d)", method, path,
                        response.status_code if response is not None else type(exc).__name__, took_ms, attempt)
            if attempt > self.max_retry or not should_retry(method, headers, response, exc):
                break
            await self.sleep(wait_sec(attempt, response, self.backoff_sec, self.backoff_max_sec))
        return raise_for_result(method, path, response, exc, self.timeout_sec, attempt)

    # GET → JSON
    # path: 경로 / params: 쿼리 인자
    async def get_json(self, path, params=None):
        return (await self.request("GET", path, params=params)).json()

    # POST → JSON
    # path: 경로 / body: JSON / idempotency_key: 중복 실행 방지 키
    async def post_json(self, path, body, idempotency_key=None):
        # 요청 헤더
        headers = {"Idempotency-Key": idempotency_key} if idempotency_key else {}
        return (await self.request("POST", path, json=body, headers=headers)).json()

    # 연결 닫기
    async def close(self):
        await self.http.aclose()


# 페이지 번호 방식 — 빈 페이지 또는 size 보다 적게 오면 끝
# get_json: (경로, 쿼리) → dict 함수(ApiClient.get_json) / path: 경로 / items_key: 목록이 든 키
# page_param · size_param: 쿼리 이름 / size: 한 페이지 개수 / start: 첫 페이지 번호 / max_pages: 무한 반복 방지 상한
def iter_pages(get_json, path, items_key="items", page_param="page", size_param="size", size=100, start=1, max_pages=10000):
    # 페이지 번호
    for page in range(start, start + max_pages):
        # 이번 페이지 목록
        items = get_json(path, {page_param: page, size_param: size}).get(items_key) or []
        # 항목 하나
        for item in items:
            yield item
        if len(items) < size:
            return
    raise ExternalError("{} 페이지가 {}장을 넘음 — 끝 신호 없음".format(path, max_pages))


# 커서 방식 — 응답의 다음 커서가 비면 끝 · 같은 커서가 다시 오면 무한 반복이라 실패
# get_json: (경로, 쿼리) → dict 함수 / path: 경로 / items_key: 목록 키 / cursor_key: 응답의 다음 커서 키
# cursor_param: 쿼리의 커서 이름 / extra: 함께 보낼 쿼리
def iter_cursor(get_json, path, items_key="items", cursor_key="next_cursor", cursor_param="cursor", extra=None):
    # 이번에 보낼 커서 — 처음엔 없음
    cursor = None
    # 이미 받은 커서들
    seen = set()
    while True:
        # 쿼리
        params = dict(extra or {})
        if cursor is not None:
            params[cursor_param] = cursor
        # 응답 본문
        data = get_json(path, params)
        # 항목 하나
        for item in data.get(items_key) or []:
            yield item
        cursor = data.get(cursor_key)
        if not cursor:
            return
        if cursor in seen:
            raise ExternalError("{} 커서 반복({}) — 무한 반복 방지로 중단".format(path, cursor))
        seen.add(cursor)
