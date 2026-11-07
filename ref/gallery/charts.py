# 그래프 갤러리 — ECharts 옵션 함수 7개 + 그래프 카드(오른쪽 요약 숫자) + matplotlib PNG 2개 + 데모 페이지
#   쓰는 법: 필요한 함수만 src/ui 로 복사. 모든 그래프 함수는 제목 · 단위 · 기준선(없으면 None)을 키워드로 반드시 받음
#   실행(데모): python3 ref/gallery/charts.py → http://<주소>:<PORT 또는 3000>/
import os
import sys
from pathlib import Path

import numpy as np

# 저장소 루트 — 이 파일을 직접 실행해도 src 를 찾게 sys.path 앞에 추가
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.core.errors import InputError  # noqa: E402
from src.ui.theme import (  # noqa: E402
    ACCENT, BG_PANEL, BORDER, FONT, FONT_FILE, NG, OK, SPEC_LINE, TEXT, TEXT_DIM, WAIT, echart_base)

# 관리 한계 폭 — 평균 ± 3 표준편차(슈하트 관리도 기본)
SIGMA_K = 3
# 히스토그램 기본 구간 수
DEFAULT_BINS = 10
# 상태 이름 → 색 — 파이 · 막대 항목 이름이 판정 값이면 배지와 같은 색
STATUS_COLORS = {"OK": OK, "NG": NG, "대기": WAIT}


# ===== 공통 조각 =====

# 길이 확인 — 두 목록 길이가 다르면 입력 오류(그래프가 조용히 어긋나는 것 방지)
# a: 첫 목록 / b: 둘째 목록 / what: 오류 문구 앞머리
def _same_len(a, b, what):
    if len(a) != len(b):
        raise InputError("{} 길이 불일치 ({} · {})".format(what, len(a), len(b)))


# 기준선 markLine — ref_line 이 None 이면 빈 dict(선 없음)
# ref_line: 기준선 값 또는 None / unit: 단위 / name: 선 이름
def _mark_line(ref_line, unit, name="기준"):
    if ref_line is None:
        return {}
    return {"markLine": {
        "symbol": "none", "silent": True,
        "lineStyle": {"color": SPEC_LINE, "type": "dashed", "width": 1.5},
        "label": {"color": SPEC_LINE, "position": "insideEndTop", "formatter": "{} {}{}".format(name, ref_line, unit)},
        "data": [{"yAxis": ref_line}],
    }}


# 축 · 제목 · 여백 공통 옵션
# title: 제목 / unit: 값 축 단위 / x_name: 가로축 이름
def _frame(title, unit, x_name=""):
    # 옵션 dict — 테마 바탕 위에 덮어씀
    opt = echart_base()
    opt.update({
        "title": {"text": title, "left": 0, "textStyle": {"color": TEXT, "fontSize": 15, "fontWeight": 600}},
        "tooltip": {"trigger": "axis"},
        "grid": {"left": 56, "right": 24, "top": 76, "bottom": 36},
        "xAxis": {"type": "category", "name": x_name, "axisLine": {"lineStyle": {"color": BORDER}},
                  "axisLabel": {"color": TEXT_DIM}},
        "yAxis": {"type": "value", "name": unit, "nameTextStyle": {"color": TEXT_DIM},
                  "axisLabel": {"color": TEXT_DIM}, "splitLine": {"lineStyle": {"color": BORDER, "type": "dashed"}}},
    })
    return opt


# ===== 그래프 옵션 함수 7개 =====

# 1. 막대 — 항목별 값 비교
# categories: 항목 이름 / values: 값 / title: 제목 / unit: 단위 / ref_line: 기준선 값 또는 None
def bar_option(categories, values, *, title, unit, ref_line):
    _same_len(categories, values, "막대 항목 · 값")
    # 옵션
    opt = _frame(title, unit)
    opt["xAxis"]["data"] = list(categories)
    opt["series"] = [{"type": "bar", "name": title, "data": list(values), "barMaxWidth": 36,
                      "itemStyle": {"color": ACCENT}, **_mark_line(ref_line, unit)}]
    return opt


