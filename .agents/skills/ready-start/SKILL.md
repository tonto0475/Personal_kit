---
name: ready-start
description: MAIN 환경 세팅 — 두 단계. 1단계(과제를 받은 직후 처음 세션의 «$ready-start») = Codex 설정 넣기 · 압축 훅 · git 이름 · 내 UUID → ReadyStart.txt(재시작 · INSP · 2ND 명령). 2단계(재시작한 MAIN 의 «$main» 이 맨 처음 이 파일을 읽어서) = AGENTS · 스킬 확인 · 라이브러리 · 환경 점검 · 작업 폴더 git 등록 · devview 설문 확인. 대회 맥락 · 역할 · 작업 범위는 $main · $insp · $2nd. 키트와 과제 저장소의 겹치는 이름은 같은 폴더의 overlap.py 로 목록만 본다.
---

# ready-start — 환경 세팅 · 확인 (MAIN 전용)

- **MAIN 세션 하나에서만** 부른다. 대회 맥락 · 역할 · 작업 범위는 다루지 않는다 → $main · $insp · $2nd
- 키트 폴더(아래 «키트») = 키트를 푼 곳(보통 <루트>/kit) = **작업 폴더**. 문서 · 앱 코드 · 스킬 · .venv 를 여기서 쓴다(2026-10-30 유저 지정)
	- 스킬은 설치 한 줄이 ~/.codex/skills 로 복사한다 → 처음 세션(루트에서 그냥 codex)에서도 $ready-start 가 보인다 · 설치본 키트의 스킬 원본은 skills_src/(이름 바꿈 — 두 곳 중복 방지)
	- 키트를 기본 경로로 잡는 건 6절 명령이다 — MAIN 재시작 · INSP · 2ND 를 -C <키트> --add-dir <루트> 로 띄워 키트 AGENTS 가 실리고(0.163 · codex debug prompt-input 실측) 루트 과제 파일 · .git 에도 쓴다
	- 아래 명령의 상대 경로(docs/ · scripts/)는 키트 기준 — 처음 세션은 루트에서 떠 있으니 cd <키트> 뒤 실행 · 스킬 도구는 ~/.codex/skills/… · <루트> = git rev-parse --show-toplevel(대회는 /home/user)
- ⭐ **두 단계로 나눈다**(2026-10-31 유저 지정 — 처음 세션에서 devview · venv 까지 하려다 실패)
	- **1단계 = 처음 세션(루트에서 뜬 Codex)의 «$ready-start»**: 5절(git 이름) → 2절(config) → 3절(훅) → 6절(내 UUID → ReadyStart.txt) **만** 하고 끝낸다. 보고 표의 나머지 줄은 «2단계» 로 적는다
	- **2단계 = 재시작한 MAIN 이 «$main» 맨 처음에 이 파일을 읽고**(main 0-0 · 키트에서 떠 있다): 1절(AGENTS · 스킬) → 0절(라이브러리 · .venv) → 0-1(envcheck) → 1-1(git 등록) → 4절(devview 설문 — 유저가 ReadyStart.txt 0번 줄로 devview 를 띄운 뒤) → 7절 마무리 · 보고 표 전체
	- 명령은 **하나씩** 실행하고 결과를 본 뒤 다음으로 — 여러 명령을 ; · && 로 묶지 않고, 한 번에 여러 명령을 동시에 돌리지도 않는다(묶음은 마지막 명령의 종료코드만 남아 무엇이 깨졌는지 모른다 — 1단계에서 없는 .gitignore 를 cat 한 것 하나로 묶음 전체가 «Failed» 로 보였다)
	- 없을 수 있는 파일은 읽기 전에 test -f 로 본다(대회 기계는 처음에 .gitignore · .env.example 이 없다)
	- ⭐ 설정 · 훅은 Codex 를 **다시 띄워야** 먹는다 — 1단계 세션은 옛 설정 그대로가 정상이다(2026-10-31 실측: 넣은 설정으로 새로 띄우면 단축키 · 상태줄이 바뀜)
- 🔴 Codex 샌드박스 안에서는 ~/.codex 가 읽기 전용이다 → 2 · 3 의 쓰기는 **샌드박스 밖 실행 승인**을 요청한다. 거절되거나 막히면 유저 터미널 탭에서 칠 명령 한 줄을 준다
- 덮어쓰기 금지 — 이미 있는 파일 · 키는 바꾸지 않고 보고만 한다(바꿀지는 유저)

