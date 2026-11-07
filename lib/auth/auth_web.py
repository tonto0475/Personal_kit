# 로그인 웹 연결 — FastAPI · NiceGUI 앱에 /auth/login · /auth/logout · /auth/me 경로 + 서명 쿠키 세션 + 역할 데코레이터
#   역할: auth_core 판정을 HTTP 로 — 로그인 성공 시 HttpOnly 쿠키, 요청마다 쿠키 → 계정, 역할 · 소유자가 틀리면 401 · 403(또는 로그인 화면으로 이동)
#   어디에: app.py 에서 add_auth(app, store) 한 번(nicegui 의 app 도 FastAPI 라 그대로) → 경로 함수 · @ui.page 함수에 request 인자 + @require_role("운영자")
#   실패하면: 비밀키 없음 → add_auth 에서 InputError(앱 시작 단계에서 멈춤) · 로그인 실패 → 401 {"detail": 문구} · 남의 것 → 403 {"detail": 문구}
import functools
import inspect
import json
from urllib.parse import parse_qs, quote

from fastapi import Request
from fastapi.responses import JSONResponse, RedirectResponse

from lib.auth.auth_core import (MSG_NEED_LOGIN, SESSION_SEC, AuthError, authenticate, check_owner, check_role,
                                get_secret, make_token, read_token)


# 로그인 설정 묶음 — add_auth 가 app.state.auth 에 넣고 current_user · require_role 이 읽는다
class AuthConfig:
    # store: UserStore / secret: 비밀키 / cookie: 쿠키 이름 / secure: https 전용 쿠키 / login_url: 화면 로그인 주소(None 이면 JSON 401) / home: 로그인 뒤 기본 이동
    def __init__(self, store, secret, cookie, secure, login_url, home):
        # 계정 표
        self.store = store
        # 비밀키
        self.secret = secret
        # 쿠키 이름
        self.cookie = cookie
        # https 전용 여부
        self.secure = secure
        # 로그인 화면 주소
        self.login_url = login_url
        # 로그인 뒤 기본 이동 주소
        self.home = home


# 이동 주소가 같은 사이트 안 경로인지 — «/x» 만 허용(«//다른사이트» · «http://» 차단)
# url: next 값
def _safe_next(url, default):
    if url and url.startswith("/") and not url.startswith("//") and "\\" not in url:
        return url
    return default


# 요청 본문에서 아이디 · 비밀번호 · next 읽기 — JSON 또는 form(urlencoded) 둘 다(python-multipart 없이)
# request: 요청
async def _read_login_body(request):
    # 원문 바이트
    raw = await request.body()
    # 본문 형식
    ctype = request.headers.get("content-type", "")
    if "application/json" in ctype:
        try:
            # JSON 사전
            data = json.loads(raw.decode("utf-8") or "{}")
        except (ValueError, UnicodeDecodeError):
            data = {}
        return str(data.get("id", "")), str(data.get("password", "")), None, False
    # form 값 사전(값마다 목록)
    form = parse_qs(raw.decode("utf-8", "replace"))
    # 첫 값 꺼내기
    first = lambda k: (form.get(k) or [""])[0]
    return first("id"), first("password"), first("next") or None, True


