# -*- coding: utf-8 -*-
"""envcheck — 대회 환경 점검(사전 체험 15분용). 실패 · 정보 항목만 한 줄씩, 마지막 줄에 요약.

실행: bash scripts/envcheck/envcheck.sh            (파이썬이 없어도 0단계가 돈다)
      python3 scripts/envcheck/envcheck.py [--no-install] [--where 이름]
- 사용자 터미널에서 한 번, Codex 에게 한 번 돌려 두 요약을 비교한다(다른 항목 = 샌드박스가 막는 것)
- 흔적을 남기지 않는다: 시험용 파일 · 폴더는 전부 임시 폴더에 만들고 끝나면 지운다
- 표준 라이브러리만 쓴다 · 파이썬 3.8 이상
"""
import argparse
import importlib.metadata as md
import os
import re
import shutil
import socket
import subprocess
import sys
import sysconfig
import tempfile
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

# 이 파일 위치 · 키트 루트(scripts/envcheck 의 두 단계 위) — 단독으로 받았으면 키트 없음
HERE = Path(__file__).resolve().parent
KIT = HERE.parents[1] if (HERE.parents[1] / "AGENTS.md").is_file() else None
# 접속 시험 대기 상한(초) — 막힌 네트워크에서 오래 멈추지 않게, 넘으면 실패 신호로 처리
NET_WAIT = 5
# 명령 하나가 응답 없이 멈췄을 때만 끊는 상한(초)
CMD_WAIT = 30
# 결과 — (번호, 상태 ok/fail/info, 사유)
RESULTS = []
# 끝날 때 지울 임시 폴더(A11 venv 는 E 항목이 NiceGUI 를 띄우는 데 다시 쓴 뒤 지운다)
CLEANUP = []
# NiceGUI 를 띄울 파이썬 — (인자 목록, 추가 환경 변수). A11 설치에 성공하면 그 venv
NG = None
# 자세한 기록(로그 파일로)
DETAIL = []


# 결과 하나 기록
# no: 항목 번호 · state: ok/fail/info · reason: 사유 코드 + 짧은 설명
def add(no, state, reason=""):
    RESULTS.append((no, state, reason))


# 명령 실행 — (종료코드, 출력). 없는 명령은 (127, "")
# cmd: 인자 목록 · cwd: 실행 폴더 · env: 환경 변수
def run(cmd, cwd=None, env=None, wait=CMD_WAIT):
    try:
        p = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, timeout=wait,
                           encoding="utf-8", errors="replace")
        out = (p.stdout or "") + (p.stderr or "")
        DETAIL.append(f"$ {' '.join(cmd)} → {p.returncode}\n{out.strip()[:2000]}")
        return p.returncode, out
    except FileNotFoundError:
        return 127, ""
    except subprocess.TimeoutExpired:
        DETAIL.append(f"$ {' '.join(cmd)} → 응답 없음({wait}초)")
        return 124, ""


# 주소에 HEAD 요청 — 성공이면 True
# url: 주소
def reachable(url):
    try:
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "envcheck"})
        with urllib.request.urlopen(req, timeout=NET_WAIT) as r:
            return r.status < 500
    except Exception as e:
        DETAIL.append(f"HEAD {url} 실패: {e!r}")
        return False


# 임시 폴더 지우기 — git 이 만든 읽기 전용 파일(윈도우)도 쓰기 가능으로 바꿔 지운다
# path: 지울 폴더
def rmtree(path):
    def unlock(fn, p, _exc):
        os.chmod(p, 0o700)
        fn(p)
    shutil.rmtree(path, onerror=unlock)


# 비어 있는 포트 번호 하나
def free_port():
    s = socket.socket()
    s.bind(("0.0.0.0", 0))
    port = s.getsockname()[1]
    s.close()
    return port


# ======= requirements 읽기 — python_version 조건만 해석(키트 requirements 형식) =======
# 조건식 비교 연산
OPS = {"<": lambda a, b: a < b, "<=": lambda a, b: a <= b, ">": lambda a, b: a > b,
       ">=": lambda a, b: a >= b, "==": lambda a, b: a == b, "!=": lambda a, b: a != b}
MARK_RE = re.compile(r'python_version\s*(<=|>=|==|!=|<|>)\s*["\'](\d+)\.(\d+)["\']')


