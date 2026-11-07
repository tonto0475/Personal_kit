# -*- coding: utf-8 -*-
# 그래프 예시 시험 — docs/examples/graph_example.md 의 명령 블록을 임시 그래프로 그대로 돌려 명세대로 그려지나 본다
"""
사용: python3 -m pytest -q .agents/skills/graph
- 키트 폴더를 스킬 폴더 위에서 찾는다(설치본처럼 docs 가 없으면 건너뜀)
- 진짜 그래프(docs/flowtree/)는 건드리지 않는다 — --tree 로 임시 파일만 쓴다
"""
import json
import re
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

# 키트 폴더
KIT = Path(__file__).resolve().parents[3]
# 예시 문서 · 명령 도구
EXAMPLE = KIT / "docs" / "examples" / "graph_example.md"
TOOL = KIT / "devview" / "flowtree" / "flowtree.py"


# 예시의 명령 줄 → 인자 목록들
def commands():
    block = re.search(r"```bash\n(.*?)```", EXAMPLE.read_text(encoding="utf-8"), re.S).group(1)
    return [shlex.split(ln)[1:] for ln in block.splitlines() if ln.startswith("FT ")]


# 명령 하나 실행 → 출력
def ft(path, role, *args):
    r = subprocess.run([sys.executable, str(TOOL), "--role", role, "--tree", str(path), "--root", str(KIT), *args],
                       cwd=KIT, capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, f"{args[:3]} — {r.stdout}{r.stderr}"
    return r.stdout


@pytest.fixture(scope="module")
def tree_path(tmp_path_factory):
    if not EXAMPLE.is_file() or not TOOL.is_file():
        pytest.skip("키트 폴더가 아니다")
    path = tmp_path_factory.mktemp("graph") / "tree.json"
    for args in commands():
        ft(path, "main", *args)
    return path


@pytest.fixture(scope="module")
def tree(tree_path):
    return json.loads(tree_path.read_text(encoding="utf-8"))


# 그래프 안 채운 노드를 종류별로(빈 틀 노드 제외)
def by_kind(tree, kind):
    nodes = tree["nodes"]
    items = nodes.values() if isinstance(nodes, dict) else nodes
    return [n for n in items if n.get("kind") == kind and not n.get("frame")]


def test_명세의_개수대로_그려진다(tree):
    tasks = by_kind(tree, "task")
    assert len([t for t in tasks if t["screen"] == 0]) == 4  # 섹션0 틀 작업 전부
    assert 3 <= len(by_kind(tree, "survey")) <= 5
    assert by_kind(tree, "verify")


def test_맨_앞_설문은_범위_시작이고_추천이_있다(tree):
    surveys = by_kind(tree, "survey")
    assert "이 범위로 시작" in surveys[0]["title"] or "이 범위로 시작" in json.dumps(surveys[0], ensure_ascii=False)
    assert all(s.get("recommend") is not None and s.get("why") for s in surveys)


def test_모든_노드가_한_그래프에_이어져_있다(tree):
    nodes = [n for k in ("task", "verify", "survey") for n in by_kind(tree, k)]
    assert {n["graph"] for n in nodes} == {"hand_off"}
    # 맨 위 = 틀 작업뿐 · 설문 · 검증은 그 작업 밑
    assert {n["kind"] for n in nodes if not n.get("parent")} == {"task"}
    assert all(n["id"].startswith(n["parent"]) for n in nodes if n.get("parent") and n["id"].startswith("s"))


def test_틀_밖_작업은_앞_작업_밑_그_섹션에_붙는다(tree):
    out = [n for n in by_kind(tree, "task") if not n["id"].startswith("s")]
    assert [(n["parent"], n["screen"]) for n in out] == [("s1-t1", 1)]


def test_설문은_번호_없이_풀어_쓴다(tree):
    for s in by_kind(tree, "survey"):
        # 사람이 읽을 칸 전부
        text = " ".join([s["title"], s["detail"], s["why"], *[" ".join([o["label"], o.get("text", ""), *o.get("pros", []), *o.get("cons", [])]) for o in s["options"]]])
        assert not re.search(r"(?<![A-Za-z])[A-Z]\d+|hand_off|\d+-\d+", text), text
        assert s["detail"].count(".") >= 3  # 짧은 문장 여럿


def test_사슬은_명령이_막는다(tree_path):
    r = subprocess.run([sys.executable, str(TOOL), "--role", "main", "--tree", str(tree_path), "--root", str(KIT), "verify-add", "s0-t2-v1", "다음 검증"],
                       cwd=KIT, capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 1 and "검증 대상 아님" in r.stdout + r.stderr


def test_빈_틀은_inbox_와_check_에_안_나온다(tree_path, tree):
    assert len([n for n in tree["nodes"] if n.get("frame")]) == 252 - 5 - 4 - 2  # 채운 작업 · 설문 · 검증을 뺀 틀
    box = ft(tree_path, "main", "inbox")
    assert "s0-t1" in box and "s5-t1" not in box
    assert "s5-t1" not in ft(tree_path, "main", "check")


def test_설문_검증은_섹션0_에_있다(tree):
    nodes = [n for k in ("verify", "survey") for n in by_kind(tree, k)]
    assert {n.get("screen") for n in nodes} == {0}  # 칸 이름은 screen


def test_범위_설문_답이_inbox_로_와서_닫힌다(tree_path):
    ft(tree_path, "user", "vote", "s0-t1-s1", "--pick", "1")
    assert "[설문 결정됨] 이 범위로 시작할까?" in ft(tree_path, "main", "inbox")
    ft(tree_path, "main", "survey-ack", "s0-t1-s1", "hand_off 1-1 수정 범위 승인")
    assert "설문 결정됨" not in ft(tree_path, "main", "inbox")


def test_담당자_답이_필요한_항목은_그래프에_없다(tree):
    assert not by_kind(tree, "question")
