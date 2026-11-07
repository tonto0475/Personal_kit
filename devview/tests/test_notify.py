"""알림 종(notify.py · devview /api/notify) 로직 시험 — 임시 폴더 · 빈 포트 시험 서버(그 PID 만 끔)

    py -3 -m pytest -q tests/test_notify.py          (devview 폴더에서 · 키트도 같은 파일)

스크립트 한 줄 등록 · 동시 덧붙이기 · 키트 찾기 · 자동 수집(tree.json 기록 · 책 notes.json 답 · 설문 · 허브 대기)
· 처음 보는 출처는 기준점만 · 재시작해도 중복 없음 · 서버 API(목록 · 읽음 · 서버 꺼진 동안 등록 · 시작 때 기존 기록 무시)
"""
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
DV = HERE.parent
sys.path.insert(0, str(DV))
import notify  # noqa: E402

NOTIFY = DV / "notify.py"
DEVVIEW = DV / "devview.py"
# flowtree 공용 쓰기 통로 — 키트 = devview/flowtree · 로컬 = tools/flowtree(읽기만 · 시험은 그 apply 로 tree.json 에 덧붙임)
FT_DIR = next(d for d in (DV / "flowtree", DV.parent / "flowtree") if (d / "flowtree_store.py").is_file())
sys.path.insert(0, str(FT_DIR))
import flowtree_store as store  # noqa: E402


def cli(kit, *args):
    r = subprocess.run([sys.executable, str(NOTIFY), "--kit", str(kit), *args], capture_output=True, text=True,
                       encoding="utf-8", env=dict(os.environ, PYTHONUTF8="1"))
    assert r.returncode == 0, r.stderr
    return r.stdout


def new_tree(kit):
    tp = kit / "docs" / "flowtree" / "tree.json"
    t1 = store.apply(tp, "main", "add", parent=None, title="첫 작업")["id"]
    return tp, t1


# ======= 스크립트 · 저장 =======
def test_cli_add_list_read(tmp_path):
    out = cli(tmp_path, "add", "--kind", "done", "--title", "t3 완료", "--to", "graph:t3")
    assert "알림" in out
    v = notify.Feed(tmp_path).view()
    assert v["unread"] == 1 and v["items"][0]["title"] == "t3 완료"
    assert v["items"][0]["to"] == {"view": "graph", "node": "t3"} and v["items"][0]["src"] == "script"
    notify.mark_read(tmp_path, [v["items"][0]["id"]])
    assert notify.Feed(tmp_path).view()["unread"] == 0
    assert "안 읽음 0" in cli(tmp_path, "list")


