# -*- coding: utf-8 -*-
"""책 정보(META) · 장 순서(ORDER) — 과제 파악 책 v3 양식
장 순서(바꾸지 않는다): 한눈에 → 1 과제가 진짜 묻는 것 → 2 함정 → 3 질문 → 4 알고리즘 → 5 시스템 → 부록 A 자료 함정 · B 나머지 질문 · C 시스템 상세"""
from .content import data
from .content.meta import fill  # noqa: F401  — 칸(과제마다 채우는 곳)은 content/meta.py


# ══ 구조 — 고치지 않는다(장 번호 · 앵커 · 읽기 기록 · 용어 사전 없음은 v3 그대로) ══
# 칸 값(한 번만 계산)
_K = fill()
# 비어 있는 META 칸 — 한눈에(pv)가 빌드 때 «빈 칸: META · 이름» 으로 알린다
META_BLANKS = [k for k, v in _K.items() if not v]

META = {
    "doc": _K["doc"] or "book",
    "title": _K["title"] or "⟦빈 칸 — META · title⟧",
    "short": _K["short"] or _K["title"] or "⟦빈 칸 — META · short⟧",
    "kicker": _K["kicker"],
    "description": _K["description"],
    "env": data.env,
    "code": {},
    "labels": {"한눈에": "pv", "1": "s1", "2": "s2", "3": "s3", "4": "s4", "5": "s5",
               "부록 A": "aA", "부록 B": "aB", "부록 C": "aC"},
    "index": False,  # 용어 사전 장 없음 — 용어는 쪽 아래 각주로만(흩어진 각주 · v3 스티커 edf14308)
    "home": "/",
    "reading_log": True,
    "qa": None,
    "no_fn": ["print", "len", "True", "False", "None", "list", "dict", "str", "int", "float", "sum", "max", "min", "range"],
    # 단계별 배포(빌드 --stage 1|2) — 1차판에 싣는 장(1장 요구 · 3장 README 질문 · 5장 시스템) · 나머지 장은 회색 «2차판에서 채워짐» 자리
    "stage1": ["s1", "s3", "s5"],
    # 1차판에서 자리만 두는 장 — 모듈 → [(장 번호, 제목)]
    "stubs": {"pv": [("한눈에", "한눈에")], "s2": [("2", "함정")], "s4": [("4", "알고리즘")],
              "apx": [("부록 A", "자료 함정 전체"), ("부록 B", "나머지 질문"), ("부록 C", "시스템 상세")]},
    # 판 표시(첫 블록 위 · 머리글)
    "editions": {1: "1차판 · 알고리즘 · 함정 준비 중", 2: "2차판"},
}

ORDER = ["pv", "s1", "s2", "s3", "s4", "s5", "apx"]
