# skeleton 시험 — 계획표 · flowtree 올리기 · 부품 복사 · 냉시동 판정(임시 폴더만 · 키트 파일 안 건드림)
#   python3 -m pytest -q skeleton
import json
import subprocess
import sys
from pathlib import Path

import pytest

# skeleton 폴더 · 키트 폴더
HERE = Path(__file__).resolve().parent
KIT = HERE.parent
# flowtree 명령 파일
FLOWTREE = KIT / "devview" / "flowtree" / "flowtree.py"


# 스크립트 실행 → (종료코드, 출력)
# name: skeleton 안 파일 / args: 인자
def run(name, *args):
    # 실행 결과
    r = subprocess.run([sys.executable, str(HERE / name), *map(str, args)], capture_output=True, text=True, encoding="utf-8")
    return r.returncode, r.stdout + r.stderr


# 작은 가짜 과제 — README + CSV 두 개
@pytest.fixture
def task(tmp_path):
    # 과제 폴더
    t = tmp_path / "task"
    (t / "data").mkdir(parents=True)
    (t / "README.md").write_text("# 가짜 과제\n- 화면: 운영자가 파일을 업로드하면 검사 결과를 본다. 결과는 지도로 본다\n"
                                 "- 자료는 DB 에 저장한다\n- Docker 로 실행\n", encoding="utf-8")
    (t / "data" / "orders.csv").write_text("order_id,qty\nA,1\nB,2\nB,3\n", encoding="utf-8")
    (t / "data" / "zz_widgets.csv").write_text("wid,size\nW1,3\n", encoding="utf-8")
    return t


# 계획표 — 자료 파일마다 읽기 함수 · 화면 자리 · 컨테이너 · 다듬을 칸
def test_plan(task, tmp_path):
    code, out = run("plan.py", "--task", task, "--out", tmp_path / "out")
    assert code == 0, out
    # 계획표
    plan = json.loads((tmp_path / "out" / "plan.json").read_text(encoding="utf-8"))
    # 묶음 id → 묶음
    b = {x["id"]: x for x in plan["bundles"]}
    assert plan["task"] == "가짜 과제"
    # K1 함수 이름
    funcs = [i["func"] for i in b["K1"]["items"]]
    assert "주문_읽기" in funcs and "전부_읽기" in funcs
    assert any(i["func"] == "zz_widgets_읽기" and i["todo"] for i in b["K1"]["items"])
    assert {p["path"] for p in b["K3"]["items"]} >= {"/", "/upload", "/map"}
    assert "컨테이너 요구 있음" in json.dumps(b["K0"], ensure_ascii=False)
    assert [x["id"] for x in plan["bundles"] if x["confirm"]] == ["K1", "K2", "K4"]
    assert (tmp_path / "out" / "plan.md").read_text(encoding="utf-8").startswith("# 뼈대 계획표")


# flowtree 올리기(Main 방식) — 묶음마다 완료 노드(add → start → done) · 두 번 불러도 노드가 늘지 않음 · 요약에 «이름:» · 이름 칸 처음 값
#   --section 으로 붙일 섹션을 지정 · --map 으로 묶음별 섹션 · --bundles 로 일부만
@pytest.mark.skipif(not FLOWTREE.is_file(), reason="flowtree.py 없음")
def test_to_flowtree(task, tmp_path):
    run("plan.py", "--task", task, "--out", tmp_path / "out")
    plan = tmp_path / "out" / "plan.json"
    # 임시 그래프
    tree = tmp_path / "ft" / "tree.json"
    tree.parent.mkdir()
    for _ in range(2):
        code, out = run("to_flowtree.py", "--plan", plan, "--tree", tree)
        assert code == 0, out
    # 노드 — 기본 섹션 1 + 묶음 6(빈 틀 제외)
    nodes = [n for n in json.loads(tree.read_text(encoding="utf-8"))["nodes"] if not n.get("frame")]
    assert sorted(n["kind"] for n in nodes) == ["task"] * 7
    sec = next(n for n in nodes if n["title"] == "뼈대(skeleton)")
    # 묶음 노드 — 섹션 밑 · 완료(start · done 사건)
    bundles = [n for n in nodes if n["title"].startswith("뼈대 K")]
    assert len(bundles) == 6 and all(n["parent"] == sec["id"] and n["graph"] == "hand_off" for n in bundles)
    assert all([e["t"] for e in n["events"]] == ["start", "done"] for n in bundles)
    assert all(n["summary"].startswith("이름:") and len(n["summary"]) <= 60 for n in bundles)
    # 이름 칸(--names)은 함수 표(funcs) 행으로 올라간다(2026-11-04 flowtree 함수 표)
    assert all(n.get("funcs") and not n.get("confirmed") for n in bundles)
    k1 = next(n for n in bundles if n["title"].startswith("뼈대 K1"))
    assert any("전부_읽기" in (r.get("name") or "") for r in k1["funcs"])
    # 섹션 지정 · 묶음별 섹션 · 일부만
    tree2 = tmp_path / "ft2" / "tree.json"
    tree2.parent.mkdir()
    flow = [sys.executable, str(FLOWTREE), "--role", "main", "--tree", str(tree2)]
    for title in ("1-1 입력", "1-2 저장"):
        subprocess.run([*flow, "add", "-", title], check=True, capture_output=True)
    code, out = run("to_flowtree.py", "--plan", plan, "--tree", tree2, "--bundles", "K1", "K2", "K3", "--section", "t1", "--map", "K2=t2")
    assert code == 0, out
    got = {n["title"][:5]: n["parent"] for n in json.loads(tree2.read_text(encoding="utf-8"))["nodes"] if n["title"].startswith("뼈대 K")}
    assert got == {"뼈대 K1": "t1", "뼈대 K2": "t2", "뼈대 K3": "t1"}
    assert not any(n["title"] == "뼈대(skeleton)" for n in json.loads(tree2.read_text(encoding="utf-8"))["nodes"])


