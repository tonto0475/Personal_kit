---
name: codex-hub
description: devview 허브(대화 탭)에 이 세션을 붙이고($codex-hub [이름]) 지금 작업(상태 줄) · 큰 완료(누적)를 알리고 다른 세션에 글을 보낸다. 역할 스킬이 시작 때 부른다. 허브에서 온 «$역할-magic 요청id» 는 그 magic 스킬.
---

# codex-hub — 허브에 붙기 · 상태 줄 · 누적 · 보내기

1. 이름(앞에서부터 처음 나오는 것): 유저가 준 이름(«$codex-hub 이름») → 역할 스킬이 정한 이름(main|2nd) → 세션 이름(python3 ~/.codex/skills/ready-start/whoami.py list | grep "$CODEX_THREAD_ID" 줄의 UUID 뒤 글자 · None 이면 없음) → 없으면 유저에게 «허브에 쓸 이름?» 묻고 멈춘다
   - 붙기(세션 시작 때 한 번): `./kit hub register --nick '이름'`(키트 폴더에서 · = python3 ~/.codex/skills/codex-hub/hub.py …)
   - thread 는 CODEX_THREAD_ID · 비면 출력 «thread 없음» 그대로 보고 · 같은 이름이면 이 세션으로 바뀜
   - 보고 한 줄: «대화 탭에 <이름> 등록 · thread <앞 8자>»
   - Claude 세션이면: `./kit hub register --nick '이름' --claude` — 세션 id 는 스크립트가 찾는다 · «tmux 밖» 이 나오면 읽기만 된다고 보고(보내기 · 마법봉은 tmux 안에서 띄운 세션만)
2. 상태 줄 — 일을 시작할 때: `./kit hub status` '❇️_절번호 : 일 종류. 무엇'
   - 한 줄 · 60자 안팎 · 숫자만 쓰지 않는다 · 섹션 밖 일은 '확인 : …' · '답변 : …'
3. 누적 — 섹션 안 큰 단위가 끝났을 때만: `./kit hub log` '❇️_절번호 결과 한 줄 · 근거 파일'
   - 쓴다: 큰 단위 완료(화면 하나 · API 묶음) · 섹션 검증 결과 · ready-end · 도커 빌드
   - 안 쓴다: 도구 하나마다 · 질문 답 · 유저가 시킨 확인 · 디버깅(상태 줄만 바꾼다)
4. 허브에서 온 queue 메시지는 유저 메시지와 같다 · 🪄 로 시작하고 끝 줄이 «$main-magic 요청id»(Claude 는 «/main-magic 요청id») 면 그 스킬을 따른다 · «@이름 » 으로 시작하면 그 세션이 보낸 글
5. 다른 세션에 보내기(유저가 시킨 그 한 번만): `./kit hub send --to 이름 '글'` — 앞에 «@내이름 » 이 자동으로 붙는다
- 글은 작은따옴표로(큰따옴표면 $ 낱말이 빈 값) · 성공은 한 줄 · «실패: 원인» 이면 원인대로
- 파일은 작업 폴더 .codex-hub/ — 손으로 고치지 않는다 · 시험: python3 -m pytest -q .agents/skills/codex-hub