## 결과 보고 — 언제나 이 표 하나
- 아래 9줄을 그대로 쓴다. 상태 = 🟢 됨 · 🟠 유저 판단 필요 · 🔴 안 됨. 🟢 이면 «안 될 때 영향» 칸은 비우고, 🟠 · 🔴 이면 그 줄의 영향 문장을 그대로 넣고 뒤에 «무엇을 하면 되나» 한 마디

| 항목 | 상태 | 안 될 때 영향 |
|---|---|---|
| git 이름 · 메일(5절 · 1단계) | | 커밋이 전부 실패한다 → 작업 기록 증거가 안 남는다 |
| config(2절 · 1단계) | | 키트 화면 · 단축키 설정이 안 먹는다(작업은 된다) |
| 압축 훅(3절 · 1단계) | | 압축 직후 인계 안내가 저절로 안 뜬다 → $hand-on 을 손으로 |
| AGENTS 실림(1절 · 2단계) | | 우리 규칙(보안 · 커밋 · 문서)이 안 실려 Codex 가 기본 동작으로 일한다 |
| 스킬 실림(1절 · 2단계) | | 빠진 $스킬은 못 쓴다(빠진 이름을 적는다) |
| 라이브러리 설치(0절 · 2단계) | | 과제에 필요한 라이브러리(nicegui 등)를 못 깐다 → 표준 라이브러리로만 |
| 환경 점검(0-1절 · 2단계) | | 체험 뒤 바뀐 것(외부 접속 · 버전 · 막힌 기능)을 작업 중간에야 알게 된다 |
| 작업 폴더 git 등록(1-1절 · 2단계) | | 규칙 · 스킬 · 문서가 커밋 기록에 안 남고, 도구 폴더가 섞여 들어갈 수 있다 |
| devview 설문(4절 · 2단계) | | 설문 · 설명 폼을 못 쓴다 → 질문은 채팅 선택지로 |

- 1단계는 표(2단계 줄의 상태 칸은 «2단계») · «명령은 <키트>/ReadyStart.txt 에 — 0 → 1 → 2 → 3 순서로(devview → MAIN 재시작 → INSP → 2ND)» · «설정 · 훅은 1번 줄로 다시 띄우면 먹는다 · 다시 뜨면 «Hooks need review» 질문이 바로 나온다 → 2(Trust all and continue)» 세 줄로 끝낸다
- 2단계는 표 전체 · 7절 안내로 끝낸다(커밋 목록은 띄우지 않는다 — 7절)

## 0. 이 기계 — 체험 1 · 2회차 실측 (라이브러리 확인은 2단계)
- 대회 플랫폼이 응시자마다 주는 일회용 리눅스 샌드박스 · **과제 폴더 = 홈(/home/user)** · git 저장소
- python 3.11 · git 2.39 · node 22 · 외부 접속 · pip 됨 · chromium · bwrap 없음 · codex 0.163 · 서버는 유저 터미널 탭에서(Codex 샌드박스는 소켓을 막는다)
- 라이브러리 설치: python3 -m pip install --dry-run pip 로 본다
	- 되면 🟢 «시스템 pip 그대로»
	- «externally-managed-environment»(PEP668)로 막히면 키트 안에 python3 -m venv .venv 를 만들어 그 안에 설치한다(<키트>/.venv · 1-1 이 커밋에서 뺌) → 만들어지면 🟢 «막힘 → venv 로» · venv 도 실패하면 🔴 · venv 를 만들었으면 이후 시험 · 점검 · 앱 실행은 python3 대신 .venv/bin/python(run.sh 는 .venv 가 있으면 알아서 쓴다)

## 0-1. 환경 점검 — envcheck 한 번(샌드박스 밖 승인 · 2단계)
- bash scripts/envcheck/envcheck.sh --no-install — **처음부터 샌드박스 밖 실행 승인을 요청**한다(기본 샌드박스는 소켓을 막아 PermissionError 로 멈춘다 · 2회차 실측) · 약 7초 · 실패 · 정보 줄과 «요약: 번호» 만 나온다
- 체험 때 실패: A6(git 이름 · 메일 → 5절이 채움) · B3(AGENTS · 스킬 위치 — 키트에서 띄웠으면 정보) · B4(bwrap 없음 · 대처 없음 · 정보) — 이 셋만이면 🟢 «체험과 같음»
- 그 밖 번호가 있으면 🟠 번호 · 사유(envcheck README 3절의 대처) — 체험 뒤 기계가 바뀐 것이다
- docs/WORKLOG.md(키트) «0. 수정 전 기준선 · 환경» 칸에 한 줄: «환경 점검: envcheck 요약 <번호> · 조치 <한 일 또는 없음>»