# flowtree 올리기(섹션 방식) — 새 노드 없이 빈 틀을 fill · 모자라면 다음 섹션 · 끝까지 없으면 실패 보고 · 다시 불러도 안 늘어남
@pytest.mark.skipif(not FLOWTREE.is_file(), reason="flowtree.py 없음")
def test_to_flowtree_섹션_틀(task, tmp_path):
    run("plan.py", "--task", task, "--out", tmp_path / "out")
    plan = tmp_path / "out" / "plan.json"
    tree = tmp_path / "ft" / "tree.json"
    tree.parent.mkdir()
    # 지금 노드 — id → 노드
    now = lambda: {n["id"]: n for n in json.loads(tree.read_text(encoding="utf-8"))["nodes"]}  # noqa: E731
    for _ in range(2):
        code, out = run("to_flowtree.py", "--plan", plan, "--tree", tree, "--section", "3")
        assert code == 0, out
    assert "섹션 3 틀이 모자람" in out or len(now()) == 252
    nodes = now()
    assert len(nodes) == 252  # 틀 수 그대로 — 새 노드 없음
    full = sorted(k for k, n in nodes.items() if n["title"].startswith("뼈대 K"))
    assert full == ["s3-t1", "s3-t2", "s3-t3", "s3-t4", "s4-t1", "s4-t2"]  # 위에서부터 · 넘친 2개는 다음 섹션
    assert all(not nodes[k].get("frame") and [e["t"] for e in nodes[k]["events"]] == ["start", "done"] for k in full)
    k1 = nodes["s3-t2"]
    assert k1["title"].startswith("뼈대 K1") and k1["summary"].startswith("이름:") and k1["doc"]["path"] == "skeleton/cards/K1.md"
    assert any("전부_읽기" in (r.get("name") or "") for r in k1["funcs"])
    # 묶음별 대상 · 그 칸부터
    tree2 = tmp_path / "ft2" / "tree.json"
    tree2.parent.mkdir()
    code, out = run("to_flowtree.py", "--plan", plan, "--tree", tree2, "--bundles", "K1", "K2", "--section", "s5-t3", "--map", "K2=0")
    assert code == 0, out
    got = {n["id"] for n in json.loads(tree2.read_text(encoding="utf-8"))["nodes"] if n["title"].startswith("뼈대 K")}
    assert got == {"s5-t3", "s0-t1"}
    # 틀이 끝까지 모자람 — 실패 보고 · 넣은 것은 남음
    tree3 = tmp_path / "ft3" / "tree.json"
    tree3.parent.mkdir()
    code, out = run("to_flowtree.py", "--plan", plan, "--tree", tree3, "--section", "8")
    assert code == 1 and "빈 틀 작업 칸 없음" in out and "K4" in out and "K5" in out
    assert sum(n["title"].startswith("뼈대 K") for n in json.loads(tree3.read_text(encoding="utf-8"))["nodes"]) == 4
    # 없는 섹션 · 미리 보기는 파일을 안 만듦
    code, out = run("to_flowtree.py", "--plan", plan, "--tree", tree3, "--section", "9")
    assert code == 1 and "0~8" in out
    tree4 = tmp_path / "ft4" / "tree.json"
    code, out = run("to_flowtree.py", "--plan", plan, "--tree", tree4, "--section", "2", "--dry")
    assert code == 0 and "섹션 2 빈 틀" in out and not tree4.exists()


