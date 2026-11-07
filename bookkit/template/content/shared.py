# -*- coding: utf-8 -*-
"""여러 장이 함께 쓰는 그림 · 재생기 — 계약에서 자동(집필이 고치지 않는다). 시스템 층만 content/s5.py 의 layers()"""
from . import data as D, s5


# 칸 값은 계약에서 온다 — 큰 흐름 · 재생기 셋 = steps.json(A3) · 자료 띠 = facts.json(A1) · 시스템 층 = content/s5.py(W5)
# json 으로 쓸 때: 짝 (a, b) = 목록 [a, b] · 함수 칸(measure · deadhead · place) = 표 — bookkit/contracts/README.md
def fill():
    return {
        # 큰 흐름 + 묶음 막대 — figs.overview 칸. 한눈에 첫 그림 · 1장 첫 그림
        #   위 흐름 = 입력 → 검증 · 적용 → 계획 계산 → 화면 둘(상자 글, 줄바꿈 \n · 3줄 안쪽)
        #   아래 막대 = 하루에 일이 몰리는 묶음(열 4~12개 · 열마다 막대 1~3개 · 값은 실측)
        # 예: book_example/template_examples.md · 그림_큰흐름
        "그림_큰흐름": D.figure("그림_큰흐름"),
        # 자료 띠 — figs.file_band 칸. 한눈에 둘째 그림 · 2장 첫 그림
        #   가장 큰 자료 함정을 «파일 줄 구간» 으로(구간 2~5개 · 줄 번호는 원본에서 센 값) + 정리 전후 숫자 막대(에러 없이 틀린 숫자)
        # 예: book_example/template_examples.md · 그림_자료띠
        "그림_자료띠": D.figure("그림_자료띠"),
        # 시스템 층 — figs.layers 칸. 한눈에 셋째 그림 · 5장 그림 — 집필 W5 가 content/s5.py 의 layers() 에 쓴다
        "그림_시스템층": s5.layers(),
        # 재생기 1 «채우기» — kit.stepper_fill 칸. 한눈에 · 4장 방안 A
        #   한 단계 = 한 곳의 사람(물건)을 차 하나에 담기 · 단계 글 = 동작 + 결과 숫자 · 끝 단계가 허점을 드러낸다 · 차 하나 = 색 하나(v3 시각화 규칙)
        # 예: book_example/template_examples.md · 재생기_채우기
        "재생기_채우기": D.player("채우기"),
        # 재생기 2 «한 곳씩 고치기» — kit.stepper_fix 칸. 한눈에 · 4장 방안 B
        #   한 단계 = 바꾸기 한 번(순서 바꾸기 · 옮기기 · 맞바꾸기) · 바뀐 차만 굵게(hl) · 더는 안 들르는 곳에 빨간 ×(gone) · 표의 그 단계 행 강조(row)
        # 예: book_example/template_examples.md · 재생기_고치기
        "재생기_고치기": D.player("고치기"),
        # 재생기 3 «이어 붙이기» — kit.stepper_chain 칸. 한눈에 · 4장 공통 단계
        #   한 단계 = 일(트립 · 운반) 하나를 시작 시각 순서로 붙이기 · 시간 안에 닿는 빈 차가 있으면 그 차, 없으면 새 차 · 보유선 위로 올라가는 순간이 결론
        # 예: book_example/template_examples.md · 재생기_이어붙이기
        "재생기_이어붙이기": D.player("이어붙이기"),
    }