## 1. AGENTS.md — 우리 것이 실렸나 (2단계)
- Codex 가 읽는 곳: ~/.codex/AGENTS.md(플랫폼 안전 규칙 — 건드리지 않는다) + git 루트부터 **띄운 폴더**까지의 AGENTS.md. 키트에서 띄우면 <키트>/AGENTS.md 가 실린다(1단계 세션은 루트에서 떠 있어 안 실린 게 정상 — 그래서 이 확인은 2단계)
- 확인: 지금 내 지시문에 키트 AGENTS 의 «4. 보안 · 안전» 절(4-1 비밀값 · 4-3 파괴적 명령)이 있나
	- 있으면 🟢
	- 없으면 -C <키트> 없이 띄운 것이다 → 🔴 «ReadyStart.txt 1번 줄 그대로 다시 띄우기» · 루트로 복사하지 않는다
	- 루트에 과제 AGENTS.md 가 있으면 둘 다 실린다(루트 → 키트 순) → 크기만 본다 · 과제 규칙과 부딪치는 줄이 보이면 🟠 유저에게
- 크기: 플랫폼 AGENTS + (루트 AGENTS) + 키트 AGENTS 바이트 합(wc -c)이 32768(32KiB · 넘으면 뒤가 잘려 안 실림)을 넘으면 🔴
- 스킬: python3 ~/.codex/skills/ready-start/skillcheck.py --kit <키트> → 🟢 · 빠짐 · 다름이 있으면 🔴(이름을 적는다). 스킬은 암묵 호출을 꺼 두어 Codex 목록에 안 뜨는 게 정상이다
	- «중복» 줄(같은 이름이 키트 .agents/skills 에도 — 설치가 이름을 못 바꿈)은 🟠 — «$이름» 이 안 불릴 수 있다 → mv <키트>/.agents <키트>/skills_src 한 줄을 유저 확인 뒤
- AGENTS 는 세션을 시작할 때만 읽힌다 — 1절에서 고친 게 있으면 다시 띄운 뒤 «$ready-start 재검사» 로 이 절만 다시 본다

## 1-1. 작업 폴더 git 등록 — 규칙 · 스킬 · 문서는 커밋, 도구 · 설치본은 제외 (2단계)
- 왜: 키트는 처음에 추적 안 되는 폴더다 · 규칙 · 스킬(«자기 스킬 가져오기» 가중치) · 문서는 커밋 기록에 남겨야 하고, 우리 도구는 제출물에 섞이면 안 된다
- 루트 .gitignore — 대회 기계는 처음에 **없다**: test -f <루트>/.gitignore 로 보고, 없으면 아래 블록으로 새로 만든다 · 있으면 grep -q "ready-start 1-1" 로 블록이 있나만 보고 없을 때 맨 아래에 덧붙인다(통째로 cat 하지 않는다 · 키트가 kit/ 가 아니면 경로 앞부분을 바꿔 쓴다)

		# ===== 키트 = 작업 폴더 — 우리 도구 · 설치본은 커밋하지 않는다(ready-start 1-1) =====
		kit/devview/
		kit/ref/
		kit/install.sh
		kit/scripts/envcheck/
		kit/scripts/codex_config/
		kit/scripts/hooks/
		kit/docs/examples/
		kit/.venv/
		kit/ReadyStart.txt

- 🔴 git 이름 · 메일은 1단계 5절에서 넣었다 — 커밋이 «Author identity unknown» 으로 실패하면 5절을 먼저 다시(대회 기계는 비어 있다 · 체험 1회차)
- 커밋(2단계는 키트에서 돈다 — 경로가 루트 기준이라 git -C <루트>): git -C <루트> add .gitignore kit/AGENTS.md kit/.gitignore kit/skills_src kit/docs → git -C <루트> commit -m "[환경] 작업 환경 등록 — 키트 = 작업 폴더(규칙 · 스킬 · 문서 양식)" — 둘 다 처음부터 샌드박스 밖 승인(.git 은 --add-dir 로도 샌드박스에서 읽기 전용 · AGENTS 2-2)
	- 🔴 git add -A · git add . · git add kit 통째 금지 — 앱 조각(src · scripts · tests 양식)은 **쓸 때 그 파일만** add 한다(과설계 감점 · 커밋에 이유가 남게)
	- 현장 git 이 예상과 다르면(루트가 git 저장소가 아님 · 이미 다른 구조 · 과제 .gitignore 와 부딪침) 멈추지 말고 판단해 맞추고, 무엇을 어떻게 했는지 보고 표 줄에 적는다
