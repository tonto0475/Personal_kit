"""magic.py 시험 — show(main 작업 · 검증 · 질문 노드 · 멈춤 / 2nd 답변 준비 중) · 답 자리(node · md · code · form)
    python3 -m pytest -q .agents/skills/codex-hub        (임시 작업 폴더 · flowtree 는 키트 devview/flowtree 를 그대로 씀)
"""
import json
import sys
import time
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import hub  # noqa: E402
import magic  # noqa: E402

# flowtree — 키트 devview/flowtree(설치본 skills_src 도) · 로컬 원본
FLOWTREE = next((d for d in (HERE.parents[2] / "devview" / "flowtree", HERE.parents[3] / "devview" / "flowtree",
                             Path.home() / "PyCharmMiscProject" / "probe_ide" / "tools" / "flowtree")
                 if (d / "flowtree_store.py").is_file()), None)
TH = "019a2222-3333-7444-8555-666677778888"
MD = "---\ntitle: 시험\n---\n# 메모\n\n첫 문단 글이다.\n둘째 줄도 같은 문단.\n\n```\n코드 줄\n```\n\n| 열 A | 열 B |\n|---|---|\n| 가 | 1 |\n| 나 | 2 |\n\n## 다음 절\n\n끝\n"
PY = "#!/usr/bin/env python3\n# -*- coding: utf-8 -*-\nimport os\n\n\ndef calc(x):\n    return x * 2\n"


@pytest.fixture
def world(tmp_path, monkeypatch):
    if FLOWTREE is None:
        pytest.skip("flowtree 없음")
    sys.path.insert(0, str(FLOWTREE))
    import flowtree_store as fs
    work = tmp_path / "kit"
    (work / "docs" / "flowtree").mkdir(parents=True)
    (work / "AGENTS.md").write_text("#\n", encoding="utf-8")
    (work / "docs" / "notes.md").write_text(MD, encoding="utf-8", newline="\n")
    (work / "src").mkdir()
    (work / "src" / "calc.py").write_text(PY, encoding="utf-8", newline="\n")
    tp = work / "docs" / "flowtree" / "tree.json"
    tp.write_text(json.dumps({"version": 2, "rev": 0, "title": "시험", "nodes": [{"id": "r1", "kind": "req", "title": "요구 하나"}],
                              "edges": []}), encoding="utf-8")
    fs.apply(tp, "main", "add", parent="-", title="ADR 작업", summary="화면", graph="adr", doc="docs/notes.md#1-2")
    fs.apply(tp, "main", "add", parent="-", title="Task 작업", graph="task")
    fs.apply(tp, "main", "verify-add", target="t1", what="tests/test_a.py")
    fs.apply(tp, "user", "ask", text="왜 이렇게?", target="t1")
    monkeypatch.chdir(work)
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex"))
    monkeypatch.setenv("CODEX_THREAD_ID", TH)
    monkeypatch.setenv("MAGIC_SURVEY_DIR", str(tmp_path / "sv"))
    monkeypatch.setenv("SURVEY_REGISTRY", str(tmp_path / "survey_stores.json"))
    monkeypatch.setenv("SURVEY_NO_QUEUE", "1")
    monkeypatch.delenv("CODEX_HUB_DIR", raising=False)
    monkeypatch.setattr(hub, "process_effort", lambda: None)
    hub.main(["register", "--nick", "2nd", "--effort", "low"])
    return {"work": work, "tree": tp, "fs": fs, "tmp": tmp_path}


# 요청 파일 쓰기(devview 가 쓰는 모양) — 반환 요청 id
# w: 시험 세계 / role: 역할 / **kw: 요청 칸
_n = [0]


def req(w, role, **kw):
    _n[0] += 1
    rid = f"m1102-0300{_n[0]:02d}-abcd"
    d = {"id": rid, "skill": f"{role}-magic", "nick": role, "role": role, "at": "2026-11-02 03:00:00", "view": kw.pop("view", "graph"),
         "question": kw.pop("question", ""), "nodes": kw.pop("nodes", []), "root": str(w["work"]), "tree": str(w["tree"]),
         "flowtree": str(FLOWTREE), "target": kw.pop("target", None)}
    p = w["work"] / ".codex-hub" / "requests" / f"{rid}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    return rid


