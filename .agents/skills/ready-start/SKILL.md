---
name: ready-start
description: 준비 전용 세션 — 과제를 받은 직후 루트에서 뜬 첫 Codex 의 «$ready-start». 맨 먼저 <키트>/ReadyStart.md(devview · MAIN · 2ND 띄우는 명령)를 쓰고, 유저가 그 명령으로 두 세션을 띄우는 동안 git 이름 · git 등록 · config · 압축 훅 · AGENTS · 스킬 확인 · 라이브러리 · 환경 점검(+ 배포 계획서 사실 칸) · devview 연결을 끝내며 «준비 상태» 를 한 줄씩 남긴다. 대회 맥락 · 역할 · 작업 범위는 $main · $2nd. 키트와 과제 저장소의 겹치는 이름은 같은 폴더의 overlap.py 로 목록만 본다.
---

# ready-start — 준비 전용 세션 (두 세션과 따로)

- 과제 루트에서 뜬 **첫 Codex 하나에서만** 부른다 · MAIN 이 아니다(MAIN 으로 재시작하지 않는다 — 2026-11-04 유저 지정: 병렬을 위해 준비하는 동안 두 세션을 먼저 띄운다 · 두 세션은 뜨자마자 devview 허브에 붙은 뒤 MAIN 은 과제 파악($ontology) · 2ND 는 대기 서브 + 가볍게 과제 훑기 — 이 세션은 그동안 준비만) · 대회 맥락 · 역할 · 작업 범위는 다루지 않는다 → $main · $2nd
- 키트 폴더(아래 «키트») = 키트를 푼 곳(보통 <루트>/kit) = **작업 폴더**. 문서 · 앱 코드 · 스킬 · .venv 를 여기서 쓴다(2026-10-30 유저 지정)
	- 스킬은 설치 한 줄이 ~/.codex/skills 로 복사한다 → 처음 세션(루트에서 그냥 codex)에서도 $ready-start 가 보인다 · 설치본 키트의 스킬 원본은 skills_src/(이름 바꿈 — 두 곳 중복 방지)
	- 🔴 두 세션은 전용 앱 서버(0번 줄이 뒤로 띄움 · ~/.codex/rs/app.sock)에 --remote 로 붙는다 — 그래야 devview 글 · 마법봉이 턴 중에 바로 들어간다(steer · 2026-11-06 실측) · 루트 쓰기는 서버 writable_roots · 서브 상한 8 은 서버 인자 · 서버가 안 뜨면 ReadyStart «앱 서버가 안 뜰 때» 일반 명령(글은 큐로)
	- 키트를 기본 경로로 잡는 건 6절 명령이다 — MAIN · 2ND 를 -C <키트> 로 띄워 키트 AGENTS 가 실리고(0.163 · codex debug prompt-input 실측) 루트 과제 파일 · .git 에도 쓴다
	- 아래 명령의 상대 경로(docs/ · scripts/)는 키트 기준 — 이 세션은 루트에서 떠 있으니 cd <키트> 뒤 실행 · 스킬 도구는 ~/.codex/skills/… · <루트> = git rev-parse --show-toplevel(대회는 /home/user)
- ⭐ **순서**(앞 단계가 끝나야 되는 것만 순서대로)
	- **0단계 = 다른 확인 없이 6절(ReadyStart.md 쓰기 · 파이썬 한 번)** → 바로 유저에게 한 줄 «<키트>/ReadyStart.md 의 명령으로 devview · 두 세션을 띄워 — 나는 준비를 계속한다» → 턴을 끝내지 않고 이어서
	- 5절(git 이름) → 1-1(git 등록 커밋 — 두 세션의 커밋보다 먼저) → 2절(config) → 3절(압축 훅) → 1절(AGENTS · 스킬) → 0절(라이브러리 · .venv) → 0-1(envcheck · 배포 계획서 0 · 1절) → 4절(devview 연결) → 7절 보고 표
	- 단계가 끝날 때마다 «준비 상태» 한 줄: python3 ~/.codex/skills/ready-start/readystart.py status <항목> "<🟢|🟠|🔴> 한 마디" --kit <키트> — 항목 이름은 git 이름 · git 등록 · config · 훅 · AGENTS · 스킬 · venv · envcheck · devview · 끝(두 세션이 이 이름으로 기다릴지 정한다 · main 0-0)
	- 의존이 없는 읽기 확인(git config 두 값 · test -f · merge.py 비교 · skillcheck · wc -c 같은)은 **한 번에 묶어** 실행하되 줄마다 이름과 종료코드를 따로 찍는다(예: `for c in …; do …; echo "<이름> rc=$?"; done`) — 묶음 끝의 종료코드 하나로 판정하지 않는다(10/31: 없는 .gitignore 를 cat 한 하나로 묶음 전체가 «Failed» 로 보였다) · 쓰기 · 승인이 필요한 명령은 하나씩
	- 없을 수 있는 파일은 test -f 로 본다(대회 기계는 처음에 .gitignore · .env.example 이 없다)
	- ⭐ 이 세션은 옛 설정 · 훅 그대로가 정상이다(설정 · 훅 · AGENTS 는 세션이 뜰 때 읽힌다) — 확인은 두 세션 쪽 사실로 한다(1 · 2 · 3절)
