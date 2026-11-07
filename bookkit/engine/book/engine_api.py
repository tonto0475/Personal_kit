# -*- coding: utf-8 -*-
r"""책 엔진 확장 — 요청 · 응답 · 서버 코드 · 순서도 · 타임라인 · 책 사이 연결고리 블록 (과목과 무관)

Writer 의 call · exchange · http · listing · seq · gantt · back_x 가 이 모듈의 함수를 부른다(engine.py 에서 위임).
판다스 책처럼 이 블록을 쓰지 않는 책은 이 모듈을 불러오지도 않는다(FastAPI · httpx 가 없어도 판다스 책은 빌드된다).
사용법은 book\README.md «API 책 블록» 절.
"""
from http import HTTPStatus
import json as _json
import re
import traceback
import unicodedata
import warnings
from urllib.parse import urlsplit

from .engine import BuildError, Item, Svg, _tone, esc, hl_code

# 해부도에서 기본으로 숨기는 헤더 — TestClient · httpx 가 붙이는 잡음(요청), 빌드마다 바뀌는 값(응답)
NOISE = {"req": {"user-agent", "accept-encoding", "connection", "accept"}, "res": {"date"}}


# ════════════════════════════════════════════════════════════
# 주고받은 한 쌍 — 실행 결과(w.call) 와 녹화(w.exchange) 가 같은 모양
# ════════════════════════════════════════════════════════════
class _Headers:
    """헤더 목록(순서 · 중복 유지) — 이름은 대소문자 구분 없이 찾는다. h["content-type"] · h.get(…) · h.all(…)"""

    def __init__(self, items):
        self.items = [(str(k), str(v)) for k, v in items]

    def get(self, name, default=None):
        n = name.lower()
        for k, v in self.items:
            if k.lower() == n:
                return v
        return default

    def all(self, name):
        n = name.lower()
        return [v for k, v in self.items if k.lower() == n]

    def __getitem__(self, name):
        v = self.get(name)
        if v is None:
            raise KeyError(name)
        return v

    def __contains__(self, name):
        return self.get(name) is not None

    def __iter__(self):
        return iter(self.items)

    def __len__(self):
        return len(self.items)

    def __repr__(self):
        return f"_Headers({self.items!r})"


def _parse_json(text, ctype):
    if not text or ("json" not in (ctype or "").lower() and not text.lstrip().startswith(("{", "["))):
        return None
    try:
        return _json.loads(text)
    except ValueError:
        return None


class Exchange:
    """요청 하나 ↔ 응답 하나

    요청: method · url(표시용 전체 주소) · path · query · http_version(요청 시작줄) · req_headers · req_body(글자) · req_json
    응답: res_version(상태줄) · status · reason · headers · body(글자) · json(가능하면, 아니면 None) · size(본문 바이트)
    그 밖: recorded(녹화면 True) · source(녹화 출처) · history(따라간 리다이렉트의 앞 단계들)
    문장에서: {ex.status} · {ex.reason} · {ex.json["total"]} · {ex.headers["location"]} · {ex.size}"""

    def __init__(self, *, method, url, path, query="", http_version="HTTP/1.1", res_version=None, req_headers=(), req_body="",
                 status=0, reason="", headers=(), body="", size=None, recorded=False, source=None, history=()):
        self.method = method
        self.url = url
        self.path = path
        self.query = query
        self.http_version = http_version
        self.res_version = res_version or http_version
        self.req_headers = _Headers(req_headers)
        self.req_body = req_body or ""
        self.req_json = _parse_json(self.req_body, self.req_headers.get("content-type"))
        self.status = int(status)
        self.reason = reason or (HTTPStatus(self.status).phrase if self.status in HTTPStatus._value2member_map_ else "")
        self.headers = _Headers(headers)
        self.body = body or ""
        self.json = _parse_json(self.body, self.headers.get("content-type"))
        self.size = len(self.body.encode("utf-8")) if size is None else size
        self.recorded = recorded
        self.source = source
        self.history = list(history)

    @property
    def target(self):
        """요청 시작줄의 두 번째 칸 — 경로 + 쿼리(보낸 글자 그대로)"""
        return self.path + (f"?{self.query}" if self.query else "")

    def __repr__(self):
        return f"<Exchange {self.method} {self.target} → {self.status}{' (녹화)' if self.recorded else ''}>"


