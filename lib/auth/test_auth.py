# lib/auth 시험 — 해시(평문 미저장) · 토큰 위조 · 만료 · 로그인 실패 문구 · 역할 403 · 남의 것 403 · 자기 것만 · FastAPI 경로
#   핵심(auth_core)은 표준 라이브러리만 — WSL python3 에 fastapi 가 없어도 돈다 · FastAPI 시험은 fastapi 가 있을 때만
import sqlite3
import sys
from pathlib import Path

import pytest

# 이 폴더 · 저장소 루트 — import 경로에 추가
HERE = Path(__file__).resolve().parent
for p in (HERE.parents[1],):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from lib.auth.auth_core import (MSG_EMPTY, MSG_FORBIDDEN, MSG_LOGIN_FAIL, MSG_NEED_LOGIN, MSG_NOT_OWNER,  # noqa: E402
                                AuthError, UserStore, authenticate, check_owner, check_role, get_secret,
                                hash_password, make_test_store, make_token, own_rows, owner_where, read_token,
                                verify_password)
from src.core.errors import InputError  # noqa: E402

# 시험 비밀키 — 실제 값이 아님(16자 이상)
SECRET = "test-secret-0123456789"
# 시험 비밀번호
PW = "test1234"
# 시험 계정 표(해시 반복을 줄여 빠르게)
STORE = make_test_store(PW, rounds=1000)
# 업무 행 — 소유자 칸 owner_id
ROWS = [{"no": 1, "owner_id": "E1001"}, {"no": 2, "owner_id": "E1002"}, {"no": 3, "owner_id": "E1001"}]


# 해시 — 평문이 안 보이고 · 같은 비밀번호도 소금이 달라 해시가 다르고 · 맞는 것만 통과 · 깨진 저장값은 False
def test_hash():
    # 해시 둘
    h1, h2 = hash_password(PW, 1000), hash_password(PW, 1000)
    assert PW not in h1 and h1 != h2 and h1.startswith("pbkdf2$1000$")
    assert verify_password(PW, h1) and not verify_password("wrong", h1)
    assert not verify_password(PW, "깨진값") and not verify_password(PW, None)


# 계정 표 — 평문 password 칸을 넣으면 거부
def test_store_rejects_plain():
    with pytest.raises(InputError, match="평문"):
        UserStore([{"id": "x", "role": "사원", "password": "1234"}])


# 로그인 — 성공은 해시 뺀 계정 · 없는 아이디와 틀린 비밀번호는 같은 문구 · 빈 입력 문구
def test_authenticate():
    # 확인된 계정
    user = authenticate(STORE, " E1001 ", PW)
    assert user == {"id": "E1001", "role": "사원", "name": "사원1"}
    for login_id, pw in [("E1001", "wrong"), ("없음", PW)]:
        with pytest.raises(AuthError) as e:
            authenticate(STORE, login_id, pw)
        assert str(e.value) == MSG_LOGIN_FAIL and e.value.status == 401
    with pytest.raises(AuthError, match=MSG_EMPTY):
        authenticate(STORE, "", PW)


# 토큰 — 왕복 · 서명 위조 · 본문 바꿔치기 · 다른 비밀키 · 만료 · 형식 깨짐 모두 None
def test_token():
    # 토큰
    tok = make_token({"id": "E1001", "role": "사원", "name": "사원1"}, SECRET, ttl=60, now=1000)
    assert read_token(tok, SECRET, now=1030) == {"id": "E1001", "role": "사원", "name": "사원1"}
    # 본문 · 서명
    body, sig = tok.split(".")
    # 운영자로 바꾼 본문
    forged = make_token({"id": "E1001", "role": "운영자"}, SECRET, ttl=60, now=1000).split(".")[0]
    assert read_token(forged + "." + sig, SECRET, now=1030) is None
    assert read_token(body + "." + sig[:-2] + "AA", SECRET, now=1030) is None
    assert read_token(tok, "other-secret-0123456789", now=1030) is None
    assert read_token(tok, SECRET, now=1061) is None
    assert read_token("", SECRET) is None and read_token("a.b.c", SECRET) is None


# 비밀키 — 환경변수가 없거나 짧으면 InputError(이름만 알림)
def test_secret(monkeypatch):
    monkeypatch.delenv("AUTH_SECRET", raising=False)
    with pytest.raises(InputError, match="AUTH_SECRET"):
        get_secret()
    monkeypatch.setenv("AUTH_SECRET", SECRET)
    assert get_secret() == SECRET


# 역할 · 소유자 — 로그인 안 함 401 · 역할 밖 403 · 남의 것 403 · 운영자는 통과
def test_role_owner():
    # 계정 둘
    admin, emp = authenticate(STORE, "admin", PW), authenticate(STORE, "E1001", PW)
    with pytest.raises(AuthError, match=MSG_NEED_LOGIN):
        check_role(None)
    with pytest.raises(AuthError) as e:
        check_role(emp, ("운영자",))
    assert e.value.status == 403 and str(e.value) == MSG_FORBIDDEN
    assert check_role(admin, ("운영자",)) is admin
    with pytest.raises(AuthError) as e:
        check_owner(emp, "E1002")
    assert e.value.status == 403 and str(e.value) == MSG_NOT_OWNER
    assert check_owner(emp, "E1001") is emp and check_owner(admin, "E1002") is admin


