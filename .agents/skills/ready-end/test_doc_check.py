#!/usr/bin/env python3
# doc_check.py 시험 — 임시 폴더에 git 저장소를 만들고 경우별로 실행해 종료코드 · 출력 줄로 판정
#   python3 -m pytest -q .agents/skills/ready-end
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# 시험 대상 스크립트
TOOL = Path(__file__).resolve().with_name("doc_check.py")

# 깨끗한 결정 문서 — 진행 표 커밋 칸은 {h} 로 채움
ADR = """# ADR

| 번호 | 섹션 | 커밋 |
|------|------|------|
| 1-1  | 시작 | {h} |
| 1-2  | 화면 | — |

## 1-1

> [!warning] ❇️ 수정 범위
> - src/app.py — main
> - 생성 예정 파일
> 	- (없음)
> > 🚹

- 자리 표시는 건너뜀: src/<모듈>.py · tests/test_*.py · docs/(이름).md
- 경로: src/app.py 와 tests/test_app.py 를 본다
- 🤖 재시도 간격은? 추천: 1초
> > 🚹 1초로
- 🤖 화면은?
> > 🚹
"""


# 파일 하나 쓰기(폴더까지 만듦)
# p: 파일 / text: 내용
def put(p: Path, text: str = "x") -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8", newline="\n")


# git 실행 → 표준 출력
# repo: 저장소 / args: git 인자
def git(repo: Path, *args: str) -> str:
    r = subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "core.autocrlf=false",
                        "-C", str(repo), *args], capture_output=True, encoding="utf-8", check=True)
    return r.stdout.strip()


# 전부 담아 커밋 → 커밋 해시
# repo: 저장소 / msg: 메시지
def commit(repo: Path, msg: str) -> str:
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", msg)
    return git(repo, "rev-parse", "HEAD")


# doc_check 실행 → (종료코드, 출력 줄 목록)
# repo: 실행 폴더 / args: 인자
def run(repo: Path, *args: str) -> tuple:
    r = subprocess.run([sys.executable, str(TOOL), *args], cwd=str(repo),
                       capture_output=True, encoding="utf-8", timeout=60)
    return r.returncode, (r.stdout + r.stderr).splitlines()


# 깨끗한 저장소 — 커밋 2개(두 번째에 첫 커밋 해시를 진행 표에 적음)
# tmp: 임시 폴더 / name: 저장소 폴더 이름 → 저장소 경로
def clean_repo(tmp: Path, name: str = "repo") -> Path:
    repo = tmp / name
    repo.mkdir()
    git(repo, "init", "-q")
    put(repo / "AGENTS.md", "- docs/ADR.md · docs/WORKLOG.md\n")
    put(repo / "src" / "app.py", "print(1)\n")
    put(repo / "tests" / "test_app.py", "def test_a():\n    pass\n")
    put(repo / "docs" / "WORKLOG.md", "# 작업 기록\n- 🚹 첫 지시: 시작\n")
    put(repo / "docs" / "ADR.md", ADR.format(h="—"))
    first = commit(repo, "first")
    put(repo / "docs" / "ADR.md", ADR.format(h=first[:7]))
    commit(repo, "second")
    return repo


# 깨끗한 저장소 → 0
def test_clean(tmp_path):
    repo = clean_repo(tmp_path)
    code, lines = run(repo)
    assert code == 0, lines
    assert lines[-1] == "문제 없음 — 종료코드 0"
    assert "  통과 — 문서 경로" in lines and "  통과 — 커밋 해시" in lines
    assert "  통과 — 고아 문서" in lines and "  통과 — 🚹 줄" in lines


# 없는 경로 → 1 · «파일:줄 — 경로» · 생성 예정 목록 표시
def test_missing_path(tmp_path):
    repo = clean_repo(tmp_path)
    text = (repo / "docs" / "ADR.md").read_text(encoding="utf-8")
    text = text.replace("> \t- (없음)", "> \t- src/new_mod.py") + "- 설정은 config/app.yaml 을 읽는다\n"
    put(repo / "docs" / "ADR.md", text)
    code, lines = run(repo)
    assert code == 1, lines
    no_new = next(i for i, ln in enumerate(text.splitlines(), 1) if "src/new_mod.py" in ln)
    no_cfg = next(i for i, ln in enumerate(text.splitlines(), 1) if "config/app.yaml" in ln)
    assert "  문제 2건 — 문서 경로" in lines
    assert f"    docs/ADR.md:{no_new} — src/new_mod.py (생성 예정 목록)" in lines
    assert f"    docs/ADR.md:{no_cfg} — config/app.yaml" in lines
    assert lines[-1] == "문제 2건 — 종료코드 1"


# 가짜 해시 → 1
def test_fake_hash(tmp_path):
    repo = clean_repo(tmp_path)
    text = (repo / "docs" / "ADR.md").read_text(encoding="utf-8").replace("| — |", "| deadbee |")
    put(repo / "docs" / "ADR.md", text)
    code, lines = run(repo)
    assert code == 1, lines
    assert "  문제 1건 — 커밋 해시" in lines
    assert "    docs/ADR.md:6 — deadbee" in lines