def _netloc(host):
    """«https://fab.example» · «fab.example» → «fab.example»"""
    if not host:
        return ""
    return urlsplit(host if "//" in host else "//" + host).netloc


def _origin(host):
    if not host:
        return ""
    return host.rstrip("/") if "//" in host else "https://" + host.rstrip("/")


def _from_response(r, show_host, history=()):
    """httpx 응답 → Exchange. 표시 주소 · host 헤더는 show_host 로 바꾼다(포트 번호처럼 빌드마다 바뀌는 값이 책에 남지 않게)"""
    req = r.request
    raw = req.url.raw_path.decode("ascii", "replace")
    path, _, query = raw.partition("?")
    nl = req.url.netloc
    host = _netloc(show_host) if show_host else (nl.decode("ascii", "replace") if isinstance(nl, bytes) else nl)
    rh = []
    for k, v in req.headers.raw:
        k, v = k.decode("latin-1").lower(), v.decode("latin-1")
        if k == "host":
            v = host
        rh.append((k, v))
    try:
        req_body = req.content.decode("utf-8")
    except UnicodeDecodeError:
        req_body = f"(이진 본문 {len(req.content)}바이트)"
    hh = [(k.decode("latin-1").lower(), v.decode("latin-1")) for k, v in r.headers.raw]
    origin = _origin(show_host) if show_host else f"{req.url.scheme}://{host}"
    return Exchange(method=req.method, url=origin + raw, path=path, query=query, http_version="HTTP/1.1",  # httpx · TestClient 는 HTTP/1.1 로 보낸다
                    res_version=r.http_version or "HTTP/1.1",
                    req_headers=rh, req_body=req_body, status=r.status_code, reason=r.reason_phrase, headers=hh,
                    body=r.text, size=len(r.content), history=history)


def _client_for(w, app, base):
    """요청을 보낼 클라이언트 · 표시 호스트. 장(Writer)마다 캐시 — 같은 장 안에서는 쿠키 · 앱 상태가 이어진다"""
    meta = w.book.meta
    cache = w.__dict__.setdefault("_clients", {})
    if base:
        key = ("base", base)
        if key not in cache:
            import httpx
            cache[key] = httpx.Client(base_url=base, timeout=10)
        u = urlsplit(base)
        return cache[key], f"{u.scheme}://{u.hostname}"
    name = app or meta.get("default_app", "client")
    if name not in w.env:
        raise BuildError(f"{w._where()}: 실행 환경에 «{name}» 가 없다 — TestClient 나 ASGI 앱을 그 이름으로 만들어 둘 것")
    obj = w.env[name]
    show = meta.get("display_host")
    if hasattr(obj, "request") and hasattr(obj, "cookies"):  # 이미 만든 클라이언트(TestClient · httpx.Client)
        return obj, show
    if not callable(obj):
        raise BuildError(f"{w._where()}: «{name}» 는 클라이언트도 ASGI 앱도 아니다 ({type(obj).__name__})")
    key = ("app", name, id(obj))
    if key not in cache:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            from starlette.testclient import TestClient
            host = _netloc(show) or "testserver"
            # 500 을 보여 줘야 하는 장이 있어 서버 예외는 응답(500)으로 돌려받는다 — 빌드 경고로는 알린다
            cache[key] = TestClient(obj, base_url=f"http://{host}", raise_server_exceptions=False)
    return cache[key], show


