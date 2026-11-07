"""devview 그래프 보기(flowtree /ft/) 시험 — 임시 작업 폴더 + 시험 서버(빈 포트) + 헤드리스 크롬

    py -3 tests/test_flowtree.py              결과 PASS/FAIL · 캡처 tests/shots/ft_*.png
    CC_HEADED=1 py -3 tests/test_flowtree.py  창을 띄워 눈으로 보기

시험 재료: 이 파일 안에서 만드는 작은 가상 앱(app/src · 모듈 5개)과 가상 그래프(docs/flowtree/tree.json)를
임시 작업 폴더에 쓰고 노드에 연결 문서(doc · 파일 노드 path)를 붙인다. 실제 작업 폴더 · 8701 · 8786/8787 무관
단언 대상은 관측 결과: 보이는 보기 · 열린 파일 경로 · 편집기 줄 · 화면 글자 · HTTP 상태
"""
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

# 시험 폴더 · devview 폴더
HERE = Path(__file__).resolve().parent
DEVVIEW = HERE.parent / "devview.py"
# flowtree 폴더 — devview 와 같은 순서로 찾음(키트 devview/flowtree → 로컬 형제 ../flowtree)
FLOWTREE = next(d for d in (HERE.parent / "flowtree", HERE.parent.parent / "flowtree") if (d / "server.py").is_file())
# 캡처 폴더
SHOTS = HERE / "shots"
# 창 띄우기 여부 — 기본 헤드리스
HEADED = os.environ.get("CC_HEADED") == "1"
# 결과 목록
RESULTS = []

# 시험용 hand_off 문서 — 절 번호 제목(키트 docs/hand_off.md 와 같은 «## 1-2 · 이름 — 위험도» 모양) · 1-20 은 1-2 와 다른 절
HAND_OFF = "# hand_off — 시험\n\n## 📋 진행 기록\n\n" + "\n".join(f"줄 {i}" for i in range(30)) + \
      "\n\n## 1-1 · 첫 절 — 저위험\n\n내용\n\n## 1-20 · 스무째 — 민감\n\n내용\n\n## 1-2 · 동시 적용 — 민감\n\n판 번호로 막는다\n"
# 시험용 메모 — 옵시디언 블록 id
NOTES = "# 메모\n\n" + "\n".join(f"줄 {i}" for i in range(20)) + "\n\n기준값은 45 다 ^blk-cap\n\n끝\n"

# 시험용 가상 앱 — 모듈 5개(진입점 · 화면 · 처리 · 규칙 · 저장소). 파일 경로 → 소스
APP_FILES = {
    "src/main.py": "# 진입점 — 화면 모듈을 불러와 시작\nfrom src.ui import screen\n\n\n# 시작\ndef main():\n    screen.screen_page()\n",
    "src/ui/screen.py": "# 화면 — 버튼 하나가 처리 함수 하나를 부름\nfrom src.service import flow\n\n\n"
                        "# 화면 진입점\ndef screen_page():\n    return flow.run_check(\"data\")\n",
    "src/service/flow.py": "# 처리 — 파일 읽기 → 규칙 검사 → 결과\nfrom pathlib import Path\n\nfrom src.core import rules\nfrom src.db.store import Store\n\n\n"
                           "# 점검 결과 — 문제 목록 · 판 번호\nclass Report:\n    # 문제 목록\n    issues = []\n\n\n"
                           "# 폴더 → {파일 이름: 줄 목록}\n# data_dir: 폴더\ndef read_tables(data_dir):\n    tables = {}\n"
                           "    for path in sorted(Path(data_dir).glob(\"*.csv\")):\n        tables[path.stem] = path.read_text(encoding=\"utf-8\").splitlines()\n"
                           "    return tables\n\n\n"
                           "# 점검 버튼. 문제 목록 · 판 번호 반환\n# data_dir: 폴더\ndef run_check(data_dir):\n    tables = read_tables(data_dir)\n"
                           "    rep = Report()\n    rep.issues = rules.check_all(tables)\n    rep.version = Store().data_version()\n    return rep\n",
    "src/core/rules.py": "# 규칙 — 순수 계산. 표 묶음 → 문제 목록\n\n\n# 모든 표의 빈 줄을 모음\n# tables: {파일 이름: 줄 목록}\n"
                         "def check_all(tables):\n    return [(name, i) for name, rows in tables.items() for i, row in enumerate(rows) if not row.strip()]\n",
    "src/db/store.py": "# 저장소 — 판 번호 보관\n\n\n# 저장소\nclass Store:\n    # 지금 판 번호\n    def data_version(self):\n        return 1\n",
}
# 가상 그래프의 코드 설정 — 층 5개
CODE_CFG = {"root": "../../app", "layers": [{"prefix": "src.main", "layer": "app"}, {"prefix": "src.ui", "layer": "ui"},
                                              {"prefix": "src.service", "layer": "service"}, {"prefix": "src.core", "layer": "core"},
                                              {"prefix": "src.db", "layer": "db"}],
            "layer_order": ["app", "ui", "service", "core", "db"],
            "layer_names": {"app": "진입점", "ui": "화면", "service": "처리", "core": "규칙", "db": "저장소"}}


# 빈 포트 하나(키트 tests 에는 fixture.py 가 없어 이 파일 안에 둠)
def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# 결과 한 줄
# name: 항목 / ok: 통과 / detail: 덧붙임
def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'PASS' if ok else 'FAIL'} | {name}{' | ' + str(detail)[:240] if detail else ''}", flush=True)


