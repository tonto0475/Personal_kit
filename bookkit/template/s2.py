# -*- coding: utf-8 -*-
"""2 계획을 통째로 틀리게 만드는 함정 — v3 양식
흐름(바꾸지 않는다): 가장 큰 함정(자료 띠 그림) → 함정마다 ◎ 카드(실제 원본 줄 · 그냥 하면(실측 틀린 숫자) · 이렇게) → 규칙 → 먼저 맞혀 보기
v3 스티커 98318ce8(«천천히 보니 매우 중요» — 원본 줄 · 분류 색 · 굵게로 한눈에) · 702a5491(근거는 줄 번호가 아니라 실제 원본 줄)"""
from . import figs, kit, shared
from .kit import raw  # noqa: F401  — 원본 줄 조각 raw((설명, None), (원본 줄, "bad"), …)
from .content.s2 import fill  # noqa: F401  — 칸(과제마다 채우는 곳)은 content/s2.py


# ══ 구조 — 고치지 않는다(v3 블록 순서 · 상자) ══
def build(w):
    K = kit.slots(w, "s2", fill())
    S = kit.slots(w, "shared", shared.values())
    w.chapter("2", K["제목"], K["질문"])
    w.p(*K.tf("들어가며"))
    w.p(*K.tf("가장_큰_함정"))
    if S.need("그림_자료띠"):
        w.svg(figs.file_band(S["그림_자료띠"]), caption=K["그림_캡션"])
    if K.need("함정"):
        for t in K["함정"]:
            kit.qitem(w, t["title"], t["cat"], [("실제 데이터", t["data"]), ("그냥 하면", t["naive"]), ("이렇게", t["do"])],
                      raw=("실제 데이터",), fn=t.get("fn"), key=kit.rid(t))
    kit.extra_figs(w, K.opt("추가_그림"))  # 선택 — 비우면 블록 없음
    w.rule(K["규칙"])
    if K.need("맞혀보기"):
        q, a = K["맞혀보기"]
        w.guess(q, a)