def call(w, method, path, *, app=None, params=None, json=None, data=None, content=None, headers=None, cookies=None,
         follow_redirects=False, base=None, name=None, jar=True, show_host=None):
    """요청을 실제로 보내고 Exchange 를 돌려준다(블록은 만들지 않는다 — 그리려면 w.http(ex))"""
    import httpx
    client, show = _client_for(w, app, base)
    if show_host is not None:
        show = show_host
    kw = {k: v for k, v in (("params", params), ("json", json), ("data", data), ("content", content),
                            ("headers", headers), ("cookies", cookies)) if v is not None}
    saved = None
    if not jar:  # 쿠키 상자를 비운 채 보낸다(처음 온 브라우저처럼) — 이 응답의 Set-Cookie 도 담지 않는다
        saved, client.cookies = client.cookies, httpx.Cookies()
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            r = client.request(method.upper(), path, follow_redirects=follow_redirects, **kw)
    except httpx.HTTPError as e:
        raise BuildError(f"{w._where()}: 요청 {method} {path} 실패 — {type(e).__name__}: {e}") from None
    except Exception as e:
        raise BuildError(f"{w._where()}: 요청 {method} {path} 중 앱 오류 — {type(e).__name__}: {e}") from None
    finally:
        if saved is not None:
            client.cookies = saved
    hist = [_from_response(h, show) for h in r.history]
    ex = _from_response(r, show, hist)
    if ex.status >= 500 and not base:
        w.book.warnings.append(f"{w._where()}: {method} {path} → {ex.status} (의도한 500 이 아니면 앱 코드를 볼 것)")
    if name:
        w.env[name] = ex
    return ex


# ── 녹화 ─────────────────────────────────────────────────
def _parse_raw(text, is_req):
    lines = str(text).strip("\n").replace("\r\n", "\n").split("\n")
    start = lines[0].strip()
    hs, i = [], 1
    while i < len(lines) and lines[i].strip():
        k, _, v = lines[i].partition(":")
        hs.append((k.strip(), v.strip()))
        i += 1
    body = "\n".join(lines[i + 1:]) if i < len(lines) else ""
    parts = start.split(" ", 2)
    if is_req:
        if len(parts) < 2:
            raise BuildError(f"녹화 요청의 시작줄을 읽지 못했다 — {start}")
        return {"method": parts[0], "target": parts[1], "version": parts[2] if len(parts) > 2 else "HTTP/1.1",
                "headers": hs, "body": body}
    if len(parts) < 2 or not parts[1].isdigit():
        raise BuildError(f"녹화 응답의 상태줄을 읽지 못했다 — {start}")
    return {"version": parts[0], "status": int(parts[1]), "reason": parts[2] if len(parts) > 2 else "", "headers": hs, "body": body}


def _hlist(h):
    if h is None:
        return []
    return list(h.items()) if isinstance(h, dict) else [tuple(x) for x in h]


def _body_of(d):
    if d.get("json") is not None:
        return _json.dumps(d["json"], ensure_ascii=False, indent=2)
    return d.get("body", "") or ""


def exchange(w, req, res, source, name=None):
    """녹화 예시 — 외부 서비스의 요청 · 응답을 손으로 적는다(빌드 때 보내지 않는다)
    req · res = 원문 글자(«POST /v1/messages HTTP/1.1\\nhost: …\\n\\n{…}») 또는 dict
      req dict: method · url(전체 주소) 또는 path · headers(dict 또는 [(이름, 값)]) · json 또는 body
      res dict: status · reason(생략하면 표준 사유) · headers · json 또는 body"""
    if not source:
        raise BuildError(f"{w._where()}: 녹화 예시에는 출처(source=공식 문서 주소)가 필요하다")
    if isinstance(req, str):
        q = _parse_raw(req, True)
        method, target, ver, rh, rb = q["method"], q["target"], q["version"], q["headers"], q["body"]
        host = _Headers(rh).get("host", "")
        if target.startswith("http"):
            u = urlsplit(target)
            host, target = u.netloc, (u.path or "/") + (f"?{u.query}" if u.query else "")
        url = f"https://{host}{target}" if host else target
    else:
        method, ver, rh, rb = req.get("method", "GET"), req.get("version", "HTTP/1.1"), _hlist(req.get("headers")), _body_of(req)
        url = req.get("url") or req.get("path", "/")
        u = urlsplit(url)
        target = (u.path or "/") + (f"?{u.query}" if u.query else "")
        if u.netloc and not _Headers(rh).get("host"):
            rh = [("host", u.netloc)] + rh
    if isinstance(res, str):
        s = _parse_raw(res, False)
        status, reason, hh, body, rver = s["status"], s["reason"], s["headers"], s["body"], s["version"]
    else:
        status, reason, hh, body = res.get("status", 200), res.get("reason", ""), _hlist(res.get("headers")), _body_of(res)
        rver = res.get("version", ver)
    path, _, query = target.partition("?")
    ex = Exchange(method=method.upper(), url=url, path=path, query=query, http_version=ver, res_version=rver, req_headers=rh, req_body=rb,
                  status=status, reason=reason, headers=hh, body=body, recorded=True, source=source)
    if name:
        w.env[name] = ex
    return ex


