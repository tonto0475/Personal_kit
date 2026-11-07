# -*- coding: utf-8 -*-
"""부록 칸 — 세 파일을 합친다(고치지 않는다). 부록 A = apx_a.py(W2) · B = apx_b.py(W3) · C = apx_c.py(W5)"""
from . import apx_a, apx_b, apx_c


def fill():
    return {**apx_a.fill(), **apx_b.fill(), **apx_c.fill()}
