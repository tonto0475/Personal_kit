# -*- coding: utf-8 -*-
"""3장 칸 — 담당: 집필 W3(cards/W3.md). 질문 카드는 reqs.json questions(A2, main=true)에서 자동"""
from . import data as D


# 칸 — 과제마다 채운다(비면 책에 «⟦빈 칸 — s3 · 이름⟧», 빌드 끝에 «빈 칸: s3 · 이름»)
def fill():
    F = D.facts()  # noqa: F841  — 과제 분석 결과(content/data.py)
    return {
        # 장 제목 · v3 문구 그대로 써도 된다
        "제목": "지금 담당자에게 물을 것",
        # 이 장의 질문 · v3 문구 그대로 써도 된다
        "질문": "계획의 뼈대를 바꾸는 질문은 무엇이고, 답이 반대로 나오면 무엇이 달라지나?",
        # 첫 문단 — 고른 기준(뼈대를 바꾸는 것 · 예/아니오로 답이 나오게) · 추천 = 기본 가정 · 나머지 개수는 부록 B · 2~3문장
        # 예: book_example/template_examples.md · 들어가며
        "들어가며": "",
        # 질문 — [(질문 한 줄(예 · 아니오로 답이 나오게), 분류, 이유(이 자료의 숫자 2~3문장), 추천(기본 가정 · 짧게), 반대면(답이 반대면 무엇이 바뀌나 · 숫자))] 5~8개
        # 1장 «README 가 말하지 않은 곳» 가운데 뼈대를 바꾸는 것 — 질문 번호를 4장 선택표가 그대로 쓴다
        # 예: book_example/template_examples.md · 질문들
        "질문들": D.question_rows(True),
        # 생각해 보기 — 질문을 셋만 보낼 수 있다면? + 고르는 기준 한 줄(답 없이 생각만 시킨다)
        # 예: book_example/template_examples.md · 생각해보기
        "생각해보기": "",
    }