# ════════════════════════════════════════════════════════════
# 해부도 · 코드 묶음 공통 — 글자 폭 · 줄 바꿈 · 줄 주석
# ════════════════════════════════════════════════════════════
def _cw(ch):
    return 2 if unicodedata.east_asian_width(ch) in "WF" else 1


def _wrap(line, width):
    """표시 폭(한글 2칸) width 를 넘는 줄을 조각으로 — 고정폭 글꼴 기준"""
    out, cur, n = [], [], 0
    for ch in line:
        c = _cw(ch)
        if n + c > width and cur:
            out.append("".join(cur))
            cur, n = [], 0
        cur.append(ch)
        n += c
    out.append("".join(cur))
    return out


def _note(w, v):
    """줄 주석 — 글 또는 (글, 색). 꾸밈 글(`코드` · {식})"""
    txt, tone = (v[0], v[1]) if isinstance(v, (tuple, list)) else (v, "")
    return f'<span class="ln {tone}">{w.t(txt)}</span>'


# ════════════════════════════════════════════════════════════
# HTTP 메시지 해부도
# ════════════════════════════════════════════════════════════
def _pretty_body(ex, side, pretty=True):
    body = ex.req_body if side == "req" else ex.body
    hs = ex.req_headers if side == "req" else ex.headers
    js = ex.req_json if side == "req" else ex.json
    ctype = (hs.get("content-type") or "").lower()
    if js is not None and pretty:
        return _json.dumps(js, ensure_ascii=False, indent=2).split("\n"), "json"
    if not body:
        return [], "none"
    return body.replace("\r\n", "\n").rstrip("\n").split("\n"), ("html" if "html" in ctype else "text")


def _key_of(k):
    return k.lower() if isinstance(k, str) else k