# 2. 선(추이) — 시간 순 변화 · 계열 여럿
# x: 가로축 값(시각 · 날짜) / series: {계열 이름: 값 목록} / title · unit · ref_line: 위와 같음
def line_option(x, series, *, title, unit, ref_line):
    # 옵션
    opt = _frame(title, unit)
    opt["xAxis"]["data"] = list(x)
    opt["xAxis"]["boundaryGap"] = False
    opt["legend"] = {"top": 0, "right": 0, "textStyle": {"color": TEXT_DIM}}
    opt["series"] = []
    # 계열 번호 · 이름 · 값
    for i, (name, values) in enumerate(series.items()):
        _same_len(x, values, "선 '{}' 가로축 · 값".format(name))
        # 계열 하나 — 기준선은 첫 계열에만(같은 선이 겹쳐 그려지지 않게)
        s = {"type": "line", "name": name, "data": list(values), "showSymbol": False, "smooth": False}
        if i == 0:
            s.update(_mark_line(ref_line, unit))
        opt["series"].append(s)
    return opt


# 관리 한계 — 중심선 · UCL · LCL(평균 ± SIGMA_K 표준편차) · 이탈 점 번호
# values: 측정값 목록
def control_limits(values):
    if len(values) < 2:
        raise InputError("관리도 측정값 부족 ({}개 · 2개 이상 필요)".format(len(values)))
    # 측정값 배열
    arr = np.asarray(values, dtype=float)
    # 중심선 · 표준편차(표본)
    center = float(arr.mean())
    sd = float(arr.std(ddof=1))
    # 관리 상한 · 하한
    ucl = center + SIGMA_K * sd
    lcl = center - SIGMA_K * sd
    # 이탈 점 번호
    out_idx = [int(i) for i in np.where((arr > ucl) | (arr < lcl))[0]]
    return {"center": center, "ucl": ucl, "lcl": lcl, "sd": sd, "out": out_idx}


# 3. 관리도(SPC) — 중심선 · UCL · LCL · 이탈 점 빨강
# x: 표본 번호 · 시각 / values: 측정값 / limits: control_limits 결과(None 이면 values 로 계산 — 기준 기간을 따로 잡을 때 넘김)
# title · unit: 위와 같음 / ref_line: 규격선 값 또는 None(관리 한계와 별개)
def control_option(x, values, *, title, unit, ref_line, limits=None):
    _same_len(x, values, "관리도 가로축 · 값")
    # 관리 한계
    lim = limits if limits is not None else control_limits(values)
    # 점 목록 — 이탈 점만 빨강 · 크게
    data = [{"value": v, "itemStyle": {"color": NG}, "symbolSize": 9} if i in lim["out"] else v
            for i, v in enumerate(values)]
    # 한계선 3개 — 이름 · 값 · 색 · 선 모양
    lines = [("UCL", lim["ucl"], NG, "dashed"), ("CL", lim["center"], TEXT_DIM, "solid"),
             ("LCL", lim["lcl"], NG, "dashed")]
    # 옵션
    opt = _frame(title, unit)
    opt["xAxis"]["data"] = list(x)
    # 세로축 범위 — 0 부터가 아니라 값 · 한계선 · 규격선이 모두 보이는 범위(한계선 사이가 눌리지 않게)
    edge = list(values) + [lim["ucl"], lim["lcl"]] + ([] if ref_line is None else [ref_line])
    # 여백 — 범위의 8%
    pad = (max(edge) - min(edge)) * 0.08 or 1
    opt["yAxis"]["min"] = round(min(edge) - pad, 3)
    opt["yAxis"]["max"] = round(max(edge) + pad, 3)
    # 범위 끝 눈금 숫자 숨김 — 여백 값(54.695 같은 끝수)이 찍히지 않게
    opt["yAxis"]["axisLabel"].update({"showMinLabel": False, "showMaxLabel": False})
    opt["series"] = [{
        "type": "line", "name": title, "data": data, "symbol": "circle", "symbolSize": 5,
        "lineStyle": {"color": ACCENT, "width": 1.5}, "itemStyle": {"color": ACCENT},
        "markLine": {"symbol": "none", "silent": True, "data": [
            {"yAxis": round(val, 3), "lineStyle": {"color": color, "type": kind},
             "label": {"color": color, "position": "insideEndTop", "formatter": "{} {:.3g}".format(name, val)}}
            for name, val, color, kind in lines]},
    }]
    if ref_line is not None:
        opt["series"][0]["markLine"]["data"].append(
            {"yAxis": ref_line, "lineStyle": {"color": SPEC_LINE, "type": "dotted"},
             "label": {"color": SPEC_LINE, "position": "insideEndTop", "formatter": "규격 {}{}".format(ref_line, unit)}})
    return opt