- 확인: git -C <루트> ls-files kit | head 에 AGENTS.md · skills_src · docs 가 있고 kit/devview 가 없으면 🟢 · 이후 문서는 <키트>/docs 에서만 고친다

## 2. config.toml — 키트 키만 넣는다 (1단계 · 확인은 2단계)
- 과제 폴더 = 홈이라 프로젝트 설정과 전역 설정이 같은 파일(~/.codex/config.toml)이다 → 아래 merge 로 전역 설정에 넣는다
	- 키트에서 띄운 세션(-C <키트> · 폴더 신뢰)은 키트의 .codex/config.toml 도 프로젝트 설정으로 겹쳐 싣는다 — 값이 같아 부딪치지 않는다(2026-10-31 실측). 루트에서 뜬 1단계 세션 · 신뢰 안 한 폴더는 전역 설정만 본다
- 비교: python3 scripts/codex_config/merge.py → 키마다 같음 · 다름 · 없음
- 넣기: «없음» 이 있으면 python3 scripts/codex_config/merge.py --apply (샌드박스 밖 승인) — 없는 키만 넣고, 백업 → 쓰기 → 다시 읽어 검사 → 깨졌으면 되돌림
- «다름» 은 바꾸지 않는다 → 🟠 키 이름 · 키트 값만 보고(플랫폼 값은 출력하지 않는다 — 비밀값이 섞였을 수 있음)
- 적용 불가 키(버전 · 환경 차이로 이 Codex 에 없는 키): codex doctor 의 Configuration 절 «ignoring … unrecognized configuration setting» 줄에서 **키트 키 이름만** 골라 🔴 키 이름 · 이유(그 밖 키는 이름도 옮기지 않는다)
	- 모르는 키는 무시되고 Codex 는 뜬다(0.163 실측). 🔴 아는 키에 틀린 값(예: 승인 리뷰어 bogus · 승인 정책 untrusted)은 **시작이 실패**한다 → doctor 에 오류가 보이면 재시작 명령을 내기 전에 🔴 로 멈춘다
- 설정은 Codex 를 다시 띄워야 적용된다 — 1단계 세션에서 «안 먹는다» 는 정상이다. 2단계에서 확인: 상태줄이 모델 · 승인 방식 · 폴더 · 맥락 % · 상태 · 토큰으로 길게 나오고, ? 단축키 목록의 기록 보기가 ^o 면 🟢(기본값이면 상태줄이 «모델 · 폴더» 뿐이고 ^t · 2026-10-31 실측)
- 단축키 값이 틀려도(충돌 · 없는 키 이름) 0.163 화면은 거부하지 않고 뜬다 — 그 단축키만 조용히 안 먹을 수 있다(2026-10-31 실측). 모르는 키 이름은 codex --strict-config 로 띄우면 시작이 실패해 드러난다

## 3. hooks.json — 압축 훅 (1단계)
- bash scripts/hooks/install_hooks.sh (샌드박스 밖 승인) — ~/.codex/hooks.json 이 없으면 만들고, 있으면 덮지 않고 넣을 내용만 보여 준다 → 그때는 🟠 «기존 hooks.json 있음 · 합칠지 유저 판단»
- 재시작 뒤 두 훅(압축 직전 스냅숏 · 압축 직후 인계 안내)을 «신뢰» 해야 돈다 — 다시 띄우면 «Hooks need review · 2 hooks are new or changed» 질문이 저절로 뜬다 → 2(Trust all and continue)(2026-10-31 실측 · 놓쳤으면 /hooks) → 1단계 끝 안내 · 7절에 넣는다