def http(w, ex, part="both", notes=None, marks=None, hide=None, body_lines=12, title=None, wrap=None, pretty=True,
         fn=None, id=None):
    """HTTP 메시지 해부도 블록 — 시작줄 · 헤더 · 빈 줄 · 본문을 원문 모양으로, 영역마다 괄호 이름표
    notes · marks = {"req": {줄: …}, "res": {줄: …}} — 줄 = "start" · 헤더 이름 · "blank" · "body" · "body:N"(본문 N번째 줄, 0부터) · 정수(표시 줄 위치, 시작줄 0)
    hide = 숨길 헤더 이름 목록(주면 기본값을 대신한다) · body_lines = 본문 최대 줄(넘으면 «… 총 N줄»)
    pretty=True 면 JSON 본문을 2칸 들여쓰기로(읽기용 — content-length 는 실제로 보낸 바이트 수), False 면 보낸 글자 그대로
    wrap = 줄을 꺾는 표시 폭(한글 2칸, 기본 80 · 줄 주석이 있으면 58) — 꺾인 자리에 ↵"""
    if not isinstance(ex, Exchange):
        raise BuildError(f"{w._where()}: w.http 에는 w.call · w.exchange 결과(Exchange)를 넘긴다")
    sides = {"both": ["req", "res"], "req": ["req"], "res": ["res"]}.get(part)
    if not sides:
        raise BuildError(f"{w._where()}: part 는 both · req · res 중 하나")
    notes = notes or {}
    marks = marks or {}
    out = []
    for side in sides:
        nt = {_key_of(k): v for k, v in (notes.get(side) or {}).items()}
        mk = {_key_of(k): v for k, v in (marks.get(side) or {}).items()}
        width = wrap or (58 if nt else 80)
        hidden = {h.lower() for h in hide} if hide is not None else NOISE[side]
        if side == "req":
            start = f"{ex.method} {ex.target} {ex.http_version}"
            hs = [(k, v) for k, v in ex.req_headers if k.lower() not in hidden]
            head = f'<span class="hmk">요청</span><span class="hmu">{esc(ex.method)} {esc(ex.url)}</span>'
            lab0 = "시작줄"
        else:
            start = f"{ex.res_version} {ex.status} {ex.reason}".rstrip()
            hs = [(k, v) for k, v in ex.headers if k.lower() not in hidden]
            tone = "ok" if ex.status < 300 else "acc" if ex.status < 400 else "ng"
            head = f'<span class="hmk">응답</span><span class="hmu st-{tone}">{ex.status} {esc(ex.reason)}</span>'
            lab0 = "상태줄"
        if ex.recorded:
            head += '<span class="hmrec">녹화 — 실행 아님</span>'
        lines, kind = _pretty_body(ex, side, pretty)
        limit = min(body_lines, 8) if kind == "html" else body_lines
        more = len(lines) - limit if len(lines) > limit else 0
        shown = lines[:limit] if more else lines
        used = set()

        def row(text, keys, idx):
            mark = ""
            note = ""
            for k in keys:
                if k in mk:
                    mark = mk[k]
                    used.add(("m", k))
                if k in nt and not note:
                    note = _note(w, nt[k])
                    used.add(("n", k))
            pieces = _wrap(text, width) if text else [""]
            h = []
            for j, pc in enumerate(pieces):
                tail = '<span class="hmw">↵</span>' if j < len(pieces) - 1 else ""
                h.append(f'<div class="hml {mark}"><span class="hmt">{esc(pc) or " "}{tail}</span>{note if j == 0 else ""}</div>')
            return "".join(h)

        pos = 0
        regs = []
        regs.append(("st", lab0, row(start, ["start", pos], pos)))
        pos += 1
        hrows = []
        for k, v in hs:
            hrows.append(row(f"{k}: {v}", [k.lower(), pos], pos))
            pos += 1
        if hrows:
            regs.append(("hd", "헤더", "".join(hrows)))
        regs.append(("bl", "빈 줄", row("", ["blank", pos], pos)))
        pos += 1
        if shown:
            brows = [row(t, (["body"] if i == 0 else []) + [f"body:{i}", pos + i], pos + i) for i, t in enumerate(shown)]
            if more:
                brows.append(f'<div class="hml more"><span class="hmt">… 총 {len(lines):,}줄</span></div>')
            regs.append(("bd", "본문", "".join(brows)))
        else:
            regs.append(("bd0", "본문", f'<div class="hml none"><span class="hmt">(본문 없음)</span>{_note(w, nt["body"]) if "body" in nt else ""}</div>'))
            if "body" in nt:
                used.add(("n", "body"))
        miss = [k for k in nt if ("n", k) not in used] + [k for k in mk if ("m", k) not in used]
        if miss:
            raise BuildError(f"{w._where()}: 해부도({side}) 줄 주석 · 표시의 대상 줄이 없다 — {miss} (숨긴 헤더인지 · 본문 줄 수를 볼 것)")
        body = "".join(f'<div class="hmr r-{c}"><div class="hmb"><span>{esc(lab)}</span></div><div class="hmls">{rows}</div></div>'
                       for c, lab, rows in regs)
        out.append(f'<div class="hm hm-{side}"><div class="hmh">{head}</div><div class="hmbody">{body}</div></div>')
    cap = f'<p class="hmc">{w.t(title)}</p>' if title else ""
    h = f'<div class="hmw2">{cap}{"".join(out)}</div>'
    fn = dict(fn or {})
    h, fids = w._fn(h, fn)
    if ex.recorded:  # 출처 각주 — 용어 찾아보기에는 넣지 않는다
        fid = w.book.add_fn("녹화 — 실행 아님", "출처", w, index=False)
        w.book.fns[fid]["text"] = (f'실행하지 않고 공식 문서의 형식대로 적은 예시. 출처 — '
                                   f'<a class="url" href="{esc(ex.source)}" target="_blank" rel="noopener">{esc(ex.source)}</a>')
        w.book.fns[fid]["label"] = "녹화"
        from .engine import _insert_marker
        h = _insert_marker(h, "녹화 — 실행 아님", fid)
        fids.append(fid)
    return w._add("http", h, fids, id=id, cap=re.sub("<[^>]+>", "", cap))


