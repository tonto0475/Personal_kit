# readystart.py 시험 — ReadyStart.md 명령 · 준비 상태
#   python3 -m pytest -q .agents/skills/ready-start
import shlex
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOOL = HERE / "readystart.py"


def run(cwd, *args):
    p = subprocess.run([sys.executable, str(TOOL), *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8")
    return p.returncode, p.stdout, p.stderr


# 루트(git) 안에 kit/ — 대회 모양
def make_root(tmp_path):
    root = tmp_path / "home"
    (root / "kit" / "docs").mkdir(parents=True)
    (root / "kit" / "AGENTS.md").write_text("# 규칙\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    return root


def test_write_from_root_finds_kit(tmp_path):
    root = make_root(tmp_path)
    code, out, err = run(root, "write")
    assert code == 0, err
    kit = (root / "kit").resolve()
    text = (kit / "ReadyStart.md").read_text(encoding="utf-8")
    lines = text.splitlines()
    codex = [l for l in lines if l.startswith("codex ")]
    # 두 세션 · 순서 · 강도 · 끝의 시작 메시지(작은따옴표)
    # 2ND 는 «$2nd 파악시작» 으로 뜬다(허브 → 가볍게 훑기) · whoami 는 시작 메시지 앞부분 «$2nd» 로 찾는다
    assert [l.split(" --approve-for-me ", 1)[1] for l in codex] == ["'$main'", "'$2nd 파악시작'"]
    assert ["effort=high" in codex[0], "effort=medium" in codex[1]] == [True] * 2
    for l in codex:
        # 경로는 셸 따옴표가 붙을 수 있다(윈도우 경로의 \ 등) — shlex.quote 한 모양으로 비교
        assert f"-C {shlex.quote(str(kit))}" in l and f"--add-dir {shlex.quote(str(root.resolve()))}" in l and "--approve-for-me" in l
        assert "-c model_verbosity=high -c service_tier=fast" in l
        assert l.count("features.multi_agent_v2.") == 4 and "min_wait_timeout_ms=600000" in l
        assert "-c agents.max_concurrent_threads_per_session=8" in l
        assert "max_wait_timeout_ms=3600000" in l
    # devview 줄이 맨 앞 · 훅 설치가 그 줄에 · 준비 상태 절이 맨 아래
    first = next(i for i, l in enumerate(lines) if "devview/dv" in l.replace("\\", "/"))  # 윈도우에서 돌리면 \ 경로
    assert first < lines.index(codex[0]) and "install_hooks.sh" in lines[first]
    assert lines.index("## 준비 상태") > lines.index(codex[-1])
    assert lines[-1].endswith("⏳ 준비 중(git 이름 → git 등록 → config → 훅 → AGENTS · 스킬 → venv → envcheck → devview)")


def test_write_from_kit_and_status_append(tmp_path):
    root = make_root(tmp_path)
    kit = root / "kit"
    assert run(kit, "write")[0] == 0
    code, _, err = run(kit, "status", "git 등록", "🟢 커밋 abc1234")
    assert code == 0, err
    last = (kit / "ReadyStart.md").read_text(encoding="utf-8").splitlines()[-1]
    assert last.endswith("git 등록 — 🟢 커밋 abc1234")


def test_status_without_file_and_no_kit(tmp_path):
    root = make_root(tmp_path)
    code, _, err = run(root, "status", "venv", "🟢")
    assert code == 2 and "먼저 write" in err
    empty = tmp_path / "empty"
    empty.mkdir()
    code, _, err = run(empty, "write")
    assert code == 2 and "키트 못 찾음" in err