# 조건이 참이 될 때까지 기다림(상한은 멈춤 방지용)
# fn: 조건 함수 / timeout: 상한 초
def wait_for(fn, timeout=10.0, step=0.15):
    # 끝 시각
    end = time.time() + timeout
    while time.time() < end:
        try:
            if fn():
                return True
        except Exception:  # noqa: BLE001
            pass
        time.sleep(step)
    return False


# 시험 작업 폴더 만들기 — 반환 (폴더, hand_off 1-2 줄, 메모 ^bus-cap 줄)
# base: 임시 폴더
def make_project(base):
    # 작업 폴더
    root = Path(base) / "proj"
    for rel, src in APP_FILES.items():
        (root / "app" / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / "app" / rel).write_text(src, encoding="utf-8")
    (root / "docs" / "flowtree").mkdir(parents=True)
    (root / "docs" / "hand_off.md").write_text(HAND_OFF, encoding="utf-8")
    (root / "docs" / "notes.md").write_text(NOTES, encoding="utf-8")
    (root / "data").mkdir()
    (root / "data" / "sample.csv").write_text("번호,이름\n1,가\n", encoding="utf-8")
    (root / "data" / "extra.csv").write_text("번호\n1\n", encoding="utf-8")
    (root / "data" / "_origin_md5.txt").write_text("지문\n", encoding="utf-8")
    (root / "data" / ".hidden").write_text("숨김\n", encoding="utf-8")
    # 트리 — 코드 루트를 작업 폴더/app 으로 · 노드에 연결 문서
    nodes = [
        {"id": "root", "kind": "root", "title": "가상 앱", "summary": "시험용 그래프"},
        {"id": "g-files", "kind": "group", "parent": "root", "section": "files", "title": "파일"},
        {"id": "f-data", "kind": "file", "parent": "g-files", "title": "sample.csv", "path": "data/sample.csv"},
        {"id": "g-req", "kind": "group", "parent": "root", "section": "req", "title": "요구"},
        {"id": "r-check", "kind": "req", "parent": "g-req", "title": "점검 버튼", "summary": "표의 빈 줄을 목록으로 보여 줌",
         "doc": {"path": "docs/notes.md", "anchor": "^blk-cap"}},
        {"id": "r-doc", "kind": "req", "parent": "g-req", "title": "문서 연결", "summary": "절 번호 앵커",
         "doc": {"path": "docs/hand_off.md", "anchor": "1-2"}},
        {"id": "r-apply", "kind": "req", "parent": "g-req", "title": "반영 버튼", "summary": "점검 통과분을 저장"},
        {"id": "g-mod", "kind": "group", "parent": "root", "section": "modules", "title": "모듈"},
        {"id": "m-main", "kind": "module", "parent": "g-mod", "title": "진입점", "code": "src.main", "layer": "app"},
        {"id": "m-screen", "kind": "module", "parent": "g-mod", "title": "화면 모듈", "code": "src.ui.screen", "layer": "ui"},
        {"id": "m-flow", "kind": "module", "parent": "g-mod", "title": "처리 모듈", "code": "src.service.flow", "layer": "service",
         "summary": "파일 읽기 → 검사 → 결과"},
        {"id": "m-rules", "kind": "module", "parent": "g-mod", "title": "문제 규칙", "code": "src.core.rules", "layer": "core"},
        {"id": "m-store", "kind": "module", "parent": "g-mod", "title": "저장소", "code": "src.db.store", "layer": "db"},
    ]
    # 노드 수를 늘리는 채움 항목 — 화면에 노드가 20개를 넘는지 보는 시험용
    nodes += [{"id": f"r-fill{i}", "kind": "req", "parent": "g-req", "title": f"항목 {i}"} for i in range(1, 13)]
    edges = [{"source": s, "target": t, "kind": "implements"} for s, t in
             (("r-check", "m-flow"), ("r-apply", "m-flow"), ("r-check", "m-rules"), ("r-apply", "m-store"))]
    tree = {"version": 2, "title": "가상 앱 — 시험 그래프", "code": CODE_CFG, "nodes": nodes, "edges": edges, "rev": 1}
    (root / "docs" / "flowtree" / "tree.json").write_text(json.dumps(tree, ensure_ascii=False, indent=1), encoding="utf-8")
    (root / "docs" / "flowtree" / "tree.user.json").write_text(json.dumps(
        {"version": 1, "picks": {}, "verify": {}, "edges": [], "nodes": [], "positions": {}, "collapsed": [], "questions": []}),
        encoding="utf-8")
    # 기대 줄 번호
    adr_line = HAND_OFF.splitlines().index("## 1-2 · 동시 적용 — 민감") + 1
    note_line = NOTES.splitlines().index("기준값은 45 다 ^blk-cap") + 1
    return root, adr_line, note_line


# devview 시험 서버 띄우기 — (프로세스, 주소)
# root: 작업 폴더
def start(root):
    # 포트
    port = free_port()
    proc = subprocess.Popen(
        [sys.executable, str(DEVVIEW), str(root), "--host", "127.0.0.1", "--port", str(port)],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        env=dict(os.environ, DEVVIEW_NO_VAULT="1"))
    # 주소
    base = f"http://127.0.0.1:{port}"
    for _ in range(100):
        if proc.poll() is not None:
            raise RuntimeError("서버 기동 실패: " + proc.stdout.read().decode("utf-8", "replace"))
        try:
            urllib.request.urlopen(base + "/api/info", timeout=1).read()
            return proc, base
        except OSError:
            time.sleep(0.1)
    proc.kill()
    raise RuntimeError("서버 응답 없음")