# ════════════════════════════════════════════════════════════
# 서버 코드 묶음
# ════════════════════════════════════════════════════════════
_KW = re.compile(r"\b(def|return|class|async|await|import|from|as|if|elif|else|for|while|in|not|and|or|is|with|yield|"
                 r"raise|try|except|finally|lambda|None|True|False|pass|global)\b")
_STR = re.compile(r'("[^"\n]*"|\'[^\'\n]*\')|(#.*$)')


def hl_py(line):
    """파이썬 한 줄 칠하기 — 글자 · 주석은 공용 hl_code 와 같은 색, 키워드 · 데코레이터만 더한다"""
    m = re.match(r"^(\s*)(@[\w.]+)(.*)$", line)
    if m:
        return esc(m.group(1)) + f'<span class="d">{esc(m.group(2))}</span>' + hl_py(m.group(3))
    out, pos = [], 0
    for t in _STR.finditer(line):
        out.append(_KW.sub(r'<span class="k">\1</span>', esc(line[pos:t.start()])))
        out.append(hl_code(t.group(0)))
        pos = t.end()
    out.append(_KW.sub(r'<span class="k">\1</span>', esc(line[pos:])))
    return "".join(out)


def listing(w, lines, title=None, run=True, marks=None, notes=None, start=1, fn=None, id=None):
    """서버 코드 묶음 블록 — 줄 번호 · 칠하기 · 줄 주석. marks · notes 의 열쇠 = 화면에 보이는 줄 번호(start 부터)
    run=True 면 그 장 실행 환경에서 실행 — 여기서 정의한 앱을 바로 w.call(app="이름") 으로 부른다"""
    if isinstance(lines, str):
        lines = lines.split("\n")
    lines = list(lines)
    marks = marks or {}
    notes = notes or {}
    last = start + len(lines) - 1
    bad = [k for k in list(marks) + list(notes) if not (isinstance(k, int) and start <= k <= last)]
    if bad:
        raise BuildError(f"{w._where()}: 코드 묶음의 줄 표시 · 주석 번호 {bad} 가 범위({start}~{last}) 밖이다")
    if run:
        src = "\n".join(lines)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            try:
                exec(compile(src, "<listing>", "exec"), w.env)
            except SyntaxError as e:
                n = (e.lineno or 1)
                raise BuildError(f"{w._where()}: 코드 묶음 {start + n - 1}번 줄 문법 오류 — {e.msg}\n  {lines[n - 1] if 0 < n <= len(lines) else ''}") from None
            except Exception as e:
                tb = [f for f in traceback.extract_tb(e.__traceback__) if f.filename == "<listing>"]
                n = tb[-1].lineno if tb else 1
                raise BuildError(f"{w._where()}: 코드 묶음 {start + n - 1}번 줄 실행 실패 — {type(e).__name__}: {e}\n  {lines[n - 1]}") from None
    rows = []
    for i, ln in enumerate(lines):
        no = start + i
        nt = _note(w, notes[no]) if no in notes else ""
        rows.append(f'<div class="lsl {marks.get(no, "")}"><span class="lsi">{no}</span><span class="lst">{hl_py(ln) or " "}</span>{nt}</div>')
    head = f'<div class="lsh">{w.t(title)}</div>' if title else ""
    h = f'<div class="ls">{head}<div class="lsb">{"".join(rows)}</div></div>'
    h, fids = w._fn(h, fn)
    return w._add("listing", h, fids, id=id)


# ════════════════════════════════════════════════════════════
# 순서도 · 타임라인 (SVG, 폭 664 = 쪽 폭 1:1)
# ════════════════════════════════════════════════════════════
PAGE_W = 664


def _tw(s, size):
    """글자 폭 어림(px) — 한글 1em, 그 밖 0.56em"""
    return sum(size * (1.0 if _cw(c) == 2 else 0.56) for c in str(s))


