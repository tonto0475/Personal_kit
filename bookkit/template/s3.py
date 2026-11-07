# -*- coding: utf-8 -*-
"""3 지금 담당자에게 물을 것 — v3 양식. 표 대신 ◎ 질문 · 이유 · 추천 · 반대면(v3 스티커 225e8c94 · 702a5491)
흐름(바꾸지 않는다): 들어가며(추천 = 답이 없을 때의 기본 가정) → 질문 ◎ 카드들 → 생각해 보기(질문 셋만 보낸다면 — 스티커 e0da804c «필요하다»)"""
from . import kit
from .content.s3 import fill  # noqa: F401  — 칸(과제마다 채우는 곳)은 content/s3.py


# ══ 구조 — 고치지 않는다(v3 블록 순서 · 상자) ══
def build(w):
    K = kit.slots(w, "s3", fill())
    w.chapter("3", K["제목"], K["질문"])
    w.p(*K.tf("들어가며"))
    if K.need("질문들"):
        for i, row in enumerate(K["질문들"]):
            q, cat, why, rec, opp = row
            kit.qitem(w, f"질문 {kit.no(row, i + 1)}. {q}", cat, [("이유", why), ("추천", rec), ("반대면", opp)], key=kit.rid(row))
    w.think(K["생각해보기"])