# HTTP 요청 → (상태, 본문 바이트)
# url: 주소 / data: POST 본문(없으면 GET) / headers: 머리글
def http(url, data=None, headers=None):
    # 요청
    req = urllib.request.Request(url, data=data, headers=headers or {}, method="POST" if data is not None else "GET")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


# API 시험 — /ft/ 화면 · 정적 파일 · 데이터 · 연결 문서 풀이 · 쓰기 보호 · info
# base: 서버 주소 / adr_line · note_line: 기대 줄
def test_api(base, adr_line, note_line):
    code, body = http(base + "/ft/")
    check("/ft/ 화면 html", code == 200 and b"flowtree.js" in body, code)
    code, body = http(base + "/ft/static/flowtree.js")
    check("/ft/static/flowtree.js", code == 200 and len(body) > 100000, (code, len(body)))
    check("키트판 화면에 «온톨로지» 없음(로컬 시험 기능 · 화면 연결 해제)", "온톨로지".encode("utf-8") not in body
          and b"\x5cuC628\x5cuD1A8" not in body)
    code, body = http(base + "/ft/api/data")
    d = json.loads(body)
    check("/ft/api/data 트리 · 스캔", code == 200 and d["tree"]["title"].startswith("가상 앱") and len(d["auto"]["modules"]) == 5,
          (code, d.get("tree", {}).get("title"), len(d.get("auto", {}).get("modules", []))))
    check("meta.code_rel = app", d["meta"]["code_rel"] == "app", d["meta"].get("code_rel"))
    docs = d["meta"]["docs"]
    check("hand_off 절 번호 1-2 → 줄(1-20 과 안 섞임)", docs["r-doc"]["line"] == adr_line, (docs["r-doc"], adr_line))
    check("블록 id ^blk-cap → 줄", docs["r-check"]["line"] == note_line, (docs["r-check"], note_line))
    check("파일 노드 path", docs["f-data"]["path"] == "data/sample.csv" and not docs["f-data"]["error"], docs["f-data"])
    check("연결 문서 오류 없음(점검)", not any(p["code"].startswith("doc-") for p in d["check"]),
          [p for p in d["check"] if p["code"].startswith("doc-")])
    code, _ = http(base + "/ft/api/scan", data=b"")
    check("POST /ft/ X-Devview 없으면 403", code == 403, code)
    code, _ = http(base + "/ft/api/scan", data=b"", headers={"X-Devview": "1"})
    check("POST /ft/api/scan X-Devview 있으면 200", code == 200, code)
    info = json.loads(http(base + "/api/info")[1])
    check("info.flowtree 연결 · tree 있음", info["flowtree"]["ok"] and info["flowtree"]["exists"], info["flowtree"])
    code, body = http(base + "/api/codex/sessions?limit=2")
    check("GET /api/codex/sessions 응답", code == 200 and "sessions" in json.loads(body), code)


# 그래프 iframe 프레임 객체
# page: 페이지
def ft_frame(page):
    return page.frame_locator("#ftView iframe")


# 지금 보기 이름
# page: 페이지
def cur_view(page):
    return page.evaluate("window.devview.view()")


# 그래프에서 노드 고르기 — 가운데로 옮긴 뒤 클릭(선택 + 그래프 문서에 포커스)
# page: 페이지 / nid: 노드 id
def pick(page, nid):
    # 그래프 프레임(실제 frame)
    fr = page.frame(url=lambda u: "/ft/" in u)
    fr.evaluate(f"window.__flowtree.center({json.dumps(nid)}, 1.2)")
    time.sleep(0.4)
    fr.locator(f'.react-flow__node[data-id="{nid}"]').click(position={"x": 30, "y": 12})
    time.sleep(0.2)
    return fr