# magic.main → (종료코드, 출력, 오류)
def run(capsys, *argv):
    code = magic.main(list(argv))
    o = capsys.readouterr()
    return code, o.out.strip(), o.err.strip()


def status_of(w, nick):
    return json.loads((w["work"] / ".codex-hub" / "sessions" / f"{nick}.json").read_text(encoding="utf-8"))["status"]


def lines_of(w, rel):
    return (w["work"] / rel).read_text(encoding="utf-8").split("\n")


def test_show_main_work_and_stop(world, capsys, monkeypatch):
    # MAIN 은 자기 thread(2ND 와 다름) — 상태 줄은 CODEX_THREAD_ID 로 자기 등록을 찾아 바꿈
    monkeypatch.setenv("CODEX_THREAD_ID", TH.replace("8888", "9999"))
    hub.main(["register", "--nick", "main"])
    rid = req(world, "main", nodes=[{"id": "t1"}, {"id": "r1"}])
    code, out, _ = run(capsys, "show", rid)
    assert code == 0 and "할 일: t1" in out and "맥락: r1" in out and "flowtree.py --role main start" in out
    # 구현은 서브에게(세션이 직접 쓰지 않음)
    assert "구현 서브에게 시킨다" in out and "ADR" not in out.split("할 일:")[1]
    assert status_of(world, "main").startswith("❇️_1-2 : 작업. ADR 작업")
    rid = req(world, "main", nodes=[{"id": "r1"}, {"id": "t2"}])
    code, out, _ = run(capsys, "show", rid)
    assert code == 0 and "멈춤: 고른 노드에 작업 · 검증 · 질문 노드 없음" in out and "할 일:" not in out


# 함수 표 · 이름 바뀜 — show 에 함수 표 · «이름 바뀜» · done 뒤 자동 «이름 바꾸기» 작업도 hand_off 작업 노드라 MAIN 마법봉 대상
def test_show_main_funcs_rename(world, capsys, monkeypatch):
    monkeypatch.setenv("CODEX_THREAD_ID", TH.replace("8888", "9999"))
    hub.main(["register", "--nick", "main"])
    fs, tp = world["fs"], world["tree"]
    fs.apply(tp, "main", "funcs-set", task="t1", rows=["src/calc.py | calc | 두 배 | ⭐"])
    fs.apply(tp, "main", "start", task="t1")
    fs.apply(tp, "main", "done", task="t1")
    rid_task = fs.apply(tp, "user", "funcs", task="t1", row="f1", cells={"name": "두배_하기"})["id"]
    code, out, _ = run(capsys, "show", req(world, "main", nodes=[{"id": "t1"}]))
    assert code == 0 and "  f1 src/calc.py | 두배_하기 | 두 배 | ⭐" in out
    assert "이름 바뀜: src/calc.py · calc → src/calc.py · 두배_하기" in out and "funcs-ack" in out
    # 자동 «이름 바꾸기» 작업 — 할 일로 잡힘(멈춤 아님)
    code, out, _ = run(capsys, "show", req(world, "main", nodes=[{"id": rid_task}]))
    assert code == 0 and f"할 일: {rid_task}" in out and "이름 바꾸기" in out and "funcs-ack t1" in out


