# -*- coding: utf-8 -*-
"""4장 칸 — 두 파일을 합친다(고치지 않는다). 앞 절반 = s4_a.py(W4) · 뒤 절반 = s4_b.py(W5)
«자료_상태» = steps.json "data"(A3 이 자료 정리 A1 전에 계산했으면 "raw" → 4장 머리에 «자료 정리 전 · 2차판 갱신»)"""
from . import data as D, s4_a, s4_b


def fill():
    return {**s4_a.fill(), **s4_b.fill(), "자료_상태": D.contract("steps").get("data", "")}