def test_cli_bad_kind_and_to(tmp_path):
    r = subprocess.run([sys.executable, str(NOTIFY), "--kit", str(tmp_path), "add", "--kind", "완료", "--title", "x"],
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 2 and "종류" in r.stderr
    r = subprocess.run([sys.executable, str(NOTIFY), "--kit", str(tmp_path), "add", "--title", "x", "--to", "zzz:1"],
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 2 and "--to" in r.stderr


def test_parse_to():
    assert notify.parse_to("book:demo:n1:t2") == {"view": "book", "book": "demo", "note": "n1", "t": "t2"}
    assert notify.parse_to("book:demo") == {"view": "book", "book": "demo"}  # 책 새 판 = 마지막 판
    assert notify.parse_to("file:src/a.py:12") == {"view": "code", "path": "src/a.py", "line": 12}
    assert notify.parse_to("hub:main") == {"view": "chat", "nick": "main"}
    assert notify.parse_to("survey:s1") == {"view": "survey", "id": "s1"}
    assert notify.parse_to("") == {}


def test_bad_kinds_are_red(tmp_path):
    for k in ("block", "fail", "queue-fail", "route-fail"):
        assert notify.make(k, "x")["level"] == "bad"
    assert notify.make("done", "x")["level"] == ""


def test_concurrent_appends(tmp_path):
    code = ("import sys;sys.path.insert(0,sys.argv[1]);import notify\n"
            "for i in range(25): notify.add(sys.argv[2],'info',f'p{sys.argv[3]}-{i}','본문 '*20)")
    ps = [subprocess.Popen([sys.executable, "-c", code, str(DV), str(tmp_path), str(n)]) for n in range(8)]
    assert all(p.wait(60) == 0 for p in ps)
    lines = notify.feed_path(tmp_path).read_text(encoding="utf-8").splitlines()
    assert len(lines) == 200 and all(json.loads(x)["op"] == "add" for x in lines)
    assert notify.Feed(tmp_path).view(limit=1000)["total"] == 200


def test_find_kit_upward(tmp_path, monkeypatch):
    monkeypatch.delenv("DEVVIEW_KIT", raising=False)
    notify.add(tmp_path, "info", "x")
    deep = tmp_path / "a" / "b"
    deep.mkdir(parents=True)
    assert notify.find_kit(start=deep) == tmp_path.resolve()
    other = Path(tempfile.mkdtemp())
    (other / "kit").mkdir()
    (other / "kit" / "AGENTS.md").write_text("x", encoding="utf-8")
    assert notify.find_kit(start=other) == other.resolve() / "kit"


def test_partial_line_waits(tmp_path):
    notify.add(tmp_path, "info", "하나")
    with open(notify.feed_path(tmp_path), "ab") as f:
        f.write(b'{"op":"add","id":"half"')         # 쓰는 중인 줄
    feed = notify.Feed(tmp_path)
    assert feed.view()["total"] == 1
    with open(notify.feed_path(tmp_path), "ab") as f:
        f.write(b',"kind":"info","title":"\xeb\x91\x98","ts":1}\n')
    assert feed.view()["total"] == 2


# ======= 자동 수집 =======
def test_tree_baseline_then_new(tmp_path):
    tp, t1 = new_tree(tmp_path)
    store.apply(tp, "main", "done", task=t1)                   # 시작 전 기록
    col = notify.Collector(tmp_path, tree_path=lambda: tp)
    assert col.tick() == []                                    # 기준점만
    store.apply(tp, "main", "start", task=t1)
    assert col.tick() == []                                    # 착수는 알림 아님
    store.apply(tp, "main", "block", task=t1, note="DB 접속 정보 필요")
    new = col.tick()
    assert [(r["kind"], r["level"], r["to"]["node"]) for r in new] == [("block", "bad", t1)]
    assert "DB 접속" in new[0]["body"] and new[0]["src"] == "tree"
    store.apply(tp, "main", "done", task=t1)
    assert [r["kind"] for r in col.tick()] == ["done"]
    assert col.tick() == []                                    # 같은 기록 두 번 안 함
    # 재시작(새 Collector) — 본 기록은 그대로 · 꺼진 동안 생긴 기록은 알림
    store.apply(tp, "main", "hold", task=t1, note="유저 확인 대기")
    col2 = notify.Collector(tmp_path, tree_path=lambda: tp)
    assert [r["kind"] for r in col2.tick()] == ["hold"]
    assert notify.Feed(tmp_path).view()["total"] == 3


def test_tree_verify_question_survey_ack(tmp_path):
    tp, t1 = new_tree(tmp_path)
    col = notify.Collector(tmp_path, tree_path=lambda: tp)
    col.tick()
    v1 = store.apply(tp, "main", "verify-add", target=t1, what="화면 확인")["id"]
    store.apply(tp, "insp", "run", verify=v1, result="fail", note="tests/x.py")
    store.apply(tp, "insp", "run", verify=v1, result="pass", note="tests/x.py")
    q1 = store.apply(tp, "user", "ask", text="왜?", target=t1)["id"]
    store.apply(tp, "2nd", "answer", question=q1, short="이래서")
    new = col.tick()
    assert [(r["kind"], r["to"]["node"]) for r in new] == [("fail", v1), ("pass", v1), ("answer", q1)]
    assert new[0]["level"] == "bad" and new[2]["body"] == "이래서"
    # 노드 종류(node) — 종 목록 색(notify.js tone)
    assert [r.get("node") for r in new] == ["verify", "verify", "question"]
    store.apply(tp, "main", "done", task=t1)
    assert [(r["kind"], r.get("node")) for r in col.tick()] == [("done", "task")]
    assert all(r.get("node") for r in notify.Feed(tmp_path).view()["items"])       # 저장 · 화면 목록에도 실림
    rec = notify.make("fail", "스크립트 등록")                                      # 스크립트 등록 = node 없음(회색)
    assert "node" not in rec


def test_tree_screen_passed(tmp_path):
    tree = {"nodes": [{"id": "t9", "kind": "task", "title": "섹션 작업", "screen": 3, "graph": "hand_off",
                       "events": [{"seq": 4, "t": "done", "ts": 1, "at": "2026-11-04 10:00:00"}]}]}
    (k, rec), = notify.tree_events(tree)
    assert rec["to"] == {"view": "graph", "node": "t9", "screen": 3, "graph": "hand_off"}


def test_notes_answer_and_thread(tmp_path):
    nf = tmp_path / "bookkit" / "books" / "demo" / "notes.json"
    nf.parent.mkdir(parents=True)
    note = {"id": "n1", "ts": "2026-11-04 10:00:00", "doc": "demo", "ctx": "x | b=s1-3", "text": "이건 왜 이렇지?"}
    nf.write_text(json.dumps([note], ensure_ascii=False), encoding="utf-8")
    col = notify.Collector(tmp_path, book_path=lambda b: f"bookkit/books/{b}/dist/{b}.html")
    assert col.tick() == []
    note.update(answer="이유는 이것", answer_ts="2026-11-04 10:01:00", title="짧은 제목")
    nf.write_text(json.dumps([note], ensure_ascii=False), encoding="utf-8")
    new = col.tick()
    assert len(new) == 1 and new[0]["kind"] == "note" and "짧은 제목" in new[0]["title"]
    assert new[0]["to"] == {"view": "book", "book": "demo", "note": "n1", "path": "bookkit/books/demo/dist/demo.html"}
    note["thread"] = [{"id": "t1", "q": "꼬리 질문", "ts": "x"}]
    nf.write_text(json.dumps([note], ensure_ascii=False), encoding="utf-8")
    assert col.tick() == []                                    # 답 없는 꼬리 질문
    note["thread"][0].update(a="꼬리 답", a_ts="2026-11-04 10:03:00")
    nf.write_text(json.dumps([note], ensure_ascii=False), encoding="utf-8")
    new = col.tick()
    assert len(new) == 1 and new[0]["to"]["t"] == "t1" and new[0]["body"] == "꼬리 답"


class FakeSurvey:
    """survey.py 모듈 흉내 — all_surveys · result_file · project_dir"""

    def __init__(self, base):
        self.base = base
        self.items = []

    def all_surveys(self):
        return [("k1", self.base, "proj", s) for s in self.items]

    def project_dir(self, st, pr):
        return st / pr

    def result_file(self, folder, sid):
        return folder / f"{sid}.result.json"


def test_survey_new_and_route_fail(tmp_path):
    fs = FakeSurvey(tmp_path)
    fs.items = [{"id": "old", "title": "옛 설문", "state": "pending"}]
    col = notify.Collector(tmp_path, survey=fs)
    assert col.tick() == []
    col.tick()                                                 # 홀수 차례는 설문 안 봄
    fs.items.append({"id": "s2", "title": "새 설문 제목", "state": "pending"})
    fs.items.append({"id": "s3", "title": "이미 답함", "state": "done"})
    new = col.tick()
    assert [(r["kind"], r["to"]["id"]) for r in new] == [("survey", "s2")]
    assert new[0]["to"] == {"view": "survey", "s": "k1", "p": "proj", "id": "s2"}
    (tmp_path / "proj").mkdir()
    (tmp_path / "proj" / "s3.result.json").write_text(json.dumps({"route": [{"to": "MAIN", "ok": False, "error": "queue 실패"}]}),
                                                      encoding="utf-8")
    col.tick()
    new = col.tick()
    assert [(r["kind"], r["level"]) for r in new] == [("route-fail", "bad")] and new[0]["body"] == "queue 실패"


class FakeHub:
    def __init__(self):
        self.rows_ = []

    def rows(self, root):
        return {"rows": self.rows_}


def test_hub_waiting(tmp_path):
    hub = FakeHub()
    hub.rows_ = [{"nick": "main", "label": "MAIN", "registered": True, "state": "approval", "last_event_at": "a1"}]
    col = notify.Collector(tmp_path, hub=hub)
    assert col.tick() == []                                    # 시작 때 이미 대기 = 기준점
    col.tick()
    hub.rows_ = [{"nick": "main", "label": "MAIN", "registered": True, "state": "working", "last_event_at": "a2"},
                 {"nick": "2nd", "label": "2ND", "registered": True, "state": "survey", "last_event_at": "b1", "status": "질문 답 대기"}]
    new = col.tick()
    assert [(r["title"], r["to"]) for r in new] == [("2ND 입력 대기", {"view": "chat", "nick": "2nd"})]
    col.tick()
    assert col.tick() == []                                    # 같은 대기 두 번 안 함


# ======= 서버 API =======
def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def start_server(root):
    home = root.parent / "home"
    home.mkdir(exist_ok=True)
    port = free_port()
    env = dict(os.environ, DEVVIEW_NO_VAULT="1", HOME=str(home), USERPROFILE=str(home), CODEX_HOME=str(home / ".codex"), PYTHONUTF8="1")
    proc = subprocess.Popen([sys.executable, str(DEVVIEW), str(root), "--host", "127.0.0.1", "--port", str(port), "--page-port", "0"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
    url = f"http://127.0.0.1:{port}"
    for _ in range(150):
        assert proc.poll() is None, "서버 기동 실패"
        try:
            urllib.request.urlopen(url + "/api/info", timeout=1).read()
            return proc, url
        except OSError:
            time.sleep(0.1)
    proc.kill()
    raise RuntimeError("서버 응답 없음")


def stop(proc):
    proc.terminate()
    try:
        proc.wait(5)
    except subprocess.TimeoutExpired:
        proc.kill()


def get(url, path):
    return json.loads(urllib.request.urlopen(url + "/api/" + path, timeout=5).read())


def post(url, path, body):
    req = urllib.request.Request(url + "/api/" + path, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "X-Devview": "1"})
    return json.loads(urllib.request.urlopen(req, timeout=5).read())


def wait(fn, sec=8):
    end = time.time() + sec
    while time.time() < end:
        v = fn()
        if v:
            return v
        time.sleep(0.2)
    return fn()


@pytest.fixture
def world():
    base = Path(tempfile.mkdtemp(prefix="dv_notify_"))
    root = base / "proj"
    root.mkdir()
    yield root
    import shutil
    shutil.rmtree(base, ignore_errors=True)


def test_server_api(world):
    root = world
    tp, t1 = new_tree(root)
    store.apply(tp, "main", "done", task=t1)                   # 시작 전 기록
    cli(root, "add", "--kind", "report", "--title", "서버 꺼진 동안 등록")
    proc, url = start_server(root)
    try:
        assert get(url, "info")["notify"] is True
        time.sleep(2)
        v = get(url, "notify")
        assert [r["title"] for r in v["items"]] == ["서버 꺼진 동안 등록"]   # 시작 전 tree 기록은 알림 안 됨
        store.apply(tp, "main", "done", task=t1)
        v = wait(lambda: (lambda x: x if x["total"] == 2 else None)(get(url, "notify")))
        assert v and v["items"][0]["kind"] == "done" and v["items"][0]["to"]["node"] == t1 and v["unread"] == 2
        # 세션이 키트 안 하위 폴더에서 --kit 없이 — 위로 찾음
        sub = root / "src"
        sub.mkdir()
        r = subprocess.run([sys.executable, str(NOTIFY), "add", "--kind", "decide", "--title", "결정 필요"], cwd=sub,
                           capture_output=True, text=True, encoding="utf-8", env={k: v for k, v in os.environ.items() if k != "DEVVIEW_KIT"})
        assert r.returncode == 0, r.stderr
        v = wait(lambda: (lambda x: x if x["total"] == 3 else None)(get(url, "notify")))
        assert v and v["unread"] == 3
        v = post(url, "notify/read", {"ids": [v["items"][0]["id"]]})
        assert v["unread"] == 2
        v = post(url, "notify/read", {"all": True})
        assert v["unread"] == 0 and all(r["read"] for r in v["items"])
    finally:
        stop(proc)
    # 재시작 — 읽음 유지 · 중복 없음
    proc, url = start_server(root)
    try:
        time.sleep(2)
        v = get(url, "notify")
        assert v["total"] == 3 and v["unread"] == 0
    finally:
        stop(proc)
