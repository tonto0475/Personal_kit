# -*- coding: utf-8 -*-
"""5 시스템 — v3 양식(알고리즘 뒤: 스티커 bbfbb1d9). 층 그림(스티커 49e4e6a1 «눈에 잘 보이고 이해 잘 됨») 유지
흐름(바꾸지 않는다): 한 문단 요약(저장소 · 화면은 읽기만 · 한 번에 교체) → 시스템 층 그림 → 주의 ◎ 카드(왜 해당하나 · 이렇게) → **해당 없음** 한 문단 → 부록 C 안내"""
from . import figs, kit, shared
from .content.s5 import fill  # noqa: F401  — 칸(과제마다 채우는 곳)은 content/s5.py


# ══ 구조 — 고치지 않는다(v3 블록 순서 · 상자) ══
def build(w):
    K = kit.slots(w, "s5", fill())
    S = kit.slots(w, "shared", shared.values())
    w.chapter("5", K["제목"], K["질문"])
    w.p(*K.tf("들어가며"))
    if S.need("그림_시스템층"):
        w.svg(figs.layers(S["그림_시스템층"]), caption=K["그림_캡션"])
    if K.need("주의"):
        for t in K["주의"]:
            kit.qitem(w, t["title"], t["cat"], [("왜 해당하나", t["why"]), ("이렇게", t["do"])], fn=t.get("fn"))
    kit.extra_figs(w, K.opt("추가_그림"))  # 선택 — 비우면 블록 없음
    w.p(*K.tf("해당_없음"))
    w.p(*K.tf("맺음"))