def seq(w, lanes, steps, title=None, caption=None, fn=None, id=None, row=36):
    """순서도 블록 — lanes = 주체 이름 목록, steps 원소 = (보내는 쪽, 받는 쪽, 글[, tone[, 점선]]) 또는
    dict(frm, to, text, tone="acc"|"ok"|"ng"|"gray", dashed=응답, note=작은 글). 보내는 쪽 = 받는 쪽이면 자기 처리 상자"""
    lanes = [str(x) for x in lanes]
    n = len(lanes)
    if n < 1:
        raise BuildError(f"{w._where()}: 순서도에 주체가 없다")
    st = []
    for s in steps:
        if isinstance(s, dict):
            d = dict(s)
            d.setdefault("frm", d.pop("from", None))
        else:
            d = {"frm": s[0], "to": s[1], "text": s[2]}
            if len(s) > 3:
                d["tone"] = s[3]
            if len(s) > 4:
                d["dashed"] = s[4]
        for k in ("frm", "to"):
            if str(d[k]) not in lanes:
                raise BuildError(f"{w._where()}: 순서도 단계의 주체 «{d[k]}» 가 lanes 에 없다 ({lanes})")
        st.append(d)
    W = PAGE_W
    top = 46 if title else 20
    hdr_h = 30
    margin = 64 if n > 1 else W / 2
    xs = [W / 2] if n == 1 else [margin + i * (W - 2 * margin) / (n - 1) for i in range(n)]
    gap = (xs[1] - xs[0]) if n > 1 else W
    heights = [row + (14 if d.get("note") else 0) for d in st]
    H = top + hdr_h + 16 + sum(heights) + 14
    s = Svg(W, H)
    if title:
        s.text(W / 2, 16, w_plain(title), size=13, tone="ink", bold=True)
    y_end = H - 8
    for i, (x, nm) in enumerate(zip(xs, lanes)):
        s.line(x, top + hdr_h, x, y_end, tone="mute", sw=1.2, dash=True)
    for x, nm in zip(xs, lanes):
        bw = min(max(_tw(nm, 12) + 20, 70), max(gap - 8, 70))
        s.box(x - bw / 2, top, bw, hdr_h, nm, tone="ink", size=12, bold=True, fill="#f1f3f6", rx=5)
    y = top + hdr_h + 16
    for k, (d, hh) in enumerate(zip(st, heights)):
        tone = d.get("tone") or ("gray" if d.get("dashed") else "acc")
        a, b = xs[lanes.index(str(d["frm"]))], xs[lanes.index(str(d["to"]))]
        label = f"{k + 1}. {d['text']}"
        ya = y + 20
        if a == b:  # 자기 처리 — 주체 줄 위의 상자
            bw = _tw(label, 11.5) + 18
            bx = min(max(a - bw / 2, 4), W - 4 - bw)
            s.box(bx, y + 4, bw, 24, label, tone=tone, size=11.5, rx=4)
        else:
            s.arrow(a, ya, b, ya, tone=tone, sw=1.8, head=7, dash=bool(d.get("dashed")))
            tw = _tw(label, 11.5)
            cx = (a + b) / 2
            cx = min(max(cx, tw / 2 + 4), W - 4 - tw / 2)
            s.text(cx, ya - 10, label, size=11.5, tone=tone, bold=True, halo=True)
        if d.get("note"):
            nx = (a + b) / 2
            tw = _tw(d["note"], 10.5)
            nx = min(max(nx, tw / 2 + 4), W - 4 - tw / 2)
            s.text(nx, y + row + 2, d["note"], size=10.5, tone="gray", halo=True)
        y += hh
    cap = f'<p class="cap">{w.t(caption)}</p>' if caption else ""
    h = f'<div class="svgw">{s.render(w_plain(title or caption or "순서도"))}</div>{cap}'
    h, fids = w._fn(h, fn)
    return w._add("seq", h, fids, id=id, cap=re.sub("<[^>]+>", "", cap))


def _nice_step(span, want=6):
    if span <= 0:
        return 1
    raw = span / want
    p = 10 ** int(f"{raw:e}".split("e")[1])
    for m in (1, 2, 2.5, 5, 10):
        if raw <= m * p:
            return m * p
    return 10 * p