# 앱에 로그인 경로 붙이기 — 앱 시작 때 한 번
# app: FastAPI 또는 nicegui.app / store: UserStore / secret: 비밀키(None 이면 AUTH_SECRET 환경변수) / cookie: 쿠키 이름
# secure: https 에서만 쿠키 전송 / login_url: 로그인 화면 주소(NiceGUI 면 "/login") / home: 로그인 뒤 기본 이동 / prefix: 경로 앞머리
def add_auth(app, store, secret=None, cookie="sid", secure=False, login_url=None, home="/", prefix="/auth"):
    # 설정 묶음 — 비밀키가 없으면 여기서 InputError
    cfg = AuthConfig(store, get_secret(secret), cookie, secure, login_url, home)
    app.state.auth = cfg

    # 로그인 — 성공: 쿠키 + {"ok","user"}(form 이면 next 로 303) / 실패: 401 {"detail"}(form 이면 로그인 화면으로 ?error=1)
    async def login(request: Request):
        # 아이디 · 비밀번호 · 이동 주소 · form 여부
        login_id, password, nxt, is_form = await _read_login_body(request)
        try:
            # 확인된 계정
            user = authenticate(cfg.store, login_id, password)
        except AuthError as err:
            if is_form and cfg.login_url:
                # 실패 뒤에도 돌아갈 주소 유지
                keep = "&next=" + quote(_safe_next(nxt, cfg.home), safe="") if nxt else ""
                return RedirectResponse(cfg.login_url + "?error=1" + keep, status_code=303)
            return JSONResponse({"detail": str(err)}, status_code=err.status)
        # 응답 — form 이면 이동, 아니면 JSON
        resp = (RedirectResponse(_safe_next(nxt, cfg.home), status_code=303) if is_form
                else JSONResponse({"ok": True, "user": user}))
        resp.set_cookie(cfg.cookie, make_token(user, cfg.secret), max_age=SESSION_SEC,
                        httponly=True, samesite="lax", secure=cfg.secure, path="/")
        return resp

    # 로그아웃(POST) — 쿠키 지우고 JSON
    async def logout_post():
        # 응답
        resp = JSONResponse({"ok": True})
        resp.delete_cookie(cfg.cookie, path="/")
        return resp

    # 로그아웃(GET) — 링크 · 버튼용 · 쿠키 지우고 로그인 화면(없으면 /)으로
    async def logout_get():
        # 응답
        resp = RedirectResponse(cfg.login_url or "/", status_code=303)
        resp.delete_cookie(cfg.cookie, path="/")
        return resp

    # 지금 로그인한 계정 — 없으면 401
    async def me(request: Request):
        # 계정
        user = current_user(request)
        if user is None:
            return JSONResponse({"detail": MSG_NEED_LOGIN}, status_code=401)
        return {"user": user}

    app.post(prefix + "/login")(login)
    app.post(prefix + "/logout")(logout_post)
    app.get(prefix + "/logout")(logout_get)
    app.get(prefix + "/me")(me)
    return cfg


# 요청의 쿠키 → 계정 {"id","role","name"} · 없거나 위조 · 만료면 None
# request: 요청(FastAPI · NiceGUI 페이지 함수의 request 인자)
def current_user(request):
    # 설정 묶음
    cfg = getattr(request.app.state, "auth", None)
    if cfg is None:
        raise RuntimeError("add_auth(app, store) 를 먼저 호출")
    return read_token(request.cookies.get(cfg.cookie), cfg.secret)


# 실패 응답 — 401 이고 로그인 화면이 있으면 그리로 이동(돌아올 주소 next) · 아니면 JSON {"detail"}
# request: 요청 / err: AuthError
def _fail_response(request, err):
    # 설정 묶음
    cfg = request.app.state.auth
    if err.status == 401 and cfg.login_url:
        # 돌아올 주소
        back = request.url.path + ("?" + request.url.query if request.url.query else "")
        return RedirectResponse("{}?next={}".format(cfg.login_url, quote(back, safe="")), status_code=303)
    return JSONResponse({"detail": str(err)}, status_code=err.status)


# 역할 확인 데코레이터 — 감싼 함수에 request 인자가 있어야 한다 · 통과하면 request.state.user 에 계정
#   FastAPI:  @app.get("/admin")  다음 줄  @require_role("운영자")  · 함수 async def f(request: Request)
#   NiceGUI:  @ui.page("/admin")  다음 줄  @require_role("운영자")  · 함수 def page(request: Request)
# roles: 허용 역할(비우면 로그인만 확인)
def require_role(*roles):
    # 실제 데코레이터
    def deco(func):
        if "request" not in inspect.signature(func).parameters:
            raise TypeError("{}: require_role 을 쓰는 함수는 request 인자가 필요".format(func.__name__))

        # 감싼 함수 — 원래 서명을 그대로 보이게(functools.wraps → FastAPI · NiceGUI 가 request 를 넣어 줌)
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # 요청 객체
            request = kwargs.get("request") or next(a for a in args if isinstance(a, Request))
            try:
                request.state.user = check_role(current_user(request), roles)
            except AuthError as err:
                return _fail_response(request, err)
            # 원래 함수 결과
            result = func(*args, **kwargs)
            if inspect.isawaitable(result):
                result = await result
            return result

        return wrapper

    return deco


# 행 하나가 요청한 사람 것인지 — 남의 것이면 403 응답 객체 · 내 것(또는 운영자)이면 None
#   사용:  deny = deny_if_not_owner(request, row["owner_id"]);  if deny: return deny
# request: 요청 / owner_id: 그 행의 소유자 아이디
def deny_if_not_owner(request, owner_id):
    try:
        check_owner(current_user(request), owner_id)
    except AuthError as err:
        return _fail_response(request, err)
    return None