- 🔴 Codex 샌드박스 안에서는 ~/.codex 가 읽기 전용이다 → 2 의 쓰기는 **샌드박스 밖 실행 승인**을 요청한다. 거절되거나 막히면 유저 터미널 탭에서 칠 명령 한 줄을 준다
- 덮어쓰기 금지 — 이미 있는 파일 · 키는 바꾸지 않고 보고만 한다(바꿀지는 유저)

## 결과 보고 — 언제나 이 표 하나
- 아래 9줄을 그대로 쓴다. 상태 = 🟢 됨 · 🟠 유저 판단 필요 · 🔴 안 됨. 🟢 이면 «안 될 때 영향» 칸은 비우고, 🟠 · 🔴 이면 그 줄의 영향 문장을 그대로 넣고 뒤에 «무엇을 하면 되나» 한 마디

| 항목 | 상태 | 안 될 때 영향 |
|---|---|---|
| git 이름 · 메일(5절) | | 커밋이 전부 실패한다 → 작업 기록 증거가 안 남는다 |
| 작업 폴더 git 등록(1-1절) | | 규칙 · 스킬 · 문서가 커밋 기록에 안 남고, 도구 폴더가 섞여 들어갈 수 있다 |
| config(2절) | | 키트 화면 · 단축키 설정이 안 먹는다(작업은 된다) |
| 압축 훅(3절) | | 압축 뒤 참조 목록이 안 들어간다 → 압축 요약만으로 이어 가 문서를 다시 읽거나 맥락을 놓친다 |
| AGENTS 실림(1절) | | 우리 규칙(보안 · 커밋 · 문서)이 안 실려 Codex 가 기본 동작으로 일한다 |
| 스킬 실림(1절) | | 빠진 $스킬은 못 쓴다(빠진 이름을 적는다) |
| 라이브러리 설치(0절) | | 과제에 필요한 라이브러리(nicegui 등)를 못 깐다 → 표준 라이브러리로만 |
| 환경 점검(0-1절) | | 체험 뒤 바뀐 것(외부 접속 · 버전 · 막힌 기능)을 작업 중간에야 알게 된다 |
| devview 연결(4절) | | flowtree · 문서 · 설문 화면을 못 본다 → 유저가 ReadyStart.md 0번 줄로 띄운다 |

- 표 · 7절 안내로 끝낸다(커밋 목록은 띄우지 않는다 — 7절) · 마지막 «준비 상태» 줄은 «끝 — 🟢 전부» 또는 «끝 — 🟠 · 🔴 <항목들>»

## 0. 이 기계 — 체험 1 · 2회차 실측 (라이브러리)
- 대회 플랫폼이 응시자마다 주는 일회용 리눅스 샌드박스 · **과제 폴더 = 홈(/home/user)** · git 저장소
- python 3.11 · git 2.39 · node 22 · 외부 접속 · pip 됨 · chromium · bwrap 없음 · codex 0.163 · 서버는 유저 터미널 탭에서(Codex 샌드박스는 소켓을 막는다)
- 라이브러리 설치(명령은 늘 키트 폴더에서 — `cd <키트> && …`): 키트에 .venv 가 이미 있으면 그대로 쓰고 끝 · 없으면 python3 -m pip install --dry-run pip 로 본다(PEP668 거부가 이 기계의 정상 결과 — 오류가 아니라 venv 신호 · ls .venv 같은 확인을 같이 붙이지 않는다)
	- 되면 🟢 «시스템 pip 그대로»
	- «externally-managed-environment»(PEP668)로 막히면 키트 안에 python3 -m venv .venv 를 만들어 그 안에 설치한다(<키트>/.venv · 1-1 이 커밋에서 뺌) → 만들어지면 🟢 «막힘 → venv 로» · venv 도 실패하면 🔴 · venv 를 만들었으면 이후 시험 · 점검 · 앱 실행은 python3 대신 .venv/bin/python(run.sh 는 .venv 가 있으면 알아서 쓴다)

