# -*- coding: utf-8 -*-
"""4 알고리즘 — v3 양식(시스템보다 앞: 스티커 bbfbb1d9)
흐름(바꾸지 않는다): 가장 작은 경우는 다 세면 된다(성공 · 표 + 작은 지도) → 크기가 늘면 곱으로 늘어 막힌다(실측 시간 표) → 그제서야 이름(이름 상자) → 맞혀 보기
      → 방안 A(규칙으로 한 번에 · 채우기 재생기) → 장단점 · 주의 상자 → 방안 B(솔버 · 한 곳씩 고치기 재생기) → 규칙
      → 두 방안 공통 단계(세 단계 띠 · 이어 붙이기 재생기) → ↩ 1장 되돌아보기 → 규칙 → 맞혀 보기 · 조건별 표 → 선택표
v3 스티커 b3bd7396(«이해 안 됨» — 구체 예 없이 시작 · 한 상자에 용어 넷) · cbb680cd(결과 스냅샷 대신 바꾸기 하나씩) · 9acdc018(재생기 A 가 하이라이트)"""
from . import figs, kit, shared
from .content.s4 import fill  # noqa: F401  — 칸(과제마다 채우는 곳)은 content/s4.py


# ══ 구조 — 고치지 않는다(v3 블록 순서 · 상자 · 조작 블록) ══
def build(w):
    K = kit.slots(w, "s4", fill())
    S = kit.slots(w, "shared", shared.values())
    w.chapter("4", K["제목"], K["질문"])
    if K.opt("자료_상태") == "raw":  # steps.json "data": "raw" — 4장 숫자가 자료 정리(A1) 전 값
        w.p("⟪자료 정리 전 · 2차판 갱신⟫ 이 장의 숫자는 원본 자료를 정리하기 전에 계산한 값이다. 2차판에서 정리한 자료로 다시 계산한다.")

    # ── 4.1 쉬운 질문 → 막힘 → 이름 ─────────────────────
    w.section(K["절1_제목"])
    w.p(*K.tf("쉬운_질문"))
    if all([K.need("순서_표"), K.need("순서_지도")]):  # 둘 다 확인(비면 둘 다 알린다)
        w.fig(w.T(**K["순서_표"]), w.svg_item(figs.orders_map(K["순서_지도"]), width="45%"), caption=K["순서_캡션"])
    w.p(*K.tf("순서_차이"))
    w.p(*K.tf("곱으로_늘어남"))
    if K.need("전부세기_표"):
        w.table(**K["전부세기_표"])
    w.p(*K.tf("한_대뿐"))
    t, f = K.tf("이름_붙이기")
    w.name(t, fn=f)
    w.p(*K.tf("두_갈래"))
    if K.need("맞혀보기1"):
        q, a = K["맞혀보기1"]
        w.guess(q, a)

    # ── 4.2 방안 A ───────────────────────────────────────
    with w.keep():
        w.section(K["절2_제목"])
        w.p(*K.tf("방안A_설명"))
        if S.need("재생기_채우기"):
            kit.stepper_fill(w, "stepA", S["재생기_채우기"], note=False)
    w.p(*K.tf("방안A_장단점"))
    w.ng(K["주의_글"], title=K["주의_제목"])

    # ── 4.3 방안 B ───────────────────────────────────────
    w.section(K["절3_제목"])
    w.p(*K.tf("방안B_설명"))
    w.p(*K.tf("방안B_장단점"))
    with w.keep():
        w.p(*K.tf("고치기_설명"))
        if S.need("재생기_고치기"):
            kit.stepper_fix(w, "stepB", S["재생기_고치기"])
    w.p(*K.tf("고치기_결과"))
    w.rule(K["규칙1"])

    # ── 4.4 두 방안 공통 — 이어 붙이기 · 검증기 ───────────
    w.section(K["절4_제목"])
    w.p(*K.tf("공통_설명"))
    if K.need("공통_띠"):
        w.svg(figs.strip3(K["공통_띠"]), caption=K["공통_띠_캡션"])
    w.p(*K.tf("하루_대수"))
    with w.keep():
        t, f = K.tf("이어붙이기_이름")
        w.name(t, fn=f)
        if S.need("재생기_이어붙이기"):
            kit.stepper_chain(w, "chain", S["재생기_이어붙이기"])
    w.back("1", None, K["되돌아보기"])
    w.rule(K["규칙2"])
    if K.need("맞혀보기2"):
        q, a = K["맞혀보기2"]
        w.guess(q, a)
    if K.need("조건별_표"):
        w.table(**K["조건별_표"])
    w.p(*K.tf("조건별_표_설명"))
    kit.extra_figs(w, K.opt("추가_그림"))  # 선택 — 비우면 블록 없음
    w.p(*K.tf("검증기_설명"))

    # ── 4.5 선택표 ───────────────────────────────────────
    with w.keep():
        w.section(K["절5_제목"])
        w.p(*K.tf("선택표_설명"))
        if K.need("선택표"):
            w.table(**K["선택표"])