## 4. devview — 설문 하나로 연결 확인 (2단계 · 유저가 ReadyStart.txt 0번 줄로 띄운 뒤)
- 떠 있나: curl -s http://127.0.0.1:8701/sv/api/state — **처음부터 샌드박스 밖 승인으로** 친다(샌드박스는 127.0.0.1 접속도 막아 devview 가 떠 있어도 종료코드 7 로 실패한다 · 2026-10-31 리허설) → seen_ago 가 든 json 이면 🟢 연결
- 승인받고도 연결 실패면 안 떠 있는 것이다 — 실패로 적지 말고 직접 띄우지도 않는다 → 유저에게 «ReadyStart.txt 0번 줄(bash <키트>/devview/dv)을 새 탭에서 · 뜨면 '띄웠어'» 한 줄로 턴을 끝내고 다음 턴에 다시 확인(dv 는 자기가 든 키트를 열어 Alt+A · S · D 가 <키트>/docs 를 연다 · Codex 가 띄운 서버는 끊긴 적이 있다)
- 설문 하나: python3 ~/.codex/skills/survey/survey.py new ~/.codex/skills/ready-start/devview_check.json — 질문 «인터페이스 테스트» · 선택지 «확인» 하나(기타 · 보류 · 메모 칸은 도구가 붙인다)
- 유저에게 «devview 설문 탭(Alt+S) · 확인 눌러 줘»(화면이 저절로 넘어가지 않는다 — 알림 · 배지만) 한 줄 · «제출하면 '제출' 한마디» 로 턴을 끝낸다(대기 · 폴링 안 함 — $survey 3절) → 다음 턴에 result 로 제출이면 🟢 · 취소 · 미제출이면 🔴

## 5. git 이름 · 메일 — 비어 있으면 기본값 (1단계 맨 처음)
- 둘 다 비면 커밋이 실패한다(«Author identity unknown» · 종료코드 128 · 1회차 체험 기계가 비어 있었음)
- 확인: git config user.name · git config user.email — 둘 다 값이 있으면 🟢 · 건드리지 않는다(플랫폼 값일 수 있음)
- 빈 칸만 이 저장소에 넣는다(--global 없이): git config user.name "person" · git config user.email "person@example.com" — .git 쓰기라 처음부터 샌드박스 밖 승인(1단계엔 AGENTS 2-2 가 안 실려 있다) → 🟢 «기본값 넣음»
- 넣기도 실패하면 🔴

## 6. 명령 블록 — 이 세션 재시작 · INSP · 2ND 띄우기 (1단계 마지막)
- 내 UUID: python3 ~/.codex/skills/ready-start/whoami.py mark → 결과를 본 **다음 명령으로** whoami.py find 표식 → uuid 한 줄. /status 의 chat ID 와 같아야 한다
	- «Guardian review»(Approve for me 의 승인 판정용 하위 세션)도 명령 글을 읽어 표식이 남지만 find 가 뺀다(2026-10-31 실측 · 0.166) — 그래도 두 줄 이상이면 /status 의 chat ID 와 같은 줄만 쓴다
- 값: 모델 gpt-6.1-sol · 강도 MAIN medium · INSP high · 2ND medium · 승인 = --approve-for-me(Approve for me — 승인 요청을 자동 리뷰가 판정 · 샌드박스 workspace-write)
- 아래 블록을 **<키트>/ReadyStart.txt** 에 쓴다(1-1 이 커밋에서 뺌 · 터미널 출력은 복사가 불편 · 유저가 에디터에서 줄마다 복사). <UUID> · <키트> · <루트> 는 실제 전체 경로로 바꿔 쓴다 · 있으면 덮어쓴다(이 스킬이 만드는 파일)
	- 대화창에는 «명령은 <키트>/ReadyStart.txt 에» 한 줄만(블록을 다시 출력하지 않는다)

		# 0) devview — 안 떠 있을 때만 · 새 터미널 탭에서(띄운 탭은 닫지 않는다)
		bash <키트>/devview/dv
		# 1) MAIN 재시작 — 이 Codex 를 끝낸 뒤(/quit) 같은 탭에서 두 줄(첫 줄 = 이 대화를 쥔 데몬 끄기 · 데몬이 없으면 notRunning)
		codex app-server daemon stop
		codex resume <UUID> -C <키트> --add-dir <루트> -m gpt-6.1-sol -c model_reasoning_effort=medium --approve-for-me '$main'
		# 2) INSP — 새 터미널 탭에서(이름은 시작 메시지로 찾으니 /rename 은 선택)
		codex -C <키트> --add-dir <루트> -m gpt-6.1-sol -c model_reasoning_effort=high --approve-for-me '$insp'
		# 3) 2ND — 새 터미널 탭에서(/rename 은 선택)
		codex -C <키트> --add-dir <루트> -m gpt-6.1-sol -c model_reasoning_effort=medium --approve-for-me '$2nd'

