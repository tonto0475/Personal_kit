# -*- coding: utf-8 -*-
"""부록 B 칸(나머지 질문) — 담당: 집필 W3(cards/W3.md). 질문 카드는 reqs.json questions(A2, main=false)에서 자동"""
from . import data as D


# 원본 조각은 mono("값", "bad" | "good" | "") · 원본 줄 비교는 raw((설명, None), (원본 줄, "bad"), …) — 원본은 계약(facts.json)에서
def fill():
    F = D.facts()  # noqa: F841  — 실측 값(계약 numbers)
    return {
        # 제목(개수 포함) · 예: book_example/template_examples.md · B_제목
        "B_제목": "",
        # 질문 · 예: book_example/template_examples.md · B_질문
        "B_질문": "",
        # 첫 문단 · v3 문구 그대로 써도 된다
        "B_들어가며": "계획의 뼈대는 바꾸지 않지만, 답에 따라 화면 · 검증 · 저장이 달라지는 질문이다. 3장과 같은 형식으로 썼다.",
        # 나머지 질문 — [(질문, 분류, 이유, 추천, 반대면)] · 3장 «질문들» 과 같은 모양 · 6~10개
        "나머지_질문": D.question_rows(False),
    }