# 이 파이썬에 해당하는 줄인가
# marker: 세미콜론 뒤 조건식(없으면 빈 문자열) · ver: (주, 부) 파이썬 버전
def marker_ok(marker, ver):
    marker = marker.strip()
    if not marker:
        return True
    m = MARK_RE.fullmatch(marker)
    if not m:
        return True
    return OPS[m.group(1)](ver, (int(m.group(2)), int(m.group(3))))


# requirements 의 (이름, 고정 버전) 목록 — 이 파이썬에 해당하는 줄만
# text: 파일 내용 · ver: (주, 부)
def parse_requirements(text, ver):
    out = []
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        spec, _, marker = line.partition(";")
        if not marker_ok(marker, ver):
            continue
        m = re.match(r"([A-Za-z0-9_.\-]+)\s*(?:==\s*([^\s,]+))?", spec.strip())
        if m:
            out.append((m.group(1), m.group(2)))
    return out


# pip 실패 출력 → 사유 코드
# out: pip 출력
def classify_pip(out):
    low = out.lower()
    if "externally-managed" in low or "externally managed" in low:
        return "PEP668"
    if "no matching distribution" in low or "could not find a version" in low or "requires-python" in low:
        return "VERS"
    if any(k in low for k in ("connection", "network", "timed out", "name resolution", "proxy", "ssl")):
        return "NET"
    return "PIPFAIL"


