# 그래프 갤러리 시험 — 함수 7개가 제목 · 단위 · 기준선을 옵션 dict 에 담는지 · 기준선 인자를 빼면 실패하는지 · PNG 저장
import sys
from pathlib import Path

import pytest

# 이 폴더 — charts 를 바로 import
sys.path.insert(0, str(Path(__file__).resolve().parent))

import charts  # noqa: E402
from src.core.errors import InputError  # noqa: E402

# 데모 데이터
D = charts.demo_data()


# 옵션 안 markLine 의 y 값 목록(계열 전부)
# opt: 그래프 옵션
def _mark_values(opt):
    return [m.get("yAxis", m.get("xAxis")) for s in opt["series"] for m in s.get("markLine", {}).get("data", [])]


# 축 있는 6종 — 제목 · 단위(세로축 이름) · 기준선이 옵션에 들어감
# make: (기준선) → 옵션 / unit: 기대 세로축 이름
@pytest.mark.parametrize("make, unit", [
    (lambda r: charts.bar_option(D["lines"], D["yield"], title="T", unit="%", ref_line=r), "%"),
    (lambda r: charts.line_option(D["days"], D["trend"], title="T", unit="개", ref_line=r), "개"),
    (lambda r: charts.control_option(D["days"], D["meas"], title="T", unit="µm", ref_line=r), "µm"),
    (lambda r: charts.scatter_option(D["pairs"], title="T", unit="mΩ", x_unit="°C", ref_line=r), "mΩ"),
    (lambda r: charts.bar_target_option(D["lines"], D["defect"], title="T", unit="%", ref_line=r), "%"),
])
def test_axis_charts(make, unit):
    # 기준선 있는 옵션
    opt = make(2.0)
    assert opt["title"]["text"] == "T"
    assert opt["yAxis"]["name"] == unit
    assert 2.0 in _mark_values(opt)


# 기준선 None 이면 기준선 없음(관리도는 CL · UCL · LCL 3개만)
def test_ref_line_none():
    assert _mark_values(charts.bar_option(["a"], [1], title="T", unit="%", ref_line=None)) == []
    assert len(_mark_values(charts.control_option(D["days"], D["meas"], title="T", unit="µm", ref_line=None))) == 3


# 제목 · 단위 · 기준선은 필수 — 빠지면 TypeError(호출하는 쪽이 None 을 명시적으로 써야 함)
def test_required_kwargs():
    with pytest.raises(TypeError, match="ref_line"):
        charts.bar_option(["a"], [1], title="T", unit="%")
    with pytest.raises(TypeError, match="unit"):
        charts.pie_option({"a": 1}, title="T", ref_line=None)


# 관리도 — 이탈 점(25번째)만 빨강 · 한계는 평균 ± 3σ
def test_control_out_point():
    # 관리 한계
    lim = charts.control_limits(D["meas"])
    assert lim["out"] == [24]
    assert lim["ucl"] == pytest.approx(lim["center"] + 3 * lim["sd"])
    # 점 목록
    data = charts.control_option(D["days"], D["meas"], title="T", unit="µm", ref_line=None)["series"][0]["data"]
    assert data[24]["itemStyle"]["color"] == charts.NG
    assert not isinstance(data[0], dict)


# 히스토그램 — 구간 수 · 개수 합 · 단위(가로축) · 규격선
def test_hist():
    # 옵션
    opt = charts.hist_option(D["dist"], title="T", unit="µm", ref_line=52.0, bins=16)
    assert len(opt["xAxis"]["data"]) == 16
    assert sum(opt["series"][0]["data"]) == len(D["dist"])
    assert opt["xAxis"]["name"] == "µm"
    assert _mark_values(opt) and opt["series"][0]["markLine"]["label"]["formatter"] == "규격 52.0µm"


# 파이 — 기준선 금지 · 판정 이름은 상태 색
def test_pie():
    # 옵션
    opt = charts.pie_option(D["share"], title="T", unit="개", ref_line=None)
    assert opt["series"][0]["data"][1]["itemStyle"]["color"] == charts.NG
    with pytest.raises(InputError, match="파이 그래프 기준선"):
        charts.pie_option(D["share"], title="T", unit="개", ref_line=1)


# 막대+목표선 — 목표 None 금지 · 목표 초과 막대만 빨강
def test_bar_target():
    with pytest.raises(InputError, match="목표선 값 없음"):
        charts.bar_target_option(["a"], [1], title="T", unit="%", ref_line=None)
    # 막대 색
    colors = [d["itemStyle"]["color"] for d in charts.bar_target_option(
        D["lines"], D["defect"], title="T", unit="%", ref_line=2.0)["series"][0]["data"]]
    assert colors.count(charts.NG) == 1 and colors[2] == charts.NG


# 길이가 다르면 입력 오류(그래프가 조용히 어긋나지 않게)
def test_length_mismatch():
    with pytest.raises(InputError, match="길이 불일치 \\(2 · 1\\)"):
        charts.bar_option(["a", "b"], [1], title="T", unit="%", ref_line=None)


# matplotlib PNG 두 종이 파일로 저장됨
def test_png(tmp_path):
    # 저장 경로
    bar = charts.png_bar(D["lines"], D["defect"], title="T", unit="%", ref_line=2.0, path=tmp_path / "b.png")
    ctl = charts.png_control(D["days"], D["meas"], title="T", unit="µm", ref_line=None, path=tmp_path / "c.png")
    assert bar.read_bytes()[:4] == b"\x89PNG" and ctl.stat().st_size > 1000