# main 마법봉 — 작업 · 검증 · 질문 노드를 종류별 할 일로 나눈다(작업 → 구현 서브 · 검증 → 검증관 · 질문 → 놀고 있는 서브)
def test_show_main_three_kinds(world, capsys, monkeypatch):
    monkeypatch.setenv("CODEX_THREAD_ID", TH.replace("8888", "9999"))
    hub.main(["register", "--nick", "main"])
    rid = req(world, "main", nodes=[{"id": "t1"}, {"id": "v1"}, {"id": "q1"}])
    code, out, _ = run(capsys, "show", rid)
    assert code == 0 and "v1 [미검증] tests/test_a.py" in out and "q1 [" in out and "멈춤" not in out
    assert "할 일: t1 — " in out and "구현 서브에게 시킨다" in out
    assert "검증 할 일: v1 — 검증관에게 고정 양식" in out and "--role insp verify-start" in out
    assert "질문 할 일: q1 — 놀고 있는 서브에게" in out and "--role 2nd answer-start" in out
    assert status_of(world, "main").startswith("❇️_1-2 : 작업. ADR 작업")
    # 검증만 · 질문만 — 멈춤 아님 · 작업 할 일 없음
    code, out, _ = run(capsys, "show", req(world, "main", nodes=[{"id": "v1"}]))
    assert code == 0 and "검증 할 일: v1" in out and "멈춤" not in out and "\n할 일:" not in out and "질문 할 일" not in out
    assert status_of(world, "main").startswith("확인 : 마법봉 v1")
    code, out, _ = run(capsys, "show", req(world, "main", nodes=[{"id": "q1"}]))
    assert code == 0 and "질문 할 일: q1" in out and "멈춤" not in out and "검증 할 일" not in out


# INSP 세션은 없다 — 옛 insp 요청은 역할 모름
def test_show_insp_role_gone(world, capsys):
    code, _, err = run(capsys, "show", req(world, "insp", nodes=[{"id": "v1"}]))
    assert code == 1 and "역할 모름: insp" in err


def test_show_and_answer_node(world, capsys):
    rid = req(world, "2nd", question="왜 이렇게?", target={"kind": "node", "question": "q1", "targets": ["t1"]})
    code, out, _ = run(capsys, "show", rid)
    tree = json.loads(world["tree"].read_text(encoding="utf-8"))
    q = next(n for n in tree["nodes"] if n["id"] == "q1")
    assert code == 0 and "q1 답변 준비 중" in out and "→ t1" in out and "answer-node" in out
    assert q["events"][-1]["t"] == "start" and q["events"][-1]["by"] == "2nd"
    assert status_of(world, "2nd") == "답변 : 왜 이렇게?"
    code, out, _ = run(capsys, "answer-node", rid, "--short", "판 번호로 막음", "근거 src/a.py:12")
    tree = json.loads(world["tree"].read_text(encoding="utf-8"))
    q = next(n for n in tree["nodes"] if n["id"] == "q1")
    assert code == 0 and out == "q1 답변 완료" and q["answers"][-1]["short"] == "판 번호로 막음"


def test_answer_md_top_section(world, capsys):
    rid = req(world, "2nd", question="이 문서 요지?", target={"kind": "md", "file": "docs/notes.md"})
    code, out, _ = run(capsys, "answer-md", rid, "요지는 둘\n- 하나")
    ls = lines_of(world, "docs/notes.md")
    i = ls.index("## 🤖 질문 · 답변")
    assert code == 0 and ls[3] == "# 메모" and i == 5 and ls[7] == "> [!answer] 🤖 2ND · 이 문서 요지?" and ls[8] == "> 요지는 둘"
    assert out == "답 넣음: docs/notes.md:8"
    # 두 번째 — 같은 절 끝에 덧붙임(다음 제목 앞)
    rid = req(world, "2nd", question="둘째 질문", target={"kind": "md", "file": "docs/notes.md"})
    run(capsys, "answer-md", rid, "둘째 답")
    ls = lines_of(world, "docs/notes.md")
    assert ls.count("## 🤖 질문 · 답변") == 1
    j = ls.index("> [!answer] 🤖 2ND · 둘째 질문")
    assert j > i and ls[j + 1] == "> 둘째 답" and ls.index("# 메모") < i and j < ls.index("첫 문단 글이다.")
    assert ls[j - 1] == "" and ls[j - 2] == "> - 하나"


