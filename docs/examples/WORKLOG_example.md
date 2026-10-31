# WORKLOG — 주문 API 안정성 개선 작업 기록 (예시)

> 🔴 이 파일은 **예시**다. docs/examples/ADR_example.md 와 같은 과제 · 같은 시점(1-3 «변경 1» 승인 대기)으로 채웠다. 해시 · 시각은 가짜다.
> 결정의 정본은 ADR — 여기 옮긴 결정은 그 시점 사본이다.

> [!abstract] 🔄 인계 — 10-31 12:50 갱신
> - **지금 하던 일**: 1-3 1회차 — 단계 1(요청 구별 키 · 중복 금지 설정) 통과 · 커밋. 단계 2(timeout → «확인 중») 구현 중 화면 파일이 범위 밖이라 수정 범위 «변경 1» 등록 → 승인 대기
> - **다음에 할 일**: 유저 «승인»이 오면 src/ui/order_page.py 의 결과 표시 수정 → 검증 요청(1-3 단계 2). 승인 전에는 1-2 숫자 카드 마무리
> - **열린 질문**: ADR 1-1 3회차 🔴(다시 시도 연속 클릭) · ADR 1-3 변경 1 승인 · 지도 «확인할 것» Q2 · Q3
> - **마지막 통과 커밋**: e7f8a9b — 1-3 단계 1(tests/test_orders_retry.py 6 passed · 동시 요청 틀 행 수 1)
> - **다음 세션이 먼저 읽을 스킬 파일**: ~/.codex/skills/decision-work/SKILL.md · 1-3
> - **버린 시도 · 이유**: timeout 을 «실패»로 바로 보이는 안 — 담당자 답(«처리 대기») 과 달라 버림
> - **유저와 하던 일**: 변경 1(화면 파일 범위 추가) 승인을 기다리는 중 · 그동안 1-2 숫자 카드를 하기로 함
>
> **참조 중인 문서** — 경로 · 어느 부분 · 왜
> - docs/ADR.md — 1-3 수정 범위 · 성공 기준 C3 ~ C5 — 단계 2 구현 기준 · 변경 1 승인 여부
> - docs/ONTOLOGY.md — 6번 결제 경우 · 7번 규칙 2 — «모름 → 확인 중» 흐름의 근거
> - docs/INTERVIEW.md — 2절 10:40 받은 답 — 담당자 «처리 대기» 원문
> - docs/CODE_RULE.md — 7절 에러 종류 — timeout 을 외부 실패와 따로 나누는 이유

---

## 0. 수정 전 기준선 · 환경
- **도구 버전**: Python 3.12.3 · git 2.43.0 · node 없음(파이썬 과제라 설치 안 함)
- **수정 전 기준선**: python3 -m pytest -q tests → 9 passed · 0 failed · 종료코드 0(10:08 · 유저가 «돌려» 로 승인)
- **기존 테스트가 보는 것 · 안 보는 것**: 결제 timeout 이면 «에러가 나는지»만 본다 — 주문이 어떤 상태로 남는지 · 같은 요청 두 번에 몇 줄 생기는지는 안 본다

## 서술형 재료
- [핵심 동작] 1-3 · 같은 요청 구별 키로 두 번 보내도 주문 1줄 → tests/test_orders_retry.py 6 passed · 커밋 e7f8a9b
- [장애 대응] 1-3 · 결제 timeout 재시도 때 주문 2줄 → 실제 실패 입력 그대로 재현(6d7e8f9) → 요청 구별 키 + 중복 금지 설정 · 커밋 e7f8a9b
- [설계 결정] 기존 테스트는 «에러가 나는지» 만 봄 → 주문 상태 · 줄 수를 보는 테스트를 더함(기준선 9 passed)

## 기록

### 10:05 · 시작 · 정찰
- **한 일**: 키트 겹침 목록(AGENTS.md · README.md · docs/README.md · .env.example) → 유저가 «과제 AGENTS.md 아래에 우리 AGENTS 를 붙이고 나머지는 과제 것 유지»로 정하고 직접 옮김 → 세션 다시 시작 → $ready-start → 정찰 6항목(requirements.txt · FastAPI · app/main.py · 상위 2단계 폴더 · config/settings.toml · tests/) → «주문 생성» 요청 하나 추적: POST /orders → create_order → request_payment → orders 표
- **바뀐 파일**: docs/README.md(구조표)
- **커밋**: 1a2b3c4

### 10:30 · 지도 초안 · 담당자 질문
- **한 일**: $ontology 초안(확인할 것 8개) → 유저가 1단계 4개를 자기 말로 담당자에게 물음(INTERVIEW 2절 10:32)
- **바뀐 파일**: docs/ONTOLOGY.md · docs/INTERVIEW.md
- **커밋**: 2b3c4d5

### 12:05 · 1-3 · 섹션 시작
- **한 일**: 논의 1회차 정리 · 수정 범위(파일 3개 · 함수 5개 · 생성 예정 2개) → 유저 «승인» → 초록
- **섹션 시작 커밋**: 5c6d7e8(검증 범위의 기준점)

### 12:20 · 1-3 · 디버깅 1회차 — 재현
- **한 일**: 같은 요청 구별 키로 두 번 → 주문 2줄을 실제 실패한 입력 그대로 재현. 예상된 실패 표시(raises=AssertionError · strict=True)를 붙여 커밋
- **실행 · 결과**: python3 -m pytest -q tests/test_orders_retry.py → 1 xfailed · 종료코드 0
- **커밋**: 6d7e8f9 «[1-3] 중복 주문 재현 테스트 - 같은 키 두 번에 주문 2줄»

### 12:35 · 1-3 · 구현 단계 1 — 요청 구별 키 · 중복 금지 설정
- **한 일**: 주문 표의 요청 구별 키에 중복 금지 설정 · 같은 키면 기존 주문을 돌려줌 · 재시도에 처음과 같은 키. 재현 테스트의 표시를 뗌
- **바뀐 파일**: src/core/orders.py · src/api/payments.py · src/db/schema.py · tests/test_orders_retry.py
- **실행 · 결과**: python3 -m pytest -q tests/test_orders_retry.py → 6 passed · 종료코드 0 / 동시 요청 틀: 동시 2번 1행 · 0.1초 간격 2번 1행 · 중복 금지 설정 확인 참
- **커밋**: e7f8a9b «[1-3] 요청 구별 키 · 중복 금지 설정 - 재시도 때 주문 2줄(재현 6d7e8f9)»
- **검증 요청**: «$decision-work verify 1-3 · 단계 1 · 범위 5c6d7e8..e7f8a9b · src/core/orders.py · src/api/payments.py · src/db/schema.py»

### 12:48 · 1-3 · 논의 변경 — 범위 밖 파일
- **한 일**: «확인 중»을 화면에 보이려면 src/ui/order_page.py 가 필요 → 수정 범위 «변경 1» 등록 · 콜아웃 주황 · 승인 전에는 손대지 않고 1-2 로 넘어감
- **바뀐 파일**: docs/ADR.md
- **커밋**: f8a9b0c

### 12:50 · 인계 · 압축
- **한 일**: 유저가 맥락 % 를 보고 $hand-off → 맨 위 인계 칸 갱신 · 커밋 → 유저 /compact → $hand-on 으로 인계 칸 · 참조 문서의 적힌 부분만 · 압축 직전 10턴을 다시 읽음
- **커밋**: a9b0c1d «[인계] 1-3 단계 2 · 변경 1 승인 대기»