# 화면 시험 — 첫 화면 · Alt+Q(MAIN 마법봉) · ` 파일 열기 · 앵커 줄 · 닫기 · 모듈 설명
# base: 서버 주소 / adr_line · note_line: 기대 줄
def test_ui(base, adr_line, note_line):
    with sync_playwright() as pw:
        try:
            br = pw.chromium.launch(headless=not HEADED)
        except Exception:  # noqa: BLE001
            br = pw.chromium.launch(channel="chrome", headless=not HEADED)
        page = br.new_page(viewport={"width": 1600, "height": 960})
        errs = []
        page.on("pageerror", lambda e: errs.append(str(e)))
        page.goto(base + "/")
        page.wait_for_selector("html[data-ready='1']", timeout=30000)
        check("첫 화면 = 그래프", cur_view(page) == "graph" and page.is_visible("#ftView") and not page.is_visible("#codeView"),
              cur_view(page))
        fr = None
        ok = wait_for(lambda: page.frame(url=lambda u: "/ft/" in u) and page.frame(url=lambda u: "/ft/" in u)
                      .locator(".react-flow__node").count() > 20, 20)
        fr = page.frame(url=lambda u: "/ft/" in u)
        check("그래프 iframe 에 노드 그려짐", ok, fr.locator(".react-flow__node").count() if fr else None)
        time.sleep(0.6)
        SHOTS.mkdir(exist_ok=True)
        page.screenshot(path=str(SHOTS / "ft_graph_first.png"))
        head = fr.locator("header.top").inner_text()
        check("화면 하나 — 화면 탭 · 화면 전환 · 온톨로지 단추 없음", fr.locator("header.top .tabs").count() == 0
              and "화면 전환" not in head and "온톨로지" not in head, head)
        check("노드 추가 단추 4개(work · insp · question · suggest)",
              [b.get_attribute("title") for b in fr.locator(".addbar button").all()] == ["work", "insp", "question", "suggest"])

        # Alt+Q = 고른 노드로 MAIN 마법봉 — 나가는 요청만 잡는다(실제 codex 안 부름)
        magic = []

        # 마법봉 요청 받기
        def on_magic(route):
            magic.append(route.request.post_data_json)
            route.fulfill(status=200, content_type="application/json", body='{"msg": "보냄"}')

        page.route("**/api/hub/magic", on_magic)
        # sync 판은 evaluate 때 경로 처리기가 돈다
        sent = lambda n: wait_for(lambda: page.evaluate("1") and len(magic) == n, 3)  # noqa: E731
        wait_for(lambda: page.locator("#hub .dv-hub-row").count() > 0, 5)
        fr.locator(".react-flow__pane").click(position={"x": 40, "y": 40})
        check("포커스가 그래프 iframe 안", page.evaluate("document.activeElement.tagName") == "IFRAME")
        page.keyboard.press("Alt+q")
        check("고른 노드 없이 Alt+Q → 알림 · 요청 안 나감 · 보기 그대로", wait_for(lambda: "노드를 고르지 않음" in page.inner_text("#toasts"), 3)
              and not magic and cur_view(page) == "graph", (magic, cur_view(page)))
        fr = pick(page, "f-data")
        wait_for(lambda: page.evaluate("window.devview.flowSelection().nodes.length") == 1, 3)
        page.keyboard.press("Alt+q")
        check("iframe 안 Alt+Q → 고른 노드로 MAIN 마법봉 요청", sent(1) and magic[0]["nick"] == "main"
              and [n["id"] for n in magic[0]["selection"]["nodes"]] == ["f-data"], magic)
        check("iframe 안 Alt+Q → 보기 그대로", cur_view(page) == "graph", cur_view(page))
        # 편집기 안 포커스에서도
        page.evaluate("window.devview.showView('code')")
        page.evaluate("window.devview.openFile('app/src/main.py')")
        wait_for(lambda: page.evaluate("window.devview.activePath()") == "app/src/main.py", 5)
        page.evaluate("window.devview.editor().focus()")
        main_py0 = page.evaluate("window.devview.editor().getValue()")
        page.keyboard.press("Alt+q")
        # 유저 결정(11/05): Alt+Q 는 그래프 보기에서만 고른 노드를 보낸다 — 다른 보기에서는 마지막 그래프 선택을 보내지 않고 알림만
        time.sleep(1)
        check("편집기 안 Alt+Q → 마법봉 요청 안 감 · 보기 그대로(그래프 보기에서만)", len(magic) == 1 and cur_view(page) == "code", (magic[1:], cur_view(page)))
        check("Alt+Q 가 편집기에 글자를 넣지 않음", page.evaluate("window.devview.editor().getValue()") == main_py0)
        page.unroute("**/api/hub/magic")
        page.evaluate("window.devview.showView('graph')")
        wait_for(lambda: cur_view(page) == "graph", 3)

        # 파일 노드 → ` → 오른쪽 절반에 파일
        fr = pick(page, "f-data")
        page.keyboard.press("Backquote")
        ok = wait_for(lambda: page.evaluate("window.devview.activePath()") == "data/sample.csv", 5)
        check("파일 노드 ` → 오른쪽에 파일 열림", ok and page.evaluate("document.querySelector('.dv-main').classList.contains('is-ftsplit')"),
              page.evaluate("window.devview.activePath()"))
        # 배치 — 그래프 왼쪽 절반 · 코드 보기 오른쪽 절반 · 파일 트리 숨김
        r_ft = page.locator("#ftView").bounding_box()
        r_cv = page.locator("#codeView").bounding_box()
        check("그래프 왼쪽 절반 · 문서 오른쪽 절반", abs(r_ft["width"] - 800) < 4 and abs(r_cv["x"] - 800) < 4 and r_cv["width"] > 780,
              (r_ft, r_cv))
        check("파일 트리 숨김", not page.is_visible("#tree"))
        check("flowtree 패널 숨김(파일 열린 동안)", fr.locator("aside.panel").count() == 0)
        check("포커스는 그래프로 돌아옴", wait_for(lambda: page.evaluate("document.activeElement.tagName") == "IFRAME", 2))
        page.keyboard.press("Backquote")
        ok = wait_for(lambda: not page.evaluate("document.querySelector('.dv-main').classList.contains('is-ftsplit')"), 3)
        check("` 다시 → 닫힘 · 원래 패널", ok and wait_for(lambda: fr.locator("aside.panel").count() == 1, 3) and not page.is_visible("#codeView"))

        # hand_off 문서 노드 → ` → 1-2 절 줄로 · Esc 로 닫기
        fr = pick(page, "r-doc")
        page.keyboard.press("Backquote")
        ok = wait_for(lambda: page.evaluate("window.devview.activePath()") == "docs/hand_off.md", 5)
        time.sleep(0.8)
        # 1-2 제목 줄이 오른쪽 칸 안에 보이는지(md 편집기)
        vis = page.evaluate("""() => {
          const host = document.querySelector('#codeView');
          const hr = host.getBoundingClientRect();
          const line = [...document.querySelectorAll('#codeView .cm-line')].find((x) => x.textContent.includes('1-2 · 동시 적용'));
          if (!line) return null;
          const r = line.getBoundingClientRect();
          return r.top >= hr.top && r.bottom <= hr.bottom && r.height > 0;
        }""")
        check("hand_off 앵커 1-2 → 그 절 제목이 보임", ok and vis, (page.evaluate("window.devview.activePath()"), vis))
        check("머리 막대에 경로:줄", f"docs/hand_off.md:{adr_line}" in page.inner_text("#ftBarPath"), page.inner_text("#ftBarPath"))
        page.screenshot(path=str(SHOTS / "ft_file_open.png"))
        page.keyboard.press("Escape")
        check("Esc → 닫힘", wait_for(lambda: not page.evaluate("document.querySelector('.dv-main').classList.contains('is-ftsplit')"), 3))

        # 블록 id 노드 → ` → × 로 닫기
        fr = pick(page, "r-check")
        page.keyboard.press("Backquote")
        ok = wait_for(lambda: page.evaluate("window.devview.activePath()") == "docs/notes.md", 5)
        time.sleep(0.6)
        vis = page.evaluate("""() => {
          const hr = document.querySelector('#codeView').getBoundingClientRect();
          const line = [...document.querySelectorAll('#codeView .cm-line')].find((x) => x.textContent.includes('기준값은 45'));
          if (!line) return null;
          const r = line.getBoundingClientRect();
          return r.top >= hr.top && r.bottom <= hr.bottom && r.height > 0;
        }""")
        check("블록 id ^blk-cap → 그 줄이 보임", ok and vis, vis)
        page.click("#ftClose")
        check("× → 닫힘 · flowtree 패널 되살아남", wait_for(lambda: not page.evaluate(
            "document.querySelector('.dv-main').classList.contains('is-ftsplit')"), 3) and wait_for(lambda: fr.locator("aside.panel").count() == 1, 3))

        # 모듈 노드 → ` → 모듈 설명
        fr = pick(page, "m-flow")
        page.keyboard.press("Backquote")
        ok = wait_for(lambda: fr.locator(".mdoc").count() == 1, 3)
        md = fr.locator(".mdoc").inner_text() if ok else ""
        # 기대 값 — 가상 앱 소스에서 셈
        flow_src = APP_FILES["src/service/flow.py"].splitlines()
        run_line = flow_src.index("def run_check(data_dir):") + 1
        check("모듈 노드 ` → 모듈 설명", ok and "처리 모듈" in md and f"app/src/service/flow.py · {len(flow_src)}줄" in md, md[:120])
        check("연관 기능 ★ 점검 버튼 · ★ 반영 버튼", "★ 점검 버튼" in md and "★ 반영 버튼" in md)
        box = fr.locator(".mdc-box", has_text="run_check(data_dir)")
        bt = box.inner_text() if box.count() else ""
        check("함수 상자 — 이름 · 행 · 바로 위 주석", f"{run_line}행" in bt and "점검 버튼. 문제 목록" in bt, bt[:160])
        check("부르는 것 · 부르는 곳", "check_all" in bt and "Store.data_version" in bt and "read_tables" in bt and "screen_page" in bt, bt)
        check("class Report 상자", fr.locator(".mdc-box", has_text="class Report").count() == 1)
        r_md = fr.locator(".mdoc").bounding_box()
        check("모듈 설명 = 오른쪽 절반", r_md and abs(r_md["x"] - 800) < 6, r_md)
        page.screenshot(path=str(SHOTS / "ft_module_doc.png"))
        # 같은 모듈 이름 → 그 상자로(깜빡임 표시)
        box.locator("button.mdc-call", has_text="read_tables").click()
        check("같은 모듈 이름 → 그 상자로", wait_for(lambda: fr.locator(".mdc-box.mdc-flash", has_text="read_tables(data_dir)").count() == 1, 2))
        # 다른 모듈 이름 → 그 모듈 설명으로
        fr.locator(".mdc-box", has_text="run_check(data_dir)").locator("button.mdc-call", has_text="check_all").click()
        check("다른 모듈 이름 → 그 모듈 설명", wait_for(lambda: "문제 규칙" in fr.locator(".mdc-head").inner_text(), 3),
              fr.locator(".mdc-head").inner_text())
        # 함수 이름 → devview 에 그 파일 그 줄
        fr.locator(".mdc-fn", has_text="check_all").first.click()
        ok = wait_for(lambda: page.evaluate("window.devview.activePath()") == "app/src/core/rules.py", 5)
        time.sleep(0.4)
        # 기대 줄(스캔 결과)
        d = json.loads(http(base + "/ft/api/data")[1])
        want = next(x["line"] for m in d["auto"]["modules"] if m["name"] == "src.core.rules" for x in m["defs"] if x["name"] == "check_all")
        got = page.evaluate("window.devview.editor().getPosition().lineNumber")
        check("함수 이름 → 그 파일 그 줄", ok and got == want, (page.evaluate("window.devview.activePath()"), got, want))
        check("함수 열면 모듈 설명 대신 파일(패널 숨김)", fr.locator(".mdoc").count() == 0 and fr.locator("aside.panel").count() == 0)
        page.keyboard.press("Backquote")
        check("` → 원래 패널", wait_for(lambda: fr.locator("aside.panel").count() == 1 and fr.locator(".mdoc").count() == 0, 3))
        # 모듈 설명은 Esc 로도 닫힘
        fr = pick(page, "m-flow")
        page.keyboard.press("Backquote")
        wait_for(lambda: fr.locator(".mdoc").count() == 1, 3)
        page.keyboard.press("Escape")
        check("모듈 설명 Esc → 원래 패널", wait_for(lambda: fr.locator(".mdoc").count() == 0 and fr.locator("aside.panel").count() == 1, 3))
        check("페이지 예외 없음", not errs, errs[:3])
        br.close()