def test_answer_md_below_paragraph_and_relocate(world, capsys):
    p = world["work"] / "docs" / "notes.md"
    # 요청 뒤 유저가 위에 두 줄을 넣음 — 기록 줄(6)이 밀려도 고른 글자로 다시 찾음
    rid = req(world, "2nd", question="이 문장?", target={"kind": "md", "file": "docs/notes.md",
                                                       "range": {"start_line": 6, "end_line": 6}, "text": "첫 문단 글이다"})
    p.write_text(MD.replace("# 메모\n", "# 메모\n\n추가 줄\n"), encoding="utf-8", newline="\n")
    code, out, _ = run(capsys, "answer-md", rid, "그 문장의 뜻")
    ls = lines_of(world, "docs/notes.md")
    k = ls.index("둘째 줄도 같은 문단.")
    assert code == 0 and ls[k + 1] == "" and ls[k + 2] == "> [!answer] 🤖 2ND · 이 문장?" and ls[k + 3] == "> 그 문장의 뜻" and ls[k + 4] == ""


def test_answer_md_code_fence(world, capsys):
    rid = req(world, "2nd", question="코드?", target={"kind": "md", "file": "docs/notes.md", "range": {"start_line": 10, "end_line": 10},
                                                    "text": "코드 줄"})
    run(capsys, "answer-md", rid, "답")
    ls = lines_of(world, "docs/notes.md")
    c = ls.index("코드 줄")
    assert ls[c + 1] == "```" and ls[c + 3] == "> [!answer] 🤖 2ND · 코드?"


def test_answer_md_table_row_and_header(world, capsys):
    rid = req(world, "2nd", question="나 의 값?", target={"kind": "md", "file": "docs/notes.md", "range": {"start_line": 16, "end_line": 16},
                                                      "text": "2", "table": {"line": 16, "col": 1}})
    code, out, _ = run(capsys, "answer-md", rid, "2 는 | 기호 포함\n둘째 줄")
    ls = lines_of(world, "docs/notes.md")
    r = ls.index("| 나 | 2 |")
    assert code == 0 and ls[r + 1] == "| 🤖 | 2 는 \\| 기호 포함 둘째 줄 |" and out.endswith(f":{r + 2}")
    rid = req(world, "2nd", question="머리?", target={"kind": "md", "file": "docs/notes.md", "range": {"start_line": 13, "end_line": 13},
                                                    "text": "열 A", "table": {"line": 13, "col": 0}})
    run(capsys, "answer-md", rid, "머리 답")
    ls = lines_of(world, "docs/notes.md")
    h = ls.index("| 열 A | 열 B |")
    assert ls[h + 1] == "|---|---|" and ls[h + 2] == "| 🤖 머리 답 |  |"


def test_answer_md_keeps_crlf_bom(world, capsys):
    p = world["work"] / "docs" / "crlf.md"
    p.write_bytes(b"\xef\xbb\xbf" + "# 제목\r\n\r\n본문\r\n".encode("utf-8"))
    rid = req(world, "2nd", question="q", target={"kind": "md", "file": "docs/crlf.md"})
    run(capsys, "answer-md", rid, "a")
    raw = p.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf") and b"\r\n" in raw and b"\n" not in raw.replace(b"\r\n", b"") and "> a".encode() in raw


def test_answer_code_below_and_top(world, capsys):
    rid = req(world, "2nd", question="왜 두 배?", target={"kind": "code", "file": "src/calc.py", "range": {"start_line": 6, "end_line": 7},
                                                      "text": "def calc(x):\n    return x * 2"})
    code, out, _ = run(capsys, "answer-code", rid, "요구가 두 배\n근거 README 3줄")
    ls = lines_of(world, "src/calc.py")
    assert code == 0 and ls[7] == "    # 🤖 2ND · 질문: 왜 두 배?" and ls[8] == "    # 요구가 두 배" and ls[9] == "    # 근거 README 3줄"
    rid = req(world, "2nd", question="파일 요지?", target={"kind": "code", "file": "src/calc.py"})
    run(capsys, "answer-code", rid, "계산 모듈")
    ls = lines_of(world, "src/calc.py")
    assert ls[0].startswith("#!") and ls[1].startswith("# -*- coding") and ls[2] == "# 🤖 2ND · 질문: 파일 요지?" and ls[3] == "# 계산 모듈"