# 4. 산점도 — 두 값의 관계
# points: [(x, y), ...] / x_unit: 가로축 단위 / title · unit(세로축 단위) · ref_line(세로 기준) : 위와 같음
def scatter_option(points, *, title, unit, x_unit, ref_line):
    # 옵션
    opt = _frame(title, unit, x_unit)
    opt["yAxis"]["scale"] = True
    opt["xAxis"] = dict(opt["yAxis"], name=x_unit)
    opt["tooltip"] = {"trigger": "item"}
    opt["series"] = [{"type": "scatter", "name": title, "data": [list(p) for p in points], "symbolSize": 7,
                      "itemStyle": {"color": ACCENT, "opacity": 0.8}, **_mark_line(ref_line, unit)}]
    return opt


# 5. 히스토그램 — 값 분포(구간별 개수)
# values: 측정값 / bins: 구간 수 / title · unit(측정값 단위) · ref_line(가로 위치 = 규격 값) : 위와 같음
def hist_option(values, *, title, unit, ref_line, bins=DEFAULT_BINS):
    if len(values) == 0:
        raise InputError("히스토그램 측정값 없음")
    # 구간별 개수 · 구간 경계
    counts, edges = np.histogram(np.asarray(values, dtype=float), bins=bins)
    # 구간 이름 — «시작~끝»
    labels = ["{:.3g}~{:.3g}".format(edges[i], edges[i + 1]) for i in range(len(counts))]
    # 옵션
    opt = _frame(title, "개수", unit)
    opt["xAxis"]["data"] = labels
    opt["series"] = [{"type": "bar", "name": title, "data": [int(c) for c in counts], "barCategoryGap": "2%",
                      "itemStyle": {"color": ACCENT}}]
    if ref_line is not None:
        # 기준 값이 든 구간 번호 — 범위 밖이면 양 끝
        idx = int(np.clip(np.searchsorted(edges, ref_line, side="right") - 1, 0, len(counts) - 1))
        opt["series"][0]["markLine"] = {
            "symbol": "none", "silent": True, "lineStyle": {"color": SPEC_LINE, "type": "dashed", "width": 1.5},
            "label": {"color": SPEC_LINE, "formatter": "규격 {}{}".format(ref_line, unit)},
            "data": [{"xAxis": labels[idx]}]}
    return opt


# 6. 파이 — 구성 비율(합이 의미 있을 때만)
# items: {항목 이름: 값} / title · unit : 위와 같음 / ref_line: 파이는 기준선이 없어 반드시 None
def pie_option(items, *, title, unit, ref_line):
    if ref_line is not None:
        raise InputError("파이 그래프 기준선 지정 불가 (ref_line={})".format(ref_line))
    # 옵션 — 축 없음
    opt = echart_base()
    opt.update({
        "title": {"text": title, "left": 0, "textStyle": {"color": TEXT, "fontSize": 15, "fontWeight": 600}},
        "tooltip": {"trigger": "item", "formatter": "{{b}}: {{c}}{} ({{d}}%)".format(unit)},
        "legend": {"orient": "vertical", "right": 0, "top": "middle", "textStyle": {"color": TEXT_DIM}},
        "series": [{"type": "pie", "name": title, "radius": ["40%", "68%"], "center": ["40%", "55%"],
                    "itemStyle": {"borderColor": BG_PANEL, "borderWidth": 2},
                    "label": {"color": TEXT, "formatter": "{b} {d}%"},
                    "data": [{"name": k, "value": v, **({"itemStyle": {"color": STATUS_COLORS[k]}} if k in STATUS_COLORS else {})}
                             for k, v in items.items()]}],
    })
    return opt


# 7. 막대 + 목표선 — 목표를 넘은 막대 빨강(표의 «목표 초과 빨강» 규칙과 같음)
# categories · values · title · unit : 위와 같음 / ref_line: 목표 값(이 그래프는 None 불가)
def bar_target_option(categories, values, *, title, unit, ref_line):
    if ref_line is None:
        raise InputError("목표선 값 없음 (막대+목표선은 ref_line 필수)")
    # 옵션 — 막대 그래프에 목표선 · 막대별 색
    opt = bar_option(categories, values, title=title, unit=unit, ref_line=None)
    opt["series"][0]["data"] = [{"value": v, "itemStyle": {"color": NG if v > ref_line else ACCENT}}
                                for v in values]
    opt["series"][0].update(_mark_line(ref_line, unit, "목표"))
    return opt


# ===== 오른쪽 요약 숫자 =====

