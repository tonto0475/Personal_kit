#!/usr/bin/env python3
# merge.py 시험 — 플랫폼 설정을 흉내 낸 임시 파일에 키트 설정을 넣어 보고 판정 · 보존 · 되돌림을 본다
#   python3 -m pytest -q scripts/codex_config
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

tomllib = pytest.importorskip("tomllib")
TOOL = Path(__file__).resolve().with_name("merge.py")
KIT = Path(__file__).resolve().parents[2] / ".codex" / "config.toml"
SECRET = "sk-plat-SECRET-123"
# 플랫폼 설정 흉내 — 최상위 키 · 공급자 표(비밀값) · 이미 있는 tui 표(다른 값 하나)
PLATFORM = f"""model = "gpt-6.1-sol"
model_provider = "probe-openai"

[model_providers.probe-openai]
name = "probe"
base_url = "https://proxy.example/v1"
api_key = "{SECRET}"

[tui]
mouse_scroll_speed = 3.0
"""


def run(target: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(TOOL), "--target", str(target), *args],
                          capture_output=True, encoding="utf-8", timeout=60)


def test_compare_only_changes_nothing(tmp_path):
    t = tmp_path / "config.toml"
    t.write_text(PLATFORM, encoding="utf-8")
    r = run(t)
    assert r.returncode == 0 and "비교만" in r.stdout
    assert t.read_text(encoding="utf-8") == PLATFORM
    assert "tui.mouse_scroll_speed" in r.stdout and "다름" in r.stdout
    assert SECRET not in r.stdout and "base_url" not in r.stdout


def test_apply_inserts_missing_keeps_platform_and_different(tmp_path):
    t = tmp_path / "config.toml"
    t.write_text(PLATFORM, encoding="utf-8")
    r = run(t, "--apply")
    assert r.returncode == 0, r.stderr
    after = tomllib.loads(t.read_text(encoding="utf-8"))
    kit = tomllib.loads(KIT.read_text(encoding="utf-8"))
    # 플랫폼 값 그대로
    assert after["model_provider"] == "probe-openai" and after["model_providers"]["probe-openai"]["api_key"] == SECRET
    # 다른 값은 바꾸지 않음
    assert after["tui"]["mouse_scroll_speed"] == 3.0
    # 없던 키트 키는 들어감
    assert after["check_for_update_on_startup"] == kit["check_for_update_on_startup"]
    assert after["features"]["computer_use"] is False
    assert after["tui"]["status_line"] == kit["tui"]["status_line"]
    assert after["tui"]["keymap"]["composer"]["submit"] == kit["tui"]["keymap"]["composer"]["submit"]
    assert list(tmp_path.glob("config.toml.bak_kit_*")), "백업 없음"
    assert SECRET not in r.stdout
    # 두 번째는 넣을 것 없음
    r2 = run(t, "--apply")
    assert r2.returncode == 0 and "넣을 것 없음" in r2.stdout


def test_no_target_file_creates_it(tmp_path):
    t = tmp_path / "sub" / "config.toml"
    r = run(t, "--apply")
    assert r.returncode == 0, r.stderr
    after = tomllib.loads(t.read_text(encoding="utf-8"))
    assert after["tui"]["mouse_scroll_speed"] == 8.0


def test_broken_target_untouched(tmp_path):
    t = tmp_path / "config.toml"
    t.write_text("[tui\nbroken", encoding="utf-8")
    r = run(t, "--apply")
    assert r.returncode == 2 and t.read_text(encoding="utf-8") == "[tui\nbroken"