# ======= A. 환경 기본 =======
def check_a(repo, install, repo_err=""):
    ver = sys.version_info[:2]
    pyver = ".".join(map(str, sys.version_info[:3]))
    # A1 — 파이썬 3.8(키트 도구) · 3.10(NiceGUI) 기준 · git · node
    missing = [b for b in ("git", "node") if not shutil.which(b)]
    if ver < (3, 8):
        add("A1", "fail", f"PYOLD {pyver} (키트 도구 3.8 이상)")
    elif ver < (3, 10):
        add("A1", "fail", f"PY310 {pyver} (NiceGUI 3.10 이상)")
    elif missing:
        add("A1", "fail", f"NOBIN {' '.join(missing)} · python {pyver}")
    else:
        add("A1", "info", f"python {pyver} · {run(['git', '--version'])[1].strip()} · node {run(['node', '--version'])[1].strip()}")
    # A2 — github 접속
    add("A2", "ok" if reachable("https://github.com") else "fail", "NET github.com")
    # A3 — pip · PyPI · 시스템 관리 환경(PEP 668)
    rc, _ = run([sys.executable, "-m", "pip", "--version"])
    pep668 = (Path(sysconfig.get_paths()["stdlib"]) / "EXTERNALLY-MANAGED").is_file()
    pypi = reachable("https://pypi.org/simple/")
    if rc != 0:
        add("A3", "fail", "NOPIP (python3 -m pip 없음)")
    elif not pypi:
        add("A3", "fail", "NET pypi.org")
    elif pep668:
        add("A3", "info", "PEP668 시스템 설치 거부 → venv 로 설치")
    else:
        add("A3", "ok")
    # A4 — 키트 설치 위치 · 파일 수
    if KIT:
        n = sum(1 for p in KIT.rglob("*") if p.is_file() and ".git" not in p.parts)
        add("A4", "info", f"kit {KIT} · 파일 {n}개")
    else:
        add("A4", "info", "NOKIT 단독 실행(키트 항목 건너뜀)")
    # A5 — ref/ 가 git 에서 제외되나 · 키트를 루트로 옮긴 뒤(ref/)와 옮기기 전(kit/ref) 둘 다 본다
    cands = ([Path(repo) / "ref" / "CHECKSHEET.md"] if repo else []) + ([KIT / "ref" / "CHECKSHEET.md"] if KIT else [])
    ref = next((p for p in cands if p.is_file()), None)
    if ref and repo:
        # --no-index — 이미 추적 중인 파일(패키지 저장소의 add -f)도 규칙만으로 판정
        rc, _ = run(["git", "check-ignore", "-q", "--no-index", str(ref)], cwd=repo)
        add("A5", "ok" if rc == 0 else "fail", "REFVIS ref/ 가 커밋될 수 있음")
    else:
        # 건너뛴 이유를 구별 — git 실패(소유권 경고 · git 없음)와 ref/ 없음은 다른 문제다
        why = f"git 저장소 인식 실패: {repo_err}" if not repo else "ref/CHECKSHEET.md 없음(키트 미설치 · 단독 실행)"
        add("A5", "info", f"건너뜀({why})")
    # A6 — git 이름 · 메일 · 임시 저장소 커밋
    name = run(["git", "config", "user.name"], cwd=repo)[1].strip()
    mail = run(["git", "config", "user.email"], cwd=repo)[1].strip()
    tmp = tempfile.mkdtemp(prefix="envcheck_git_")
    try:
        (Path(tmp) / "a.txt").write_text("a", encoding="utf-8")
        ok = run(["git", "init", "-q"], cwd=tmp)[0] == 0 and run(["git", "add", "a.txt"], cwd=tmp)[0] == 0 and \
            run(["git", "-c", "user.name=envcheck", "-c", "user.email=envcheck@local", "commit", "-q", "-m", "t"],
                cwd=tmp)[0] == 0
    finally:
        rmtree(tmp)
    if not ok:
        add("A6", "fail", "GIT 임시 저장소 커밋 실패")
    elif not (name and mail):
        add("A6", "fail", "GITID 이름 · 메일 없음 → git config user.name/user.email(--global 없이)")
    else:
        add("A6", "ok")
    # A7 — 명령 기록 · 홈
    hist = Path(os.environ.get("HISTFILE") or Path.home() / ".bash_history")
    add("A7", "info", f"명령 기록 {'있음' if hist.exists() else '없음'} ({hist}) · 홈 {Path.home()}")
    # A8 — requirements 라이브러리가 이미 깔려 있나
    req = KIT / "requirements.txt" if KIT else None
    reqs = parse_requirements(req.read_text(encoding="utf-8"), ver) if req and req.is_file() else []
    if reqs:
        lack = []
        for nm, _v in reqs:
            try:
                md.version(nm)
            except md.PackageNotFoundError:
                lack.append(nm)
        add("A8", "info", f"LIB 미설치 {len(lack)}/{len(reqs)} {' '.join(lack[:6])}" if lack else f"LIB 전부 있음 {len(reqs)}개")
    else:
        add("A8", "info", "건너뜀(requirements 없음)")
    # A9 — push 경로(원격 · 자격 도우미)만 본다 · 실제 push 안 함
    remotes = run(["git", "remote", "-v"], cwd=repo)[1].split() if repo else []
    helper = run(["git", "config", "credential.helper"], cwd=repo)[1].strip()
    add("A9", "info", f"원격 {remotes[1] if len(remotes) > 1 else '없음'} · 자격 도우미 {helper or '없음'}")
    # A10 — 로케일 · 출력 인코딩
    lang = os.environ.get("LC_ALL") or os.environ.get("LANG") or ""
    enc = (sys.stdout.encoding or "").lower()
    add("A10", "ok" if ("utf" in lang.lower() or "utf" in enc) else "fail", f"LANG '{lang}' · 출력 {enc}")
    # A11 — requirements 설치 시간(임시 venv · 끝나면 지움)
    if not install:
        add("A11", "info", "건너뜀(--no-install)")
    elif not reqs:
        add("A11", "info", "건너뜀(requirements 없음)")
    elif not pypi:
        add("A11", "info", "건너뜀(NET — pypi.org 접속 안 됨)")
    else:
        check_libtime(req)


# A11 — 임시 venv 에 requirements 설치 시간을 잰다(venv 를 못 만들면 임시 폴더에 --target)
# req: requirements.txt 경로
def check_libtime(req):
    tmp = tempfile.mkdtemp(prefix="envcheck_lib_")
    print(f"A11 설치 시간 재는 중 — pip install -r {req.name} (조금 걸림)", file=sys.stderr, flush=True)
    try:
        venv = Path(tmp) / "v"
        rc, _ = run([sys.executable, "-m", "venv", str(venv)])
        py = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        how = "venv"
        if rc == 0 and py.exists():
            cmd = [str(py), "-m", "pip", "install"]
        else:
            how = "target(VENV 없음)"
            cmd = [sys.executable, "-m", "pip", "install", "--target", str(Path(tmp) / "t")]
        t0 = time.time()
        # 요청마다 5초 · 재시도 없음 — pip 기본값(15초 × 5번)이면 막힌 네트워크에서 패키지마다 몇 분씩 멈춘다
        rc, out = run(cmd + ["-q", "--disable-pip-version-check", "--timeout", "5", "--retries", "0",
                             "-r", str(req)], wait=None)
        sec = round(time.time() - t0)
        if rc == 0:
            add("A11", "info", f"LIBTIME {sec}초 ({how})")
            global NG
            NG = ([str(py)], {}) if how == "venv" else ([sys.executable], {"PYTHONPATH": str(Path(tmp) / "t")})
        else:
            add("A11", "fail", f"{classify_pip(out)} 설치 실패 {sec}초 ({how})")
    finally:
        CLEANUP.append(tmp)