# 자기 것만 — 사원은 자기 행만 · 운영자는 전부 · SQL 조각도 같은 결과
def test_own_rows_and_sql():
    # 계정 둘
    admin, emp = authenticate(STORE, "admin", PW), authenticate(STORE, "E1001", PW)
    assert [r["no"] for r in own_rows(ROWS, emp)] == [1, 3]
    assert [r["no"] for r in own_rows(ROWS, admin)] == [1, 2, 3]
    # 메모리 DB
    con = sqlite3.connect(":memory:")
    con.execute("CREATE TABLE t (no INTEGER, owner_id TEXT)")
    con.executemany("INSERT INTO t VALUES (?, ?)", [(r["no"], r["owner_id"]) for r in ROWS])
    for user, expected in [(emp, [1, 3]), (admin, [1, 2, 3])]:
        # 조건 · 값
        where, params = owner_where(user)
        assert [n for (n,) in con.execute("SELECT no FROM t WHERE " + where + " ORDER BY no", params)] == expected


# ======= FastAPI 경로 — fastapi 가 있을 때만 =======


# 시험용 앱 — 로그인 경로 + 운영자 전용 · 로그인만 · 행 하나(소유자 확인) · 내 목록
@pytest.fixture
def client():
    pytest.importorskip("fastapi")
    from fastapi import FastAPI, Request
    from fastapi.testclient import TestClient

    from lib.auth.auth_web import add_auth, current_user, deny_if_not_owner, require_role

    # 앱
    app = FastAPI()
    add_auth(app, STORE, secret=SECRET)

    # 운영자 전용
    @app.get("/admin")
    @require_role("운영자")
    async def admin_page(request: Request):
        return {"who": request.state.user["id"]}

    # 로그인만 확인(동기 함수도 되는지)
    @app.get("/mine")
    @require_role()
    def mine(request: Request):
        return {"rows": own_rows(ROWS, request.state.user)}

    # 행 하나 — 남의 것이면 403
    @app.get("/rows/{no}")
    async def row(no: int, request: Request):
        # 찾은 행
        found = next(r for r in ROWS if r["no"] == no)
        deny = deny_if_not_owner(request, found["owner_id"])
        return deny or found

    # 현재 계정 확인(데코레이터 없이)
    @app.get("/who")
    async def who(request: Request):
        return {"user": current_user(request)}

    return TestClient(app)


# 로그인 함수 — JSON 으로 로그인한 TestClient 반환
def _login(client, login_id):
    # 응답
    r = client.post("/auth/login", json={"id": login_id, "password": PW})
    assert r.status_code == 200, r.text
    return r


# 로그인 실패 · 쿠키 속성 · /me · 로그아웃
def test_fastapi_login_logout(client):
    # 실패 응답
    r = client.post("/auth/login", json={"id": "E1001", "password": "x"})
    assert r.status_code == 401 and r.json()["detail"] == MSG_LOGIN_FAIL
    assert client.get("/auth/me").status_code == 401
    # 성공 응답
    r = _login(client, "E1001")
    # 쿠키 머리줄
    set_cookie = r.headers["set-cookie"].lower()
    assert "httponly" in set_cookie and "samesite=lax" in set_cookie and PW not in set_cookie
    assert client.get("/auth/me").json()["user"]["id"] == "E1001"
    assert client.post("/auth/logout").status_code == 200
    assert client.get("/auth/me").status_code == 401


# 역할 — 로그인 전 401 · 사원 403 · 운영자 200
def test_fastapi_role(client):
    assert client.get("/admin").status_code == 401
    _login(client, "E1001")
    # 사원 응답
    r = client.get("/admin")
    assert r.status_code == 403 and r.json()["detail"] == MSG_FORBIDDEN
    _login(client, "admin")
    assert client.get("/admin").json() == {"who": "admin"}


# 남의 것 보기 403 · 내 것 200 · 내 목록은 내 행만 · 운영자는 남의 것도
def test_fastapi_owner_403(client):
    _login(client, "E1001")
    assert client.get("/rows/1").status_code == 200
    # 남의 행 응답
    r = client.get("/rows/2")
    assert r.status_code == 403 and r.json()["detail"] == MSG_NOT_OWNER
    assert [x["no"] for x in client.get("/mine").json()["rows"]] == [1, 3]
    _login(client, "admin")
    assert client.get("/rows/2").status_code == 200


# 위조 쿠키 — 역할을 운영자로 바꾼 본문 + 원래 서명은 401
def test_fastapi_forged_cookie(client):
    # 사원 토큰
    tok = _login(client, "E1001").cookies["sid"]
    # 운영자 본문
    forged_body = make_token({"id": "E1001", "role": "운영자"}, SECRET).split(".")[0]
    # 진짜 쿠키를 지우고 위조 쿠키만(httpx 판에 따라 set 이 같은 이름 쿠키를 하나 더 붙임)
    client.cookies.clear()
    client.cookies.set("sid", forged_body + "." + tok.split(".")[1])
    assert client.get("/admin").status_code == 401 and client.get("/who").json()["user"] is None


# form 전송 — 성공은 next 로 303 · 외부 주소 next 는 기본(/)으로 · 실패는 JSON 401(login_url 없음)
def test_fastapi_form(client):
    # 성공 응답
    r = client.post("/auth/login", data={"id": "E1001", "password": PW, "next": "/mine"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/mine"
    r = client.post("/auth/login", data={"id": "E1001", "password": PW, "next": "//evil.com"}, follow_redirects=False)
    assert r.headers["location"] == "/"
    assert client.post("/auth/login", data={"id": "E1001", "password": "x"}).status_code == 401


# request 인자 없는 함수에 데코레이터 — 정의 시점에 TypeError
def test_require_role_needs_request():
    pytest.importorskip("fastapi")
    from lib.auth.auth_web import require_role

    with pytest.raises(TypeError, match="request"):
        @require_role("운영자")
        def bad():
            return 1
