# -*- coding: utf-8 -*-
"""ready-end 시험 — 임시 저장소에 문제를 심어 두고 잡는지 · 깨끗한 저장소는 통과하는지
실행: python3 -m pytest -q .agents/skills/ready-end
"""
import subprocess
import sys
from pathlib import Path

import pytest

TOOL = Path(__file__).resolve().with_name("ready_end.py")
# 시험에 쓰는 가짜 키 — 실제 키 모양이지만 아무 데도 안 쓰임
FAKE_KEY = "sk-proj-" + "A1b2C3d4E5f6G7h8I9j0K1l2"


def git(root, *args):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=root, check=True,
                   capture_output=True)


def run(root, *args, env=None):
    p = subprocess.run([sys.executable, str(TOOL), "--root", str(root), "--no-test", *args], capture_output=True,
                       text=True, encoding="utf-8", env=env)
    return p.returncode, p.stdout


def make(tmp_path, files):
    root = tmp_path / "task"
    root.mkdir()
    git(root, "init", "-q")
    git(root, "config", "user.name", "t")
    git(root, "config", "user.email", "t@t")
    for rel, body in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8", newline="\n")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "init")
    return root


CLEAN = {
    ".gitignore": ".env\n__pycache__/\n",
    ".env.example": "API_KEY=your-key-here\n",
    "requirements.txt": "httpx==0.28.1\n",
    "run.sh": "#!/usr/bin/env bash\npython3 -m src.app --host 0.0.0.0 --port 8080\n",
    "src/__init__.py": "",
    "src/app.py": "import os\nimport httpx\n\nKEY = os.environ.get('API_KEY')\n\n"
                  "def q(db, x):\n    return db.execute('select * from t where id = ?', (x,))\n",
}


# ======= 깨끗한 저장소 — 실패 없음 · 종료코드 0 =======
def test_clean_repo_passes(tmp_path):
    root = make(tmp_path, CLEAN)
    rc, out = run(root)
    assert rc == 0, out
    assert out.strip().splitlines()[-1] == "요약: 실패 없음", out


# ======= 문제를 심으면 각각 잡고 · 비밀값은 값을 찍지 않는다 =======
def test_planted_problems_found(tmp_path):
    files = dict(CLEAN)
    files.update({
        "src/app.py": CLEAN["src/app.py"] + f"\nTOKEN = '{FAKE_KEY}'\n"
                      "def bad(db, x):\n    return db.execute(f\"select * from t where id = {x}\")\n"
                      "def run(c):\n    import subprocess\n    subprocess.run(c, shell=True)\n"
                      "import yaml\n",
        "src/ui.py": "def main(ui):\n    ui.run(host='127.0.0.1', port=8080)  # DEV-ONLY 캡처\n",
        "data/raw.db": "x",
    })
    root = make(tmp_path, files)
    rc, out = run(root)
    assert rc == 1
    summary = out.strip().splitlines()[-1]
    for no in ("S1", "S3", "V1", "V3", "V6", "R1", "R4"):
        assert no in summary, (no, out)
    assert FAKE_KEY not in out                       # 값은 안 찍고 위치만
    assert "src/app.py:" in out and "pyyaml" in out


# ======= .env 값이 다른 파일에 그대로 · .env 가 무시 대상 아님 =======
def test_env_leak_and_ignore(tmp_path):
    files = dict(CLEAN)
    files[".gitignore"] = "__pycache__/\n"
    root = make(tmp_path, files)
    (root / ".env").write_text("DB_PASSWORD=hunter2hunter2\n", encoding="utf-8")
    (root / "src/conf.py").write_text("PW = 'hunter2hunter2'\n", encoding="utf-8")
    rc, out = run(root)
    assert rc == 1
    assert "S2" in out and "DB_PASSWORD" in out and "hunter2hunter2" not in out
    assert "S4" in out
    assert "추적 안 됨" in out                       # .env 가 git add . 로 들어갈 수 있다는 표시


# ======= 커밋 안 된 변경 · CRLF run.sh =======
def test_dirty_tree_and_crlf(tmp_path):
    files = dict(CLEAN)
    files["run.sh"] = "#!/usr/bin/env bash\r\npython3 -m src.app --host 0.0.0.0\r\n"
    root = make(tmp_path, files)
    (root / "src/app.py").write_text(CLEAN["src/app.py"] + "\n# 고침\n", encoding="utf-8")
    rc, out = run(root)
    assert "R2" in out and "R5" in out and "CRLF" in out