# ======= B. Codex =======
def check_b(repo):
    # B1 — codex 버전
    rc, out = run(["codex", "--version"])
    if rc == 127:
        add("B1", "fail", "NOBIN codex")
    else:
        add("B1", "info", f"{out.strip().splitlines()[0] if out.strip() else '버전 못 읽음'} (연습 0.163 · 0.164)")
    # B2 — 기능 목록에서 auto_compaction · unified_exec
    rc, out = run(["codex", "features", "list"])
    if rc == 0:
        def state(key):
            line = next((l for l in out.splitlines() if key in l), "")
            if not line:
                return "없음"
            return "켜짐" if re.search(r"\b(true|enabled|on|stable)\b", line.lower()) else "꺼짐/실험"
        add("B2", "info", f"auto_compaction {state('auto_compaction')} · unified_exec {state('unified_exec')}")
    else:
        add("B2", "info", "기능 목록 못 읽음")
    # B3 — Codex 가 읽는 범위(git 저장소 루트 → 지금 폴더)에 AGENTS.md · .agents/skills 가 있나
    cwd = Path.cwd().resolve()
    chain = [cwd]
    if repo:
        top = Path(repo).resolve()
        while chain[-1] != top and chain[-1].parent != chain[-1]:
            chain.append(chain[-1].parent)
    agents = any((d / "AGENTS.md").is_file() for d in chain)
    # 스킬은 저장소 .agents/skills 또는 Codex 홈 skills(install.sh 가 복사 · 10/29 체험: kit/ 안은 /skills 에 안 보임)
    codex_skills = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex") / "skills"
    home_skills = [p for p in (codex_skills, Path.home() / ".agents" / "skills") if (p / "ready-start").is_dir()]
    skills = any((d / ".agents" / "skills").is_dir() for d in chain) or bool(home_skills)
    where = f" · 스킬 위치 {home_skills[0]}" if home_skills else ""
    if agents and skills:
        add("B3", "ok")
    elif KIT:
        lack = " · ".join(x for x, ok in (("AGENTS.md", agents), ("스킬(.agents/skills · ~/.codex/skills)", skills)) if not ok)
        add("B3", "fail", f"AGPATH {lack} 가 읽히는 범위 밖({KIT.name}/ 안) → ReadyStart.txt 1번 줄(-C <키트>)로 다시 띄운다 · 루트로 옮기지 않는다{where}")
    else:
        add("B3", "info", f"건너뜀(키트 없음){where}")
    # B5 — 세션 기록 읽기(whoami · hand-on 이 쓴다)
    codex_home = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
    idx, sess = codex_home / "session_index.jsonl", codex_home / "sessions"
    if not idx.exists() and not sess.exists():
        # 정보 — Codex 를 한 번도 안 띄운 새 환경이면 정상적으로 없다. 읽기가 막힌 것(NOREAD)만 실패
        add("B5", "info", f"NOIDX {codex_home} 에 세션 기록 없음(Codex 를 띄운 뒤 다시 보면 생김)")
    else:
        try:
            if idx.exists():
                with open(idx, "rb") as f:
                    f.read(1)
            if sess.exists():
                next(iter(sess.iterdir()), None)
            add("B5", "ok")
        except OSError as e:
            add("B5", "fail", f"NOREAD 세션 기록 못 읽음 ({e.__class__.__name__})")
    # B4 — 샌드박스 도구(bwrap) · 사용자 이름공간
    if os.name == "nt":
        add("B4", "info", "윈도우 — 해당 없음")
    elif not shutil.which("bwrap"):
        add("B4", "fail", "BWRAP 없음")
    else:
        rc, _ = run(["unshare", "-U", "true"])
        add("B4", "ok" if rc == 0 else "fail", "BWRAP 사용자 이름공간 막힘")


