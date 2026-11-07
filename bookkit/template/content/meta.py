# -*- coding: utf-8 -*-
"""책 이름 · 제목 칸 — 담당: 집필 W1(cards/W1.md). new_book.py 가 "doc" 을 넣는다"""


# 칸 — 책 이름 · 제목(과제마다)
def fill():
    return {
        # 문서 이름 — new_book.py 가 책 폴더 이름으로 넣는다(영문 · 숫자 · _ · -). 출력 파일 이름 · 스티커 · 읽기 기록의 열쇠
        "doc": "",
        # 제목 — 브라우저 탭 · 쪽 머리글 · 30자 안팎 · 예: book_example/template_examples.md · title
        "title": "",
        # 짧은 제목 — 좁은 화면 머리글 · 15자 안팎 · 예: book_example/template_examples.md · short
        "short": "",
        # 과제 이름 한 줄(엔진이 표지 위 작은 글로 읽는다 — 이 양식은 표지가 없다) · 예: book_example/template_examples.md · kicker
        "kicker": "",
        # 설명 한 줄(html description) · 예: book_example/template_examples.md · description
        "description": "",
    }