## 0-1. 환경 점검 — envcheck 한 번(샌드박스 밖 승인)
- bash scripts/envcheck/envcheck.sh --no-install — **처음부터 샌드박스 밖 실행 승인을 요청**한다(기본 샌드박스는 소켓을 막아 PermissionError 로 멈춘다 · 2회차 실측) · 약 7초 · 실패 · 정보 줄과 «요약: 번호» 만 나온다 · 출력은 화면으로 받는다(파일로 받아야 하면 키트 out/envcheck.txt — 없는 임시 폴더로 리다이렉트하지 않는다)
- 체험 때 실패: A6(git 이름 · 메일 → 5절이 채움) · B3(AGENTS · 스킬 위치 — 이 세션은 루트에서 떠 있어 늘 뜬다 · 실림은 1절이 본다 · 정보) · B4(bwrap 없음 · 대처 없음 · 정보) — 이 셋만이면 🟢 «체험과 같음»
- 그 밖 번호가 있으면 🟠 번호 · 사유(envcheck README 3절의 대처) — 체험 뒤 기계가 바뀐 것이다
- docs/WORKLOG.md(키트) «0. 수정 전 기준선 · 환경» 칸의 «환경 점검» 줄을 채운다(고치기 직전 다시 읽고 그 줄만 — 두 세션의 서브도 이 문서를 쓴다): «환경 점검: envcheck 요약 <번호> · 조치 <한 일 또는 없음>»
- 배포 계획서(docs/DEPLOY_PLAN.md)에 **사실만** 적는다 · 계획은 MAIN 이 README 를 읽은 뒤($main 1-1) · 이 줄도 «환경 점검» 행에 포함
	- 0절 docker: envcheck 의 C6 줄 그대로(대회 기계에서 컨테이너를 실제로 돌릴 수 있나)
	- 1절 README 원문: grep -n -i -E "docker|container|컨테이너|배포|deploy|how to run|실행 방법" <루트>/README.md 에 걸린 줄(줄 번호 + 원문 · 없으면 «배포 낱말 없음(grep)») · 제출 문서 양식: ls <루트> 에서 How to run · AI collaboration 같은 양식 파일 이름

## 1. AGENTS.md — 두 세션에 우리 것이 실리나
- Codex 가 읽는 곳: ~/.codex/AGENTS.md(플랫폼 안전 규칙 — 건드리지 않는다) + git 루트부터 **띄운 폴더**까지의 AGENTS.md. 키트에서 띄우면 <키트>/AGENTS.md 가 실린다(이 세션은 루트에서 떠 있어 안 실린 게 정상)
- 확인: cd <키트> 뒤 codex debug prompt-input | grep -c "## 4. 보안 · 안전" — 키트에서 뜬 세션이 받을 지시문을 그대로 뽑는다(2026-11-04 · 0.163 실측: 키트에서 1 · 루트에서 0)
	- 1 이상이면 🟢
	- 0 이면 🔴 · 루트로 복사하지 않는다 · 두 세션이 ReadyStart.md 명령(-C <키트>) 그대로 떴는지 유저에게
	- 루트에 과제 AGENTS.md 가 있으면 둘 다 실린다(루트 → 키트 순) → 크기만 본다 · 과제 규칙과 부딪치는 줄이 보이면 🟠 유저에게
- 크기: 플랫폼 AGENTS + (루트 AGENTS) + 키트 AGENTS 바이트 합(wc -c)이 32768(32KiB · 넘으면 뒤가 잘려 안 실림)을 넘으면 🔴
- 스킬: python3 ~/.codex/skills/ready-start/skillcheck.py --kit <키트> → 🟢 · 빠짐 · 다름이 있으면 🔴(이름을 적는다). 스킬은 암묵 호출을 꺼 두어 Codex 목록에 안 뜨는 게 정상이다
	- «중복» 줄(같은 이름이 키트 .agents/skills 에도 — 설치가 이름을 못 바꿈)은 🟠 — «$이름» 이 안 불릴 수 있다 → mv <키트>/.agents <키트>/skills_src 한 줄을 유저 확인 뒤
