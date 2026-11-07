# skillcheck.py 시험 — 가짜 키트 · 가짜 CODEX_HOME · 가짜 저장소로 같음 · 빠짐 · 다름 · 저장소 루트에서 읽힘
#   python3 -m pytest -q .agents/skills/ready-start
import os
import subprocess
import sys
from pathlib import Path

TOOL = Path(__file__).with_name("skillcheck.py")


# 스킬 폴더 하나 만들기
def make(root: Path, name: str, body: str = "본문"):
    d = root / name
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(body, encoding="utf-8")


def run(tmp_path, kit, repo):
    env = dict(os.environ, CODEX_HOME=str(tmp_path / "codex"), PYTHONUTF8="1")
    r = subprocess.run([sys.executable, str(TOOL), "--kit", str(kit), "--repo", str(repo)],
                       capture_output=True, text=True, encoding="utf-8", env=env)
    return r.returncode, r.stdout


def test_same_missing_diff(tmp_path):
    kit = tmp_path / "kit"
    for n in ("a", "b", "c"):
        make(kit / ".agents" / "skills", n)
    codex = tmp_path / "codex" / "skills"
    make(codex, "a")
    make(codex, "b", "옛 본문")
    repo = tmp_path / "repo"
    repo.mkdir()
    code, out = run(tmp_path, kit, repo)
    assert code == 1
    assert "같음 | a" in out and "다름 | b" in out and "빠짐 | c" in out


def test_read_from_repo_root(tmp_path):
    # 키트를 과제 폴더 맨 위에 풀면 키트 = 저장소 루트 · ~/.codex/skills 가 없어도 같음
    repo = tmp_path / "repo"
    make(repo / ".agents" / "skills", "a")
    code, out = run(tmp_path, repo, repo)
    assert code == 0, out
    assert "같음 | a" in out and "전부 같게" in out


def test_no_place(tmp_path):
    kit = tmp_path / "kit"
    make(kit / ".agents" / "skills", "a")
    repo = tmp_path / "repo"
    repo.mkdir()
    code, out = run(tmp_path, kit, repo)
    assert code == 2


def test_duplicate_reported_not_failed(tmp_path):
    # 같은 이름이 ~/.codex/skills 와 저장소 루트 둘 다에 있으면 «중복» 보고만(종료코드는 같음 기준 · 지우지 않음)
    repo = tmp_path / "repo"
    make(repo / ".agents" / "skills", "a")
    make(tmp_path / "codex" / "skills", "a")
    code, out = run(tmp_path, repo, repo)
    assert code == 0, out
    assert "중복 | a" in out and "유저 판단" in out
    assert (tmp_path / "codex" / "skills" / "a" / "SKILL.md").is_file()



def test_read_from_kit_as_work_folder(tmp_path):
    # 키트 = 작업 폴더 — Codex 를 <루트>/kit 에서 띄우면 kit/.agents/skills 가 읽히는 곳
    repo = tmp_path / "repo"
    kit = repo / "kit"
    make(kit / ".agents" / "skills", "a")
    env = dict(os.environ, CODEX_HOME=str(tmp_path / "codex"), PYTHONUTF8="1")
    r = subprocess.run([sys.executable, str(TOOL), "--kit", str(kit), "--repo", str(repo)], cwd=kit,
                       capture_output=True, text=True, encoding="utf-8", env=env)
    assert r.returncode == 0, r.stdout
    assert "같음 | a" in r.stdout
