# -*- coding: utf-8 -*-
"""한눈에 — 표지 · 차례 대신 본문의 그림 · 조작 블록을 먼저 모아 보인다(v3 스티커 551bf9ff «시작하자마자 시각 자료 · 간단한 설명 · 조작 키트»)
순서(바꾸지 않는다): 그림 셋(큰 흐름 · 자료 띠 · 시스템 층) → 조작 블록 셋(채우기 · 한 곳씩 고치기 · 이어 붙이기)
그림 · 재생기 데이터는 shared.py — 여기는 그림마다 «무엇을 보면 되는지» 한두 줄(같은 그림이 본문에 다시 나오고 거기서 자세히)"""
from . import META_BLANKS, figs, kit, shared
from .content.pv import fill  # noqa: F401  — 칸(과제마다 채우는 곳)은 content/pv.py


# ══ 구조 — 고치지 않는다(v3 블록 순서 · 상자 · 조작 블록) ══
def build(w):
    K = kit.slots(w, "pv", fill())
    S = kit.slots(w, "shared", shared.values())
    for k in META_BLANKS:
        kit.blank(w, f"META · {k}")
    w.chapter("한눈에", K["제목"], K["질문"])
    w.html(kit.STYLE + f"<p>{w.t(K['들어가며'])}</p>")

    w.sub(K["그림1_제목"])
    if S.need("그림_큰흐름"):
        w.svg(figs.overview(S["그림_큰흐름"]))
    w.p(*K.tf("그림1_설명"))

    w.sub(K["그림2_제목"])
    if S.need("그림_자료띠"):
        w.svg(figs.file_band(S["그림_자료띠"]))
    w.p(*K.tf("그림2_설명"))

    w.sub(K["그림3_제목"])
    if S.need("그림_시스템층"):
        w.svg(figs.layers(S["그림_시스템층"]))
    w.p(*K.tf("그림3_설명"))

    with w.keep():
        w.sub(K["재생기1_제목"])
        w.p(*K.tf("재생기1_설명"))
        if S.need("재생기_채우기"):
            kit.stepper_fill(w, "pvA", S["재생기_채우기"], note=True)

    with w.keep():
        w.sub(K["재생기2_제목"])
        w.p(*K.tf("재생기2_설명"))
        if S.need("재생기_고치기"):
            kit.stepper_fix(w, "pvB", S["재생기_고치기"])

    with w.keep():
        w.sub(K["재생기3_제목"])
        w.p(*K.tf("재생기3_설명"))
        if S.need("재생기_이어붙이기"):
            kit.stepper_chain(w, "pvC", S["재생기_이어붙이기"])
