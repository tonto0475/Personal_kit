# 데이터 품질 리포트 + 로트 · 웨이퍼 집계
#   역할: 표 하나의 행 수 · 열별 결측률 · 중복 행 · 범위 밖 개수를 dict 와 마크다운 표로 · 그룹별 개수 · 불량 수 · 불량률
#   어디에: 입력을 읽은 직후 «무엇이 비었나» 를 담당자에게 보이는 표 · 대시보드의 로트별 불량률 표
#   실패하면: 없는 열 이름 · 범위 하한 > 상한 · 미측정 처리 인자 누락이면 InputError(추측해서 채우지 않음)
import pandas as pd

from src.core.errors import InputError


# 품질 리포트 dict. ranges 를 주면 열마다 범위 밖 개수도 셈(결측은 범위 밖에 넣지 않음)
# df: 검사할 표 / ranges: {열 이름: (하한, 상한)} — 한쪽만 볼 때는 None
def quality_report(df, ranges=None):
    # 전체 행 수
    rows = len(df)
    # 열별 결과 — 열 이름 → {결측 수, 결측률 %}
    columns = {}
    # 검사할 열 이름
    for col in df.columns:
        # 이 열 결측 개수
        missing = int(df[col].isna().sum())
        columns[col] = {
            "missing": missing,
            "missing_pct": round(missing * 100.0 / rows, 2) if rows else 0.0,
        }
    # 범위 밖 결과 — 열 이름 → {하한, 상한, 범위 밖 개수}
    out_of_range = {}
    # 열 이름 / (하한, 상한)
    for col, (low, high) in (ranges or {}).items():
        if col not in df.columns:
            raise InputError("범위 검사 열 없음: {}".format(col))
        if low is not None and high is not None and low > high:
            raise InputError("범위 하한이 상한보다 큼: {} ({} > {})".format(col, low, high))
        # 숫자로 바꾼 값 — 숫자가 아닌 칸은 NaN(결측과 같이 범위 검사에서 빠짐)
        values = pd.to_numeric(df[col], errors="coerce")
        # 범위 밖 여부 — 처음엔 전부 거짓
        bad = pd.Series(False, index=df.index)
        if low is not None:
            bad = bad | (values < low)
        if high is not None:
            bad = bad | (values > high)
        out_of_range[col] = {"low": low, "high": high, "count": int(bad.sum())}
    return {
        "rows": rows,
        "duplicate_rows": int(df.duplicated().sum()),
        "columns": columns,
        "out_of_range": out_of_range,
    }


# 품질 리포트 dict → 마크다운 표 문자열(보고서 · 화면 ui.markdown 에 그대로)
# report: quality_report 결과
def report_markdown(report):
    # 출력 줄 목록
    lines = [
        "- 행 수: {}".format(report["rows"]),
        "- 중복 행: {}".format(report["duplicate_rows"]),
        "",
        "| 열 | 결측 수 | 결측률(%) | 범위 | 범위 밖 |",
        "|---|---|---|---|---|",
    ]
    # 열 이름 / 결측 정보
    for col, info in report["columns"].items():
        # 이 열의 범위 검사 결과(없으면 None)
        rng = report["out_of_range"].get(col)
        # 범위 칸 문구
        rng_text = "-" if rng is None else "{} ~ {}".format(
            "" if rng["low"] is None else rng["low"], "" if rng["high"] is None else rng["high"])
        # 범위 밖 칸 문구
        bad_text = "-" if rng is None else str(rng["count"])
        lines.append("| {} | {} | {} | {} | {} |".format(
            col, info["missing"], info["missing_pct"], rng_text, bad_text))
    return "\n".join(lines)


# 그룹별 개수 · 측정 수 · 불량 수 · 불량률(%). 판정 열은 참(불량) · 거짓(양품) · 결측(미측정)
# df: 표 / keys: 묶을 열(예: ["lot"] · ["lot", "wafer"]) / ng_col: 불량 여부 열
# exclude_unmeasured: 참이면 미측정을 분모에서 뺌(불량률 = 불량 / 측정 수), 거짓이면 전체 개수로 나눔 — 기본값 없음(과제마다 숨은 기준이라 반드시 명시)
def group_defect_rate(df, keys, ng_col, *, exclude_unmeasured):
    if not isinstance(exclude_unmeasured, bool):
        raise InputError("exclude_unmeasured 는 True · False 로 명시")
    # 확인할 열 — 묶음 열 + 판정 열
    for col in list(keys) + [ng_col]:
        if col not in df.columns:
            raise InputError("집계 열 없음: {}".format(col))
    # 작업용 사본 — 측정 여부 · 불량 여부 열을 덧붙임
    work = df.copy()
    work["_measured"] = work[ng_col].notna()
    work["_ng"] = work[ng_col].fillna(False).astype(bool)
    # 그룹별 합계 표
    out = work.groupby(list(keys), dropna=False).agg(
        count=(ng_col, "size"), measured=("_measured", "sum"), ng=("_ng", "sum")).reset_index()
    out["measured"] = out["measured"].astype(int)
    out["ng"] = out["ng"].astype(int)
    # 분모 — 미측정 제외면 측정 수, 아니면 전체 개수
    denom = out["measured"] if exclude_unmeasured else out["count"]
    # 분모 0 은 불량률 NaN(0 % 로 보이면 «양품» 으로 오해)
    out["ng_rate_pct"] = (out["ng"] * 100.0 / denom.where(denom > 0)).round(2)
    return out
