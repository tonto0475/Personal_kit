# gitfiles.py 시험 — 임시 저장소에 커밋된 파일 · 새 파일 · 제외 파일 · 키트 · .venv 를 만들고 표를 본다
#   python3 -m pytest -q .agents/skills/ready-start/test_gitfiles.py
import subprocess
import sys
from pathlib import Path

TOOL = Path(__file__).with_name("gitfiles.py")


def put(p: Path, text="x\n"):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def run(root: Path, *args):
    r = subprocess.run([sys.executable, str(TOOL), "--repo", str(root), *args], capture_output=True, text=True, encoding="utf-8")
    return r.returncode, r.stdout


def test_table(tmp_path):
    root = tmp_path / "ws"
    put(root / "README.md")
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "add", "README.md"], check=True)
    subprocess.run(["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "init"], check=True)
    put(root / "docs" / "ADR.md")
    put(root / ".gitignore", "ReadyStart.txt\n.venv/\n")
    put(root / "kit" / "ReadyStart.txt")
    put(root / "kit" / "a" / "b.md")
    put(root / "kit" / "devview" / "x.js")
    put(root / "kit" / "devview" / "y.js")
    put(root / ".venv" / "lib" / "x.py")
    put(root / ".venv" / "lib" / "y.py")
    code, out = run(root)
    lines = out.splitlines()
    assert code == 0
    assert f"| 커밋됨 | {root / 'README.md'} |" in lines
    assert f"| 새 파일 | {root / 'docs' / 'ADR.md'} |" in lines
    assert f"| 새 파일 | {root / '.gitignore'} |" in lines
    # 키트 = 작업 폴더 — 키트 파일은 하나씩, 키트 안 도구 폴더만 한 줄(ReadyStart.txt 는 제외 쪽)
    assert f"| 새 파일 | {root / 'kit' / 'a' / 'b.md'} |" in lines
    assert f"| 새 파일 | {root / 'kit' / 'devview'}/ (폴더 · 파일 2개) |" in lines
    assert f"| 제외 | {root / 'kit' / 'ReadyStart.txt'} |" in lines
    assert f"| 제외 | {root / '.venv'}/ (폴더 · 파일 2개) |" in lines
    assert not any("x.py" in ln or "x.js" in ln for ln in lines)
    assert lines[-1] == "요약: 커밋됨 1줄 · 새 파일 4줄 · 제외 2줄"


def test_not_repo(tmp_path):
    code, out = run(tmp_path)
    assert code == 2 and "git 저장소가 아님" in out
