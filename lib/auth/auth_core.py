# 로그인 핵심 — 비밀번호 해시 · 서명 세션 토큰 · 계정 표 · 역할 확인 · «자기 것만» 거르기(표준 라이브러리만)
#   역할: 웹 틀(NiceGUI · FastAPI)과 무관한 판정만 — 맞는 비밀번호인가 · 토큰이 위조 · 만료되지 않았나 · 이 역할이 볼 수 있나 · 이 행이 내 것인가
#   어디에: auth_web.py 가 이 함수들을 불러 쿠키 · 경로 · 데코레이터를 만든다 · 화면 없이 서비스 함수 안에서 own_rows · check_owner 를 직접 써도 된다
#   실패하면: 로그인 실패 · 권한 없음 → AuthError(status 401 · 403 · 문구 고정) · 비밀키 없음 → InputError(«AUTH_SECRET 환경변수 없음»)
import base64
import hashlib
import hmac
import json
import os
import secrets
import time

from src.core.errors import InputError

# 실패 문구 — 화면 · 응답 detail 에 그대로(아이디가 없는 경우와 비밀번호가 틀린 경우를 같은 문구로 — 아이디 존재 여부를 알리지 않기 위해)
MSG_LOGIN_FAIL = "로그인 실패 (아이디 또는 비밀번호 불일치)"
# 빈 입력 문구
MSG_EMPTY = "아이디 · 비밀번호 입력 필요"
# 로그인 안 한 상태 문구
MSG_NEED_LOGIN = "로그인 필요"
# 역할 · 소유자가 맞지 않을 때 문구
MSG_FORBIDDEN = "권한 없음"
# 남의 자료를 열 때 문구
MSG_NOT_OWNER = "권한 없음 (본인 자료만 조회 가능)"

# 비밀키 환경변수 이름 — 값은 .env 에만(코드 · 로그 · 커밋 금지)
SECRET_ENV = "AUTH_SECRET"
# 세션 유지 시간(초) — 8시간
SESSION_SEC = 8 * 3600
# 비밀번호 해시 반복 횟수 — PBKDF2-SHA256
HASH_ROUNDS = 200_000
# 운영자 역할 이름 — own_rows · check_owner 에서 전체를 보는 역할 기본값
ADMIN_ROLES = ("운영자",)


# 로그인 · 권한 실패 — status 는 HTTP 코드(401 로그인 필요 · 실패 / 403 권한 없음)
class AuthError(InputError):
    # message: 화면 문구 / status: HTTP 코드
    def __init__(self, message, status=401):
        super().__init__(message)
        # HTTP 코드
        self.status = status


# 비밀번호 → 저장용 해시 문자열 «pbkdf2$반복$소금hex$해시hex»(평문은 어디에도 남기지 않는다)
# password: 평문 / rounds: 반복 횟수(시험에서만 줄임)
def hash_password(password, rounds=HASH_ROUNDS):
    # 계정마다 다른 소금 — 같은 비밀번호도 다른 해시
    salt = secrets.token_bytes(16)
    # 해시 바이트
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, rounds)
    return "pbkdf2${}${}${}".format(rounds, salt.hex(), digest.hex())


# 평문이 저장 해시와 맞나 — 상수시간 비교 · 형식이 깨진 해시는 False
# password: 입력 평문 / stored: hash_password 결과
def verify_password(password, stored):
    try:
        # 해시 네 조각
        algo, rounds, salt_hex, digest_hex = stored.split("$")
        if algo != "pbkdf2":
            return False
        # 다시 계산한 해시
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(rounds))
    # 조각 수 · 숫자 · hex 가 틀린 저장값
    except (ValueError, AttributeError):
        return False
    return hmac.compare_digest(digest.hex(), digest_hex)


# 비밀키 읽기 — 인자로 받으면 그 값(시험용) · 없으면 환경변수 · 둘 다 없으면 InputError
# secret: 직접 넘긴 비밀키(None 이면 환경변수)
def get_secret(secret=None):
    # 쓸 비밀키
    value = secret or os.environ.get(SECRET_ENV, "")
    if len(value) < 16:
        raise InputError("{} 환경변수 없음 또는 16자 미만 (.env 에 설정)".format(SECRET_ENV))
    return value


