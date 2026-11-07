# -*- coding: utf-8 -*-
"""4장 칸 앞 절반(4.1 쉬운 질문 → 막힘 → 이름 · 4.2 방안 A · 주의) — 담당: 집필 W4(cards/W4.md). 순서 표 · 순서 지도 · 전부 세기 표는 steps.json(A3)에서 자동"""
import math  # noqa: F401  — 경우의 수(math.factorial)

from .. import kit  # noqa: F401  — kit.sec_text(초 → 시간 글)
from . import data as D


# 칸 — 과제마다 채운다(비면 책에 «⟦빈 칸 — s4 · 이름⟧», 빌드 끝에 «빈 칸: s4 · 이름»)
# 표 칸 = w.table · w.T 에 넘길 dict({"header", "rows", "small": True, "bad_cells": [(행, 열 이름)], "good_rows", "notes", "caption"}) — 숫자는 계산값만
# 시간 글은 kit.sec_text(초) · 경우의 수는 math.factorial — 전부 세기 시간은 실제로 재서(content/data.py) 넣는다
def fill():
    F = D.facts()  # noqa: F841  — 실측 값(계약 numbers)
    return {
        # 장 제목 · v3 문구 그대로 써도 된다
        "제목": "알고리즘",
        # 이 장의 질문 · 한 줄 · 예: book_example/template_examples.md · 질문
        "질문": "",
        # ── 4.1 쉬운 질문 → 막힘 → 이름 ──
        # 절 제목 — 가장 작은 경우 · 🔴 번호(«4.1»)를 붙이지 않는다(v3 절 제목은 번호 없음 · 위 «── 4.1» 은 이 파일 안 구획 표시) · 예: book_example/template_examples.md · 절1_제목
        "절1_제목": "",
        # 쉬운 질문 — 가장 작은 경우(곳 셋)를 실제 이름으로 · 경우의 수가 몇 가지라 **전부 세어 보면** 된다 · 2문장
        # 예: book_example/template_examples.md · 쉬운_질문
        "쉬운_질문": "",
        # 순서 표 — 경우마다 한 줄 · 가장 짧은 행 good_rows · 가장 긴 행 bad_rows · notes = {행: ("← 가장 짧다", "good")}
        # 예: book_example/template_examples.md · 순서_표
        "순서_표": D.table("순서_표"),
        # 순서 작은 지도 — figs.orders_map 칸 {"points", "short", "target", "target_label", "best": (순서, "가장 짧다 50.4km"), "worst": (…), "geo", "label"}
        "순서_지도": D.figure("순서_지도"),
        # 표 + 지도 캡션 · 한 줄 · 예: book_example/template_examples.md · 순서_캡션
        "순서_캡션": "",
        # 표를 읽는 한 줄 — 차이 숫자(**굵게**) · 직관 규칙도 가장 짧지 않다
        # 예: book_example/template_examples.md · 순서_차이
        "순서_차이": "",
        # 막힘 — 곳이 늘면 경우의 수가 곱으로 · 아래 표 예고 · 2문장
        # 예: book_example/template_examples.md · 곱으로_늘어남
        "곱으로_늘어남": "",
        # 전부 세기 시간 표 — 실측 행 + 추정 행(무엇으로 추정했나) · 오래 걸리는 칸 bad_cells · caption
        # 예: book_example/template_examples.md · 전부세기_표
        "전부세기_표": D.table("전부세기_표"),
        # 더 막힘 — 이것은 차 한 대일 뿐, 실제로는 누가 어느 차에 타는지까지 · **전부 세는 방법으로는 끝나지 않는다.**
        # 예: book_example/template_examples.md · 한_대뿐
        "한_대뿐": "",
        # 이름 붙이기 상자 — 막힘 뒤에 처음 나오는 문제 이름(한 상자에 이름 둘까지 · v3 스티커 b3bd7396) + 각주
        # 예: book_example/template_examples.md · 이름_붙이기
        "이름_붙이기": "",
        # 두 갈래 — «가장 짧다» 보장을 내려놓고 괜찮은 답을 빨리 · 방안 A(규칙) · 방안 B(프로그램이 고쳐 감)
        # 예: book_example/template_examples.md · 두_갈래
        "두_갈래": "",
        # 먼저 맞혀 보기 1 — (곳 넷이면 가장 짧은 순서는?, 답 + 그것이 방안 A 의 어느 차인지)
        # 예: book_example/template_examples.md · 맞혀보기1
        "맞혀보기1": (),
        # ── 4.2 방안 A ──
        # 절 제목 · 번호 없이(«방안 A — …») · 예: book_example/template_examples.md · 절2_제목
        "절2_제목": "",
        # 방안 A 설명 — 규칙 두 줄 + 이름(휴리스틱) + 재생기 표 읽는 법 · 각주
        # 예: book_example/template_examples.md · 방안A_설명
        "방안A_설명": "",
        # 방안 A 장단점 — **장점** … **허점** …(재생기 끝에서 본 것을 숫자로) · 비슷한 규칙 하나 비교 · 이름(그리디) · 각주
        "방안A_장단점": "",
        # 주의 상자(빨강) — README 에 없지만 붙을 수 있는 조건이면 방안 A 가 깨지는 곳 · 제목 · 글
        # 예: book_example/template_examples.md · 주의_제목
        "주의_제목": "",
        "주의_글": "",
    }