# 시험용 웹 서버 응답
class _Hello(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *a):
        pass


# 주소에 GET — (상태 코드, 본문). 실패는 (0, "")
# url: 주소
def get(url):
    try:
        with urllib.request.urlopen(url, timeout=NET_WAIT) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception:
        return 0, ""


# ======= C. 서버 · 미리보기 =======
def check_c():
    # C1 — 0.0.0.0 서버를 띄워 자기 자신에게 접속 → 바로 끔
    try:
        srv = HTTPServer(("0.0.0.0", 0), _Hello)
        th = threading.Thread(target=srv.serve_forever, daemon=True)
        th.start()
        code, _ = get(f"http://127.0.0.1:{srv.server_address[1]}/")
        srv.shutdown()
        srv.server_close()
        add("C1", "ok" if code == 200 else "fail", "PORT 자기 접속 실패")
    except OSError as e:
        add("C1", "fail", f"BIND {e}")
    # C2 — 쓸 포트가 비었나 · 차 있으면 우리 devview(설문 상태 json 응답)인지 가른다
    busy, ours = [], []
    for port in (8600, 8701):
        s = socket.socket()
        try:
            s.bind(("0.0.0.0", port))
        except OSError:
            code, body = get(f"http://127.0.0.1:{port}/sv/api/state")
            (ours if code == 200 and body.lstrip().startswith("{") else busy).append(str(port))
        finally:
            s.close()
    if busy:
        add("C2", "fail", f"BUSY {' '.join(busy)}" + (f" · 우리 devview {' '.join(ours)}" if ours else ""))
    elif ours:
        add("C2", "info", f"우리 devview 가 이미 떠 있음 {' '.join(ours)}")
    else:
        add("C2", "ok")
    # C3 — 헤드리스 브라우저
    br = next((b for b in ("chromium", "chromium-browser", "google-chrome") if shutil.which(b)), None)
    add("C3", "info", f"{br} 있음(Codex 가 앱 화면을 찍을 수 있음)" if br else "chromium 없음")
    # C4 — devview 자체 시험
    check_devview()
    # C5 — tmux
    add("C5", "ok" if shutil.which("tmux") else "info", "NOTMUX tmux 없음")


# 시험용 환경 변수 — 설문 등록 목록을 임시 파일로 돌려 홈에 흔적을 남기지 않는다
# tmp: 임시 폴더
def _env(tmp):
    env = dict(os.environ)
    env["SURVEY_REGISTRY"] = str(Path(tmp) / "stores.json")
    env["PYTHONUTF8"] = "1"
    return env


