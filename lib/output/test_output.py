# lib/output 시험 — 한글 PNG · 마크다운 보고서 · utf-8-sig CSV (저장소 루트에서 실행 — 글꼴 경로가 루트 기준)
import os
import warnings

import pandas as pd
import pytest

from lib.output.report_out import (FONT_PATH, md_table, plt, save_csv, save_png, setup_korean_font,
                                   write_report)
from src.core.errors import InputError


# 한글 제목 · 축 · 음수 눈금 PNG — 글자 빠짐 경고 없이 저장되는지(글꼴이 안 먹으면 «Glyph missing» 경고)
def test_png_korean(tmp_path):
    assert setup_korean_font(FONT_PATH) == "Pretendard"
    # 그림 / 축
    fig, ax = plt.subplots()
    ax.plot([-1, 0, 1], [3, 1, 2])
    ax.set_title("설비별 불량률(2026-W43)")
    ax.set_ylabel("불량률 (%)")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        # 저장 경로
        path = save_png(fig, "불량률", out_dir=str(tmp_path / "out"))
    assert [str(w.message) for w in caught if "Glyph" in str(w.message)] == []
    assert path.endswith("불량률.png") and os.path.getsize(path) > 1000
    with open(path, "rb") as f:
        assert f.read(8) == b"\x89PNG\r\n\x1a\n"
    with pytest.raises(InputError, match="글꼴 없음"):
        setup_korean_font(str(tmp_path / "none.ttf"))


# 마크다운 표 — DataFrame · dict 목록 · 결측 · 세로줄
def test_md_table():
    # 표
    df = pd.DataFrame({"로트": ["A", "B|C"], "불량률(%)": [5.0, None]})
    assert md_table(df) == "| 로트 | 불량률(%) |\n|---|---|\n| A | 5.0 |\n| B\\|C |  |"
    assert md_table([{"a": 1, "b": 2}], columns=["b", "a"]) == "| b | a |\n|---|---|\n| 2 | 1 |"


# 보고서 — 제목 · 표 · 그림 상대 경로 · utf-8
def test_write_report(tmp_path):
    # 그림 파일 자리(내용은 시험과 무관)
    img = tmp_path / "out" / "chart.png"
    img.parent.mkdir()
    img.write_bytes(b"x")
    # 보고서 경로
    path = write_report(str(tmp_path / "out" / "report.md"), "주간 불량 보고", [
        ("h2", "요약"), ("text", "W43 불량률 4.2%"), ("table", [{"로트": "A", "불량": 1}]),
        ("image", str(img), "불량률 추이")])
    # 보고서 본문
    text = open(path, encoding="utf-8").read()
    assert text.startswith("# 주간 불량 보고\n\n## 요약\n\nW43 불량률 4.2%")
    assert "| 로트 | 불량 |" in text
    assert "![불량률 추이](chart.png)" in text
    with pytest.raises(InputError):
        write_report(str(tmp_path / "r.md"), "t", [("video", "x")])


# CSV — BOM 이 붙고 한글이 그대로, 행 번호 열 없음
def test_save_csv(tmp_path):
    # 저장 경로
    path = save_csv(pd.DataFrame({"로트": ["가"], "값": [1]}), str(tmp_path / "out" / "r.csv"))
    # 파일 바이트
    raw = open(path, "rb").read()
    assert raw.startswith(b"\xef\xbb\xbf")
    assert raw.decode("utf-8-sig").splitlines() == ["로트,값", "가,1"]
