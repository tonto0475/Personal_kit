# -*- coding: utf-8 -*-
"""여러 장이 함께 쓰는 칸 — 그림 셋(큰 흐름 · 자료 띠 · 시스템 층) · 단계 재생기 셋(채우기 · 한 곳씩 고치기 · 이어 붙이기)
한눈에(pv)와 본문(1 · 2 · 4 · 5장)에 같은 그림 · 재생기가 두 번 나온다 — 데이터는 여기 한 곳에서만 채운다
값은 content/shared.py 가 계약(steps.json · facts.json)에서 꺼낸다 — 값 모양은 figs.py · kit.py 의 함수 설명(docstring) · bookkit/contracts/README.md
v3 전체 값 예: 같은 키트의 books/_selftest_v3/contracts/steps.json (공개 저장소에는 없을 수 있다)"""
from .content.shared import fill  # noqa: F401  — 칸(과제마다 채우는 곳)은 content/shared.py


# ══ 구조 — 고치지 않는다 ══
# 칸 값(빌드 한 번에 한 번만 계산 — 여러 장이 나눠 쓴다)
_V = None


def values():
    """칸 값 dict — 처음 부를 때 fill() 을 한 번 돌린다"""
    global _V
    if _V is None:
        _V = fill()
    return _V
