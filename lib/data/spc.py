# SPC — 관리도 한계선 · 연속 이탈 규칙(Nelson 1 · 2 · 3) · Cpk
#   역할: 개별값(I) · X-bar 관리도의 중심선 · 상하 관리 한계(평균 ± 3σ) · 규칙 위반 점 위치 · 공정 능력 지수
#   어디에: 공정 데이터 대시보드의 관리도(ECharts 선 + 한계선 3개) · 규칙 위반 점 강조 · «Cpk 1.33 이상» 판정
#   실패하면: 값 개수 부족 · 부분군 크기 불일치 · 규격 둘 다 없음 · σ 0 이면 InputError(한계선을 0 폭으로 그리지 않음)
#   σ 추정법(교과서 Montgomery 기준 · 결과 dict 의 sigma_method 칸에도 적음)
#     개별값: 이동 범위 평균 / d2(n=2) = MR̄ / 1.128
#     X-bar : 부분군 범위 평균 / d2(n) = R̄ / d2 → 한계 = 총평균 ± 3 · σ / √n (= A2 · R̄)
#     Cpk   : 기본은 표본 표준편차(ddof=1 · 전체 산포 — 엄밀히는 Ppk). 관리도 σ 를 쓰려면 sigma 인자로 넘김
import math

import numpy as np

from src.core.errors import InputError

# 부분군 크기 n → d2 상수(범위 → σ 환산). 출처: ASTM / Montgomery 표
D2 = {2: 1.128, 3: 1.693, 4: 2.059, 5: 2.326, 6: 2.534, 7: 2.704, 8: 2.847, 9: 2.970, 10: 3.078}


# 숫자 배열로 바꾸고 결측 · 숫자 아님을 거부
# values: 값 목록 / label: 에러 문구에 쓸 이름
def _as_array(values, label):
    try:
        # 실수 배열
        arr = np.asarray(values, dtype=float)
    # 숫자로 못 바꾸는 값
    except (TypeError, ValueError):
        raise InputError("{}: 숫자가 아닌 값 포함".format(label))
    if np.isnan(arr).any():
        raise InputError("{}: 결측값 포함 (먼저 제거)".format(label))
    return arr


# 개별값(I) 관리도 한계 — σ = MR̄ / 1.128
# values: 시간 순서대로의 측정값
def individuals_limits(values):
    # 측정값 배열
    arr = _as_array(values, "개별값")
    if arr.size < 2:
        raise InputError("개별값 관리도: 값 2개 이상 필요 (현재 {})".format(arr.size))
    # 이동 범위 평균 — 이웃한 두 값 차이의 절댓값 평균
    mr_bar = float(np.mean(np.abs(np.diff(arr))))
    # 공정 σ 추정값
    sigma = mr_bar / D2[2]
    if sigma == 0:
        raise InputError("개별값 관리도: σ 0 (모든 값이 같음)")
    # 중심선
    center = float(np.mean(arr))
    return {"center": center, "ucl": center + 3 * sigma, "lcl": center - 3 * sigma,
            "sigma": sigma, "sigma_method": "MR-bar / 1.128"}


# X-bar 관리도 한계 — σ = R̄ / d2(n), 한계 = 총평균 ± 3σ/√n. 부분군 평균 목록도 같이 돌려줌
# subgroups: 부분군 목록 — [[로트1 값들], [로트2 값들], ...] · 크기는 모두 같고 2 ~ 10
def xbar_limits(subgroups):
    # 부분군 크기 목록
    sizes = {len(g) for g in subgroups}
    if len(subgroups) < 2:
        raise InputError("X-bar 관리도: 부분군 2개 이상 필요")
    if len(sizes) != 1:
        raise InputError("X-bar 관리도: 부분군 크기가 다름 {}".format(sorted(sizes)))
    # 부분군 크기
    n = sizes.pop()
    if n not in D2:
        raise InputError("X-bar 관리도: 부분군 크기 2 ~ 10 만 지원 (현재 {})".format(n))
    # 부분군 × 값 2차원 배열
    arr = _as_array(subgroups, "부분군")
    # 부분군 평균들 — 관리도에 찍는 점
    means = arr.mean(axis=1)
    # 범위 평균
    r_bar = float(np.mean(arr.max(axis=1) - arr.min(axis=1)))
    # 공정 σ 추정값
    sigma = r_bar / D2[n]
    if sigma == 0:
        raise InputError("X-bar 관리도: σ 0 (모든 부분군 범위가 0)")
    # 중심선 — 총평균
    center = float(means.mean())
    # 평균의 표준오차 — σ / √n
    se = sigma / math.sqrt(n)
    return {"center": center, "ucl": center + 3 * se, "lcl": center - 3 * se,
            "sigma": sigma, "sigma_method": "R-bar / d2(n={})".format(n), "means": means.tolist()}


