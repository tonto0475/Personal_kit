# lib/data 시험 — CSV 로더 · 품질 리포트 · 그룹 집계 · SPC (네트워크 없음)
import math

import numpy as np
import pandas as pd
import pytest

from lib.data.csv_load import read_csv_auto, split_unit
from lib.data.quality import group_defect_rate, quality_report, report_markdown
from lib.data.spc import cpk, individuals_limits, nelson_rules, xbar_limits
from src.core.errors import InputError

# 한글 열 이름 · 단위 괄호 · 앞뒤 공백이 섞인 CSV 본문
CSV_TEXT = " 로트 ,두께 (nm),온도[℃]\nA,10.5,25\nB,11.0,26\n"


# 세 인코딩으로 저장한 파일을 같은 표로 읽고, 쓴 인코딩을 돌려주는지
# enc: 저장 인코딩 / expected: 판별 결과로 기대하는 값
@pytest.mark.parametrize("enc, expected", [
    ("utf-8-sig", "utf-8-sig"), ("utf-8", "utf-8-sig"), ("cp949", "cp949")])
def test_read_csv_auto_encodings(tmp_path, enc, expected):
    # 시험 파일 경로
    path = tmp_path / "in.csv"
    path.write_text(CSV_TEXT, encoding=enc)
    # 읽은 표 / 쓴 인코딩 / 단위
    df, used, units = read_csv_auto(path)
    assert used == expected
    assert list(df.columns) == ["로트", "두께", "온도"]
    assert units == {"로트": "", "두께": "nm", "온도": "℃"}
    assert df["로트"].tolist() == ["A", "B"]


# 단위 분리 경계 — 괄호만 있는 이름은 단위로 떼지 않음
def test_split_unit_edges():
    assert split_unit("  압력(kPa) ") == ("압력", "kPa")
    assert split_unit("(nm)") == ("(nm)", "")
    assert split_unit("값") == ("값", "")


# 없는 파일 · 정리 후 중복 열은 입력 오류
def test_read_csv_auto_errors(tmp_path):
    with pytest.raises(InputError):
        read_csv_auto(tmp_path / "none.csv")
    # 정리하면 둘 다 «두께» 가 되는 파일
    path = tmp_path / "dup.csv"
    path.write_text("두께 (nm),두께(um)\n1,2\n", encoding="utf-8")
    with pytest.raises(InputError, match="중복"):
        read_csv_auto(path)


# 결측률 · 중복 행 · 범위 밖(한쪽 범위 포함) 개수와 마크다운 표
def test_quality_report():
    # 결측 1 · 중복 1 · 범위 밖 2(하한 밖 1 · 상한 밖 1)
    df = pd.DataFrame({"lot": ["A", "A", "B", "C"], "v": [1.0, 1.0, None, 50.0], "t": [0, 0, -5, 3]})
    # 리포트
    rep = quality_report(df, ranges={"v": (0, 10), "t": (0, None)})
    assert rep["rows"] == 4
    assert rep["duplicate_rows"] == 1
    assert rep["columns"]["v"] == {"missing": 1, "missing_pct": 25.0}
    assert rep["out_of_range"]["v"]["count"] == 1
    assert rep["out_of_range"]["t"]["count"] == 1
    # 마크다운 문자열
    md = report_markdown(rep)
    assert "| v | 1 | 25.0 | 0 ~ 10 | 1 |" in md
    assert "| t | 0 | 0.0 | 0 ~  | 1 |" in md
    with pytest.raises(InputError):
        quality_report(df, ranges={"없음": (0, 1)})


# 미측정 제외 / 포함 두 판 — 같은 데이터에서 불량률이 갈림
def test_group_defect_rate():
    # A: 불량 1 · 양품 1 · 미측정 2 / B: 전부 미측정
    df = pd.DataFrame({"lot": ["A", "A", "A", "A", "B"], "ng": [True, False, None, None, None]})
    # 미측정 제외 판
    ex = group_defect_rate(df, ["lot"], "ng", exclude_unmeasured=True).set_index("lot")
    assert ex.loc["A", "count"] == 4 and ex.loc["A", "measured"] == 2 and ex.loc["A", "ng"] == 1
    assert ex.loc["A", "ng_rate_pct"] == 50.0
    assert math.isnan(ex.loc["B", "ng_rate_pct"])
    # 미측정 포함 판
    inc = group_defect_rate(df, ["lot"], "ng", exclude_unmeasured=False).set_index("lot")
    assert inc.loc["A", "ng_rate_pct"] == 25.0
    assert inc.loc["B", "ng_rate_pct"] == 0.0
    with pytest.raises(InputError):
        group_defect_rate(df, ["lot"], "ng", exclude_unmeasured=None)


# 개별값 한계 — MR̄ = 2 → σ = 2/1.128
def test_individuals_limits():
    # 평균 11 · 이동 범위 전부 2
    lim = individuals_limits([10, 12, 10, 12])
    assert lim["center"] == 11
    assert lim["sigma"] == pytest.approx(2 / 1.128)
    assert lim["ucl"] == pytest.approx(11 + 3 * 2 / 1.128)
    with pytest.raises(InputError):
        individuals_limits([5, 5, 5])


# X-bar 한계 — n=2, R̄ = 2 → σ = 2/1.128, 한계 = 총평균 ± 3σ/√2
def test_xbar_limits():
    lim = xbar_limits([[10, 12], [11, 13], [9, 11]])
    assert lim["means"] == [11, 12, 10]
    assert lim["center"] == 11
    assert lim["ucl"] == pytest.approx(11 + 3 * (2 / 1.128) / math.sqrt(2))
    with pytest.raises(InputError):
        xbar_limits([[1, 2], [1, 2, 3]])


# 규칙 1 · 2 · 3 각각 한 번씩 걸리는 데이터
def test_nelson_rules():
    # 규칙1 — 4번 점만 3σ(=3) 밖
    assert nelson_rules([0, 1, -1, 0, 5], 0, 1)["rule1"] == [4]
    # 규칙2 — 9점 연속 위(0.5) → 9번째 점(위치 8)에서 처음, 10번째도 계속
    assert nelson_rules([0.5] * 10, 0, 1)["rule2"] == [8, 9]
    # 8점은 안 걸림
    assert nelson_rules([0.5] * 8, 0, 1)["rule2"] == []
    # 규칙3 — 6점 연속 증가(위치 5 에서 완성), 같은 값이 끼면 끊김
    assert nelson_rules([0, 0.1, 0.2, 0.3, 0.4, 0.5], 0, 1)["rule3"] == [5]
    assert nelson_rules([0, 0.1, 0.2, 0.2, 0.3, 0.4, 0.5], 0, 1)["rule3"] == []


# Cpk — 양쪽 · 한쪽만 · 규격 없음
def test_cpk():
    # 평균 10 · σ(ddof=1) = 1 인 값
    vals = [9, 10, 11]
    both = cpk(vals, usl=13, lsl=8)
    assert both["cpu"] == pytest.approx(1.0) and both["cpl"] == pytest.approx(2 / 3)
    assert both["cpk"] == pytest.approx(2 / 3) and not both["one_sided"]
    # 상한만
    upper = cpk(vals, usl=13)
    assert upper["cpk"] == pytest.approx(1.0) and upper["cpl"] is None and upper["one_sided"]
    # σ 직접 지정
    assert cpk(vals, lsl=7, sigma=0.5)["cpk"] == pytest.approx(2.0)
    with pytest.raises(InputError):
        cpk(vals)
    with pytest.raises(InputError):
        cpk([1, np.nan, 2], usl=5)