# base64url 인코딩(끝 = 제거)
# data: 바이트
def _b64(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


# base64url 디코딩(끝 = 복원)
# text: 문자열
def _unb64(text):
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


# 세션 토큰 만들기 — «본문b64.서명b64» · 본문 = 아이디 · 역할 · 이름 · 만료 시각(쿠키에 넣는다 · 서버 저장소 불필요)
# user: {"id","role","name"} / secret: 비밀키 / ttl: 유지 초 / now: 현재 시각(시험용)
def make_token(user, secret, ttl=SESSION_SEC, now=None):
    # 본문 사전
    payload = {"u": user["id"], "r": user["role"], "n": user.get("name", ""),
               "exp": int((now if now is not None else time.time()) + ttl)}
    # 본문 b64
    body = _b64(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    # 서명 b64
    sig = _b64(hmac.new(secret.encode("utf-8"), body.encode("ascii"), hashlib.sha256).digest())
    return body + "." + sig


# 세션 토큰 읽기 — 서명이 맞고 만료 전이면 {"id","role","name"} · 아니면 None(위조 · 만료 · 형식 깨짐 모두 None)
# token: 쿠키 값 / secret: 비밀키 / now: 현재 시각(시험용)
def read_token(token, secret, now=None):
    if not token or token.count(".") != 1:
        return None
    # 본문 · 서명
    body, sig = token.split(".")
    # 기대 서명
    expected = _b64(hmac.new(secret.encode("utf-8"), body.encode("ascii", "replace"), hashlib.sha256).digest())
    if not hmac.compare_digest(sig, expected):
        return None
    try:
        # 본문 사전
        payload = json.loads(_unb64(body).decode("utf-8"))
    # 서명은 맞는데 본문이 깨진 경우(일어나면 안 됨)
    except (ValueError, UnicodeDecodeError):
        return None
    if payload.get("exp", 0) < (now if now is not None else time.time()):
        return None
    return {"id": payload["u"], "role": payload["r"], "name": payload.get("n", "")}


# 계정 표 — 아이디 → {"id","role","name","password_hash"} · 메모리에 둔다(DB 를 쓰면 get 만 같은 모양으로 바꿔 끼운다)
class UserStore:
    # users: 계정 사전 목록(password_hash 필수 · 평문 password 칸은 받지 않는다)
    def __init__(self, users=()):
        # 아이디 → 계정
        self._users = {}
        for u in users:
            self.add(u)

    # 계정 하나 추가
    # user: {"id","role","name","password_hash"}
    def add(self, user):
        if "password" in user:
            raise InputError("계정에 평문 password 칸 금지 (hash_password 결과를 password_hash 에)")
        self._users[str(user["id"])] = dict(user)

    # 아이디로 계정 찾기 — 없으면 None
    # login_id: 아이디(사번)
    def get(self, login_id):
        return self._users.get(str(login_id))


# 아이디 · 비밀번호 확인 — 맞으면 해시 뺀 계정 {"id","role","name"} · 틀리면 AuthError(401 · 문구 고정)
# store: UserStore(get 만 있으면 됨) / login_id: 아이디 / password: 평문
def authenticate(store, login_id, password):
    # 앞뒤 공백 뺀 아이디
    login_id = (login_id or "").strip()
    if not login_id or not password:
        raise AuthError(MSG_EMPTY, 401)
    # 찾은 계정
    user = store.get(login_id)
    # 계정이 없어도 같은 시간 · 같은 문구 — 더미 해시로 한 번 계산
    stored = user["password_hash"] if user else _DUMMY_HASH
    if not verify_password(password, stored) or user is None:
        raise AuthError(MSG_LOGIN_FAIL, 401)
    return {"id": user["id"], "role": user["role"], "name": user.get("name", "")}


# 계정 없는 아이디에 쓰는 더미 해시 — 응답 시간으로 아이디 존재 여부가 새지 않게
_DUMMY_HASH = hash_password(secrets.token_hex(8))


# 역할 확인 — 로그인 안 했으면 401 · 역할이 목록에 없으면 403 · 맞으면 user 그대로
# user: 로그인한 계정 또는 None / roles: 허용 역할들(비면 로그인만 확인)
def check_role(user, roles=()):
    if user is None:
        raise AuthError(MSG_NEED_LOGIN, 401)
    if roles and user["role"] not in roles:
        raise AuthError(MSG_FORBIDDEN, 403)
    return user


# «자기 것만» 행 거르기 — 운영자 역할은 전부 · 그 밖은 owner_key 칸이 내 아이디인 행만
# rows: 사전 목록 / user: 로그인한 계정 / owner_key: 소유자 아이디 칸 / admin_roles: 전체를 보는 역할
def own_rows(rows, user, owner_key="owner_id", admin_roles=ADMIN_ROLES):
    check_role(user)
    if user["role"] in admin_roles:
        return list(rows)
    return [r for r in rows if str(r.get(owner_key)) == str(user["id"])]


# 행 하나가 내 것인지 — 운영자는 통과 · 남의 것이면 AuthError(403)
# user: 로그인한 계정 / owner_id: 그 행의 소유자 아이디 / admin_roles: 전체를 보는 역할
def check_owner(user, owner_id, admin_roles=ADMIN_ROLES):
    check_role(user)
    if user["role"] not in admin_roles and str(owner_id) != str(user["id"]):
        raise AuthError(MSG_NOT_OWNER, 403)
    return user


# SQL 조건 조각 — 운영자면 ("1=1", ()) · 그 밖은 ("<열> = ?", (내 아이디,)) · WHERE 뒤에 붙여 쓴다(sqlite3 자리표시자 ?)
# user: 로그인한 계정 / column: 소유자 열 이름(코드에서 정한 고정 이름만 — 사용자 입력 금지) / admin_roles: 전체를 보는 역할
def owner_where(user, column="owner_id", admin_roles=ADMIN_ROLES):
    check_role(user)
    if user["role"] in admin_roles:
        return "1=1", ()
    return "{} = ?".format(column), (str(user["id"]),)


# 시험 계정 표 — 운영자 1 · 사원 2 · 모두 같은 비밀번호(시험 · 시연 전용 — 제출 앱에서는 과제가 준 계정으로 바꾼다)
# password: 시험 비밀번호 / rounds: 해시 반복(시험에서는 줄여 빠르게)
def make_test_store(password="test1234", rounds=HASH_ROUNDS):
    # 시험 계정 셋 — (아이디, 역할, 이름)
    accounts = [("admin", "운영자", "운영자"), ("E1001", "사원", "사원1"), ("E1002", "사원", "사원2")]
    return UserStore({"id": i, "role": r, "name": n, "password_hash": hash_password(password, rounds)}
                     for i, r, n in accounts)
