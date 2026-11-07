# -*- coding: utf-8 -*-
"""부록 A · B · C — v3 양식
- 부록 A 자료 함정 전체: 파일별 결함 표(잘못된 예 · 정상 예 · 처리 · 줄 번호 근거 없음) + 사실 ◎(실제 데이터 · 계획에 주는 영향 · 이렇게) (스티커 702a5491 · 5d7f2666)
- 부록 B 나머지 질문: ◎ 질문 · 이유 · 추천 · 반대면 (스티커 225e8c94)
- 부록 C 시스템 상세: 그림 + 한두 줄 설명(전부 아니면 전무 실험 · 검증 리포트 · 계획 버전 · 화면 예시 · 층별 정리) (스티커 a6f40b93)"""
from . import figs, kit
from .kit import chip, mono, raw  # noqa: F401  — chip(분류) · mono(원본 조각) · raw(원본 줄 비교)
from .content.apx import fill  # noqa: F401  — 칸(과제마다 채우는 곳)은 content/apx.py


# ══ 구조 — 고치지 않는다(v3 블록 순서 · 상자) ══
def build(w):
    K = kit.slots(w, "apx", fill())

    # ══ 부록 A — 자료 함정 전체(파일별) ═════════════════════
    w.chapter("부록 A", K["A_제목"], K["A_질문"])
    w.p(*K.tf("A_들어가며1"))
    w.p(*K.tf("A_들어가며2"))
    if K.need("결함_파일별"):
        start = 0
        for f in K["결함_파일별"]:
            w.sub(f["sub"])
            for t in f["tables"]:
                kit.deftab(w, t["rows"], start, t["caption"], fn=t.get("fn"))
                start += len(t["rows"])
    w.sub(K["사실_제목"])
    if K.need("사실"):
        for i, row in enumerate(K["사실"]):
            t, c, dat, eff, todo = row
            kit.qitem(w, f"사실 {kit.no(row, i + 1)}. {t}", c, [("실제 데이터", dat), ("계획에 주는 영향", eff), ("이렇게", todo)], raw=("실제 데이터",),
                      key=kit.rid(row))

    # ══ 부록 B — 나머지 질문 ══════════════════════════════
    w.chapter("부록 B", K["B_제목"], K["B_질문"])
    w.p(*K.tf("B_들어가며"))
    if K.need("나머지_질문"):
        for i, row in enumerate(K["나머지_질문"]):
            q, cat, why, rec, opp = row
            kit.qitem(w, f"질문 {kit.no(row, i + 1)}. {q}", cat, [("이유", why), ("추천", rec), ("반대면", opp)], key=kit.rid(row))

    # ══ 부록 C — 시스템 상세(그림 + 설명) ═════════════════════
    w.chapter("부록 C", K["C_제목"], K["C_질문"])
    w.p(*K.tf("C_들어가며"))
    w.sub(K["C_적용_제목"])
    w.p(*K.tf("C_적용_설명"))
    if K.need("C_적용_그림"):
        w.svg(figs.txn(K["C_적용_그림"]))
    w.p(*K.tf("C_적용_결과"))
    w.newpage()
    w.sub(K["C_리포트_제목"])
    w.p(*K.tf("C_리포트_설명"))
    if K.need("C_리포트_표"):
        T = K["C_리포트_표"]
        kit.tab(w, ["파일", "줄", "종류", "원본 값", "처리"], T["rows"], T["caption"], raw_cols=(3,), fn=T.get("fn"))
    w.sub(K["C_버전_제목"])
    w.p(*K.tf("C_버전_설명"))
    if K.need("C_버전_표"):
        T = K["C_버전_표"]
        kit.tab(w, ["칸", "저장할 값", "왜"], T["rows"], T["caption"], fn=T.get("fn"))
    w.sub(K["C_화면_제목"])
    w.p(*K.tf("C_화면_설명"))
    if K.need("C_화면_그림"):
        w.svg(figs.screens(K["C_화면_그림"]))
    w.p(*K.tf("C_화면_풀이"))
    w.sub(K["C_층별_제목"])
    if K.need("C_층별_표"):
        T = K["C_층별_표"]
        kit.tab(w, ["층", "맡는 일", "분류", "근거"], [[a, b, chip(c), d] for a, b, c, d in T["rows"]], T["caption"], raw_cols=(2,), fn=T.get("fn"))