# C4 — devview 를 임시 폴더로 띄워 화면 · 설문 탭 응답을 보고 끈다
def check_devview():
    dv = KIT / "devview" / "devview.py" if KIT else None
    if not dv or not dv.is_file():
        add("C4", "info", "건너뜀(devview 없음)")
        return
    tmp = tempfile.mkdtemp(prefix="envcheck_dv_")
    port = free_port()
    proc = subprocess.Popen([sys.executable, str(dv), tmp, "--port", str(port), "--log", str(Path(tmp) / "dv.log")],
                            env=_env(tmp), stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        code = 0
        # 뜰 때까지 짧게 반복 확인 — 프로세스가 죽으면 바로 멈춘다
        for _ in range(75):
            if proc.poll() is not None:
                break
            code, _ = get(f"http://127.0.0.1:{port}/")
            if code == 200:
                break
            time.sleep(0.2)
        if code != 200:
            out = proc.stdout.read().decode("utf-8", "replace") if proc.poll() is not None else ""
            DETAIL.append(f"devview 출력: {out[-1500:]}")
            add("C4", "fail", "DV 화면 응답 없음")
            return
        sv, _ = get(f"http://127.0.0.1:{port}/sv/api/state")
        add("C4", "ok" if sv == 200 else "fail", f"DV 설문 탭 없음({sv})")
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        rmtree(tmp)


# ======= D. 설문 =======
def check_d():
    sv = next((p for p in (KIT / ".agents" / "skills" / "survey" / "survey.py",
                           KIT / "skills_src" / "skills" / "survey" / "survey.py") if p.is_file()),
              KIT / ".agents" / "skills" / "survey" / "survey.py") if KIT else None
    sample = sv.parent / "sample_questions.json" if sv else None
    if not sv or not sv.is_file() or not sample.is_file():
        add("D1", "info", "건너뜀(설문 도구 없음)")
        return
    tmp = tempfile.mkdtemp(prefix="envcheck_sv_")
    try:
        env = _env(tmp)
        rc, out = run([sys.executable, str(sv), "--dir", tmp, "new", str(sample)], env=env)
        m = re.search(r'"id":\s*"([^"]+)"', out)
        if rc != 0 or not m:
            add("D1", "fail", "SURVEY 등록 실패")
            return
        rc, out = run([sys.executable, str(sv), "--dir", tmp, "result", m.group(1)], env=env)
        add("D1", "ok" if rc == 0 and "pending" in out else "fail", "SURVEY 결과 조회 실패")
    finally:
        rmtree(tmp)


# ======= E. NiceGUI 서버 — 처음부터 켜지나 · 띄운 셸이 끝나도 사나 · 일시정지 뒤에도 사나 =======
# 시험용 최소 앱 — 제목 글자 · /health · reload 끔(파일 감시 하위 프로세스가 생기지 않게) · 0.0.0.0
NG_APP = '''import sys
from nicegui import app, ui


@app.get("/health")
def health():
    return {"ok": True}


@ui.page("/")
def index():
    ui.label("envcheck-nicegui")


if __name__ in {"__main__", "__mp_main__"}:
    ui.run(host="0.0.0.0", port=int(sys.argv[1]), reload=False, show=False, title="envcheck-ng")
'''
# 무언 정지 대비 상한(초) — 판정은 «프로세스가 죽었나 · /health 가 200 인가» 로 하고 이 값은 멈춘 경우만 끊는다
NG_WAIT = 90
# 냉시동 실패 출력 → 사유
NG_HINTS = [("address already in use", "BUSY 포트 사용 중"), ("modulenotfounderror", "LIB 모듈 없음"),
            ("permission denied", "PERM 권한 거부"), ("no such file", "FILE 파일 · 폴더 없음(logs/ · DB 경로 확인)")]


# NiceGUI 를 띄울 파이썬 — A11 venv → 지금 파이썬(이미 깔려 있으면) → None
def ng_python():
    if NG:
        return NG
    try:
        md.version("nicegui")
        return [sys.executable], {}
    except md.PackageNotFoundError:
        return None


# /health 가 200 이 될 때까지 기다림 — True / 프로세스가 죽으면 즉시 False
# port: 포트 · alive: 살아 있나를 돌려주는 함수
def wait_health(port, alive):
    t0 = time.time()
    while time.time() - t0 < NG_WAIT:
        if not alive():
            return False
        if get(f"http://127.0.0.1:{port}/health")[0] == 200:
            return True
        time.sleep(0.3)
    return False


# PID 살아 있나
# pid: 프로세스 번호
def pid_alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ValueError):
        return False


# PID 하나만 종료(이름 · 묶음 종료 안 함)
# pid: 프로세스 번호
def kill_pid(pid):
    try:
        os.kill(pid, 15)
    except OSError:
        pass


# 앱 파일을 폴더에 쓰고 경로를 돌려줌
# folder: 폴더
def write_app(folder):
    app = Path(folder) / "ng_app.py"
    app.write_text(NG_APP, encoding="utf-8")
    return app