# 고아 문서 → 1 · examples 아래는 점검 밖
def test_orphan(tmp_path):
    repo = clean_repo(tmp_path)
    put(repo / "docs" / "LOST.md", "# 아무도 안 가리킴\n")
    put(repo / "docs" / "examples" / "EX.md", "# 예시\n")
    code, lines = run(repo)
    assert code == 1, lines
    assert "  문제 1건 — 고아 문서" in lines
    assert "    docs/LOST.md" in lines


# 🚹 줄 지움 → 1 · «커밋 짧은해시 · 파일 · 사라진 줄»
def test_user_line_removed(tmp_path):
    repo = clean_repo(tmp_path)
    text = (repo / "docs" / "ADR.md").read_text(encoding="utf-8").replace("> > 🚹 1초로\n", "")
    put(repo / "docs" / "ADR.md", text)
    head = commit(repo, "ai edit")
    code, lines = run(repo)
    assert code == 1, lines
    assert "  문제 1건 — 🚹 줄" in lines
    assert f"    {head[:7]} · docs/ADR.md · > > 🚹 1초로" in lines
    assert any("유저가 직접 고친 거면 무시" in ln for ln in lines)


# 🚹 줄 글자 바꿈 → 1(같은 글자로 남아야 통과)
def test_user_line_changed(tmp_path):
    repo = clean_repo(tmp_path)
    put(repo / "docs" / "WORKLOG.md", "# 작업 기록\n- 🚹 첫 지시: 시작함\n")
    commit(repo, "ai edit")
    code, lines = run(repo)
    assert code == 1, lines
    assert any(ln.endswith("· docs/WORKLOG.md · - 🚹 첫 지시: 시작") for ln in lines)


# 빈 답 칸 채움 · AI 줄 속 출처 표시(🚹 동의) 수정 → 0
def test_fill_empty_slot(tmp_path):
    repo = clean_repo(tmp_path)
    text = (repo / "docs" / "ADR.md").read_text(encoding="utf-8")
    text = text.replace("- 🤖 화면은?\n> > 🚹\n", "- 🤖 화면은?\n> > 🚹 표 하나로\n")
    put(repo / "docs" / "ADR.md", text + "- 🟢 결정 — 1초(🚹 동의)\n")
    commit(repo, "fill")
    put(repo / "docs" / "ADR.md", text + "- 🟢 결정 — 1초(🚹 동의) → 2회차에서 바뀜\n")
    commit(repo, "ai mark")
    code, lines = run(repo)
    assert code == 0, lines
    assert lines[-1] == "문제 없음 — 종료코드 0"


# 수정 범위 콜아웃 안 🚹 승인 줄이 다음 회차에 사라짐 → 0
def test_scope_callout_rewritten(tmp_path):
    repo = clean_repo(tmp_path)
    path = repo / "docs" / "ADR.md"
    put(path, path.read_text(encoding="utf-8").replace("> > 🚹\n\n- 자리", "> > 🚹 승인\n\n- 자리"))
    commit(repo, "approve")
    put(path, path.read_text(encoding="utf-8").replace(
        "> [!warning] ❇️ 수정 범위", "> [!success] ❇️ 수정 범위").replace("> > 🚹 승인\n", "> > 🚹\n"))
    commit(repo, "next round")
    code, lines = run(repo)
    assert code == 0, lines


# --since — 그 뒤 커밋만 본다
def test_since(tmp_path):
    repo = clean_repo(tmp_path)
    put(repo / "docs" / "WORKLOG.md", "# 작업 기록\n")
    commit(repo, "user removed own line")
    mark = git(repo, "rev-parse", "HEAD")
    code, lines = run(repo)
    assert code == 1, lines
    code2, lines2 = run(repo, "--since", mark)
    assert code2 == 0, lines2


# git 저장소 아님 → 2
def test_not_git(tmp_path):
    folder = tmp_path / "plain"
    put(folder / "docs" / "ADR.md", "# x\n")
    code, lines = run(folder)
    assert code == 2, lines
    assert any("git 저장소 아님" in ln for ln in lines)


# 한글 · 공백 경로 — 저장소 폴더 · 문서 이름 · 소스 경로 모두 한글
def test_korean_paths(tmp_path):
    repo = clean_repo(tmp_path, "한글 저장소 폴더")
    put(repo / "src" / "모듈.py", "x = 1\n")
    put(repo / "docs" / "설계.md", "# 설계\n- src/모듈.py 와 src/없는모듈.py\n")
    put(repo / "AGENTS.md", "- docs/ADR.md · docs/WORKLOG.md · docs/설계.md\n")
    commit(repo, "korean")
    code, lines = run(repo)
    assert code == 1, lines
    assert "    docs/설계.md:2 — src/없는모듈.py" in lines
    assert "  통과 — 고아 문서" in lines
    # --root 로 다른 폴더에서 실행
    code2, lines2 = run(tmp_path, "--root", str(repo))
    assert code2 == 1 and lines2[-1] == "문제 1건 — 종료코드 1"


# 아무것도 쓰지 않는다 — 실행 전후 작업 트리 · git 상태 동일
def test_read_only(tmp_path):
    repo = clean_repo(tmp_path)
    before = git(repo, "status", "--porcelain", "--ignored")
    run(repo)
    assert git(repo, "status", "--porcelain", "--ignored") == before == ""