def gantt(w, tracks, unit="초", title=None, caption=None, fn=None, id=None):
    """타임라인 블록 — tracks = [(이름, [(시작, 끝, tone, 글)])]. 축 눈금 자동, 막대 안 글(넘치면 오른쪽 밖)"""
    W = PAGE_W
    tracks = [(str(nm), list(bars)) for nm, bars in tracks]
    if not tracks:
        raise BuildError(f"{w._where()}: 타임라인에 줄이 없다")
    t0 = min(min((b[0] for b in bars), default=0) for _, bars in tracks)
    t0 = min(t0, 0)
    t1 = max(max((b[1] for b in bars), default=1) for _, bars in tracks)
    step = _nice_step(t1 - t0)
    t1 = step * -(-t1 // step)
    lab_w = min(max(max(_tw(nm, 12) for nm, _ in tracks) + 14, 70), 200)
    x0, x1 = lab_w + 6, W - 14
    sx = lambda t: x0 + (t - t0) / (t1 - t0) * (x1 - x0)  # noqa: E731
    top = 28 if title else 6
    rh = 30
    H = top + len(tracks) * rh + 34
    s = Svg(W, H)
    if title:
        s.text(W / 2, 14, w_plain(title), size=13, tone="ink", bold=True)
    yb = top + len(tracks) * rh + 4
    t = t0
    while t <= t1 + 1e-9:
        x = sx(t)
        s.line(x, top, x, yb, tone="mute", sw=0.8, dash=True)
        s.text(x, yb + 11, f"{t:g}", size=10.5, tone="gray")
        t += step
    s.line(x0, yb, x1, yb, tone="gray", sw=1.2)
    s.text(x1, yb + 25, f"({unit})", size=10.5, tone="gray", anchor="end")
    for i, (nm, bars) in enumerate(tracks):
        y = top + i * rh
        s.text(lab_w, y + rh / 2, nm, size=12, tone="ink", anchor="end", bold=True)
        for b in bars:
            a, e = b[0], b[1]
            tone = b[2] if len(b) > 2 and b[2] else "acc"
            txt = str(b[3]) if len(b) > 3 and b[3] is not None else ""
            bx, bw = sx(a), max(sx(e) - sx(a), 2)
            s.box(bx, y + 5, bw, rh - 10, "", tone=tone, rx=3)
            if txt:
                tw = _tw(txt, 11)
                if tw + 8 <= bw:
                    s.text(bx + bw / 2, y + rh / 2, txt, size=11, tone=tone, bold=True)
                elif bx + bw + 4 + tw <= W - 2:
                    s.text(bx + bw + 4, y + rh / 2, txt, size=11, tone=tone, anchor="start")
                else:
                    s.text(bx - 4, y + rh / 2, txt, size=11, tone=tone, anchor="end")
    cap = f'<p class="cap">{w.t(caption)}</p>' if caption else ""
    h = f'<div class="svgw">{s.render(w_plain(title or caption or "타임라인"))}</div>{cap}'
    h, fids = w._fn(h, fn)
    return w._add("gantt", h, fids, id=id, cap=re.sub("<[^>]+>", "", cap))


def w_plain(t):
    return re.sub(r"\*\*|!!|\+\+|`", "", str(t or ""))


# ════════════════════════════════════════════════════════════
# 책 사이 연결고리
# ════════════════════════════════════════════════════════════
def back_x(w, book_doc, anchor, label, text, fn=None, id=None):
    """«↗ 다른 책 N장» 표식 + /{book_doc}#{anchor} 링크(같은 창). 책 안 ↩ 와 따로 센다"""
    if not re.fullmatch(r"[A-Za-z0-9_\-]+", str(book_doc)) or not re.fullmatch(r"[A-Za-z0-9_\-]+", str(anchor)):
        raise BuildError(f"{w._where()}: back_x 의 책 · 앵커 이름은 영문 · 숫자 · - · _ 만 — {book_doc}#{anchor}")
    body, fids = w._fn(w.t(text), fn)
    href = f"/{book_doc}#{anchor}"
    h = (f'<p class="backp backxp"><a class="backx" href="{esc(href)}" data-xb="{esc(book_doc)}">↗ {esc(label)}</a>{body}</p>')
    b = w._add("backx", h, fids, id=id)
    w.book.x_links.append((b.id, href))
    return b
