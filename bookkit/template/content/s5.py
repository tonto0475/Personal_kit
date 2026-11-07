# -*- coding: utf-8 -*-
"""5장 칸 — 담당: 집필 W5(cards/W5.md). 시스템 층 그림 칸(layers)도 여기 — shared 가 불러 한눈에 · 5장에 쓴다"""
from . import data as D


# 칸 — 과제마다 채운다(비면 책에 «⟦빈 칸 — s5 · 이름⟧», 빌드 끝에 «빈 칸: s5 · 이름»)
def fill():
    F = D.facts()  # noqa: F841  — 과제 분석 결과(content/data.py)
    return {
        # 장 제목 · 이 장의 질문 · v3 문구 그대로 써도 된다
        "제목": "시스템",
        "질문": "무엇을 어디에 저장하고, 계산은 어디서 돌리며, 무엇을 주의해야 하나?",
        # 첫 문단 — 저장소 선택 · 화면은 계산하지 않고 완성본만 · 적용은 검증 뒤 한 번에 · 각주 · 2~3문장
        # 예: book_example/template_examples.md · 들어가며
        "들어가며": "",
        # 시스템 층 그림 캡션 · v3 문구 그대로 써도 된다
        "그림_캡션": "시스템 층 — 무엇을 저장하고, 어떤 요청이 있고, 계산은 어디서 돌리는가",
        # 주의 — [{"title", "cat", "why": 왜 해당하나(README 원문 · 실험 숫자 2~3문장), "do": 이렇게(1~2문장), "fn": 각주 | None}] 2~4개
        # 예: book_example/template_examples.md · 주의
        "주의": [],
        # 추가 그림(선택 · 비우면 블록 없음) · 한 대(한 건)가 거치는 상태는 «상태전이» — [{"fig": "상태전이" | "시각막대" | "두줄비교", "P": 그림 칸, "caption": 한 줄}]
        #   그림 칸은 계약에서: D.figure("시각막대") 처럼(분석 틀이 낸 것) · 모양은 figs.states · time_bars · pair_rows 설명
        "추가_그림": [],
        # 해당 없음 — **해당 없음 — …(굵게)** 로 시작 · 왜 필요 없나(숫자) · 각주
        # 예: book_example/template_examples.md · 해당_없음
        "해당_없음": "",
        # 맺음 한 줄 — 부록 C 에 무엇이 그림으로 있나 · v3 문구 그대로 써도 된다
        "맺음": "층마다 맡는 일, 검증 리포트 · 계획 버전 · 화면의 실제 모양은 부록 C 에 그림으로 있다.",
    }


# 시스템 층 그림 칸 — figs.layers(한눈에 셋째 그림 · 5장 그림). shared 가 이 함수를 부른다 · 비우면 두 곳에 빈 칸
# 예: book_example/template_examples.md · layers()
def layers():
    return {}