# 요약 숫자 — [(이름, 글자)] 최근 · 평균 · 최대 · 최소(Tabler 차트 오른쪽 칸 모양)
# values: 값 목록 / unit: 단위 / digits: 소수 자리
def summary(values, unit, digits=1):
    if len(values) == 0:
        return [("데이터", "없음")]
    # 값 배열
    arr = np.asarray(values, dtype=float)
    # 숫자 → 글자
    fmt = "{:,." + str(digits) + "f}" + (" " + unit if unit else "")
    return [("최근", fmt.format(arr[-1])), ("평균", fmt.format(arr.mean())),
            ("최대", fmt.format(arr.max())), ("최소", fmt.format(arr.min()))]


# 그래프 카드 — 왼쪽 그래프 · 오른쪽 요약 숫자 칸
# options: 그래프 옵션 / stats: [(이름, 글자)] 또는 None(요약 칸 없음) / height_px: 그래프 높이
def chart_card(options, stats, height_px=300):
    from nicegui import ui
    # 카드
    with ui.card().classes("w-full p-4") as card:
        with ui.row().classes("w-full no-wrap items-stretch gap-4"):
            ui.echart(options).classes("grow").style("height: {}px; min-width: 0".format(height_px))
            if stats:
                with ui.column().classes("gap-0 justify-center").style("min-width: 120px"):
                    # 항목 번호 · 이름 · 글자
                    for i, (name, text) in enumerate(stats):
                        if i:
                            ui.separator().classes("my-2")
                        ui.label(name).classes("text-sm").style("color: {}".format(TEXT_DIM))
                        ui.label(text).classes("text-xl font-semibold whitespace-nowrap")
    return card


# ===== matplotlib PNG(결과물 파일 — out/) =====

# matplotlib 테마 — 검정 바탕 · 흰 글자 · Pretendard
def _mpl_setup():
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib import font_manager, pyplot as plt
    font_manager.fontManager.addfont(str(FONT_FILE))
    plt.rcParams.update({
        "font.family": FONT, "axes.unicode_minus": False,
        "figure.facecolor": BG_PANEL, "axes.facecolor": BG_PANEL, "savefig.facecolor": BG_PANEL,
        "axes.edgecolor": BORDER, "axes.labelcolor": TEXT_DIM, "text.color": TEXT,
        "xtick.color": TEXT_DIM, "ytick.color": TEXT_DIM, "grid.color": BORDER,
    })
    return plt


# PNG 막대(+기준선) — 보고서 · 제출용 그림 파일
# categories · values · title · unit · ref_line : 위와 같음 / path: 저장 경로(.png)
def png_bar(categories, values, *, title, unit, ref_line, path):
    _same_len(categories, values, "막대 항목 · 값")
    plt = _mpl_setup()
    # 그림 · 축
    fig, ax = plt.subplots(figsize=(8, 4.5), dpi=120)
    ax.bar(list(categories), list(values),
           color=[NG if ref_line is not None and v > ref_line else ACCENT for v in values])
    if ref_line is not None:
        ax.axhline(ref_line, color=SPEC_LINE, linestyle="--", linewidth=1.2, label="기준 {}{}".format(ref_line, unit))
        ax.legend(facecolor=BG_PANEL, edgecolor=BORDER)
    ax.set_title(title, loc="left")
    ax.set_ylabel(unit)
    ax.grid(axis="y", linestyle="--", alpha=0.6)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    return Path(path)