# 그래프 파일 없는 작업 폴더 — 빈 그래프로 시작(개편 2026-11-03) · 첫 화면 그래프 · 아래 막대 한 줄 · 단추로 첫 노드 → 파일 생김
# base: 서버 주소 / root: 작업 폴더
def test_missing(base, root):
    code, body = http(base + "/ft/api/data")
    d = json.loads(body)
    check("tree.json 없음 → 처음 열 때 틀을 깔아 파일 생김(새 폴더에서도 섹션에 틀이 보임)",
          code == 200 and len(d["tree"].get("nodes", [])) == 252 and d["meta"]["missing"] is None and (root / "docs" / "flowtree" / "tree.json").is_file(),
          (code, d.get("meta", {}).get("missing")))
    with sync_playwright() as pw:
        try:
            br = pw.chromium.launch(headless=not HEADED)
        except Exception:  # noqa: BLE001
            br = pw.chromium.launch(channel="chrome", headless=not HEADED)
        page = br.new_page(viewport={"width": 1200, "height": 800})
        # 콘솔 오류(404 자원 포함)
        cons = []
        page.on("console", lambda m: cons.append(m.text) if m.type == "error" else None)
        page.goto(base + "/")
        page.wait_for_selector("html[data-ready='1']", timeout=30000)
        check("tree 없어도 첫 화면 = 그래프", cur_view(page) == "graph")
        ok = wait_for(lambda: ft_frame(page).locator(".react-flow__pane").count() == 1, 15)
        check("Main 은 빈 틀을 안 보여 줌", ok and ft_frame(page).locator(".react-flow__node").count() == 0 and ft_frame(page).locator(".fatal").count() == 0)
        # 작업 단추 → 빈 곳 클릭 → 제목 → Enter → tree.json 생김
        fl = ft_frame(page)
        fl.locator(".addbar button[data-add='work']").click()
        box = fl.locator(".flow").bounding_box()
        page.mouse.click(box["x"] + box["width"] * 0.4, box["y"] + box["height"] * 0.4)
        fl.locator(".react-flow__node[data-id='__draft'] textarea").fill("첫 작업")
        page.keyboard.press("Enter")
        tp = root / "docs" / "flowtree" / "tree.json"
        ok = wait_for(lambda: fl.locator(".react-flow__node[data-id='t1']").count() == 1 and tp.is_file(), 8)
        n1 = next((n for n in json.loads(tp.read_text(encoding="utf-8"))["nodes"] if n["id"] == "t1"), {}) if tp.is_file() else {}
        check("단추로 첫 노드 → tree.json 생김(작업 · hand_off · user)", ok and (n1.get("kind"), n1.get("graph"), n1.get("by")) == ("task", "hand_off", "user"), n1)
        page.screenshot(path=str(SHOTS / "ft_empty_first_node.png"))
        fl.locator(".react-flow__pane").click(position={"x": 30, "y": 30})
        time.sleep(2.5)   # 화면이 2초마다 다시 묻는 동안에도
        check("빈 그래프 — 콘솔 오류 없음(404 안 쌓임)", not cons, cons[:3])
        br.close()


