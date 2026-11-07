# -*- coding: utf-8 -*-
r"""통근버스 노선 — 문제 파악 가이드 개편판(v3): 책 정보(META) · 모듈 순서(ORDER)

- 출발점 = v1(task10) + 독자 스티커 20개(STICKERS_v1.txt) — 반영 기록은 bookblind10o\REVISE_LOG.md
- 표지 · 차례 없음 — 첫 장 «한눈에» 가 본문 그림 · 조작 블록을 먼저 모아 보인다
- 장 순서: 한눈에 → 1 과제 → 2 함정 → 3 질문 → 4 알고리즘 → 5 시스템(알고리즘 뒤로) → 부록 A 자료 함정 · B 나머지 질문 · C 시스템 상세
- 숫자는 data.py 가 CSV 에서 다시 계산(F) · 저장 결과 work\task10_cache.json(C) · work\task10v3_cache.json(C3)
"""
from . import data

META = {
    "doc": "task10_guide_v3",
    "title": "통근버스 노선 — 문제 파악 가이드 (개편판)",
    "short": "통근버스 노선 가이드(개편판)",
    "kicker": "통근버스 노선 시스템 과제",
    "description": "과제 폴더의 README · CSV 7개를 직접 열어 계산한 문제 파악 안내서 개편판 — 숨은 요구 · 함정 · 담당자 질문 · 알고리즘 · 시스템",
    "env": data.env,
    "code": {},
    "labels": {"한눈에": "pv", "1": "s1", "2": "s2", "3": "s3", "4": "s4", "5": "s5",
               "부록 A": "aA", "부록 B": "aB", "부록 C": "aC"},
    "index": False,  # 용어 사전 장 없음 — 용어는 쪽 아래 각주로만(흩어진 각주 유지)
    "home": "/",
    "reading_log": True,
    "qa": None,
    "no_fn": ["print", "len", "True", "False", "None", "list", "dict", "str", "int", "float", "sum", "max", "min", "range"],
}

ORDER = ["pv", "s1", "s2", "s3", "s4", "s5", "apx"]