def check_e():
    found = ng_python()
    if not found:
        for no in ("E1", "E2"):
            add(no, "info", "건너뜀(LIB 없음 nicegui — --no-install · 미설치)")
        return
    py, extra = found
    env = dict(os.environ, PYTHONUTF8="1", **extra)
    tmp = tempfile.mkdtemp(prefix="envcheck_ng_")
    CLEANUP.append(tmp)
    app = write_app(tmp)
    # E1 — 냉시동: 새 프로세스로 띄워 /health 200 + 화면 제목 → 프로세스 객체로 종료
    port = free_port()
    log = open(Path(tmp) / "e1.log", "w+", encoding="utf-8")
    t0 = time.time()
    proc = subprocess.Popen(py + [str(app), str(port)], cwd=tmp, env=env, stdout=log, stderr=subprocess.STDOUT)
    try:
        ok = wait_health(port, lambda: proc.poll() is None)
        sec = round(time.time() - t0, 1)
        if ok:
            code, body = get(f"http://127.0.0.1:{port}/")
            add("E1", "ok" if code == 200 and "envcheck-ng" in body else "fail", f"NGPAGE 화면 응답 {code}")
            DETAIL.append(f"E1 냉시동 {sec}초")
        else:
            log.seek(0)
            out = log.read()
            DETAIL.append(f"E1 출력:\n{out[-2000:]}")
            hint = next((h for k, h in NG_HINTS if k in out.lower()), None)
            last = (out.strip().splitlines() or ["출력 없음"])[-1][:100]
            state = "죽음" if proc.poll() is not None else f"{NG_WAIT}초 무응답"
            add("E1", "fail", f"NGSTART 서버 {state} · {hint or last}")
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        log.close()
    # E2 — nohup 으로 띄운 셸이 먼저 끝난 뒤에도 사나(서버 탭 닫기 · Codex 턴 끝과 같은 모양)
    if os.name == "nt" or not shutil.which("nohup"):
        add("E2", "info", "건너뜀(nohup 없음 · 윈도우)")
        return
    port = free_port()
    cmd = " ".join(f"'{c}'" for c in py + [str(app), str(port)])
    rc, out = run(["sh", "-c", f"nohup {cmd} > '{tmp}/e2.log' 2>&1 & echo $!"], cwd=tmp, env=env)
    pid = int(out.strip().splitlines()[-1]) if rc == 0 and out.strip() else 0
    try:
        if not pid or not wait_health(port, lambda: pid_alive(pid)):
            add("E2", "fail", "NGDETACH 셸이 끝난 뒤 서버가 안 뜨거나 죽음")
            return
        time.sleep(2)
        add("E2", "ok" if pid_alive(pid) and get(f"http://127.0.0.1:{port}/health")[0] == 200 else "fail",
            "NGDETACH 셸이 끝난 뒤 2초 안에 죽음")
    finally:
        if pid:
            kill_pid(pid)


# E3 — 일시정지 뒤 생존(수동 두 단계). 상태는 작업 폴더 밖 ~/.envcheck 에
STATE_DIR = Path.home() / ".envcheck"


# --serve-start — 서버를 띄우고 PID · 포트를 적는다
def serve_start():
    found = ng_python()
    STATE_DIR.mkdir(exist_ok=True)
    if not found:
        venv = STATE_DIR / "venv"
        print("E3 NiceGUI 가 없어 ~/.envcheck/venv 에 설치 중", file=sys.stderr, flush=True)
        if run([sys.executable, "-m", "venv", str(venv)])[0] != 0:
            print("E3 VENV 만들기 실패")
            return 1
        vpy = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        line = next((f"nicegui=={v}" for n, v in parse_requirements(
            (KIT / "requirements.txt").read_text(encoding="utf-8"), sys.version_info[:2]) if n == "nicegui"), "nicegui") \
            if KIT and (KIT / "requirements.txt").is_file() else "nicegui"
        rc, out = run([str(vpy), "-m", "pip", "install", "-q", "--timeout", "5", "--retries", "0", line], wait=None)
        if rc != 0:
            print(f"E3 {classify_pip(out)} NiceGUI 설치 실패")
            return 1
        found = ([str(vpy)], {})
    py, extra = found
    app = write_app(STATE_DIR)
    port = free_port()
    env = dict(os.environ, PYTHONUTF8="1", **extra)
    cmd = " ".join(f"'{c}'" for c in py + [str(app), str(port)])
    rc, out = run(["sh", "-c", f"nohup {cmd} > '{STATE_DIR}/serve.log' 2>&1 & echo $!"], env=env)
    pid = int(out.strip().splitlines()[-1]) if rc == 0 and out.strip() else 0
    if not pid or not wait_health(port, lambda: pid_alive(pid)):
        print("E3 NGSTART 서버가 안 뜸 — ~/.envcheck/serve.log")
        return 1
    (STATE_DIR / "serve.txt").write_text(f"{pid} {port}\n", encoding="utf-8")
    print(f"E3 시작 · PID {pid} · 포트 {port} — 다음 명령에서 /health 확인 · 끝날 때 --serve-check")
    return 0


