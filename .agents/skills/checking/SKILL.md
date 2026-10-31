---
name: checking
description: 인지 설문 — 다른 세션이 작업하는 동안 유저가 과제 흐름(README 요구 · 구현하는 것 · 안 하는 것)을 얼마나 이해했는지 «이해했습니까?» 설문으로 확인하고, 모르는 항목은 설명 폼으로 다시 띄운다. «$checking» 으로 유저가 부른다. 도구는 같은 폴더의 cognition.py · 등록은 $survey.
---

# checking — 인지 설문

유저가 작업 흐름을 따라가고 있는지 중간중간 확인한다. 서술형(확인 문제)은 유저가 자기 말로 설명해야 하는데, 작업은 Codex 가 해서 이해가 빠지기 쉽다.

## 1. 언제
- 유저가 «$checking» 으로 부를 때(보통 2ND 세션에서 — MAIN · INSP 가 작업하는 동안)
- 인자로 범위를 줄 수 있다: «$checking README» · «$checking 1-2»(ADR 섹션) — 없으면 README 전체 + 지금까지의 ADR

## 2. 재료 모으기 — 지어내지 않는다
- 읽기: 과제 README → docs/ONTOLOGY.md 만들 것 판정 · 확인할 것(받은 답) → docs/ADR.md(합의된 범위 · 🟢 결정) → docs/WORKLOG.md 인계 칸
- /tmp/cog_재료.json 에 쓴다:

        {"title": "2ND 인지 · 주제", "readme": [README 요구 한 줄 또는 {"text": "...", "source": "README 원문 그대로"}], "do": [구현하는 것], "dont": [구현하지 않는 것]}

- README · 지도 · ADR · WORKLOG 에 **있는 것만** — 기록에 없는 요구 · 결정은 넣지 않는다

## 3. 설문 만들기 · 띄우기
        python3 ~/.codex/skills/checking/cognition.py make /tmp/cog_재료.json --out /tmp/cog

- → /tmp/cog_1.json …(10문항씩) → $survey 3절로 등록하되 저장 폴더는 저장소 밖(python3 ~/.codex/skills/survey/survey.py --dir /tmp/sv new <파일> --project 2nd — --dir 은 하위 명령 앞) · 유저에게 «설문 탭(Alt+S)» 한 줄 · 턴 끝
- 문항 = «문제에 «…» 이런 요구사항이 있었습니다. 이해했습니까?» · 선택지 예 / 아니오(+ 도구가 붙이는 기타 · 보류 · 질문)
- 🔴 설명 칸 · 메모 기본 글을 더하지 않는다 — 유저가 예를 고르면 메모에 이유를 직접 쓴다

## 4. 결과 처리
        python3 ~/.codex/skills/checking/cognition.py followup <결과.json> --survey <설문.json> --out /tmp/cog_fu.json

- → 질문 · 아니오 · 기타를 고른 항목만 모인 설명 폼 뼈대
- 항목마다 body 에 설명을 채운다 — 근거(README 원문 · ADR 결정 · 커밋)를 같이 · 유저 질문이 있으면 그 답
- 예를 고른 메모가 기록과 다르면 그 항목도 더해 바로잡는다
- $survey 2-1 설명 폼으로 다시 띄운다 · 유저 메모에 또 질문이 있으면 반복

## 5. 하지 않는 것
- 저장소에 쓰지 않는다(재료 · 질문 파일은 /tmp) · 코드 · 문서를 고치지 않는다
- 서술형 모의는 여기가 아니다($ready-end 5-1절)

## 6. 시험
        python3 ~/.codex/skills/checking/test_cognition.py