- AGENTS 는 세션을 시작할 때만 읽힌다 — 1절에서 고친 게 있으면 두 세션을 다시 띄우게 유저에게 한 줄

## 1-1. 작업 폴더 git 등록 — 규칙 · 스킬 · 문서는 커밋, 도구 · 설치본은 제외 (5절 바로 뒤 · 일찍)
- 일찍 하는 이유: 두 세션이 곧 커밋한다 — 같은 저장소에 동시에 커밋하면 index.lock 으로 부딪친다 → 두 세션은 «준비 상태» 의 «git 등록» 줄이 생긴 뒤에 커밋한다(main 0-0)
- 왜: 키트는 처음에 추적 안 되는 폴더다 · 규칙 · 스킬(«자기 스킬 가져오기» 가중치) · 문서는 커밋 기록에 남겨야 하고, 우리 도구는 제출물에 섞이면 안 된다
- 루트 .gitignore — 대회 기계는 처음에 **없다**: test -f <루트>/.gitignore 로 보고, 없으면 아래 블록으로 새로 만든다 · 있으면 grep -q "ready-start 1-1" 로 블록이 있나만 보고 없을 때 맨 아래에 덧붙인다(통째로 cat 하지 않는다 · 키트가 kit/ 가 아니면 경로 앞부분을 바꿔 쓴다)

		# ===== 키트 = 작업 폴더 — 우리 도구 · 설치본은 커밋하지 않는다(ready-start 1-1) =====
		kit/devview/
		kit/ref/
		kit/install.sh
		kit/scripts/envcheck/
		kit/scripts/codex_config/
		kit/scripts/hooks/
		kit/scripts/kit/
		kit/kit
		kit/kit.cmd
		kit/docs/examples/
		kit/.venv/
		kit/ReadyStart.md
		kit/bookkit/books/
		kit/bookkit/**/dist/
		kit/skeleton/out/
		kit/task_copy/
		kit/.codex-hub/

- 🔴 git 이름 · 메일은 바로 앞 5절에서 넣었다 — 커밋이 «Author identity unknown» 으로 실패하면 5절을 먼저 다시(대회 기계는 비어 있다 · 체험 1회차)
- 커밋(경로가 루트 기준이라 git -C <루트>): git -C <루트> add .gitignore kit/AGENTS.md kit/.gitignore kit/skills_src kit/docs → git -C <루트> commit -m "[환경] 작업 환경 등록 — 키트 = 작업 폴더(규칙 · 스킬 · 문서 양식)" — 둘 다 처음부터 샌드박스 밖 승인(.git 은 샌드박스에서 읽기 전용 · AGENTS 2-2 · 이 세션엔 AGENTS 가 안 실려 있다)
	- 🔴 git add -A · git add . · git add kit 통째 금지 — 앱 조각(src · scripts · tests 양식)은 **쓸 때 그 파일만** add 한다(과설계 감점 · 커밋에 이유가 남게)
	- 현장 git 이 예상과 다르면(루트가 git 저장소가 아님 · 이미 다른 구조 · 과제 .gitignore 와 부딪침) 멈추지 말고 판단해 맞추고, 무엇을 어떻게 했는지 보고 표 줄에 적는다
- 확인: git -C <루트> ls-files kit | head 에 AGENTS.md · skills_src · docs 가 있고 kit/devview 가 없으면 🟢 → «준비 상태» git 등록 줄(커밋 해시 앞 7자) · 이후 문서는 <키트>/docs 에서만 고친다

## 2. config.toml — 키트 키만 넣는다
- 과제 폴더 = 홈이라 프로젝트 설정과 전역 설정이 같은 파일(~/.codex/config.toml)이다 → 아래 merge 로 전역 설정에 넣는다
	- 키트에서 띄운 세션(-C <키트> · 폴더 신뢰)은 키트의 .codex/config.toml 도 프로젝트 설정으로 겹쳐 싣는다 — 값이 같아 부딪치지 않는다(2026-10-31 실측) → merge 보다 두 세션이 먼저 떠도 키트 설정은 먹는다. 루트에서 뜬 이 세션 · 신뢰 안 한 폴더는 전역 설정만 본다