# ======= 대회 환경 — 홈 = 과제 저장소: 플랫폼 파일 · 환경변수 키 =======
def test_platform_files_and_env_key(tmp_path):
    import os
    files = dict(CLEAN)
    files[".bashrc"] = "export X=1\n"                      # 실수로 커밋된 플랫폼 파일
    root = make(tmp_path, files)
    (root / ".bash_history").write_text("ls\n", encoding="utf-8")       # 미추적 플랫폼 파일
    (root / ".literacy").mkdir()
    (root / ".literacy" / "provider-env.sh").write_text("export K=1\n", encoding="utf-8")
    key = "plat-" + "Zz9Yy8Xx7Ww6Vv5"
    (root / "src" / "llm.py").write_text(f"BASE = '{key}'\n", encoding="utf-8")
    env = dict(os.environ, OPENAI_API_KEY=key)
    rc, out = run(root, env=env)
    assert rc == 1
    assert "S5" in out and ".bashrc" in out and "git rm --cached" in out
    assert ".bash_history" in out and ".git/info/exclude" in out
    assert "OPENAI_API_KEY" in out and "src/llm.py:1" in out
    assert key not in out                                  # 값은 안 찍는다
    assert ".literacy/provider-env.sh:" not in out         # 플랫폼 폴더 안은 비밀값 검사에서 뺀다(위치만 S5 로)


# ======= git 이름 · 메일이 없으면 R0 =======
def test_git_identity_missing(tmp_path):
    import os
    root = make(tmp_path, CLEAN)
    git(root, "config", "--unset", "user.name")
    env = dict(os.environ, GIT_CONFIG_GLOBAL=str(tmp_path / "none"), GIT_CONFIG_NOSYSTEM="1")
    rc, out = run(root, env=env)
    assert "R0" in out.strip().splitlines()[-1]


# ======= git 저장소가 아니면 종료코드 2 =======
def test_not_repo(tmp_path):
    rc, out = run(tmp_path)
    assert rc == 2


# ======= 키트 = 작업 폴더 — 루트 kit/ 안의 앱은 점검하고 kit 안의 도구만 뺀다 =======
def test_kit_as_work_folder(tmp_path):
    files = {"README.md": "# 과제\n", "uploads/a.csv": "x\n",
             "kit/AGENTS.md": "# 규칙\n", "kit/.gitignore": ".env\n__pycache__/\ndevview/\nReadyStart.txt\n"}
    files.update({f"kit/{k}": v for k, v in CLEAN.items() if k != ".gitignore"})
    root = make(tmp_path, files)
    # kit 안 도구(무시 대상)에 위험한 줄 · 앱에 진짜 문제 하나
    (root / "kit" / "devview").mkdir()
    (root / "kit" / "devview" / "tool.py").write_text("eval(input())\n", encoding="utf-8")
    (root / "kit" / "ReadyStart.txt").write_text("codex resume x\n", encoding="utf-8")
    (root / "kit" / "src" / "bad.py").write_text("def f(x):\n    return eval(x)\n", encoding="utf-8")
    git(root, "add", "kit/src/bad.py")
    git(root, "commit", "-q", "-m", "bad")
    rc, out = run(root)
    assert "작업 폴더 kit" in out, out
    assert "V2" in out and "kit/src/bad.py" in out, out          # 작업 폴더 앱은 점검
    assert "devview/tool.py" not in out, out                    # 도구는 뺌
    assert "✗ S5" not in out and "✗ R5" not in out and "✗ R4" not in out, out   # kit 는 플랫폼이 아님 · run.sh · requirements 는 kit 기준


# ======= R7 커밋 추천 — 커밋된 코드가 import 하거나 커밋된 글이 경로를 적은 새 파일만 =======
def test_recommend_commits(tmp_path):
    files = {"kit/AGENTS.md": "# 규칙\n", "kit/.gitignore": ".env\n__pycache__/\n",
             "kit/docs/WORKLOG.md": "- 중복 요청 시험은 scripts/race/race_check.py 로\n"}
    files.update({f"kit/{k}": v for k, v in CLEAN.items() if k != ".gitignore"})
    files["kit/src/app.py"] = CLEAN["src/app.py"] + "from src.core.errors import Busy\n"
    root = make(tmp_path, files)
    for rel, body in {"kit/src/core/errors.py": "class Busy(Exception):\n    pass\n",
                      "kit/scripts/race/race_check.py": "print(1)\n",
                      "kit/src/db/unused.py": "x = 1\n"}.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    rc, out = run(root)
    r7 = [l for l in out.splitlines() if l.startswith("△ R7")]
    assert r7, out
    assert "kit/src/core/errors.py(kit/src/app.py 가 import)" in r7[0], r7
    assert "kit/scripts/race/race_check.py(kit/docs/WORKLOG.md 에 경로)" in r7[0], r7
    assert "unused.py" not in r7[0], r7