# --serve-check — 적어 둔 PID 가 살아 있고 /health 가 200 인가 → 그 PID 만 종료 · 상태 폴더 정리
def serve_check():
    f = STATE_DIR / "serve.txt"
    if not f.is_file():
        print("E3 기록 없음 — 먼저 --serve-start")
        return 1
    pid, port = map(int, f.read_text(encoding="utf-8").split())
    alive = pid_alive(pid)
    code = get(f"http://127.0.0.1:{port}/health")[0] if alive else 0
    if alive and code == 200:
        print(f"E3 생존 · PID {pid} · /health 200")
        rc = 0
    else:
        print(f"E3 PAUSEKILL 일시정지 뒤 서버 {'꺼짐' if not alive else f'응답 {code}'} → 대회 중 서버를 다시 띄우는 습관 필요")
        rc = 1
    kill_pid(pid)
    rmtree(str(STATE_DIR))
    return rc


# 출력 — 실패 · 정보만 한 줄씩 + 요약(실패 번호)
# where: 실행 위치 이름 · why: 판별 근거
def report(where, why):
    fails = [r for r in RESULTS if r[1] == "fail"]
    passed = sum(1 for r in RESULTS if r[1] == "ok")
    lines = [f"envcheck · {where}({why}) · {len(RESULTS)}개 중 통과 {passed} · 실패 {len(fails)}"]
    lines += [f"{no} {reason}" for no, state, reason in RESULTS if state in ("fail", "info")]
    lines.append("요약: " + (" ".join(r[0] for r in fails) or "실패 없음"))
    return lines


# 실행 위치 판별 — (이름, 근거). 부모 프로세스 줄에 codex 가 있나를 먼저, 환경 변수는 두 번째 근거
# 리눅스 /proc/<pid>/stat 의 4번째 칸 = 부모 PID · comm = 실행 파일 이름
def detect_where():
    pid = os.getppid()
    for _ in range(30):
        try:
            comm = Path(f"/proc/{pid}/comm").read_text(encoding="utf-8", errors="replace").strip()
            stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8", errors="replace")
        except OSError:
            break
        if "codex" in comm.lower():
            return "Codex", "부모 프로세스"
        # comm 에 공백 · 괄호가 들어갈 수 있어 마지막 «)» 뒤부터 나눈다
        ppid = int(stat.rsplit(")", 1)[1].split()[1])
        if ppid <= 1:
            break
        pid = ppid
    if any(k.startswith("CODEX_SANDBOX") for k in os.environ):
        return "Codex", "환경 변수"
    return "사용자 터미널", "부모 프로세스에 codex 없음"


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description="대회 환경 점검")
    ap.add_argument("--no-install", action="store_true", help="A11 설치 시간 재기를 건너뜀")
    ap.add_argument("--where", default=None, help="결과 첫 줄의 실행 위치(기본: 자동 판별)")
    ap.add_argument("--serve-start", action="store_true", help="E3 1단계 — 시험 서버를 띄우고 PID · 포트를 ~/.envcheck 에 적음")
    ap.add_argument("--serve-check", action="store_true", help="E3 2단계 — 그 서버가 아직 사는지 보고 종료")
    a = ap.parse_args(argv)
    if a.serve_start:
        return serve_start()
    if a.serve_check:
        return serve_check()
    where, why = (a.where, "인자") if a.where else detect_where()
    rc, out = run(["git", "rev-parse", "--show-toplevel"])
    repo = out.strip() if rc == 0 else None
    repo_err = "git 없음" if rc == 127 else (out.strip().splitlines() or ["?"])[0][:120]
    try:
        check_a(repo, not a.no_install, repo_err)
        check_b(repo)
        check_c()
        check_d()
        check_e()
    finally:
        for tmp in CLEANUP:
            rmtree(tmp)
    lines = report(where, why)
    # 위치마다 따로 — 사용자 터미널 · Codex 두 번 돌려도 앞 결과가 지워지지 않게
    tag = {"Codex": "codex", "사용자 터미널": "user"}.get(where) or re.sub(r"[^A-Za-z0-9_-]+", "_", where) or "x"
    log = Path(tempfile.gettempdir()) / f"envcheck-{tag}.log"
    try:
        log.write_text("\n".join(lines + ["", "----- 자세히 -----"] + DETAIL) + "\n", encoding="utf-8")
        lines.append(f"자세히: {log}")
    except OSError:
        pass
    print("\n".join(lines), flush=True)
    return 1 if any(r[1] == "fail" for r in RESULTS) else 0


if __name__ == "__main__":
    sys.exit(main())