- 비교: `kit/kit config`(루트에서 · 키트 폴더면 `./kit config` · = scripts/codex_config/merge.py) → 키마다 같음 · 다름 · 없음 + 규칙 kit.rules(./kit 를 승인 없이) 있음 · 없음
- 넣기: «없음» 이 있으면 `kit/kit config --apply` (샌드박스 밖 승인 — 규칙이 아직 없다) — 없는 키 · 없는 규칙 파일만 넣고(~/.codex/rules/kit.rules · 이미 있으면 다르더라도 그대로), 백업 → 쓰기 → 다시 읽어 검사 → 깨졌으면 되돌림
- «다름» 은 바꾸지 않는다 → 🟠 키 이름 · 키트 값만 보고(플랫폼 값은 출력하지 않는다 — 비밀값이 섞였을 수 있음)
- 적용 불가 키(버전 · 환경 차이로 이 Codex 에 없는 키): codex doctor 의 Configuration 절 «ignoring … unrecognized configuration setting» 줄에서 **키트 키 이름만** 골라 🔴 키 이름 · 이유(그 밖 키는 이름도 옮기지 않는다)
	- 모르는 키는 무시되고 Codex 는 뜬다(0.163 실측). 🔴 아는 키에 틀린 값(예: 승인 리뷰어 bogus · 승인 정책 untrusted)은 **시작이 실패**한다 → doctor 에 오류가 보이면 «준비 상태» config 줄에 🔴 와 키 이름을 적고 유저에게 바로 한 줄(두 세션이 안 뜨거나 이미 뜬 세션을 다시 띄울 때 실패한다)
- 설정은 Codex 가 뜰 때 적용된다 — 이 세션에서 «안 먹는다» 는 정상이다. 두 세션 화면에서 확인(유저가 보면 된다 · 이 세션은 merge 비교가 «같음» 이면 🟢): 상태줄이 모델 · 승인 방식 · 폴더 · 맥락 % · 상태 · 토큰으로 길게 나오고, ? 단축키 목록의 기록 보기가 ^o 면 🟢(기본값이면 상태줄이 «모델 · 폴더» 뿐이고 ^t · 2026-10-31 실측)
- 단축키 값이 틀려도(충돌 · 없는 키 이름) 0.163 화면은 거부하지 않고 뜬다 — 그 단축키만 조용히 안 먹을 수 있다(2026-10-31 실측). 모르는 키 이름은 codex --strict-config 로 띄우면 시작이 실패해 드러난다

## 3. hooks.json — 압축 직후 참조 목록 훅
- 왜: 압축마다 역할 스킬을 통째로 다시 읽으면 토큰 · 시간이 샌다(10/31 실전) → 압축 직후 «인계 칸 · 내 역할 스킬의 어느 절» 경로만 넣고 본문은 모델이 필요할 때 그 절만 읽는다(hand-on/compact_hook.py · 1,500자 이하 · 10/30 판의 스냅숏 · «$hand-on 하라» 는 뺐다)
- ⭐ 훅은 세션이 **뜰 때** 읽힌다 → 그래서 ReadyStart.md 0번 줄(devview)이 유저 터미널에서 먼저 install_hooks.sh 를 돌린다(Codex 밖이라 승인 없음 · 그 뒤 뜬 두 세션에 먹는다)
- 확인: grep -c compact_hook ~/.codex/hooks.json — 1 이상이면 🟢 «0번 줄이 넣음»
	- 파일이 없으면 bash scripts/hooks/install_hooks.sh (샌드박스 밖 승인) → 🟢 «늦게 넣음 — 이미 뜬 세션은 첫 압축 전 다시 띄우기(ReadyStart.md 의 «압축 훅이 안 먹을 때»)»
	- 파일이 있는데 compact_hook 이 없으면 install_hooks.sh 가 덮지 않고 넣을 내용만 보여 준다 → 🟠 «기존 hooks.json 있음 · 합칠지 유저 판단»
- 두 세션이 뜰 때 «Hooks need review» 질문 → 2(Trust all and continue)(놓쳤으면 /hooks) — 신뢰 전에는 안 돈다

