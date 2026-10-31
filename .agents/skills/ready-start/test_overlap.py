#!/usr/bin/env python3
# overlap.py 시험 — 임시 폴더에 키트 · 과제 폴더를 만들고 실제로 실행해 종료코드 · 출력 줄로 판정
#   python3 -m pytest -q .agents/skills/ready-start
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

# 시험 대상 스크립트
TOOL = Path(__file__).resolve().with_name("overlap.py")


# 파일 하나 쓰기(폴더까지 만듦)
# p: 파일 / text: 내용
def put(p: Path, text: str = "x") -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


# 스크립트 실행 → (종료코드, 출력 글자)
# script: 실행할 overlap.py / cwd: 실행 폴더 / args: 인자
def run(script: Path, cwd: Path, *args: str) -> tuple:
    r = subprocess.run([sys.executable, str(script), *args], cwd=str(cwd),
                       capture_output=True, encoding="utf-8", timeout=60)
    return r.returncode, r.stdout + r.stderr


# 대상 안에 kit/ 를 두고 스크립트를 kit/.agents/skills/ready-start/ 로 복사 — 실제 쓰는 모양
# target: 과제 폴더 → 복사한 스크립트 경로
def install_kit(target: Path) -> Path:
    kit = target / "kit"
    put(kit / "AGENTS.md", "kit")
    put(kit / "docs" / "ADR.md", "kit")
    put(kit / "docs" / "WORKLOG.md", "kit")
    put(kit / ".agents" / "skills" / "survey" / "SKILL.md", "kit")
    put(kit / ".git" / "HEAD", "ref")
    script = kit / ".agents" / "skills" / "start" / "overlap.py"
    script.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(str(TOOL), str(script))
    return script


# 겹침 있음 — 같은 경로 파일 · 하위 AGENTS.md · 같은 이름 스킬 · 루트 참고 항목 · 키트 폴더 건너뜀
def test_overlap_found(tmp_path):
    target = tmp_path / "한글 과제 폴더"
    script = install_kit(target)
    put(target / "AGENTS.md", "task")
    put(target / "docs" / "ADR.md", "task-adr")
    put(target / "sub dir" / "AGENTS.md", "nested")
    put(target / ".agents" / "skills" / "survey" / "other.md")
    put(target / ".mcp.json", "{}")
    put(target / "node_modules" / "AGENTS.md")
    put(target / ".git" / "HEAD")
    code, out = run(script, target)
    assert code == 0, out
    lines = out.splitlines()
    assert "[1] 같은 상대 경로 파일 2개 (대상 쪽 크기 · 수정 시각)" in lines
    assert any(ln.startswith("  AGENTS.md — 4 B · ") for ln in lines)
    assert any(ln.startswith("  docs/ADR.md — 8 B · ") for ln in lines)
    # 대상 안 kit/ 자신과 node_modules 는 걷지 않음
    assert "[2] 대상 안 AGENTS.md 2개 (하위 폴더 것도 Codex 가 읽음)" in lines
    assert "  sub dir/AGENTS.md" in lines
    assert not any("kit/AGENTS.md" in ln or "node_modules" in ln for ln in lines)
    assert "  .agents/skills/survey/" in lines
    assert "  .mcp.json — 있음" in lines
    assert "  .codex — 없음" in lines
    # 키트 파일 5개(.git 제외: AGENTS · ADR · WORKLOG · SKILL · overlap.py) 중 겹침 2
    assert "요약: 겹침 2개 · 키트에만 있는 파일 3개" in lines
    assert lines[-1].startswith("다음: 겹치는 파일은 유저가 Codex 와 정한 뒤 직접 옮긴다")


# 겹침 없음 — 빈 과제 폴더
def test_overlap_none(tmp_path):
    target = tmp_path / "task"
    script = install_kit(target)
    put(target / "README.md", "task")
    code, out = run(script, target)
    assert code == 0, out
    lines = out.splitlines()
    assert "[1] 같은 상대 경로 파일 0개 (대상 쪽 크기 · 수정 시각)" in lines
    assert "[2] 대상 안 AGENTS.md 0개 (하위 폴더 것도 Codex 가 읽음)" in lines
    assert "[3] 같은 이름 스킬 폴더 0개 (대상 .agents/skills)" in lines
    assert "요약: 겹침 0개 · 키트에만 있는 파일 5개" in lines


# --kit · --target 지정 — 키트가 대상 밖에 있어도 동작
def test_overlap_explicit_args(tmp_path):
    kit = tmp_path / "kit src"
    put(kit / "docs" / "ADR.md")
    target = tmp_path / "task"
    put(target / "docs" / "ADR.md")
    code, out = run(TOOL, tmp_path, "--kit", str(kit), "--target", str(target))
    assert code == 0, out
    assert "요약: 겹침 1개 · 키트에만 있는 파일 0개" in out.splitlines()


# 같은 폴더 → 종료코드 2
def test_overlap_same_folder(tmp_path):
    put(tmp_path / "AGENTS.md")
    code, out = run(TOOL, tmp_path, "--kit", str(tmp_path), "--target", str(tmp_path))
    assert code == 2
    assert "키트와 대상이 같은 폴더" in out


# 없는 폴더 → 종료코드 2
def test_overlap_missing_folder(tmp_path):
    code, out = run(TOOL, tmp_path, "--kit", str(tmp_path), "--target", str(tmp_path / "없음"))
    assert code == 2
    assert "대상 폴더 없음" in out


# 아무것도 쓰지 않는다 — 실행 전후 파일 목록 · 내용 동일
def test_overlap_read_only(tmp_path):
    target = tmp_path / "task"
    script = install_kit(target)
    put(target / "AGENTS.md", "task")
    before = {p: p.read_bytes() for p in target.rglob("*") if p.is_file()}
    code, _ = run(script, target)
    after = {p: p.read_bytes() for p in target.rglob("*") if p.is_file()}
    assert code == 0
    assert before == after