- 지키는 것(0.163 도움말 · 실측)
	- MAIN 재시작 줄 끝 '$main' = 시작 프롬프트(0.163 도움말: codex resume [SESSION_ID] [PROMPT]) → 다시 뜨자마자 역할 스킬이 실린다
	- -C <키트> = 작업 폴더(키트 AGENTS 가 실림) · --add-dir <루트> = 루트 과제 파일 · .git 에도 쓰기(둘 다 0.163 도움말에 있음) · resume 에 -C 를 주면 루트에서 시작한 세션도 키트에서 이어진다(2026-10-31 실측: 상태줄 폴더가 바뀌고 이전 대화 · 승인 방식은 그대로)
	- 🔴 '$insp' 는 작은따옴표로 — 큰따옴표 · 맨글자면 bash 가 $insp 를 빈 변수로 지운다
	- 🔴 데몬: 루트에서 그냥 띄운 처음 세션은 공용 앱 서버 데몬 안에서 돌고, /quit 뒤에도 데몬이 그 대화를 몇 분 쥐고 있다 → -C 로 다시 열면 «This conversation is open in another app» 으로 막힌다(2026-10-31 리허설 · 약 3분 뒤 풀림) → 그래서 resume 앞에 daemon stop(공식 명령 · 이 시점엔 INSP · 2ND 가 없어 영향 없음). 그래도 막히면 그 화면의 f(fork) 또는 잠시 뒤 R
	- 새 세션은 시작할 때 이름을 붙이는 플래그가 없다(0.163) — 세션끼리는 whoami.py name 이 **시작 메시지**('$insp' · '$2nd' · '$main')로 찾으니 /rename 을 안 해도 된다. /rename INSP 를 하면 codex resume INSP 처럼 이름으로 다시 열 수 있다
	- 🔴 --approve-for-me 는 -s · -a · --yolo 와 같이 쓰지 않는다(충돌) · --full-auto 는 0.163 에 없다
	- 강도는 -c model_reasoning_effort=값 뿐이다. 오타도 오류 없이 통과하니 띄운 뒤 /status 로 확인

## 7. 마무리 안내 — 한 줄씩 (2단계 끝)
- 다시 띄울 때 «Hooks need review» 에서 신뢰를 안 했으면 지금 /hooks 에서 두 훅 신뢰(압축 직전 스냅숏 · 압축 직후 인계 안내)
- INSP · 2ND 가 아직 안 떴으면 ReadyStart.txt 2 · 3번 줄(/rename 은 선택 — 이름이 없으면 압축 뒤 요약 · 시작 메시지로 역할을 정한다)
- ⭐ **세 세션이 다 뜨면 통신 시험을 한다**(main 4절) — 이 줄은 빼지 않는다(유저가 잊지 않게)
- 커밋 대상 목록은 띄우지 않는다 — 유저가 devview 왼쪽 패널에서 직접 본다(2026-10-31 유저 지정 · 너무 길었음). 유저가 물을 때만 8절 gitfiles.py

## 8. 도구 (경로는 키트 기준)
- 커밋 대상 표: python3 ~/.codex/skills/ready-start/gitfiles.py [--repo 과제폴더] [--kit 키트폴더] — 종료코드 0 · git 저장소가 아니면 2
- 겹침 목록: python3 ~/.codex/skills/ready-start/overlap.py [--kit 키트폴더] [--target 과제폴더] — 같은 상대 경로 파일 · 대상 안 모든 AGENTS.md · 같은 이름 스킬 폴더 · .codex · .mcp.json · .env.example 유무. 읽기 전용 · 종료코드 0 정상 / 2 폴더 오류
- 스킬 확인: python3 ~/.codex/skills/ready-start/skillcheck.py [--kit 키트폴더] — 키트 스킬이 읽히는 곳에 같게 있나(같음 · 다름 · 빠짐 · 중복) · 종료코드 0 다 같음 / 1 빠짐 · 다름 / 2 폴더 없음
- 세션 이름 · 설정: python3 ~/.codex/skills/ready-start/whoami.py mark | find 표식 | name 이름 | list | check 표식 --name MAIN --effort medium | check-name 이름 --effort high
	- mark 와 find · check 는 **명령 두 번으로 따로**(표식은 첫 명령이 끝난 뒤 세션 기록에 적힌다)
	- check = 실제 적용된 이름 · 모델 · 강도 · 승인 방식(Approve for me = auto_review)을 기대값과 비교 · 다르면 종료코드 1
	- 종료코드 0 찾음 / 1 못 찾음 · 다름 / 2 인자 · 폴더 오류 · CODEX_HOME 이 있으면 그 폴더
- 시험: python3 -m pytest -q .agents/skills/ready-start