## 4. devview — 연결 확인 (유저가 ReadyStart.md 0번 줄로 띄운 뒤)
- 떠 있나: curl -s http://127.0.0.1:8701/sv/api/state — **처음부터 샌드박스 밖 승인으로** 친다(샌드박스는 127.0.0.1 접속도 막아 devview 가 떠 있어도 종료코드 7 로 실패한다 · 2026-10-31 리허설) → seen_ago 가 든 json 이면 🟢 연결
- 승인받고도 연결 실패면 안 떠 있는 것이다 — 실패로 적지 말고 직접 띄우지도 않는다 → 유저에게 «ReadyStart.md 0번 줄을 새 탭에서 · 뜨면 '띄웠어'» 한 줄로 턴을 끝내고 다음 턴에 다시 확인(Codex 가 띄운 서버는 끊긴 적이 있다) · 이 줄은 맨 마지막 단계라 다른 준비를 막지 않는다

## 5. git 이름 · 메일 — 비어 있으면 기본값 (0단계 바로 뒤)
- 둘 다 비면 커밋이 실패한다(«Author identity unknown» · 종료코드 128 · 1회차 체험 기계가 비어 있었음)
- 확인: git config user.name · git config user.email — 둘 다 값이 있으면 🟢 · 건드리지 않는다(플랫폼 값일 수 있음)
- 빈 칸만 이 저장소에 넣는다(--global 없이): git config user.name "person" · git config user.email "person@example.com" — .git 쓰기라 처음부터 샌드박스 밖 승인(이 세션엔 AGENTS 2-2 가 안 실려 있다) → 🟢 «기본값 넣음»
- 넣기도 실패하면 🔴

## 6. ReadyStart.md — 세션 띄우는 명령 (0단계 · 다른 확인보다 먼저)
- 받자마자 한 번: python3 ~/.codex/skills/ready-start/readystart.py write (루트에서 — 키트 = <루트>/kit 자동 · 다르면 --kit <키트> --root <루트>) → <키트>/ReadyStart.md 를 쓰고 그 경로 한 줄(있으면 덮어씀 — 이 스킬이 만드는 파일 · 커밋하지 않는다 — 1-1 블록 · 키트 .gitignore)
	- 대화창에는 «<키트>/ReadyStart.md 의 명령으로 devview · 두 세션을 띄워 — 나는 준비를 계속한다» 한 줄만(명령을 다시 출력하지 않는다 · 터미널 출력은 복사가 불편 — 유저가 에디터에서 줄마다 복사)
- 파일 내용: 붙여 넣는 순서(0 devview → 1 MAIN → 2 2ND · 줄마다 새 터미널 탭 · 1 · 2 는 동시에 해도 됨) · 0) `bash <키트>/scripts/hooks/install_hooks.sh; bash <키트>/devview/dv`(훅을 두 세션보다 먼저 넣는다 — 3절) · 1 · 2) 아래 codex 줄 · «압축 훅이 안 먹을 때» · 맨 아래 «준비 상태»(단계마다 status 로 한 줄)
- 값: 모델 gpt-6.1-sol · 강도 MAIN high(첫 실행만 — 온톨로지가 끝나면 유저가 직접 내린다) · 2ND medium · 답 길이 high · Fast 모드 · 서브 V2(기다리기 최소 · 기본 10분 · 최대 1시간) · 승인 = --approve-for-me(Approve for me — 승인 요청을 자동 리뷰가 판정 · 샌드박스 workspace-write)

		codex -C <키트> --add-dir <루트> -m gpt-6.1-sol -c model_reasoning_effort=<강도> -c model_verbosity=high -c service_tier=fast -c features.multi_agent_v2.enabled=true -c features.multi_agent_v2.min_wait_timeout_ms=600000 -c features.multi_agent_v2.default_wait_timeout_ms=600000 -c features.multi_agent_v2.max_wait_timeout_ms=3600000 -c agents.max_concurrent_threads_per_session=8 --approve-for-me '$main'   ← 2ND '$2nd 파악시작'

