# -*- coding: utf-8 -*-
"""4 알고리즘 — 개편판(시스템보다 앞으로: 스티커 bbfbb1d9)
흐름: 버스 한 대의 순서 — 세 곳은 다 세면 된다(성공) → 거점이 늘면 곱으로 늘고 사람 배정까지 겹쳐 막힌다(실측) → 이름(경로 문제 · CVRP)
      → 방안 A(단계 재생기 — 스티커 9acdc018 «하이라이트» 유지 + 우회 배율) → 방안 B(한 곳씩 고치기 단계 재생기 — 스티커 cbb680cd: 결과 스냅샷 대신 바꾸기 하나씩)
      → 공통: 트립 이어 붙이기(단계 재생기 — 조건 슬라이더 대신) · 검증기 → 선택표
스티커 b3bd7396(11쪽이 이해 안 됨)의 추정 원인과 고친 것은 REVISE_LOG 에"""
import math

from book.task10v3 import data, figs, kit


def build(w):
    F = data.facts()
    C = data.cache()
    A1, A2 = F["A1"], F["A2"]
    B10, B3, B1, B90 = C["B_time"]["10"], C["B_time"]["3"], C["B_time"]["1"], C["B_limit"]["90"]
    first = C["B_time"]["first"]
    sadang = F["hub_km"]["사당역"]["ICN"] / data.SPEED * 60
    det = data.detour_table()
    ic100 = data.fleet_frame("ICN", "1.0", "none")
    ic80 = data.fleet_frame("ICN", "0.8", "none")
    drop7 = next(r for r in C["drop"] if r["veh"] == F["icn_buses"] - 1)
    lim_none = next(k for k, v in C["B_limit"].items() if v is None)  # 저장 결과에서 «해 없음» 이었던 승차 한도(분)
    w.chapter("4", "알고리즘", "좋은 노선은 어떻게 만들고, 아직 모르는 정보에 따라 어느 방안을 고르나?")

    # ── 4.1 쉬운 질문 → 막힘 ─────────────────────────────
    w.section("버스 한 대의 순서부터 — 전부 세면 되나")
    rows, best, worst = data.orders_example()
    hubs = rows[0][0]
    far_first = sorted(hubs, key=lambda h: -F["hub_km"][h]["ICN"])
    far_km = next(km for o, km in rows if o == far_first)
    nm = "→".join
    w.p(f"가장 쉬운 질문부터 — 버스 한 대가 {' · '.join(data.short(h) for h in hubs)} 세 거점에서 사람을 태워 이천캠퍼스로 간다. 어느 순서로 돌아야 가장 짧을까? "
        f"세 곳이면 순서는 3 × 2 × 1 = {len(rows)}가지라 **전부 세어 보면** 된다.")
    trs = []
    for o, km in rows:
        trs.append([nm(data.short(h) for h in o) + " → 캠퍼스", f"{km:.1f}"])
    good = [i for i, (o, _) in enumerate(rows) if o == best[0]]
    bad = [i for i, (o, _) in enumerate(rows) if o == worst[0]]
    notes = {i: ("← 먼 곳부터", "muted") for i, (o, _) in enumerate(rows) if o == far_first}
    notes.update({good[0]: ("← 가장 짧다", "good"), bad[0]: ("← 가장 길다", "bad")})
    w.fig(w.T(header=["도는 순서", "길이 km"], rows=trs, good_rows=good, bad_rows=bad, notes=notes, small=True),
          w.svg_item(figs.orders_map_svg(F, best, worst), width="45%"),
          caption=f"거점 세 곳을 도는 순서 {len(rows)}가지 — 길이는 직선거리로 잰 값")
    w.p(f"순서만 바꿔도 **{worst[1] - best[1]:.1f}km** 차이가 나고, 사업장에서 먼 곳부터 도는 순서({far_km:.1f}km)는 가장 짧은 순서가 아니다.")
    br = {b["n"]: b for b in C["brute"]}
    n10 = max(br)
    est = {n: br[n10]["sec"] * math.factorial(n) / math.factorial(n10) for n in (12, 15)}
    w.p("그런데 거점이 늘면 순서가 곱으로 늘어난다. 네 곳이면 4 × 3 × 2 × 1 = 24가지, 다섯 곳이면 120가지다. 아래는 이천 쪽 거점으로 전부 세어 본 시간이다.")
    brows = [[f"{n}곳", f"{br[n]['perms']:,}", figs._sec(br[n]["sec"]), "실측"] for n in sorted(br)]
    brows += [[f"{n}곳", f"{math.factorial(n):,}", figs._sec(est[n]), "추정(10곳의 시간 × 가짓수 비율)"] for n in (12, 15)]
    w.table(header=["거점 수", "도는 순서 가짓수", "전부 세는 데 걸린 시간", "구분"], rows=brows, small=True,
            bad_cells=[(i, "전부 세는 데 걸린 시간") for i, r in enumerate(brows) if i >= len(br) - 1],
            caption="거점 수에 따라 «전부 세기» 가 걸리는 시간")
    w.p(f"게다가 이것은 **버스 한 대**의 순서일 뿐이다. 실제로는 {F['wave_n']}명을 버스 {A1['buses']}대에 나눠 태우는 것까지 함께 정해야 하고, "
        "누가 어느 버스에 타느냐가 바뀔 때마다 버스마다 순서 세기를 다시 해야 한다. **전부 세는 방법으로는 끝나지 않는다.**")
    w.name(f"이렇게 여러 곳을 들르는 순서와 어느 차가 누구를 태울지를 함께 정하는 문제를 **경로 문제**라 한다. 차마다 정원(여기서는 {data.CAP}명)이 붙은 경로 문제를 따로 CVRP 라 부른다.",
           fn={"경로 문제": "(vehicle routing problem) 여러 장소를 도는 순서와 차량 배정을 함께 정하는 문제",
               "CVRP": "(capacitated vehicle routing problem) 차마다 태울 수 있는 인원(정원)이 정해진 경로 문제"})
    w.p("전부 세지 못하므로 «가장 짧다» 는 보장은 내려놓고 **괜찮은 답을 빨리** 찾는다. 길은 두 갈래다 — 사람이 정한 규칙으로 한 번에 짜는 방안 A, "
        "프로그램이 답을 계속 고쳐 가는 방안 B.")
    b5_names = [h for h, _ in F["A1_bus_stops"][4]]
    b5_best_km, b5_best = data._best_order(b5_names)
    b5_km = data.route_km(b5_names)
    n4 = math.factorial(len(b5_names))
    w.guess(f"거점이 네 곳({' · '.join(data.short(h) for h in b5_names)})이면 도는 순서는 {n4}가지다. 가장 짧은 순서는 몇 km 일까? "
            f"사업장에서 먼 곳부터 도는 순서({'→'.join(data.short(h) for h in b5_names)})는 {b5_km:.1f}km 다.",
            f"**{b5_best_km:.1f}km** — {'→'.join(data.short(h) for h in b5_best)}. {n4}가지를 다 세면 나온다. 먼 곳부터 도는 규칙은 {b5_km - b5_best_km:.1f}km 를 더 돈다 — "
            "이 네 곳이 바로 아래 방안 A 의 버스 5 다.")

    # ── 4.2 방안 A ───────────────────────────────────────
    with w.keep():
        w.section("방안 A — 묶고 나서 순서 정하기")
        w.p(f"사람을 {data.CAP}명씩 묶고(군집화) 버스 안은 먼 거점부터 태운다. 아래는 사업장에서 먼 사람부터 {data.CAP}명씩 자르는 **거리순**이다. "
            "이처럼 정해 둔 규칙으로 빨리 답을 내는 방법을 **휴리스틱**이라 한다. 표의 우회 배율은 그 거점에서 사업장까지 직통 거리에 견줘 실제로 탄 거리다.",
            fn={"군집화": "(clustering) 가까운 사람끼리 묶기. 정원이 붙은 것을 용량 제한 군집화라 한다(독자 메모의 CCP 로 추정)",
                "휴리스틱": "(heuristic) 최선을 보장하지는 않지만 정해 둔 규칙으로 빨리 괜찮은 답을 내는 방법"})
        kit.stepper_A(w, "stepA", "다음을 눌러 가며 → 버스 5 가 채워질 때 지도의 선이 어느 방향으로 꺾이는지 봐", note=False)
    b5 = max(data.detour(F["A1_bus_stops"][4]), key=lambda x: x[4])
    w.p(f"**장점** 버스 수가 정원으로 나눠 올린 {A1['buses']}대와 같고, 규칙이 두 줄이라 설명이 쉽다. **허점** 묶는 기준이 «거리» 하나라 **방향을 보지 않는다** — "
        f"버스 5 는 {data.short(b5[0])} 사원이 직통의 {b5[4]:.1f}배를 돈다. 승차 한도 같은 조건도 규칙에 직접 넣어야 한다(90분 넘게 타는 사람 거리순 {A1['over90']}명). "
        f"사업장 둘레 각도로 줄 세워 자르는 스윕은 {A2['km']}km · 최장 {A2['max_min']}분으로 조금 낫지만 같은 한계가 있다. "
        "한 번 정하면 되돌려 고치지 않는 **그리디**다.",
        fn={"스윕": "(sweep) 사업장 둘레 각도 순서로 사람을 줄 세워 45명씩 자르는 묶기 방식",
            "그리디": "(greedy) 지금 가장 좋아 보이는 것을 차례로 고르고 되돌리지 않는 방법"})
    w.ng(f"README 에는 없지만 «직통보다 1.5배 넘게 돌아가지 않는다» 같은 **우회 한도**가 붙는 과제가 있다. 그러면 거리순 계획은 표의 빨간 칸"
         f"(버스 {' · '.join(str(i + 1) for i in det['A_over'])})이 걸려 그대로 쓸 수 없다. 방안 B 의 계획(솔버 10초)은 가장 많이 돌아가는 사원도 {max(det['B']):.2f}배다.",
         title="우회 한도가 있으면")

    # ── 4.3 방안 B ───────────────────────────────────────
    w.section("방안 B — 솔버에게 맡기기")
    w.p(f"방안 B 는 프로그램에게 맡긴다. 적어 주는 것은 세 가지 — 줄일 것(**목적**: 총거리), 지킬 것(**제약**: 정원 {data.CAP} · 승차 한도), 고칠 시간(**시간 한도**). "
        f"목적과 제약을 받아 답을 찾는 프로그램이 솔버다. 이 책은 OR-Tools 의 경로 풀이기로 풀었다 — 같은 파동이 10초 만에 **{B10['km']}km**"
        f"(방안 A 거리순 {A1['km']} · 스윕 {A2['km']}km).",
        fn={"OR-Tools": "구글이 공개한 최적화 라이브러리. 경로 문제 풀이기가 들어 있어 목적 · 제약 · 시간 한도를 적으면 답을 낸다"})
    w.p(f"**장점** 조건을 한 줄로 더한다 — 승차 90분 한도를 넣으면 총거리 {B90['km']}km · 최장 {B90['max_min']}분(90분 넘게 타는 사람 {B90['over90']}명). "
        f"**허점** 시간 한도에 따라 답이 다르고(1초 {B1['km']}km · 3초 {B3['km']}km · 10초 {B10['km']}km), 조건이 부딪치면 **해 없음**이라고만 답한다 — 승차 한도를 "
        f"{lim_none}분으로 두면 사당 직통이 {sadang:.0f}분이라 해가 없다. 버스를 {drop7['veh']}대로 못 박아도 해가 없고, 미배정을 허용해야 {drop7['drop']['dropped']}명을 남기고 풀린다. "
        f"총거리만 줄이면 오래 타는 사람이 남는다(최장 {B10['max_min']}분).")
    with w.keep():
        w.p("그러면 솔버는 안에서 무엇을 하나? 먼저 빠른 규칙으로 처음 답을 만들고, **한 곳씩 바꿔 보며 총거리가 줄면 받아들이는** 일을 시간 한도까지 되풀이한다. "
            "이것을 **국소 탐색**이라 한다. 아래는 그 «한 곳씩 바꾸기» 를 방안 A 의 계획에 그대로 해 본 기록이다. 바꾸기는 두 가지 — 버스 한 대의 **순서 바꾸기**, "
            "두 버스 사이에서 사람을 **옮기기 · 맞바꾸기**.",
            fn={"국소 탐색": "(local search) 지금 답에서 한 곳만 바꾼 답들을 만들어 보고, 더 좋은 것이 있으면 그리로 옮겨 가기를 되풀이하는 방법"})
        kit.stepper_LS(w, "stepB", "다음을 눌러 가며 → 굵어진 버스의 선이 어떻게 곧아지는지, 표의 총 km 가 얼마나 주는지 봐")
    ls = data.local_search()
    w.p(f"{len(ls) - 1}번 바꿔 {ls[0]['km']:.0f} → **{ls[-1]['km']:.0f}km**. 방안 A 의 지그재그를 바꾸기가 하나씩 지웠다. "
        f"OR-Tools 도 같은 원리로 자동으로 고친다 — 처음 답 {first['km']}km 에서 10초 동안 {B10['km']}km 까지. "
        f"출발점과 바꿔 보는 방법이 달라 멈춘 곳이 다르고({ls[-1]['km']:.0f} · {B10['km']}km), 어느 쪽도 «가장 짧다» 는 보장은 없다.")
    w.rule("**전부 셀 수 없으면 «가장 짧은 답» 대신 «괜찮은 답» 을 찾는다 — 규칙으로 한 번에 짜면(방안 A) 빠르고 설명이 쉽지만 규칙이 못 본 낭비가 남고, "
           "한 곳씩 고쳐 가면(방안 B) 그 낭비가 줄지만 답이 시간 한도와 조건에 따라 달라진다.**")

    # ── 4.4 공통 — 이어 붙이기 · 검증기 ───────────────────
    ch = kit.chain_data()
    w.section("두 방안 공통 — 트립 이어 붙이기와 검증기")
    w.p("방안 A 든 B 든 결과는 파동마다 버스가 달릴 경로의 목록이다. 그 뒤 두 단계는 어느 방안을 골라도 똑같다 — 경로를 버스에 이어 붙이고, 검증기로 숫자를 확인한다.",
        fn={"검증기": "계획 결과가 규칙(전원 1회 배정 · 정원 · 도착 시각 · 보유 대수)을 지키는지 숫자로 확인하는 프로그램"})
    w.svg(figs.chain_strip_svg(), caption="방안 A · B 는 «트립 목록» 을 만드는 단계만 다르다. 뒤의 두 단계는 같다")
    w.p(f"파동 하나는 버스 {A1['buses']}대로 풀렸다. 하루도 그만큼이면 될까? 평일 일근 출근 {F['g_total_max']}명 ÷ {data.CAP} = {F['g_div']:.1f} → {F['g_ceil']}대, "
        f"보유 {F['n_veh']}대 — 숫자로는 맞아 보인다. 그런데 이천의 하루를 시각 순서로 이어 보면 탑승률 100% 에서 **{ic100['fleet']}대**가 필요하다(보유 {F['icn_buses']}대). "
        f"같은 시각에 달리는 버스는 많아야 {ch['peak']}대인데도 그렇다.")
    with w.keep():
        w.name("버스가 경로 하나를 달리는 일(출발 시각 · 출발지 · 도착 시각 · 도착지)을 트립이라 한다. 앞 트립을 끝낸 버스가 다음 트립 출발지에 출발 시각 전에 닿으면 "
               f"같은 버스가 맡는다 — 이것이 **이어 붙이기**다. 아래는 이천 아침의 트립 {len(ch['steps'])}개를 출발 시각 순서로 하나씩 붙인 기록이다.")
        kit.stepper_chain(w, "chain", "다음을 눌러 가며 → 버스가 새로 생기는 순간, 다른 버스들이 어디에 있는지 오른쪽을 봐")
    ta, tb = data.START["D"] - data.LEAD, data.END["N"] + data.TAIL
    w.back("1", None, f"1장 그림에서 {data.hm(ta)} 에 사업장에 닿은 버스가 {tb - ta}분 뒤 {data.hm(tb)} 퇴근에 다시 쓰일 수 있다고 했다. 붙여 보니 반대도 보인다 — "
           "멀리 가서 끝나는 퇴근 트립을 맡은 버스는 한동안 못 쓴다. 버스가 는 순간은 모두 «시간 안에 출발지에 닿는 빈 버스가 없을 때» 였다.")
    w.rule("**필요한 버스 수는 동시에 달리는 버스 수가 아니라, 앞 트립을 끝낸 곳에서 다음 트립 출발지까지 시간 안에 갈 수 있는지로 정해진다.**")
    rt = {t["campus"] + str(t["rate"]): t for t in C["fleet_rate_table"]}
    rates = (0.6, 0.7, 0.8, 0.9, 1.0)
    frows = [[f"{int(r * 100)}%", rt["ICN" + str(r)]["fleet"], rt["CJU" + str(r)]["fleet"]] for r in rates]
    bc = [(i, "이천 필요") for i, r in enumerate(rates) if rt["ICN" + str(r)]["fleet"] > F["icn_buses"]]
    bc += [(i, "청주 필요") for i, r in enumerate(rates) if rt["CJU" + str(r)]["fleet"] > F["cju_buses"]]
    w.guess(f"탑승률이 {int(rates[2] * 100)}% 라면 이천은 하루 몇 대가 필요할까? 보유는 {F['icn_buses']}대다.",
            f"**{rt['ICN' + str(rates[2])]['fleet']}대** — 보유와 같아 여유가 0 이다. {int(rates[3] * 100)}% 면 {rt['ICN' + str(rates[3])]['fleet']}대로 보유를 넘는다(아래 표).")
    w.table(header=["탑승률", "이천 필요", "청주 필요"], rows=frows, bad_cells=bc, small=True,
            caption=f"탑승률별 하루 필요 대수(보유 이천 {F['icn_buses']} · 청주 {F['cju_buses']}, 넘으면 빨강)")
    w.p("11/10 하루를 방안 B 경로로 만들어 이어 붙인 저장 결과다. 탑승률은 그날 출근자 가운데 그 비율만큼 무작위로 뽑아 맞춘 것이라, 다시 뽑으면 ±1대 달라질 수 있다.")
    w.p(f"이어 붙인 뒤에는 **검증기**로 전원 1회 배정 · 버스마다 {data.CAP}명 이하 · 시작 {data.LEAD}분 전 도착 · 보유 대수 이하를 숫자로 확인한다 — "
        "AI 가 짠 계획이 맞는지 판정하는 기준이다.")

    # ── 4.5 선택표 ───────────────────────────────────────
    srows = [
        ["질문 1 목적", "총거리 최소", "B", f"{B10['km']} vs {A2['km']}~{A1['km']}km"],
        ["질문 1 목적", "설명 · 빠른 구현이 먼저", "A", "규칙 두 줄"],
        ["질문 7 승차 한도", "한도가 있다", "B(한 줄로 추가)", f"90분 → {B90['km']}km · 최장 {B90['max_min']}분"],
        ["질문 7 우회 한도", "1.5배 같은 한도가 있다", "B", f"A 거리순은 {len(det['A_over'])}대가 넘음 · B 최대 {max(det['B']):.2f}배"],
        ["질문 2 탑승률", f"지난달 수준(약 {F['ride_avg']:.0%}) 이하", "둘 다(여유 0)", f"이천 {ic80['fleet']}대 = 보유 {F['icn_buses']}대"],
        ["질문 2 탑승률", "100%", "B + 미배정 허용(질문 4)", f"이천 {ic100['fleet']}대 > 보유 {F['icn_buses']}대"],
        ["질문 3 이어 쓰기", "예", "B(짧은 경로가 이어 붙이기에 유리)", f"이어 붙이면 {ic100['fleet']}대 · 동시 {ch['peak']}대"],
        ["질문 3 이어 쓰기", "아니오", "무관 — 보유로 불가", f"트립 {len(ic100['trips'])}개 = {len(ic100['trips'])}대"],
        ["부록 B 정류지", "집 앞 정차", "B 필수", f"{C['home']['km']}km vs 거점 {B10['km']}km"]]
    with w.keep():
        w.section("어느 방안을 고르나 — 선택표")
        w.p("아직 모르는 정보(3장의 질문)의 답에 따라 고른다. 근거 칸은 같은 파동 · 같은 하루로 직접 계산한 값이다.")
        w.table(header=["질문", "이렇게 정해지면", "→ 방안", "근거(실측)"], rows=srows, cls="wr lf", small=True,
                caption="선택표 — 아직 모르는 정보가 이렇게 정해지면 이 방안")