# 섹션 칸 · 화면별 위치 시험 — 명령 · 저장(화면 동작은 test_flowtree_screens.py)
# base: 서버 주소 / root: 작업 폴더
def test_sections(base, root):
    # tree.json · tree.user.json 경로
    tp = root / "docs" / "flowtree" / "tree.json"
    up = tp.with_name("tree.user.json")
    # 명령 실행
    # args: 명령 인자
    def cli(*args):
        return subprocess.run([sys.executable, str(FLOWTREE / "flowtree.py"), "--tree", str(tp), *args],
                              capture_output=True, text=True, encoding="utf-8")
    # 노드 하나
    # nid: 노드 id
    def node(nid):
        return next(n for n in json.loads(tp.read_text(encoding="utf-8"))["nodes"] if n["id"] == nid)
    # 지급 파일 노드 — 폴더 통째 · 다시 해도 안 늘고 · 점검 정상 · Main 화면 대상(screen 칸 없음)
    r = cli("--role", "main", "--root", str(root), "file-add", "data")
    files = [n for n in json.loads(tp.read_text(encoding="utf-8"))["nodes"] if n.get("kind") == "file" and n.get("by") == "main"]
    check("file-add 폴더 → 파일 노드", r.returncode == 0 and any(n["path"] == "data/extra.csv" and "screen" not in n for n in files), (r.stdout, r.stderr, files))
    check("file-add — 지문 목록 · 점 파일 제외", not [n for n in files if n["title"] in ("_origin_md5.txt", ".hidden")], files)
    r = cli("--role", "main", "--root", str(root), "file-add", "data")
    check("file-add 다시 → 새 0", "새 0" in r.stdout, r.stdout)
    r = cli("--role", "main", "--root", str(root), "file-add", "없는폴더")
    check("file-add 없는 경로 거부", r.returncode == 1, r.stderr)
    r = cli("--role", "main", "--root", str(root), "check")
    check("file-add 뒤 파일 노드 오류 없음", "missing-parent" not in r.stdout and "graph-file" not in r.stdout, r.stdout)
    cli("--role", "main", "add", "-", "섹션 작업", "--summary", "요약", "--section", "2")
    check("add --section → screen 칸", node("t1").get("screen") == 2, node("t1"))
    cli("--role", "main", "add", "-", "칸 없는 작업")
    check("add 섹션 없음 → 칸 없음", "screen" not in node("t2"), node("t2"))
    check("옛 노드 — 칸 없음 그대로", "screen" not in node("r-check"), node("r-check"))
    r = cli("--role", "main", "section-set", "t2", "3")
    check("section-set → 섹션 바뀜", r.returncode == 0 and node("t2").get("screen") == 3 and "섹션3" in r.stdout, r.stdout)
    r = cli("--role", "main", "section-set", "t2", "-")
    check("section-set - → 칸 지움", r.returncode == 0 and "screen" not in node("t2"), r.stdout)
    r = cli("--role", "main", "section-set", "t2", "9")
    check("범위 밖 섹션 거부", r.returncode == 1 and "screen" not in node("t2"), r.stderr)
    r = cli("--role", "2nd", "section-set", "t2", "1")
    check("남의 역할 거부", r.returncode == 1 and "screen" not in node("t2"), r.stderr)
    cli("--role", "main", "verify-add", "t1", "확인", "--section", "4")
    check("verify-add --section", node("v1").get("screen") == 4, node("v1"))
    cli("--role", "main", "survey-add", "-", "고르기", "--option", "가", "--option", "나", "--section", "5")
    check("survey-add --section", node("s1").get("screen") == 5, node("s1"))
    r = cli("--role", "main", "show", "t1")
    check("show 에 섹션", "섹션: 2" in r.stdout, r.stdout[:120])
    # 화면 명령 머리글
    hdr = {"X-Devview": "1", "Content-Type": "application/json"}
    code, b = http(base + "/ft/api/act", json.dumps({"op": "node-add", "args": {"kind": "task", "title": "단추 작업", "section": 6}}).encode(), hdr)
    check("화면 node-add 섹션", code == 200 and node(json.loads(b)["id"]).get("screen") == 6, b[:120])
    code, b = http(base + "/ft/api/act", json.dumps({"op": "ask", "args": {"text": "섹션 질문", "section": 6}}).encode(), hdr)
    check("화면 ask 섹션", code == 200 and node(json.loads(b)["id"]).get("screen") == 6, b[:120])
    check("meta.screens — 스위치 개수", json.loads(http(base + "/ft/api/data")[1])["meta"]["screens"] == 10)
    # 화면별 위치 · 고른 화면
    body = {"version": 1, "positions": {"feature": {"t1": [1, 2]}, "s2": {"t1": [30, 40]}}, "screen": 2}
    code, _ = http(base + "/ft/api/user", json.dumps(body).encode(), hdr)
    # 저장된 유저 칸
    u = json.loads(up.read_text(encoding="utf-8"))
    check("화면별 위치 · 고른 화면 저장", code == 200 and u["positions"]["feature"]["t1"] == [1, 2] and u["positions"]["s2"]["t1"] == [30, 40]
          and u["screen"] == 2, u)
    code, _ = http(base + "/ft/api/user", json.dumps({"screen": "가"}).encode(), hdr)
    check("고른 화면 값 종류 거부", code == 400, code)

    # ======= 틀 노드 =======
    # 그래프 · 빈 틀
    tree = lambda: json.loads(tp.read_text(encoding="utf-8"))  # noqa: E731
    frames = [n for n in tree()["nodes"] if n.get("frame")]
    check("틀 노드 총수 = 섹션 9 × 작업 4 × (1 + 설문 2 + 검증 4)", len(frames) == 252 and tree()["framed"] == list(range(9)), len(frames))
    check("섹션 틀 구성 — 작업 4 · 설문 8 · 검증 16",
          [sum(n["kind"] == k and n["screen"] == 3 for n in frames) for k in ("task", "survey", "verify")] == [4, 8, 16])
    # 할 일 목록 · 점검
    box = {r: cli("--role", r, "inbox").stdout for r in ("main", "insp", "user")}
    check("빈 틀 — inbox 에 안 나옴", not any("s0-t" in x or "s3-t" in x for x in box.values()), box)
    r = cli("check")
    check("빈 틀 — check 경고 없음", "s0-t" not in r.stdout + r.stderr, r.stdout[:200])
    r = cli("frames", "2")
    check("frames — 그 섹션 빈 틀 id", len(r.stdout.split()) == 28 and "s2-t1-v4" in r.stdout, r.stdout[:80])
    r = cli("--role", "main", "fill", "s2-t1", "--title", "채운 작업", "--summary", "기능 설명", "--func", "a.py | run | 실행 | ⭐")
    check("fill 작업 → 일반 노드 · 함수 표", r.returncode == 0 and "frame" not in node("s2-t1") and node("s2-t1")["funcs"][0]["name"] == "run", r.stdout + r.stderr)
    check("채운 작업은 inbox 에 나옴", "s2-t1" in cli("--role", "main", "inbox").stdout)
    r = cli("--role", "main", "fill", "s2-t1-v1", "--title", "결과 확인", "--script", "tests/test_a.py")
    check("fill 검증 → 스크립트 칸", r.returncode == 0 and node("s2-t1-v1")["script"] == "tests/test_a.py" and "frame" not in node("s2-t1-v1"), r.stderr)
    r = cli("--role", "main", "fill", "s2-t1-s1", "--title", "어느 쪽?", "--option", "가", "--option", "나", "--recommend", "2")
    check("fill 설문 → 선택지 · 추천", r.returncode == 0 and node("s2-t1-s1")["recommend"] == 1 and len(node("s2-t1-s1")["options"]) == 2, r.stderr)
    r = cli("--role", "main", "fill", "s2-t2", "--script", "x.py", "--title", "가")
    check("fill 칸 종류 거부", r.returncode == 1 and "frame" in node("s2-t2"), r.stderr)
    r = cli("--role", "user", "vote", "s2-t1-s1", "--pick", "1")
    b = cli("--role", "main", "inbox").stdout
    check("설문 투표 → inbox «설문 결정됨»", "s2-t1-s1 [설문 결정됨]" in b, b[:300])
    cli("--role", "main", "survey-ack", "s2-t1-s1")
    check("survey-ack → inbox 에서 빠짐", "s2-t1-s1" not in cli("--role", "main", "inbox").stdout)
    code, b = http(base + "/ft/api/act", json.dumps({"op": "vote", "args": {"survey": "s2-t1-s1", "pick": -1, "memo": "다른 안"}}).encode(), hdr)
    b2 = cli("--role", "main", "inbox").stdout
    check("기타 선택 → inbox 에 기타 · 메모", code == 200 and "기타" in b2 and "다른 안" in b2, b2[:300])
    code, b = http(base + "/ft/api/act", json.dumps({"op": "edit", "args": {"node": "s4-t1", "title": "유저가 쓴 제목"}}).encode(), hdr)
    check("유저 edit → 틀에서 일반 노드 · 원문 칸 그대로", code == 200 and "frame" not in node("s4-t1") and node("s4-t1")["title"] == "", b[:100])
    code, b = http(base + "/ft/api/act", json.dumps({"op": "edit", "args": {"node": "s4-t1-v1", "script": "tests/x.py"}}).encode(), hdr)
    check("유저 edit 스크립트 경로", code == 200 and node("s4-t1-v1")["edit"]["script"] == "tests/x.py", b[:100])
    code, b = http(base + "/ft/api/act", json.dumps({"op": "mark", "args": {"verify": "s4-t1-v1", "result": "fail"}}).encode(), hdr)
    check("유저 성공 · 실패 표시 → 결과 기록", code == 200 and node("s4-t1-v1")["runs"][-1]["result"] == "fail" and node("s4-t1-v1")["runs"][-1]["by"] == "user", b[:100])
    code, b = http(base + "/ft/api/act", json.dumps({"op": "edit", "args": {"node": "s4-t1-s1", "title": "유저 질문"}}).encode(), hdr)
    r = cli("check")
    check("유저가 질문만 쓴 설문 — 오류 아님(경고)", code == 200 and "error" not in [p["level"] for p in json.loads(http(base + "/ft/api/data")[1])["check"] if p.get("target") == "s4-t1-s1"], r.stdout[:200])
    # 지운 틀은 다시 안 깔림
    code, b = http(base + "/ft/api/act", json.dumps({"op": "node-del", "args": {"node": "s5-t2"}}).encode(), hdr)
    # 남은 id
    ids = {n["id"] for n in tree()["nodes"]}
    check("틀 작업 Delete — 아래 빈 틀도 같이", code == 200 and "s5-t2" not in ids and "s5-t2-v1" not in ids and "s5-t1" in ids, b[:120])
    cli("--role", "main", "add", "-", "다른 쓰기")
    http(base + "/ft/api/data")
    check("지운 틀 다시 안 깔림", "s5-t2" not in {n["id"] for n in tree()["nodes"]})


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    tmp = Path(tempfile.mkdtemp(prefix="dv_ft_"))
    procs = []
    try:
        root, adr_line, note_line = make_project(tmp)
        proc, base = start(root)
        procs.append(proc)
        test_api(base, adr_line, note_line)
        test_ui(base, adr_line, note_line)
        empty = tmp / "empty"
        empty.mkdir()
        (empty / "a.py").write_text("x = 1\n", encoding="utf-8")
        proc2, base2 = start(empty)
        procs.append(proc2)
        test_missing(base2, empty.resolve())
        root3, _, _ = make_project(tmp / "sec")
        proc3, base3 = start(root3)
        procs.append(proc3)
        test_sections(base3, root3)
    finally:
        for p in procs:
            p.terminate()
            try:
                p.wait(5)
            except Exception:  # noqa: BLE001
                p.kill()
        shutil.rmtree(tmp, ignore_errors=True)
    bad = [n for n, ok in RESULTS if not ok]
    print(f"결과: {len(RESULTS) - len(bad)}/{len(RESULTS)} 통과" + (f" · 실패 {bad}" if bad else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
