# 외부 업무 API 클라이언트 — 외부 호출은 이 파일 한 곳으로 격리(CODE_RULE 3절) · timeout · 재시도 1회 · 실패 종류 구분
#   큰 판(재시도 간격 · Retry-After · 비동기 · 페이지 넘김)은 부품 창고 lib/api/api_client.py
import httpx

from src.core.errors import ExternalError, ExternalTimeout

# 재시도 대상 상태 코드 — 잠깐 몰리거나 게이트웨이 문제라 다시 보내면 될 수 있는 것
RETRY_STATUS = (429, 502, 503, 504)


# 외부 API 클라이언트
class ApiClient:
    # base_url: 기본 주소(config) / timeout_sec: 제한 시간 초(config · 기본 10) / max_retry: 재시도 횟수 / transport: 가짜 서버(시험용)
    def __init__(self, base_url, timeout_sec=10, max_retry=1, transport=None):
        # 제한 시간 초
        self.timeout_sec = timeout_sec
        # 재시도 횟수(첫 시도 제외)
        self.max_retry = max_retry
        # httpx 클라이언트 — 연결 재사용
        self.http = httpx.Client(base_url=base_url, timeout=timeout_sec, transport=transport)

    # GET → JSON. 성공 외에는 errors.py 예외
    # path: 기본 주소 뒤 경로 / params: 쿼리 인자
    def get_json(self, path, params=None):
        # 마지막 실패 사유
        reason = ""
        # 시도 번호 — 1 부터
        for attempt in range(1, self.max_retry + 2):
            try:
                # 응답
                resp = self.http.get(path, params=params)
            # 제한 시간 안에 답 없음 — 재시도 대상
            except httpx.TimeoutException:
                reason = "timeout"
                continue
            # 연결 실패 — 서버에 닿기 전이라 다시 보내도 됨(CODE_RULE 5절)
            except httpx.ConnectError:
                reason = "연결 실패"
                continue
            # 그 밖의 전송 오류 — 보냈는지 알 수 없어 다시 보내지 않음
            except httpx.HTTPError as err:
                raise ExternalError("API 연결 실패 {} ({})".format(path, type(err).__name__))
            if resp.status_code in RETRY_STATUS:
                reason = "HTTP {}".format(resp.status_code)
                continue
            if resp.status_code >= 400:
                raise ExternalError("API 오류 응답 {} (HTTP {})".format(path, resp.status_code))
            try:
                return resp.json()
            # 본문이 JSON 이 아님
            except ValueError:
                raise ExternalError("API 응답 형식 오류 {} (JSON 아님)".format(path))
        if reason == "timeout":
            raise ExternalTimeout("API 연결 실패 {} (timeout {}초 · {}회 시도)".format(path, self.timeout_sec, attempt))
        raise ExternalError("API 일시 오류 {} ({} · {}회 시도)".format(path, reason, attempt))

    # 연결 닫기
    def close(self):
        self.http.close()
