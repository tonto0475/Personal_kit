# task_peek.py 시험 — 과제 파일 목록 · CSV 헤더 + 맨 위 행 표 · 키트 제외
#   python3 -m pytest -q .agents/skills/2nd
import subprocess
import sys
from pathlib import Path

TOOL = Path(__file__).resolve().parent / "task_peek.py"


def run(root, *args):
    p = subprocess.run([sys.executable, str(TOOL), str(root), *args], capture_output=True, text=True, encoding="utf-8")
    return p.returncode, p.stdout, p.stderr


def make_task(tmp_path):
    root = tmp_path / "home"
    (root / "uploads").mkdir(parents=True)
    (root / "README.md").write_text("# 과제\n설명\n", encoding="utf-8")
    rows = "\n".join(f"{i},이름{i},{i * 10}" for i in range(1, 21))
    (root / "uploads" / "people.csv").write_text("id,name,score\n" + rows + "\n", encoding="utf-8-sig")
    (root / "uploads" / "ko.csv").write_bytes("코드;값\nA;가\nB;나\n".encode("cp949"))
    # 키트 · 숨김은 빠져야 한다
    (root / "kit").mkdir()
    (root / "kit" / "secret.csv").write_text("x\n1\n", encoding="utf-8")
    (root / ".codex").mkdir()
    (root / ".codex" / "x.csv").write_text("x\n1\n", encoding="utf-8")
    return root


def test_list_and_tables(tmp_path):
    root = make_task(tmp_path)
    code, out, err = run(root)
    assert code == 0, err
    # 목록: 과제 파일 3개 · 키트 · 숨김 없음
    assert "| README.md |" in out and "| uploads/people.csv |" in out and "| uploads/ko.csv |" in out
    assert "kit/secret.csv" not in out and ".codex" not in out
    # people.csv: 헤더 + 5행(6행째 없음) · 줄 수 21
    assert "| id | name | score |" in out
    assert "| 5 | 이름5 | 50 |" in out and "| 6 | 이름6 |" not in out
    assert "| uploads/people.csv |" in out and "| 21 |" in out
    # cp949 · ; 구분자도 읽힌다
    assert "인코딩 cp949" in out and "| 코드 | 값 |" in out and "| A | 가 |" in out


def test_rows_option(tmp_path):
    root = make_task(tmp_path)
    code, out, _ = run(root, "--rows", "2")
    assert code == 0
    assert "| 2 | 이름2 | 20 |" in out and "| 3 | 이름3 |" not in out