- 지키는 것(0.163 도움말 · 실측)
	- 끝의 시작 프롬프트 → 뜨자마자 역할 스킬이 실린다 · 두 세션 모두 **맨 먼저 devview 허브에 붙고**($codex-hub) — MAIN '$main' = 그다음 묻지 않고 과제 파악($ontology · 최초 1회 전체 · main 0-0 · 1-1) · 2ND '$2nd 파악시작' = 대기 서브 → 가볍게 과제 훑기(2nd 0-4) · 준비 상태는 기다리지 않는다 · 🔴 작은따옴표로 — 큰따옴표 · 맨글자면 bash 가 $main 을 빈 변수로 지운다
	- -C <키트> = 작업 폴더(키트 AGENTS 가 실림) · --add-dir <루트> = 루트 과제 파일 · .git 에도 쓰기(둘 다 0.163 도움말에 있음)
	- 새 세션은 시작할 때 이름을 붙이는 플래그가 없다(0.163) — 세션끼리는 whoami.py name 이 **시작 메시지**('$main' · '$2nd')로 찾으니 /rename 을 안 해도 된다($ready-start 로 시작한 이 세션은 어느 역할로도 안 잡힌다)
	- 🔴 --approve-for-me 는 -s · -a · --yolo 와 같이 쓰지 않는다(충돌) · --full-auto 는 0.163 에 없다
	- 강도는 -c model_reasoning_effort=값 뿐이다. 오타도 오류 없이 통과하니 띄운 뒤 /status 로 확인
	- 답 길이 · Fast · 서브 V2 는 키트 .codex/config.toml 에도 있지만 명령에도 붙인다 — 플랫폼 설정에 같은 키가 다른 값이면 merge 가 «다름» 으로 두고 안 바꾸기 때문(-c 가 설정 파일보다 앞섬 · 유저 지정 11/03 · V2 키 4개는 0.163 --strict-config 통과 2026-11-04) · Fast 는 요금 2 ~ 2.5배 · 세션 중 /fast 로 끔

## 7. 마무리 안내 — 한 줄씩 (끝)
- 두 세션이 아직 안 떴으면 ReadyStart.md 1 · 2번(/rename 은 선택 — 이름이 없으면 압축 뒤 요약 · 시작 메시지로 역할을 정한다)
- 이 세션은 여기서 끝 — 닫아도 된다(두 세션은 이 세션을 기다리지 않는다 · 다시 확인할 때만 «$ready-start 재검사» 로 1 · 3 · 4절)
- 세션끼리는 flowtree · hand_off 로 주고받는다(main 1-3)
- 커밋 대상 목록은 띄우지 않는다 — 유저가 devview 왼쪽 패널에서 직접 본다(2026-10-31 유저 지정 · 너무 길었음). 유저가 물을 때만 8절 gitfiles.py

## 8. 도구 (경로는 키트 기준)
- 명령 파일 · 준비 상태: python3 ~/.codex/skills/ready-start/readystart.py write [--kit 키트] [--root 루트] | status 항목 "내용" [--kit 키트] — 종료코드 0 · 키트 · 파일 없음 2
- 커밋 대상 표: python3 ~/.codex/skills/ready-start/gitfiles.py [--repo 과제폴더] [--kit 키트폴더] — 종료코드 0 · git 저장소가 아니면 2
- 겹침 목록: python3 ~/.codex/skills/ready-start/overlap.py [--kit 키트폴더] [--target 과제폴더] — 같은 상대 경로 파일 · 대상 안 모든 AGENTS.md · 같은 이름 스킬 폴더 · .codex · .mcp.json · .env.example 유무. 읽기 전용 · 종료코드 0 정상 / 2 폴더 오류
- 스킬 확인: python3 ~/.codex/skills/ready-start/skillcheck.py [--kit 키트폴더] — 키트 스킬이 읽히는 곳에 같게 있나(같음 · 다름 · 빠짐 · 중복) · 종료코드 0 다 같음 / 1 빠짐 · 다름 / 2 폴더 없음
- 세션 이름 · 설정(준비 단계에선 안 쓴다 — hand-on · codex-hub · 압축 훅이 쓴다): python3 ~/.codex/skills/ready-start/whoami.py mark | find 표식 | name 이름 | list | check 표식 --name MAIN --effort medium | check-name 이름 --effort high
	- mark 와 find · check 는 **명령 두 번으로 따로**(표식은 첫 명령이 끝난 뒤 세션 기록에 적힌다)
	- check = 실제 적용된 이름 · 모델 · 강도 · 승인 방식(Approve for me = auto_review)을 기대값과 비교 · 다르면 종료코드 1
	- 종료코드 0 찾음 / 1 못 찾음 · 다름 / 2 인자 · 폴더 오류 · CODEX_HOME 이 있으면 그 폴더
- 시험: python3 -m pytest -q .agents/skills/ready-start
