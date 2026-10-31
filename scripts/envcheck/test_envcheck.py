# -*- coding: utf-8 -*-
"""envcheck 시험 — 실행: python3 -m pytest -q scripts/envcheck"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import envcheck  # noqa: E402

HERE = Path(__file__).resolve().parent
REQ = """# 주석
nicegui==3.18.0
pandas==2.3.3; python_version < "3.11"
pandas==3.1.0; python_version >= "3.11"
numpy==2.4.6; python_version == "3.11"
"""


# ======= requirements 조건 해석 — 판마다 고정한 줄이 맞게 골라지나 =======
@pytest.mark.parametrize("ver, pandas, numpy", [((3, 10), "2.3.3", None), ((3, 11), "3.1.0", "2.4.6"),
                                                ((3, 14), "3.1.0", None)])
def test_parse_requirements(ver, pandas, numpy):
    got = dict(envcheck.parse_requirements(REQ, ver))
    assert got["nicegui"] == "3.18.0"
    assert got["pandas"] == pandas
    assert got.get("numpy") == numpy


def test_real_requirements_parse():
    # 패키지 requirements 가 판마다 정확히 한 줄씩 골라지는지
    text = (HERE.parents[1] / "requirements.txt").read_text(encoding="utf-8")
    for ver in [(3, 10), (3, 11), (3, 12), (3, 14)]:
        names = [n for n, _ in envcheck.parse_requirements(text, ver)]
        assert len(names) == len(set(names)), ver


# ======= pip 실패 분류 =======
@pytest.mark.parametrize("out, code", [
    ("error: externally-managed-environment", "PEP668"),
    ("ERROR: No matching distribution found for pandas==3.1.0", "VERS"),
    ("Connection to pypi.org timed out", "NET"),
    ("something else", "PIPFAIL"),
])
def test_classify_pip(out, code):
    assert envcheck.classify_pip(out) == code


# ======= 출력 모양 — 실패 · 정보만 줄로, 요약은 실패 번호 =======
def test_report_shape():
    envcheck.RESULTS[:] = [("A1", "info", "python 3.11"), ("A2", "ok", "NET"), ("B3", "fail", "AGPATH kit/")]
    lines = envcheck.report("사용자 터미널", "부모 프로세스에 codex 없음")
    assert lines[0] == "envcheck · 사용자 터미널(부모 프로세스에 codex 없음) · 3개 중 통과 1 · 실패 1"
    assert lines[1:3] == ["A1 python 3.11", "B3 AGPATH kit/"]
    assert lines[-1] == "요약: B3"
    envcheck.RESULTS.clear()


# ======= 실제 실행 — 흔적(임시 폴더)이 남지 않고 요약 줄이 나오나 =======
def test_run_leaves_no_trace(tmp_path):
    before = set(Path(envcheck.tempfile.gettempdir()).glob("envcheck_*"))
    p = subprocess.run([sys.executable, str(HERE / "envcheck.py"), "--no-install", "--where", "시험"],
                       capture_output=True, text=True, encoding="utf-8", cwd=str(HERE.parents[1]))
    assert p.returncode in (0, 1), p.stderr
    assert p.stdout.splitlines()[0].startswith("envcheck · 시험(인자) · ")
    assert any(l.startswith("요약: ") for l in p.stdout.splitlines())
    assert set(Path(envcheck.tempfile.gettempdir()).glob("envcheck_*")) == before


# ======= 실행 위치 — 부모 프로세스 이름에 codex 가 있으면 Codex 로 판별 =======
@pytest.mark.skipif(not Path("/proc/self/comm").exists(), reason="리눅스 /proc 전용")
def test_detect_where_parent(tmp_path):
    # 이름이 codex 인 실행 파일(= python 사본)이 envcheck 를 자식으로 부르게 한다
    fake = tmp_path / "codex"
    fake.symlink_to(sys.executable)
    code = ("import subprocess,sys;print(subprocess.run([sys.argv[1], '-c', "
            "'import sys;sys.path.insert(0,sys.argv[1]);import envcheck;print(envcheck.detect_where())', "
            "sys.argv[2]], capture_output=True, text=True).stdout)")
    p = subprocess.run([str(fake), "-c", code, sys.executable, str(HERE)], capture_output=True, text=True,
                       env={k: v for k, v in os.environ.items() if not k.startswith("CODEX_")})
    assert "('Codex', '부모 프로세스')" in p.stdout, p.stdout + p.stderr


# ======= 0단계 — python3 가 없으면 sh 가 혼자 결과를 낸다 =======
@pytest.mark.skipif(os.name == "nt" or not shutil.which("bash"), reason="리눅스 bash 전용")
def test_sh_without_python():
    p = subprocess.run(["/bin/bash", str(HERE / "envcheck.sh")], capture_output=True, text=True,
                       encoding="utf-8", env={"PATH": "/nonexistent"})
    assert p.returncode == 1
    assert "A0 NOPY" in p.stdout
    assert p.stdout.strip().splitlines()[-1] == "요약: A0"