def test_answer_code_comment_marks(world, capsys):
    for name, body, want in (("a.js", "let x = 1;\n", "// 🤖 2ND · 질문: q"), ("a.html", "<!DOCTYPE html>\n<p>x</p>\n", "<!-- 🤖 2ND · 질문: q -->"),
                             ("a.css", "p { color: red; }\n", "/* 🤖 2ND · 질문: q */"), ("a.sql", "select 1;\n", "-- 🤖 2ND · 질문: q")):
        (world["work"] / "src" / name).write_text(body, encoding="utf-8", newline="\n")
        rid = req(world, "2nd", question="q", target={"kind": "code", "file": f"src/{name}"})
        assert run(capsys, "answer-code", rid, "a")[0] == 0
        ls = lines_of(world, f"src/{name}")
        assert want in ls, (name, ls)
    assert lines_of(world, "src/a.html")[0] == "<!DOCTYPE html>"
    (world["work"] / "src" / "a.json").write_text("{}\n", encoding="utf-8")
    rid = req(world, "2nd", question="q", target={"kind": "code", "file": "src/a.json"})
    code, _, err = run(capsys, "answer-code", rid, "a")
    assert code == 1 and "answer-form" in err


def test_answer_form(world, capsys):
    rid = req(world, "2nd", question="이 표 의미?", view="code", target={"kind": "form", "file": "data/x.csv", "text": "a,b"})
    code, out, err = run(capsys, "answer-form", rid, "열 a 는 사번")
    assert code == 0, err
    sid = out.split(": ")[1].split(" ")[0]
    sv = json.loads((world["tmp"] / "sv" / "2nd" / f"{sid}.json").read_text(encoding="utf-8"))
    assert sv["mode"] == "explain" and sv["questions"][0]["body"] == "열 a 는 사번" and "data/x.csv" in sv["intro"]


def test_show_and_answer_note(world, capsys):
    # 책 스티커 — notes.json(책 폴더) · 키트 bookkit/notes.py 를 작업 폴더에 복사(answer-note 가 req.root/bookkit/notes.py 를 부름)
    kit_notes = HERE.parents[2] / "bookkit" / "notes.py"
    if not kit_notes.is_file():
        pytest.skip("bookkit/notes.py 없음")
    (world["work"] / "bookkit" / "books" / "b1").mkdir(parents=True)
    (world["work"] / "bookkit" / "notes.py").write_bytes(kit_notes.read_bytes())
    nf = world["work"] / "bookkit" / "books" / "b1" / "notes.json"
    nf.write_text(json.dumps([{"id": "ab12cd34", "doc": "b1", "ctx": "p3 | 1장 | 1-2 | «글» | b=1-개요", "text": "이 칸 뜻?"}],
                             ensure_ascii=False), encoding="utf-8")
    rid = req(world, "2nd", question="이 칸 뜻?", view="book", target={"kind": "note", "note": "ab12cd34", "notes_file": "bookkit/books/b1/notes.json",
                                                                     "doc": "b1", "book": "b1", "ctx": "p3 | 1장 | b=1-개요", "block": "1-개요"})
    code, out, err = run(capsys, "show", rid)
    assert code == 0 and "책: b1" in out and "블록 1-개요" in out and f"answer-note {rid}" in out, (out, err)
    code, out, err = run(capsys, "answer-note", rid, "개요 칸 — 과제 한 줄 요약\n근거: contracts 1-개요")
    note = json.loads(nf.read_text(encoding="utf-8"))[0]
    assert code == 0 and "답 달음" in out and note["answer"].startswith("개요 칸") and "\n근거" in note["answer"] and note.get("answer_ts"), (out, err)
    # 다른 종류 명령은 거부
    code, _, err = run(capsys, "answer-md", rid, "a")
    assert code == 1 and "answer-note" in err


def test_wrong_kind_and_bad_rid(world, capsys):
    rid = req(world, "2nd", question="q", target={"kind": "code", "file": "src/calc.py"})
    code, _, err = run(capsys, "answer-md", rid, "a")
    assert code == 1 and "answer-code" in err
    code, _, err = run(capsys, "show", "../etc")
    assert code == 1 and "형식 오류" in err
    rid = req(world, "main", nodes=[{"id": "t1"}])
    code, _, err = run(capsys, "answer-node", rid, "--short", "x")
    assert code == 1 and "2nd-magic" in err
