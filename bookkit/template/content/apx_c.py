# -*- coding: utf-8 -*-
"""부록 C 칸(시스템 상세) — 담당: 집필 W5(cards/W5.md). 적용 실험 · 화면 그림 · 리포트 표는 계약에서 자동"""
from . import data as D
from ..kit import chip, mono, raw  # noqa: F401  — chip(분류) · mono(원본 조각) · raw(원본 줄 비교)


# 원본 조각은 mono("값", "bad" | "good" | "") · 원본 줄 비교는 raw((설명, None), (원본 줄, "bad"), …) — 원본은 계약(facts.json)에서
def fill():
    F = D.facts()  # noqa: F841  — 실측 값(계약 numbers)
    return {
        # 제목 · 질문 · 첫 문단 · v3 문구 그대로 써도 된다
        "C_제목": "시스템 상세",
        "C_질문": "층마다 이 과제에서 무엇을 맡고, 검증 리포트 · 계획 기록 · 화면은 어떤 모양인가?",
        "C_들어가며": "5장의 층 그림을 층별로 풀었다. 그림마다 무엇을 보면 되는지 한두 줄씩 적었다.",
        # 전부 아니면 전무 — 작은 제목(v3 문구 그대로) · 실험 설명 · figs.txn 칸 · 결과 설명(README 원문 요구와 잇기)
        "C_적용_제목": "자료 적용 — 트랜잭션이 없을 때와 있을 때",
        # 예: book_example/template_examples.md · C_적용_설명
        "C_적용_설명": "",
        # figs.txn 칸 — {"names": [파일 이름 …], "fail": 실패 위치(0부터), "rows": {"none": {이름: 행 수}, "txn": {…}}, "labels": {"none": (이름, 설명), "txn": (…)}, …}
        # rows 는 sqlite3 메모리 DB 로 실제로 넣어 본 결과(content/data.py — _selftest_v3 의 txn_demo 참고)
        "C_적용_그림": D.figure("C_적용_그림"),
        # 예: book_example/template_examples.md · C_적용_결과
        "C_적용_결과": "",
        # 검증 리포트 — 작은 제목 · 설명(v3 문구 그대로) · 표 {"rows": [[파일, 줄, 종류, 원본 값 HTML(mono), 처리]], "caption"} (이 자료의 실제 줄 6~8개)
        "C_리포트_제목": "검증 리포트 — 운영자가 보는 자료 문제 목록",
        "C_리포트_설명": "올린 CSV 의 문제를 줄마다 보여 준다. 아래는 이 자료의 실제 줄로 만든 예다. 리포트에는 줄 번호가 있어야 운영자가 원본을 고칠 수 있다.",
        # 예: book_example/template_examples.md · C_리포트_표
        "C_리포트_표": D.report_table(),
        # 계획 버전 — 작은 제목 · 설명(v3 문구 그대로) · 표 {"rows": [[칸, 저장할 값, 왜]], "caption"}
        "C_버전_제목": "계획 버전 — 무엇을 함께 저장하나",
        "C_버전_설명": "계획을 만들 때마다 번호를 붙여 저장하고, 화면은 «현재» 표시가 붙은 버전만 읽는다. 아래 칸이 있어야 같은 계획을 다시 만들고, 설정이 바뀌었는지 알아챈다.",
        # 예: book_example/template_examples.md · C_버전_표
        "C_버전_표": {},
        # 화면 예시 — 작은 제목 · 설명 · figs.screens 칸(계획에서 읽은 실제 값) · 그림 풀이(한 사람을 따라 읽기)
        # 예: book_example/template_examples.md · C_화면_제목
        "C_화면_제목": "",
        # 예: book_example/template_examples.md · C_화면_설명
        "C_화면_설명": "",
        # figs.screens 칸 — {"left": {"title", "head", "cards": [{"tone", "fill", "label", "lines": [(글, 크기, 굵게?, 색)]}] 2장, "foot"}, "right": {"title", "cols": [(x, 열 이름)], "rows": [[…]], "foot"}, "label"}
        "C_화면_그림": D.figure("C_화면_그림"),
        # 예: book_example/template_examples.md · C_화면_풀이
        "C_화면_풀이": "",
        # 층별 정리 — 작은 제목(v3 문구 그대로) · 표 {"rows": [(층, 맡는 일, 분류, 근거)], "caption", "fn"}
        "C_층별_제목": "층별 정리",
        # 예: book_example/template_examples.md · C_층별_표
        "C_층별_표": {},
    }
