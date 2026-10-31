# 웹훅 서명 검증 — HMAC-SHA256 · 시각 허용 범위 · 상수시간 비교
#   역할: 받은 웹훅이 비밀키를 아는 상대가 보낸 것인지 · 오래된 재전송(replay)이 아닌지 확인
#   어디에: 웹훅 받는 경로(FastAPI · NiceGUI app.post) 맨 앞 — 본문을 JSON 으로 풀기 전에 원본 바이트로 검사
#   실패하면: InputError(서명 불일치 · 시각 범위 밖 · 헤더 없음) → 경로는 401 로 답하고 아무것도 저장하지 않음
#
# 서명 대상 = «시각.본문» 바이트(시각을 같이 서명해야 시각만 바꾼 재전송을 막음). 상대 규격이 다르면 signed_payload 만 고침
import hashlib
import hmac
import time

from src.core.errors import InputError

# 기본 허용 범위 초 — 보낸 시각과 지금이 이만큼 넘게 차이 나면 거부
TOLERANCE_SEC = 300


# 서명 대상 바이트 — «시각.본문»
# timestamp: 보낸 시각 문자열(유닉스 초) / body: 요청 본문 원본 바이트
def signed_payload(timestamp, body):
    return str(timestamp).encode("utf-8") + b"." + body


# 서명 만들기 — 보내는 쪽(가짜 서버 · 시험)용. 16진 문자열
# secret: 공유 비밀키 / timestamp: 보낸 시각 / body: 본문 바이트
def sign(secret, timestamp, body):
    # 비밀키 바이트
    key = secret.encode("utf-8") if isinstance(secret, str) else secret
    return hmac.new(key, signed_payload(timestamp, body), hashlib.sha256).hexdigest()


# 서명 검증 — 통과하면 None, 아니면 InputError
# secret: 공유 비밀키(환경변수에서) / body: 본문 원본 바이트 / signature: 서명 헤더 값(«sha256=» 앞머리 허용)
# timestamp: 시각 헤더 값 / tolerance_sec: 허용 범위 초 / now: 지금 유닉스 초(시험용 · None 이면 현재)
def verify_signature(secret, body, signature, timestamp, tolerance_sec=TOLERANCE_SEC, now=None):
    if not signature or not timestamp:
        raise InputError("웹훅 서명 · 시각 헤더 없음")
    try:
        # 보낸 시각 초
        sent = int(timestamp)
    # 숫자가 아닌 시각
    except ValueError:
        raise InputError("웹훅 시각 형식 오류: {}".format(timestamp))
    # 지금 초
    current = time.time() if now is None else now
    if abs(current - sent) > tolerance_sec:
        raise InputError("웹훅 시각 범위 밖 ({}초 차이 · 허용 {}초)".format(int(current - sent), tolerance_sec))
    # 받은 서명 — 앞머리 제거
    got = signature.split("=", 1)[1] if signature.startswith("sha256=") else signature
    # 기대 서명
    expected = sign(secret, timestamp, body)
    # 상수시간 비교 — 앞 글자가 맞는 만큼 빨리 끝나지 않아 한 글자씩 맞혀 보는 공격을 막음
    if not hmac.compare_digest(got, expected):
        raise InputError("웹훅 서명 불일치")
