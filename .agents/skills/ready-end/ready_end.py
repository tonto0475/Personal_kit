# -*- coding: utf-8 -*-
"""ready-end — 제출 직전 최종 점검. 찾기만 하고 고치지 않는다(고치는 건 Codex 가 걸린 곳을 읽고 판단한 뒤).

실행(과제 저장소 루트): python3 ~/.codex/skills/ready-end/ready_end.py [--no-test] [--start-port N] [--card] [--all]
- 묶음: S 보안 위생 · V 코드 취약점 · R 제출 준비 · D 문서(doc_check.py)
- 출력: 실패(✗) · 확인 필요(△)만 «번호 사유 파일:줄» 한 줄씩 + 요약. 비밀값은 값을 찍지 않고 위치만
- 종료코드: 실패가 있으면 1 · 없으면 0 · git 저장소가 아니면 2
- 표준 라이브러리만 · 파이썬 3.8 이상
"""
import argparse
import importlib.util
import os
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
# 결과 — (번호, 상태 fail/warn, 사유)
RESULTS = []
# 점검 묶음별 통과 개수
PASSED = []
# 우리 도구 · 예시 경로 — 제출물이 아니거나 우리 도구라 걸려도 의미 없음. 작업 폴더(키트) 안에서도 같은 이름을 뺀다
TOOLS = (".agents/", "skills_src/", "devview/", "ref/", "docs/examples/", "docs/surveys/", "scripts/envcheck/",
         "scripts/codex_config/", "scripts/hooks/", "install.sh")
# 기본으로 빼는 경로 — main 이 작업 폴더를 정한 뒤 채움(키트 = 작업 폴더면 kit/ 통째가 아니라 그 안의 도구만)
SKIP_PREFIX = TOOLS + ("kit/",)
# 대회 플랫폼이 홈(= 과제 저장소)에 만드는 파일 — 커밋되면 안 됨(.literacy 엔 키가 있다 · 기록 파일은 지우지도 않는다)
PLATFORM_DIRS = r"\.literacy|\.codex|\.cache|\.npm|\.devview|\.local|\.config|\.envcheck"
PLATFORM_FILES = (r"|^\.(bash_history|bashrc|profile|bash_logout|sudo_as_admin_successful|viminfo|python_history|lesshst|wget-hsts)$"
                  r"|(^|/)ReadyStart\.(txt|md)$")
PLATFORM = re.compile(rf"^({PLATFORM_DIRS}|kit)/" + PLATFORM_FILES)
# 작업 폴더 — 앱 · tests · requirements · run.sh · docs 가 있는 곳(키트를 작업 폴더로 쓰면 <루트>/kit). main 이 정함
WORK = None
# 코드 취약점에서 더 빼는 경로 — 시험 코드는 일부러 위험한 입력을 쓴다
SKIP_V = ("tests/",)


def add(no, state, reason):
    RESULTS.append((no, state, reason))


def ok(no):
    PASSED.append(no)


# git 명령 — (종료코드, 출력)
def git(root, *args):
    p = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return p.returncode, p.stdout.strip()


# 제출에 들어갈 파일 — 추적 중 + 아직 추적 안 했지만 무시 대상도 아닌 것(git add . 하면 들어감)
def submit_files(root, all_files):
    _, tracked = git(root, "ls-files")
    _, others = git(root, "ls-files", "--others", "--exclude-standard")
    every = sorted(set(f for f in (tracked + "\n" + others).splitlines() if f))
    files = [f for f in every if not PLATFORM.search(f)]
    if not all_files:
        files = [f for f in files if not f.startswith(SKIP_PREFIX)]
    return [f for f in files if (root / f).is_file()], set(others.splitlines()), every


# 글 파일 읽기 — 바이너리 · 큰 파일은 건너뜀
def read(root, f):
    p = root / f
    try:
        if p.stat().st_size > 2_000_000:
            return None
        b = p.read_bytes()
    except OSError:
        return None
    if b"\0" in b[:4096]:
        return None
    return b.decode("utf-8", "replace")