# PNG 관리도 — 중심선 · UCL · LCL · 이탈 점 빨강
# x · values · title · unit · ref_line : 위와 같음 / path: 저장 경로(.png)
def png_control(x, values, *, title, unit, ref_line, path):
    _same_len(x, values, "관리도 가로축 · 값")
    plt = _mpl_setup()
    # 관리 한계
    lim = control_limits(values)
    # 그림 · 축
    fig, ax = plt.subplots(figsize=(8, 4.5), dpi=120)
    ax.plot(range(len(values)), values, color=ACCENT, marker="o", markersize=3, linewidth=1.2)
    # 이탈 점 번호
    out = lim["out"]
    ax.scatter(out, [values[i] for i in out], color=NG, s=40, zorder=3)
    # 선 이름 · 값 · 색 · 모양
    for name, val, color, style in [("UCL", lim["ucl"], NG, "--"), ("CL", lim["center"], TEXT_DIM, "-"),
                                    ("LCL", lim["lcl"], NG, "--")]:
        ax.axhline(val, color=color, linestyle=style, linewidth=1)
        ax.annotate("{} {:.3g}".format(name, val), xy=(1.01, val), xycoords=("axes fraction", "data"),
                    color=color, va="center")
    if ref_line is not None:
        ax.axhline(ref_line, color=SPEC_LINE, linestyle=":", linewidth=1.2)
    # 눈금 간격 — 가로축 글자가 겹치지 않게 최대 10개쯤
    step = max(1, -(-len(values) // 10))
    ax.set_xticks(range(0, len(values), step))
    ax.set_xticklabels([str(x[i]) for i in range(0, len(values), step)])
    ax.set_title(title, loc="left")
    ax.set_ylabel(unit)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return Path(path)


# ===== 데모 =====

# 데모 데이터 — 시드 고정(그림이 매번 같게)
def demo_data():
    # 난수 생성기
    rng = np.random.default_rng(7)
    # 날짜 30개
    days = ["10/{:02d}".format(d) for d in range(1, 31)]
    # 관리도 측정값 — 25번째에 이탈 하나
    meas = list(np.round(rng.normal(50.0, 0.8, 30), 2))
    meas[24] = 54.1
    return {
        "lines": ["L1", "L2", "L3", "L4", "L5", "L6"],
        "yield": [97.2, 98.1, 95.4, 99.0, 96.7, 98.4],
        "defect": [1.2, 0.8, 2.6, 0.5, 1.9, 0.9],
        "days": days,
        "trend": {"생산량": list(np.round(1000 + rng.normal(0, 40, 30).cumsum(), 0)),
                  "계획": list(np.round(950 + rng.normal(0, 25, 30), 0))},
        "meas": meas,
        "pairs": [(round(float(t), 1), round(float(0.6 * t + rng.normal(0, 2)), 2)) for t in rng.uniform(20, 60, 60)],
        "dist": list(rng.normal(50.0, 1.0, 400)),
        "share": {"OK": 912, "NG": 41, "대기": 47},
    }


# 데모 페이지 — 7개 카드(class = chart-<종류> · 캡처용)
def build_demo():
    from nicegui import ui
    from src.ui.theme import apply_theme

    @ui.page("/")
    def page():
        apply_theme()
        # 데모 데이터
        d = demo_data()
        # 관리 한계
        lim = control_limits(d["meas"])
        # 카드 목록 — (id, 옵션, 요약)
        cards = [
            ("bar", bar_option(d["lines"], d["yield"], title="라인별 수율", unit="%", ref_line=None),
             summary(d["yield"], "%")),
            ("line", line_option(d["days"], d["trend"], title="일별 생산량 추이", unit="개", ref_line=1000),
             summary(d["trend"]["생산량"], "개", 0)),
            ("control", control_option(d["days"], d["meas"], title="두께 관리도", unit="µm", ref_line=None,
                                       limits=lim),
             [("CL", "{:.2f} µm".format(lim["center"])), ("UCL", "{:.2f} µm".format(lim["ucl"])),
              ("LCL", "{:.2f} µm".format(lim["lcl"])), ("이탈", "{} 점".format(len(lim["out"])))]),
            ("scatter", scatter_option(d["pairs"], title="온도 · 저항", unit="mΩ", x_unit="°C", ref_line=30),
             [("점", "{} 개".format(len(d["pairs"])))]),
            ("hist", hist_option(d["dist"], title="두께 분포", unit="µm", ref_line=52.0, bins=16),
             summary(d["dist"], "µm", 2)),
            ("pie", pie_option(d["share"], title="판정 비율", unit="개", ref_line=None),
             [(k, "{:,} 개".format(v)) for k, v in d["share"].items()]),
            ("target", bar_target_option(d["lines"], d["defect"], title="라인별 불량률", unit="%", ref_line=2.0),
             [("목표", "2.0 %"), ("초과", "{} 라인".format(sum(v > 2.0 for v in d["defect"])))]),
        ]
        with ui.column().classes("w-full max-w-5xl mx-auto p-4 gap-4"):
            # 카드 종류 · 옵션 · 요약
            for cid, opt, stats in cards:
                chart_card(opt, stats).classes("chart-{}".format(cid))


if __name__ in {"__main__", "__mp_main__"}:
    from nicegui import ui
    build_demo()
    ui.run(host="0.0.0.0", port=int(os.environ.get("PORT", 3000)), title="그래프 갤러리",
           reload=False, show=False, dark=True)