# 부품 복사 — import 바꿈 · 의존 부품 같이 · 안 덮음 · WORKLOG 덧붙이기만
def test_copy_parts(tmp_path):
    # 앱 · 배포 폴더
    app, root = tmp_path / "app", tmp_path / "root"
    (app / "docs").mkdir(parents=True)
    (app / "docs" / "WORKLOG.md").write_text("# 기록\n옛 줄\n", encoding="utf-8")
    code, out = run("copy_parts.py", "auth/auth_nicegui.py", "K0", "--app", app, "--deploy-dir", root)
    assert code == 0, out
    # 복사된 화면 쪽 인증
    text = (app / "src" / "ui" / "auth_nicegui.py").read_text(encoding="utf-8")
    assert "from lib." not in text and "from src.core.auth_core import" in text and "from src.ui.auth_web import" in text
    assert (app / "src" / "core" / "auth_core.py").is_file() and (app / "src" / "observe" / "__init__.py").is_file()
    assert (root / "Dockerfile").is_file() and not (app / "Dockerfile").exists()
    (app / "src" / "observe" / "obs_log.py").write_text("# 내가 고침\n", encoding="utf-8")
    code, out = run("copy_parts.py", "K0", "--app", app, "--deploy-dir", root)
    assert code == 0 and "있음" in out
    assert (app / "src" / "observe" / "obs_log.py").read_text(encoding="utf-8") == "# 내가 고침\n"
    # 작업 기록
    log = (app / "docs" / "WORKLOG.md").read_text(encoding="utf-8")
    assert log.startswith("# 기록\n옛 줄\n") and log.count("부품 복사") == 1


# 가짜 앱 — 표준 라이브러리만으로 K1 · K2 · K4 진입점(dup=True 면 적용할 때마다 행이 늘어나는 버그)
# app: 앱 폴더 / dup: 버그 넣기
def fake_app(app, dup=False):
    for d in ("src/core", "src/db"):
        (app / d).mkdir(parents=True, exist_ok=True)
        (app / d / "__init__.py").write_text("", encoding="utf-8")
    (app / "src" / "__init__.py").write_text("", encoding="utf-8")
    (app / "src" / "core" / "입력.py").write_text(
        "import csv\nfrom pathlib import Path\n"
        "def 전부_읽기(task_dir):\n"
        "    rows = list(csv.DictReader(open(Path(task_dir) / 'data' / 'orders.csv', encoding='utf-8')))\n"
        "    return {'tables': {'주문': rows}, 'report': []}\n", encoding="utf-8")
    (app / "src" / "db" / "저장.py").write_text(
        "import sqlite3\n"
        "def 적용(db_path, tables):\n"
        "    c = sqlite3.connect(db_path)\n"
        "    c.execute('CREATE TABLE IF NOT EXISTS t (k TEXT" + ("" if dup else " UNIQUE") + ")')\n"
        "    for r in tables['주문']:\n"
        "        c.execute('INSERT " + ("" if dup else "OR IGNORE ") + "INTO t VALUES (?)', (r['order_id'],))\n"
        "    c.commit(); n = c.execute('SELECT COUNT(*) FROM t').fetchone()[0]; c.close()\n"
        "    return {'version': 1, 'rows': {'t': n}}\n", encoding="utf-8")
    (app / "src" / "core" / "계산.py").write_text(
        "def 계획_계산(tables):\n    return {'count': len(tables['주문'])}\n", encoding="utf-8")


# 냉시동 — 통과 · 앱 없음은 건너뜀
def test_check_pass(task, tmp_path):
    fake_app(tmp_path / "app")
    code, out = run("check.py", "--app", tmp_path / "app", "--task", task, "--plan", tmp_path / "none.json")
    assert code == 0, out
    for line in ("K1 통과", "K2 통과", "K4 통과", "K0 건너뜀", "K3 건너뜀"):
        assert line in out, out


# 냉시동 — 같은 자료 두 번에 행이 늘면 K2 실패 · 거기서 멈춤(종료코드 1 · K4 안 돌림)
def test_check_fail_stops(task, tmp_path):
    fake_app(tmp_path / "app", dup=True)
    code, out = run("check.py", "--app", tmp_path / "app", "--task", task, "--plan", tmp_path / "none.json")
    assert code == 1 and "K2 실패" in out and "K4" not in out, out


# 냉시동 — 아직 없는 묶음은 건너뜀(빈 앱)
def test_check_empty_app(task, tmp_path):
    (tmp_path / "empty").mkdir()
    code, out = run("check.py", "--app", tmp_path / "empty", "--task", task, "--plan", tmp_path / "none.json")
    assert code == 0 and "K1 건너뜀" in out and "K0 건너뜀" in out, out