# ======= S. 보안 위생 =======
# 비밀값 모양 — (이름, 정규식). 값은 출력하지 않는다
SECRET_PATS = [
    ("OpenAI 키 모양", re.compile(r"sk-(?:proj-|plat-)?[A-Za-z0-9_-]{20,}")),
    ("GitHub 토큰 모양", re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}")),
    ("AWS 키 모양", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("개인 키 블록", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("슬랙 토큰 모양", re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}")),
    ("비밀값 직접 대입", re.compile(r"""(?i)\b(api[_-]?key|secret|password|passwd|token|access[_-]?key)\b\s*[:=]\s*["'][^"'\s]{8,}["']""")),
]
# 대입 문장이라도 자리 표시면 통과
PLACEHOLDER = re.compile(r"(?i)(xxx|your[_-]|changeme|example|dummy|test|fake|<|\$\{|os\.environ|getenv|\*\*\*)")
# 커밋되면 안 되는 파일 모양 — (이름, 정규식)
BAD_FILES = [
    (".env 실제 값 파일", re.compile(r"(^|/)\.env(\.[^/]*)?$")),
    ("키 · 인증서 파일", re.compile(r"\.(pem|key|p12|pfx)$|(^|/)id_(rsa|ed25519)$")),
    ("DB 파일", re.compile(r"\.(sqlite3?|db)$")),
    ("파이썬 실행 부산물", re.compile(r"(^|/)(__pycache__/|\.pytest_cache/)|\.pyc$")),
    ("가상환경", re.compile(r"(^|/)\.?venv/")),
    ("실행 로그", re.compile(r"(^|/)logs/.+\.log$")),
]
# .env 의 예시 파일은 커밋해도 된다
ENV_OK = re.compile(r"(^|/)\.env\.(example|sample|template)$")


def check_security(root, files, untracked, every):
    # S1 — 비밀값 모양
    hits = []
    for f in files:
        t = read(root, f)
        if t is None:
            continue
        for n, line in enumerate(t.splitlines(), 1):
            for name, pat in SECRET_PATS:
                m = pat.search(line)
                if m and not (name == "비밀값 직접 대입" and PLACEHOLDER.search(m.group(0))):
                    hits.append(f"{f}:{n} {name}")
    for h in hits[:15]:
        add("S1", "fail", h)
    if not hits:
        ok("S1")
    # S2 — 비밀값(환경변수 · .env)이 파일 · 커밋 이력에 그대로(8글자 이상 · 값은 안 찍음)
    #   대회는 .env 가 없고 플랫폼이 환경변수로 키를 넣는다(OPENAI_API_KEY · OPENAI_BASE_URL 등)
    env = root / ".env"
    vals = [(k, v) for k, v in os.environ.items()
            if re.search(r"KEY|TOKEN|SECRET|PASSWORD|PASSWD|BASE_URL|CREDENTIAL", k, re.I) and len(v) >= 8]
    if env.is_file():
        for line in env.read_text(encoding="utf-8", errors="replace").splitlines():
            k, _, v = line.partition("=")
            v = v.strip().strip("\"'")
            if k.strip() and not k.strip().startswith("#") and len(v) >= 8:
                vals.append((k.strip(), v))
    leak = []
    for f in files:
        if f == ".env" or ENV_OK.search(f):
            continue
        t = read(root, f)
        if t is None:
            continue
        for k, v in vals:
            if v in t:
                n = t[:t.index(v)].count("\n") + 1
                leak.append(f"{f}:{n} .env 의 {k} 값이 그대로 들어 있음")
    _, hist = git(root, "log", "-p", "--all", "--no-color")
    for k, v in vals:
        if v in hist:
            leak.append(f"커밋 이력(git log -p)에 {k} 값이 있음 — 지금 파일에서 지워도 이력에 남는다 · 유저에게 보고")
    for h in leak[:10]:
        add("S2", "fail", h)
    if not leak:
        ok("S2")
    # S3 — 커밋되면 안 되는 파일이 제출 대상에
    bad = []
    for f in files:
        if ENV_OK.search(f):
            continue
        for name, pat in BAD_FILES:
            if pat.search(f):
                bad.append(f"{f} {name}{' (추적 안 됨 — git add . 하면 들어감)' if f in untracked else ''}")
                break
    big = [f for f in files if (root / f).stat().st_size > 5_000_000]
    for f in big:
        bad.append(f"{f} 5MB 넘는 파일({(root / f).stat().st_size // 1_000_000}MB) — 원본 데이터면 커밋 제외 검토")
    for h in bad[:15]:
        add("S3", "fail", h)
    if not bad:
        ok("S3")
    # S5 — 플랫폼 · 키트 파일: 추적 중이면 실패 · 미추적이면 git add . 로 들어갈 수 있어 확인 필요
    plat = [f for f in every if PLATFORM.search(f)]
    tracked_plat = [f for f in plat if f not in untracked]
    loose = sorted({f.split("/")[0] + ("/" if "/" in f else "") for f in plat if f in untracked})
    if tracked_plat:
        add("S5", "fail", f"플랫폼 · 키트 파일이 커밋돼 있음 — {' · '.join(tracked_plat[:6])} → git rm --cached <경로> 뒤 "
                          f".git/info/exclude 에 추가(파일 자체는 지우지 않는다)")
    if loose:
        add("S5", "warn", f"미추적 플랫폼 · 키트 {len(loose)}개({' · '.join(loose[:8])}) — git add . 하면 들어감 → "
                          f"printf '%s\\n' {' '.join(loose[:8])} >> .git/info/exclude")
    if not tracked_plat and not loose:
        ok("S5")
    # S4 — .env 가 무시 대상인가
    rc, _ = git(root, "check-ignore", "-q", "--no-index", ".env")
    if rc == 0 or not env.exists():
        ok("S4")
    else:
        add("S4", "fail", ".gitignore 에 .env 없음 — 실수로 커밋될 수 있음")


# ======= V. 코드 취약점(파이썬) — 걸린 줄은 Codex 가 읽고 진짜 문제인지 판단 =======
# (번호, 상태, 이름, 정규식)
VULN = [
    ("V1", "fail", "SQL 문자열 조립(f-string · % · + · format) — 매개변수 바인딩(?)으로",
     re.compile(r"""(?i)\.(execute|executemany|executescript|read_sql(_query)?)\(\s*(f["']|["'][^"']*\b(select|insert|update|delete|where)\b[^"']*["']\s*(%|\+|\.format))""")),
    ("V2", "fail", "eval / exec — 입력이 섞이면 임의 코드 실행", re.compile(r"(?<![\w.])(eval|exec)\(")),
    ("V3", "fail", "shell=True · os.system — 명령 주입", re.compile(r"shell\s*=\s*True|os\.system\(|os\.popen\(")),
    ("V4", "fail", "안전하지 않은 역직렬화(pickle · yaml.load)", re.compile(r"pickle\.loads?\(|yaml\.load\((?![^)]*SafeLoader)")),
    ("V5", "fail", "TLS 검증 끔(verify=False)", re.compile(r"verify\s*=\s*False")),
    ("V6", "fail", "localhost 바인딩 — 대회 미리보기는 0.0.0.0 이어야 보임",
     re.compile(r"""(host\s*=\s*["'](127\.0\.0\.1|localhost)["'])|(--host\s+(127\.0\.0\.1|localhost))""")),
    ("V7", "warn", "예외를 삼킴(except: · except Exception: pass) — 실패가 조용히 사라짐",
     re.compile(r"^\s*except\s*:|^\s*except\s+(Exception|BaseException)\s*(as\s+\w+\s*)?:\s*(pass)?\s*$")),
    ("V8", "warn", "디버그 흔적(breakpoint · pdb)", re.compile(r"breakpoint\(\)|import\s+pdb|pdb\.set_trace")),
    ("V9", "warn", "경로에 외부 입력을 그대로 붙임(.. 검사 필요)",
     re.compile(r"""open\(\s*(f["'][^"']*\{|[^)]*\+\s*(request|req|params|query|filename|name)\b)""")),
]


def check_vulns(root, files):
    py = [f for f in files if f.endswith(".py") and not f.startswith(SKIP_V)]
    sh = [f for f in files if f.endswith(".sh") or f.endswith(("Procfile", "run.sh"))]
    found = {v[0]: [] for v in VULN}
    for f in py + sh:
        t = read(root, f)
        if t is None:
            continue
        for n, line in enumerate(t.splitlines(), 1):
            if line.lstrip().startswith("#"):
                continue
            for no, _st, _name, pat in VULN:
                if f in sh and no != "V6":
                    continue
                if pat.search(line):
                    found[no].append(f"{f}:{n}")
    for no, st, name, _ in VULN:
        if found[no]:
            more = f" 외 {len(found[no]) - 5}곳" if len(found[no]) > 5 else ""
            add(no, st, f"{name} — {' · '.join(found[no][:5])}{more}")
        else:
            ok(no)


# ======= R. 제출 준비 =======
# import 이름 → 배포 이름(다를 때만)
DIST = {"yaml": "pyyaml", "dotenv": "python-dotenv", "sklearn": "scikit-learn", "cv2": "opencv-python",
        "PIL": "pillow", "bs4": "beautifulsoup4", "dateutil": "python-dateutil", "jose": "python-jose",
        "multipart": "python-multipart", "pydantic_core": "pydantic-core"}


def check_ready(root, files, untracked, run_tests, start_port):
    # tests · requirements · run.sh 는 작업 폴더 기준 · git 은 루트 기준
    work = WORK or root
    # R0 — git 이름 · 메일(없으면 커밋 자체가 실패 · 체험 1회차 A6)
    name, mail = git(root, "config", "user.name")[1], git(root, "config", "user.email")[1]
    if name and mail:
        ok("R0")
    else:
        add("R0", "fail", "git 이름 · 메일 없음 — git config user.name … · user.email …(--global 없이 · 샌드박스 밖 승인)")
    # R1 — 개발 전용 표시가 남았나(캡처 단축키 등)
    dev = []
    for f in files:
        t = read(root, f)
        if t and "DEV-ONLY" in t:
            dev += [f"{f}:{n}" for n, l in enumerate(t.splitlines(), 1) if "DEV-ONLY" in l]
    if dev:
        add("R1", "fail", f"DEV-ONLY 표시가 남음 — 제출 전에 뺀다: {' · '.join(dev[:6])}")
    else:
        ok("R1")
    # R2 — 작업 트리 깨끗한가
    #   추적 파일 변경 = 실패(커밋 순서 · diff 증거에서 빠짐) · 새 파일 = 확인 필요(플랫폼 · 키트는 S5 가 맡음)
    _, st = git(root, "status", "--porcelain", "-uall")
    lines = [l for l in st.splitlines() if l and not l[3:].startswith(SKIP_PREFIX) and not PLATFORM.search(l[3:])]
    changed = [l for l in lines if not l.startswith("??")]
    new = [l[3:] for l in lines if l.startswith("??")]
    if changed:
        add("R2", "fail", f"커밋 안 된 변경 {len(changed)}개 — {' · '.join(l.strip() for l in changed[:6])}")
    if new:
        add("R2", "warn", f"커밋 안 한 새 파일 {len(new)}개 — {' · '.join(new[:6])} · 제출물이면 커밋, 아니면 exclude")
    if not changed and not new:
        ok("R2")
    # R7 — 커밋 추천: 추적 안 된 새 파일 중 커밋된 코드가 import 하거나 커밋된 글이 경로를 적은 것(쓰는데 빠진 파일)
    recommend_commits(root, work, new)
    # R3 — 전체 테스트(tests/ 가 있으면)
    if not run_tests:
        add("R3", "warn", "테스트 건너뜀(--no-test)")
    elif not (work / "tests").is_dir():
        add("R3", "warn", "tests/ 없음 — 확인한 방법을 서술형에서 무엇으로 말할지")
    elif importlib.util.find_spec("xdist") is None:
        # 전체 시험은 병렬로만 돌린다(유저 지정 11/04 — 순서대로 돌리면 제출 직전 시간을 다 쓴다)
        add("R3", "warn", "pytest-xdist 없음 — 전체 시험 건너뜀(pip install pytest-xdist 뒤 다시)")
    else:
        t0 = time.time()
        p = subprocess.run([sys.executable, "-m", "pytest", "-q", "-n", "auto", "tests"], cwd=work, capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        last = (p.stdout.strip().splitlines() or ["출력 없음"])[-1]
        if p.returncode in (0, 5):
            ok("R3")
            print(f"  R3 테스트 {last} ({round(time.time() - t0)}초)", flush=True)
        else:
            add("R3", "fail", f"테스트 실패 — {last}")
    # R4 — 코드가 import 하는 바깥 패키지가 requirements.txt 에 있나(새 환경에서 import 단계 실패 방지)
    std = getattr(sys, "stdlib_module_names", None)
    req = work / "requirements.txt"
    if std is None:
        add("R4", "warn", "파이썬 3.10 미만이라 표준 라이브러리 목록이 없어 건너뜀")
    else:
        names = set()
        if req.is_file():
            for line in req.read_text(encoding="utf-8", errors="replace").splitlines():
                m = re.match(r"\s*([A-Za-z0-9_.\-]+)", line.split("#")[0])
                if m:
                    names.add(m.group(1).lower().replace("_", "-"))
        # 우리 모듈 = 저장소 안 모든 .py 이름 · 최상위 폴더 이름(같은 폴더끼리 import 하는 시험 · 스크립트 포함)
        local = ({Path(f).stem for f in files if f.endswith(".py")} | {p.name for p in root.iterdir() if p.is_dir()}
                 | {p.name for p in work.iterdir() if p.is_dir()})
        miss = {}
        for f in files:
            if not f.endswith(".py") or f.startswith(SKIP_V):
                continue
            t = read(root, f) or ""
            for m in re.finditer(r"^\s*(?:from|import)\s+([A-Za-z_][\w]*)", t, re.M):
                mod = m.group(1)
                if mod in std or mod in local or mod == "__future__":
                    continue
                dist = DIST.get(mod, mod).lower().replace("_", "-")
                if dist not in names:
                    miss.setdefault(dist, f)
        if (work / "tests").is_dir() and "pytest" not in names:
            miss.setdefault("pytest", "tests/ — 새 venv 에서 테스트를 못 돌림")
        if miss:
            add("R4", "fail", "requirements.txt 에 없는 바깥 패키지 — " + " · ".join(f"{d}({f})" for d, f in list(miss.items())[:8]))
        else:
            ok("R4")
    # R5 — run.sh 문법 · 0.0.0.0 · (선택) 실제 기동
    run = work / "run.sh"
    if not run.is_file():
        add("R5", "warn", "run.sh 없음 — 실행 방법이 유저가 쓰는 실행 문서에 있나(유저에게 보고만)")
    else:
        body = "\n".join(l for l in run.read_text(encoding="utf-8", errors="replace").splitlines()
                         if l.strip() and not l.lstrip().startswith("#"))
        rc = subprocess.run(["bash", "-n", str(run)], capture_output=True).returncode
        if rc != 0:
            add("R5", "fail", "run.sh 문법 오류(bash -n)")
        elif b"\r\n" in run.read_bytes():                 # read_text 는 줄바꿈을 바꿔 읽어 못 잡는다
            add("R5", "fail", "run.sh 가 CRLF — 리눅스 bash 가 실패(.gitattributes · dos2unix)")
        elif not re.search(r"python3?|uvicorn|node|npm", body):
            add("R5", "warn", "run.sh 에 실행 줄이 없음(주석뿐)")
        elif start_port:
            check_start(work, run, start_port)
        else:
            ok("R5")
    # R8 — 배포 파일(Dockerfile · .dockerignore · 실행 문서 · 배포 계획서)
    check_deploy(root, work)
    # R6 — 마지막 커밋
    _, head = git(root, "log", "-1", "--format=%h %s")
    print(f"  R6 마지막 커밋 {head}", flush=True)


# R7 근거에서 뺄 키트 규칙 · 안내 문서 이름
RULE_DOCS = {"AGENTS.md", "CODE_RULE.md", "UI_RULE.md", "DOC_GUIDE.md", "WORK_GUIDE.md", "USER.md", "README.md"}


# R7 — 커밋 추천. 근거 = 커밋된 .py 의 import(점 경로 · 모듈 이름) 또는 커밋된 글(.md · .py · .sh)에 적힌 경로
#   찾기만 한다 — 넣을지는 Codex 가 근거를 읽고 판단해 그 파일만 git add(앱 조각은 쓸 때만 커밋하는 규칙의 빠짐 잡기)
def recommend_commits(root, work, new):
    if not new:
        return
    wrel = work.relative_to(root).as_posix() if work != root else ""
    _, tracked = git(root, "ls-files")
    texts = {}
    for f in tracked.splitlines():
        # 키트 규칙 · 안내 문서는 예시 경로를 적어 둔 것이라 근거에서 뺀다(실제 쓰임의 근거가 아님)
        if Path(f).name in RULE_DOCS:
            continue
        if f.endswith((".py", ".md", ".sh", ".txt", ".toml", ".json")) and not f.startswith(SKIP_PREFIX):
            t = read(root, f)
            if t:
                texts[f] = t
    picks = []
    for f in new:
        local = f[len(wrel) + 1:] if wrel and f.startswith(wrel + "/") else f
        why = None
        if local.endswith(".py"):
            dotted = local[:-3].replace("/", ".")
            dotted = dotted[:-9] if dotted.endswith(".__init__") else dotted
            stem = Path(local).stem
            pat = re.compile(rf"^\s*(from\s+{re.escape(dotted)}\b|import\s+{re.escape(dotted)}\b"
                             rf"|from\s+[\w.]+\s+import\s+[^\n]*\b{re.escape(stem)}\b)", re.M)
            why = next((src for src, t in texts.items() if src.endswith(".py") and pat.search(t)), None)
            if why:
                why = f"{why} 가 import"
        if not why:
            src = next((s for s, t in texts.items() if local in t or (f != local and f in t)), None)
            if src:
                why = f"{src} 에 경로"
        if why:
            picks.append(f"{f}({why})")
    if picks:
        add("R7", "warn", f"커밋 추천 {len(picks)}개 — 쓰이는데 커밋에 빠짐: {' · '.join(picks[:8])} → 맞으면 그 파일만 git add · 커밋")
    else:
        ok("R7")


# R5 — run.sh 를 실제로 띄워 포트가 200 을 주나 → 그 프로세스만 종료
def check_start(root, run, port):
    proc = subprocess.Popen(["bash", str(run)], cwd=root, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            start_new_session=True)
    try:
        t0 = time.time()
        while time.time() - t0 < 90:
            if proc.poll() is not None:
                out = proc.stdout.read().decode("utf-8", "replace").strip().splitlines()
                add("R5", "fail", f"run.sh 가 바로 끝남 — {(out or ['출력 없음'])[-1][:120]}")
                return
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=2) as r:
                    if r.status < 500:
                        ok("R5")
                        # /health 응답 코드 — 없으면 404(정보만 · 판정 안 함)
                        health = http_status(f"http://127.0.0.1:{port}/health")
                        print(f"  R5 run.sh 기동 {round(time.time() - t0, 1)}초 · 포트 {port} 응답 {r.status}"
                              f" · /health {health or '응답 없음'}", flush=True)
                        return
            except Exception:
                pass
            time.sleep(0.5)
        add("R5", "fail", f"run.sh 기동 90초 동안 포트 {port} 무응답")
    finally:
        if proc.poll() is None:
            import os
            import signal
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except (OSError, AttributeError):
                proc.terminate()


# 주소의 HTTP 상태 코드 — 접속 실패는 0
# url: 주소
def http_status(url):
    try:
        with urllib.request.urlopen(url, timeout=2) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception:
        return 0


# ======= R8. 배포 파일 — 계획서 · Dockerfile · .dockerignore · 실행 문서(How to run) 정적 점검 =======
# 배포 계획서 이름(작업 폴더 docs/ 아래)
PLAN_NAME = "DEPLOY_PLAN.md"
# 실행 문서 이름 모양 — 과제 양식마다 이름이 달라 넓게 본다
HOWTO_RE = re.compile(r"(?i)how[\s_-]*to[\s_-]*run|실행[\s_-]*방법")
# 빌드 맥락에서 꼭 빠져야 하는 것 — (작업 폴더 기준 시험 경로, 이름)
MUST_IGNORE = ((".env", ".env 비밀값"), (".venv/pyvenv.cfg", "가상환경 .venv"))
# 빌드 맥락에 꼭 남아야 하는 것 — 빠지면 컨테이너가 설치 · 시작을 못 한다
MUST_KEEP = ("run.sh", "requirements.txt")


# 계획서의 굵은 칸 값 첫 낱말 — «- **포트**: 3000 · 0.0.0.0» → «3000» · 칸이 없으면 None
# plan: 계획서 경로 · key: 칸 이름
def plan_value(plan, key):
    if not plan.is_file():
        return None
    m = re.search(rf"\*\*{re.escape(key)}\*\*\s*[:：]\s*([^\s·(←]+)", plan.read_text(encoding="utf-8", errors="replace"))
    return m.group(1) if m else None


# .dockerignore 한 줄 → (정규식, 다시 넣기 여부) — docker 규칙: 앞뒤 / 를 떼고 * 는 한 칸 · ** 는 여러 칸
# line: 주석 · 빈 줄이 아닌 한 줄
def ignore_rule(line):
    neg = line.startswith("!")
    pat = (line[1:] if neg else line).strip()
    pat = re.sub(r"^(\./)+", "", pat).strip("/")
    rx, i = "", 0
    while i < len(pat):
        if pat.startswith("**/", i):
            rx, i = rx + "(?:.*/)?", i + 3
        elif pat.startswith("**", i):
            rx, i = rx + ".*", i + 2
        elif pat[i] == "*":
            rx, i = rx + "[^/]*", i + 1
        elif pat[i] == "?":
            rx, i = rx + "[^/]", i + 1
        else:
            rx, i = rx + re.escape(pat[i]), i + 1
    return re.compile(rx), neg


# .dockerignore 파일 → 규칙 목록
# path: .dockerignore 경로
def ignore_rules(path):
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return [ignore_rule(l.strip()) for l in lines if l.strip() and not l.lstrip().startswith("#")]


# 빌드 맥락에서 빠지나 — 경로나 그 위 폴더에 맞는 규칙 중 마지막 것이 이긴다(! = 다시 넣기)
# rules: ignore_rules 결과 · path: 맥락 기준 상대 경로(posix)
def docker_ignored(rules, path):
    parts = path.split("/")
    heads = ["/".join(parts[:i]) for i in range(1, len(parts) + 1)]
    hit = False
    for rx, neg in rules:
        if any(rx.fullmatch(h) for h in heads):
            hit = not neg
    return hit


# 실행 문서(How to run) 찾기 — 루트 · 작업 폴더 · 그 docs/ 바로 아래(예시 폴더 제외)
# root: 저장소 루트 · work: 작업 폴더
def find_howto(root, work):
    for d in dict.fromkeys((root, work, root / "docs", work / "docs")):
        if d.is_dir():
            for p in sorted(d.iterdir()):
                if p.is_file() and HOWTO_RE.search(p.name):
                    return p
    return None


def check_deploy(root, work):
    fails, warns = [], []
    plan = work / "docs" / PLAN_NAME
    # Dockerfile — 루트 먼저(채점이 저장소 루트에서 build 할 가능성) · 없으면 작업 폴더
    dfile = next((d / n for d in dict.fromkeys((root, work)) for n in ("Dockerfile", "Containerfile")
                  if (d / n).is_file()), None)
    if dfile is None:
        if plan_value(plan, "컨테이너 요구") == "필요":
            fails.append(f"docs/{PLAN_NAME} 1절은 컨테이너 요구인데 Dockerfile 없음 → lib/deploy 양식을 <루트> 에 복사해 맞춘다")
    else:
        rel = dfile.relative_to(root).as_posix()
        # 논리 줄 — 줄 끝 \ 로 이어진 줄을 하나로(HEALTHCHECK 다음 줄 «CMD …» 를 시작 명령으로 오인하지 않게)
        body = re.sub(r"\\[ \t]*\r?\n", " ", dfile.read_text(encoding="utf-8", errors="replace"))
        lines = [l.strip() for l in body.splitlines() if l.strip() and not l.lstrip().startswith("#")]
        # 포트 — EXPOSE · ENV PORT · 계획서 «포트» 가 같아야 How to run · 채점 명령이 같은 포트를 본다
        expose = set(re.findall(r"\d+", " ".join(l[6:] for l in lines if l.upper().startswith("EXPOSE"))))
        envs = " ".join(l[3:] for l in lines if l.upper().startswith("ENV "))
        env_port = re.search(r"(?:^|\s)PORT[=\s]+[\"']?(\d+)", envs)
        plan_port = plan_value(plan, "포트")
        if not expose:
            warns.append(f"{rel} 에 EXPOSE 없음 — 앱 포트를 적어 둔다")
        elif env_port and env_port.group(1) not in expose:
            fails.append(f"{rel} ENV PORT={env_port.group(1)} 와 EXPOSE {' '.join(sorted(expose))} 가 다름")
        if expose and plan_port and plan_port.isdigit() and plan_port not in expose:
            fails.append(f"{rel} EXPOSE {' '.join(sorted(expose))} 와 계획서 포트 {plan_port} 가 다름")
        # 시작 명령 — 없으면 안 켜짐 · run.sh 가 아니면 로컬과 다른 명령으로 뜬다
        start = [l for l in lines if re.match(r"(?i)(CMD|ENTRYPOINT)\b", l)]
        if not start:
            fails.append(f"{rel} 에 CMD · ENTRYPOINT 없음 — 컨테이너가 켜지지 않는다")
        elif (work / "run.sh").is_file() and "run.sh" not in start[-1]:
            warns.append(f"{rel} 시작 명령이 run.sh 가 아님 — 로컬과 같은 명령으로 맞추거나 How to run 에 둘 다")
        if re.search(r"127\.0\.0\.1|localhost", " ".join(start) + " " + envs):
            fails.append(f"{rel} 시작 명령 · ENV 에 127.0.0.1 · localhost — 컨테이너 밖에서 안 보인다(0.0.0.0)")
        # .dockerignore — Dockerfile 폴더(= 빌드 맥락) 기준
        ign = dfile.parent / ".dockerignore"
        if not ign.is_file():
            fails.append(f"{rel} 옆에 .dockerignore 없음 — .env · .venv · 플랫폼 키 파일이 빌드 맥락에 들어간다 → lib/deploy/.dockerignore")
        else:
            rules = ignore_rules(ign)
            ctx = dfile.parent
            pre = work.relative_to(ctx).as_posix() + "/" if work != ctx and ctx in work.parents else ""
            must = [(pre + p, name) for p, name in MUST_IGNORE]
            if ctx == root:
                must.append((".literacy/provider-env.sh", "플랫폼 키 파일 .literacy"))
            leak = [name for p, name in must if not docker_ignored(rules, p)]
            if leak:
                fails.append(f"{ign.relative_to(root).as_posix()} 가 {' · '.join(leak)} 를 빼지 않음 — 이미지에 들어간다")
            lost = [n for n in MUST_KEEP if (work / n).is_file() and docker_ignored(rules, pre + n)]
            if lost:
                fails.append(f"{ign.relative_to(root).as_posix()} 가 {' · '.join(lost)} 까지 뺌 — 컨테이너가 설치 · 시작을 못 한다")
    # 실행 문서 — 있나 · 로컬 한 줄(run.sh) · 컨테이너 줄(docker)을 적었나
    howto = find_howto(root, work)
    if howto is None:
        warns.append("실행 문서(How to run) 못 찾음 — 유저가 쓰는 문서라 유저에게 보고만(이름이 다른 양식이면 무시)")
    else:
        t = (read(root, howto.relative_to(root).as_posix()) or "").lower()
        lack = [what for what, need, word in (("run.sh 실행 줄", (work / "run.sh").is_file(), "run.sh"),
                                              ("docker build · run 줄", dfile is not None, "docker"))
                if need and word not in t]
        if lack:
            warns.append(f"{howto.relative_to(root).as_posix()} 에 {' · '.join(lack)} 없음")
    for f in fails:
        add("R8", "fail", f)
    for w in warns:
        add("R8", "warn", w)
    if not fails and not warns:
        ok("R8")


# ======= D. 문서 — doc_check.py(같은 폴더) =======
def check_docs(root):
    tool = HERE / "doc_check.py"
    if not tool.is_file():
        add("D", "warn", "doc_check.py 없음")
        return
    work = WORK or root
    p = subprocess.run([sys.executable, str(tool), "--root", str(work)], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    last = (p.stdout.strip().splitlines() or ["출력 없음"])[-1]
    if p.returncode == 0:
        ok("D")
    else:
        add("D", "fail", f"문서 점검 {last} — 자세히: python3 {tool} --root {work}")


# ======= 서술형 카드 재료 — Codex 가 이걸 보고 «외우기 카드» 를 만든다 =======
def card(root):
    print("\n----- 서술형 카드 재료 -----", flush=True)
    _, log = git(root, "log", "--format=%h %s", "-40")
    fixes = [l for l in log.splitlines() if re.search(r"수정|재현|fix|원인", l, re.I)]
    print("[최근 커밋 40개 중 재현 · 수정 커밋 — 2번형(AI 제안 확인 · 수정) 후보]")
    print("\n".join(fixes[:10]) or "  없음")
    print("[최근 커밋 10개 — 1번형(핵심 동작) · 3번형(설계 결정) 후보]")
    print("\n".join(log.splitlines()[:10]))
    for doc in ("docs/WORKLOG.md", "docs/hand_off.md"):
        p = (WORK or root) / doc
        if p.is_file():
            t = p.read_text(encoding="utf-8", errors="replace")
            m = re.search(r"#+\s*[^\n]*서술형 재료[^\n]*\n(.*?)(?=\n#+\s|\Z)", t, re.S)
            if m:
                print(f"[{doc} «서술형 재료» 칸]\n{m.group(1).strip()[:1500]}")


def main(argv=None):
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description="제출 직전 최종 점검(찾기만 함)")
    ap.add_argument("--root", default=".", help="과제 저장소(기본: 지금 폴더의 git 최상위)")
    ap.add_argument("--no-test", action="store_true", help="R3 전체 테스트를 건너뜀")
    ap.add_argument("--start-port", type=int, default=0, help="R5 에서 run.sh 를 실제로 띄워 이 포트 응답을 봄")
    ap.add_argument("--card", action="store_true", help="끝에 서술형 카드 재료를 출력")
    ap.add_argument("--all", action="store_true", help="키트 · 스킬 · 도구 경로도 점검(기본은 뺌)")
    ap.add_argument("--work", default=None, help="작업 폴더(기본: 지금 폴더가 루트 아래면 그곳 · 루트에 kit/ 가 있으면 kit)")
    a = ap.parse_args(argv)
    rc, top = git(Path(a.root).resolve(), "rev-parse", "--show-toplevel")
    if rc != 0:
        print(f"git 저장소가 아님: {Path(a.root).resolve()}")
        return 2
    root = Path(top)
    # 작업 폴더 — --work → 지금 폴더가 루트 아래 하위 폴더면 그곳 → 루트에 kit/AGENTS.md 가 있으면 kit(키트 = 작업 폴더) → 루트
    global WORK, SKIP_PREFIX, PLATFORM
    here = Path(a.work or ".").resolve()
    if a.work or (here != root and root in here.parents):
        WORK = here
    elif (root / "kit" / "AGENTS.md").is_file():
        WORK = root / "kit"
    else:
        WORK = root
    wrel = WORK.relative_to(root).as_posix() if WORK != root else ""
    if wrel:
        # 작업 폴더 안의 도구만 빼고 작업 폴더는 점검한다(kit/ 통째 빼기 · 플랫폼 취급을 풂)
        SKIP_PREFIX = TOOLS + tuple(f"{wrel}/{t}" for t in TOOLS)
        PLATFORM = re.compile(rf"^({PLATFORM_DIRS})/" + PLATFORM_FILES)
    files, untracked, every = submit_files(root, a.all)
    print(f"ready-end · {root} · 작업 폴더 {wrel or '(루트)'} · 제출 대상 파일 {len(files)}개"
          f"(도구 · 스킬 경로 제외{' 안 함' if a.all else ''})", flush=True)
    check_security(root, files, untracked, every)
    check_vulns(root, files)
    check_ready(root, files, untracked, not a.no_test, a.start_port)
    check_docs(root)
    fails = [r for r in RESULTS if r[1] == "fail"]
    print(f"\n통과 {len(PASSED)} · 실패 {len(fails)} · 확인 필요 {sum(1 for r in RESULTS if r[1] == 'warn')}", flush=True)
    for no, state, reason in RESULTS:
        print(f"{'✗' if state == 'fail' else '△'} {no} {reason}", flush=True)
    print("요약: " + (" ".join(dict.fromkeys(r[0] for r in fails)) or "실패 없음"), flush=True)
    if a.card:
        card(root)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