# 연속 이탈 규칙 검사 — 규칙별로 위반을 «완성한 점» 의 위치(0부터) 목록
#   rule1(Nelson 1): 한 점이 중심 ± 3σ 밖
#   rule2(Nelson 2): 9점 연속 중심선 같은 쪽(중심선 위의 점은 흐름을 끊음)
#   rule3(Nelson 3): 6점 연속 증가 또는 감소(같은 값은 흐름을 끊음)
# values: 관리도에 찍는 점(개별값 또는 부분군 평균) / center: 중심선 / sigma: 점의 σ(X-bar 면 σ/√n)
def nelson_rules(values, center, sigma):
    # 점 배열
    arr = _as_array(values, "규칙 검사 값")
    # 규칙 → 위반 위치 목록
    hits = {"rule1": [], "rule2": [], "rule3": []}
    # 같은 쪽 연속 개수(+ 위 / - 아래) · 증감 연속 개수(+ 증가 / - 감소)
    side_run, trend_run = 0, 0
    # 점 위치 / 값
    for i, v in enumerate(arr.tolist()):
        if abs(v - center) > 3 * sigma:
            hits["rule1"].append(i)
        # 이 점의 쪽 — 1 위 · -1 아래 · 0 중심선 위
        side = (v > center) - (v < center)
        side_run = side_run + side if side != 0 and side_run * side > 0 else side
        if abs(side_run) >= 9:
            hits["rule2"].append(i)
        if i > 0:
            # 앞 점 대비 방향 — 1 증가 · -1 감소 · 0 같음
            step = (v > float(arr[i - 1])) - (v < float(arr[i - 1]))
            trend_run = trend_run + step if step != 0 and trend_run * step > 0 else step
            # 증감 5번 연속 = 6점 연속
            if abs(trend_run) >= 5:
                hits["rule3"].append(i)
    return hits


# 공정 능력 지수 Cpk. 규격이 한쪽만 있으면 그쪽 지수만으로 Cpk(=Cpu 또는 Cpl)
# values: 측정값 / usl: 규격 상한 / lsl: 규격 하한 / sigma: σ 직접 지정(없으면 표본 표준편차 ddof=1)
def cpk(values, usl=None, lsl=None, sigma=None):
    if usl is None and lsl is None:
        raise InputError("Cpk: USL · LSL 중 하나 이상 필요")
    if usl is not None and lsl is not None and lsl >= usl:
        raise InputError("Cpk: LSL 이 USL 이상 ({} >= {})".format(lsl, usl))
    # 측정값 배열
    arr = _as_array(values, "Cpk 값")
    if sigma is None and arr.size < 2:
        raise InputError("Cpk: 값 2개 이상 필요 (현재 {})".format(arr.size))
    # 평균
    mean = float(arr.mean())
    # σ 와 추정법 이름
    sd, method = (float(sigma), "given") if sigma is not None else (float(arr.std(ddof=1)), "sample std ddof=1")
    if sd == 0:
        raise InputError("Cpk: σ 0 (모든 값이 같음)")
    # 상한 쪽 지수 · 하한 쪽 지수(규격 없으면 None)
    cpu = None if usl is None else (usl - mean) / (3 * sd)
    cpl = None if lsl is None else (mean - lsl) / (3 * sd)
    # 있는 쪽 지수들
    sides = [x for x in (cpu, cpl) if x is not None]
    return {"cpk": min(sides), "cpu": cpu, "cpl": cpl, "mean": mean, "sigma": sd, "sigma_method": method,
            "one_sided": len(sides) == 1}
