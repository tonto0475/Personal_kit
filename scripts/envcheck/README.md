# envcheck — 사전 체험 환경 점검

> 사전 체험은 1회 · 15분뿐이다. 이 도구로 «되는 것 · 안 되는 것» 을 한 번에 본다.
> Codex 에게: 이 문서를 읽고 envcheck 를 돌려 결과를 해석하고, 깨지면 4절대로 즉석 대응한다. 체험 환경의 파일은 고쳐도 되지만 키트 저장소 원본은 고치지 않는다(고칠 점은 유저에게 한 줄로 보고).

## 1. 파일 · 실행

| 파일 | 하는 일 |
|---|---|
| envcheck.sh | 0단계(bash) — python3 가 없거나 3.8 미만이면 여기서 결과를 내고 끝냄. 아니면 envcheck.py 로 넘김 |
| envcheck.py | 본 점검 24항목(표준 라이브러리만 · 파이썬 3.8 이상) |
| test_envcheck.py | 도구 자체 시험 — python3 -m pytest -q scripts/envcheck |

- 기본: bash scripts/envcheck/envcheck.sh (키트가 kit/ 안이면 bash kit/scripts/envcheck/envcheck.sh)
- 설치 시간 재기를 빼고 빠르게: … envcheck.sh --no-install ($ready-start 는 이걸로 부른다 · 약 7초)
- 실행 위치 이름을 직접 줄 때: --where 이름
- 일시정지 시험(E3): 체험 시작 때 python3 scripts/envcheck/envcheck.py --serve-start → 바로 다음 명령에서 curl 127.0.0.1:포트/health(띄운 명령이 끝나도 사나) · 체험 끝날 때 --serve-check(시간은 맞추지 않음 · 경과만 기록)
- ⭐ **두 번 돌린다** — 유저 터미널 한 번, Codex 에게 한 번. 두 요약에서 다른 번호 = 샌드박스가 막는 것

## 2. 결과 읽기

    envcheck · 사용자 터미널(부모 프로세스에 codex 없음) · 24개 중 통과 12 · 실패 1
    A6 GITID 이름 · 메일 없음 → git config user.name/user.email(--global 없이)
    A11 LIBTIME 22초 (venv)
    요약: A6
    자세히: /tmp/envcheck-user.log

- 첫 줄: 실행 위치(판별 근거) · 항목 수 · 통과 · 실패. 위치는 부모 프로세스 줄에 codex 가 있으면 «Codex», 없으면 환경 변수 CODEX_SANDBOX* 를 보고, 둘 다 없으면 «사용자 터미널»
- 가운데: **실패 · 정보 항목만** «번호 사유». 통과한 항목은 안 나온다
- 요약: 실패 번호만. 체험이 끝나면 이 줄 두 개(사용자 · Codex)만 기억해서 옮겨 적는다
- 자세히: 위치마다 다른 로그(envcheck-user.log · envcheck-codex.log) — 명령마다 실행한 줄 · 종료코드 · 출력 전체
- 종료코드: 실패가 있으면 1, 없으면 0

## 3. 항목 — 무엇을 보나 · 사유 코드 · 대처

| 번호 | 검사 방법 | 사유 코드 → 뜻 · 대처 |
|---|---|---|
| A0 | (sh) command -v python3 · 버전 | NOPY → 파이썬 없음, 키트 도구 전부 못 씀 · 과제가 JS 일 가능성. uv 로 파이썬 설치를 검토 / PYOLD → 3.8 미만 |
| A1 | 파이썬 · git · node 버전 | PYOLD(3.8 미만) · PY310(3.10 미만 = NiceGUI 불가) · NOBIN(없는 명령) |
| A2 | github.com HEAD(5초) | NET → 외부 접속 막힘. 키트 받기 · git clone 불가 |
| A3 | pip 유무 · pypi.org HEAD · EXTERNALLY-MANAGED 파일 | NOPIP / NET → 설치 불가, A8 의 이미 깔린 목록으로만 / PEP668(정보) → 시스템 설치 거부, python3 -m venv .venv 로 설치 |
| A4 | 키트 루트(이 파일 두 단계 위에 AGENTS.md) · 파일 수 | NOKIT(정보) → 단독 실행, 키트 항목은 건너뜀 |
| A5 | git check-ignore --no-index 로 ref/CHECKSHEET.md(ref/ · kit/ref 중 있는 쪽) | REFVIS → 참고표가 커밋될 수 있음, ref/.gitignore 확인 / 건너뜀(git 저장소 인식 실패: …) → git 오류 원문(소유권 경고면 git config --global --add safe.directory <폴더>) |
| A6 | git 이름 · 메일 · 임시 저장소 커밋 | GITID → git config user.name · user.email 설정(--global 없이) / GIT → 커밋 자체 실패 |
| A7 | HISTFILE · ~/.bash_history · 홈 | 정보 — 명령 기록이 남는 환경인지(수집 범위) |
| A8 | requirements 중 이 파이썬에 해당하는 줄이 이미 깔렸나 | LIB(정보) → 미설치 목록. 설치가 막혀도 다 있으면 계획 그대로 |
| A9 | git remote · credential.helper | 정보 — push 경로가 있나(실제 push 안 함) |
| A10 | LC_ALL/LANG · 출력 인코딩 | LANG → 한글이 깨질 수 있음, export LANG=C.UTF-8 |
| A11 | 임시 venv 에 pip install -r requirements.txt 시간(pip 5초 · 재시도 0) | LIBTIME(정보) 걸린 초 / PEP668 · VERS(파이썬 버전에 맞는 판 없음) · NET · PIPFAIL → 로그의 pip 출력 확인 / 건너뜀(NET) → A3 이 막혀서 |
| B1 | codex --version | 정보(연습 0.163 · 0.164 와 비교) / NOBIN codex |
| B2 | codex features list 의 auto_compaction · unified_exec | 정보 — 자동 압축 끌 수 있나 · 백그라운드 터미널 켜졌나 |
| B3 | git 루트 → 지금 폴더 사이에 AGENTS.md · .agents/skills | AGPATH → 키트에서 띄우지 않은 세션(-C <키트> 빠짐). ReadyStart.txt 1번 줄로 다시 띄운다 · 루트로 옮기지 않는다 |
| B4 | which bwrap · unshare -U true | BWRAP → 샌드박스 도구 없음 · 사용자 이름공간 막힘(Codex 쪽에서 나면 정상일 수 있음) |
| B5 | CODEX_HOME(~/.codex) 의 session_index.jsonl · sessions | NOIDX(정보) → Codex 를 아직 안 띄움 / NOREAD → 읽기 막힘, whoami · hand-on 이 못 씀 |
| C1 | 0.0.0.0 빈 포트에 표준 서버 → 127.0.0.1 접속 | PORT · BIND → 서버를 못 띄움(Codex 쪽이면 권한 상승으로 띄움) |
| C2 | 8600 · 8701 바인드 | BUSY → 다른 프로그램이 씀 / «우리 devview 가 이미 떠 있음»(정보) |
| C3 | chromium · google-chrome | 정보 — 있으면 Codex 가 헤드리스로 앱 화면을 찍을 수 있음 |
| C4 | devview 를 임시 폴더로 띄워 / 와 /sv/api/state 응답 | DV → devview 가 안 뜨거나 설문 탭 없음, 로그의 devview 출력 확인 |
| C5 | which tmux | NOTMUX(정보) |
| D1 | survey.py 로 임시 폴더에 예시 설문 등록 → 결과가 pending | SURVEY → 설문 도구 실패 |
| E1 | NiceGUI 최소 앱(0.0.0.0 · reload 끔 · /health)을 새 프로세스로 → /health 200 + 화면 제목 | NGSTART(죽음 · 무응답 + 원인: BUSY · LIB · PERM · FILE 또는 마지막 출력) · NGPAGE → 처음부터 안 켜짐. 건너뜀(LIB 없음) → --no-install 이고 nicegui 미설치 — requirements 를 프로젝트 venv 에 깐 뒤 그 venv 파이썬으로 envcheck.py --no-install 을 다시 돌리면 확인됨 |
| E2 | 같은 앱을 nohup 으로 띄운 셸이 먼저 끝난 뒤에도 /health 200 | NGDETACH → 띄운 터미널 · Codex 턴이 끝나면 서버도 죽음. 서버는 유저 터미널 탭에서 띄운다 |
| E3 | (수동) --serve-start 로 띄우고 · 다음 명령에서 /health · 끝날 때 --serve-check(시간 기준 아님) | PAUSEKILL → 입력 없이 두면 서버가 꺼짐. 대회 중 서버를 다시 띄우는 습관 |

- 흔적: 시험 파일은 모두 임시 폴더(envcheck_ 접두어)에 만들고 끝나면 지운다. 설문 · devview 시험은 등록 목록(SURVEY_REGISTRY)도 임시 파일로 돌린다. E3 만 ~/.envcheck 를 쓰고 --serve-check 가 지운다. 서버는 PID 로만 종료한다
- E1 · E2 가 쓰는 NiceGUI 는 A11 이 깐 임시 venv(없으면 지금 파이썬에 깔린 것)

## 4. 깨졌을 때 — Codex 즉석 대응

| 증상 | 할 일 |
|---|---|
| 파이썬 예외(Traceback)로 멈춤 | 예외가 난 함수의 항목만 건너뛰고 나머지를 본다 — 해당 check_* 호출을 임시로 주석 처리하거나, 아래 «수동 명령» 으로 그 항목만 확인. 원인 한 줄을 유저에게 보고 |
| 한 항목에서 오래 멈춤 | 접속은 5초, 명령은 30초, NiceGUI 기동은 90초 상한이 있다. 넘게 멈추면 Ctrl+C → 로그 마지막 줄의 명령을 손으로 실행해 본다 |
| 실패가 이상함(실제론 되는데 실패) | 로그(자세히: 경로)에서 그 항목 명령 · 출력을 읽고, 같은 명령을 직접 실행해 비교한다 |
| envcheck.sh 가 «envcheck.py 없음» | 두 파일을 같은 폴더에 둔다 |
| 결과가 너무 길다 | 요약 줄만 보고, 번호를 3절 표에서 찾는다 |

**수동 명령** — 도구가 안 될 때 같은 걸 손으로

    python3 --version; git --version; node --version; codex --version
    curl -sI --max-time 5 https://github.com | head -1; curl -sI --max-time 5 https://pypi.org/simple/ | head -1
    python3 -m venv /tmp/v && /tmp/v/bin/pip install -q -r requirements.txt   # 설치 시간은 앞에 time
    git check-ignore -v --no-index ref/CHECKSHEET.md
    python3 -m http.server 8000 --bind 0.0.0.0   # 다른 탭에서 curl -s localhost:8000 | head -1
    codex features list | grep -E "auto_compaction|unified_exec"
    ls ~/.codex/session_index.jsonl ~/.codex/sessions | head

## 5. Codex 확인 프롬프트 — 스크립트가 못 보는 것

envcheck 를 두 번 돌린 뒤, Codex 입력창에 한 줄씩:

1. «scripts/envcheck/README.md 를 읽고 envcheck.sh --no-install 을 돌린 뒤, 내 터미널 결과(요약: …)와 비교해 샌드박스가 막는 항목을 한 줄로 정리해 줘»
2. «python3 -m http.server 8000 --bind 0.0.0.0 을 백그라운드로 띄워 줘» → Browser 도구 PORT 8000 이 열리나 · 승인 창이 어떻게 뜨나 · 안 열리면 «권한 상승으로 다시» 를 시켜 비교
3. «$survey 의 시험 절대로 해 줘. devview 가 안 떠 있으면 권한 상승으로 8701 에 띄워. 나는 Browser 도구 PORT 8701 → 설문 탭(Alt+8)에서 제출만 하고 채팅은 안 보낼게» → 제출 직후 Codex 가 결과를 보고하나(턴 안 대기) · devview 가 Browser 도구로 보이나(5-1 C)도 같이 확인
4. «계획 모드에서 선택지로 물어봐» → 선택지 질문이 뜨나
5. «이 세션 이름을 MAIN 으로 바꾸는 방법을 알려 주고, 바꾼 뒤 $ready-start 0-2 대로 whoami.py mark → (다음 명령) find 를 해 줘» → 이름 · UUID 가 맞게 나오나 · 대회 Codex 에서 세션 이름 바꾸는 법(MAIN · INSP · 2ND 구조와 hand-on 의 전제)

6. «devview 화면 캡처(우상단 카메라 · Ctrl+Alt+P)를 내가 찍을게. 찍으면 docs/captures 의 최신 PNG 를 열어서 무엇이 보이는지 말해 줘» → 캡처가 저장되고 Codex 가 그림을 읽나(7절)

눈으로 볼 것: /status(모델 · 권한 · 샌드박스) · /model(목록 · 추론 단계) · /skills(키트 스킬이 보이나) · 승인 창 모양 · Browser 도구 포트 전환 · 특수문자(ㅁ+한자 · Win+.) · 붙여넣기

## 6. 15분 진행표

> 전제: 키트 공개 push + Pages 의 install.sh(유저 · TODO 5-1 경고 칸)가 체험 전에 돼 있어야 0~2분 설치가 된다. 안 돼 있으면 4절 수동 명령만.

| 분 | 할 일 |
|---|---|
| 0~2 | 화면 형태 확인 · 터미널 열기 · cd <과제 폴더> && curl -sL tonto0475.github.io/k \| bash |
| 2~4 | bash kit/scripts/envcheck/envcheck.sh (설치 시간 포함 · 약 30초~1분) |
| 4~6 | envcheck 가 끝나면 바로 python3 kit/scripts/envcheck/envcheck.py --serve-start(같이 돌리면 둘이 NiceGUI 를 따로 받아 둘 다 늦어짐) · 요약 줄 기억 · 실패 번호를 3절 표로 확인 |
| 6~10 | Codex 실행 → /status · /model · /skills 눈으로 → 5절 프롬프트 1 · 2 |
| 10~13 | 5절 프롬프트 3(설문) · 4(계획 모드) · 5(세션 이름 · 1분) |
| 13~14 | python3 kit/scripts/envcheck/envcheck.py --serve-check(E3) · 5절 프롬프트 6(devview 캡처) · 특수문자 · 붙여넣기 |
| 14~15 | 체험 종료 → 예시 서술형 화면 확인 |

- 결과는 시험 화면 밖에 적지 않는다 — 요약 두 줄 · E3 한 줄만 기억했다가 체험이 끝난 뒤 적는다
- 막히면 그 항목은 넘기고 다음으로

## 7. devview — 유저에게 가장 중요한 도구

> Codex 에게: 유저는 대회 중 거의 모든 것을 devview 로 본다. 체험에서 devview 가 안 되면 대회 계획이 크게 바뀐다 → 이 절의 확인을 빠뜨리지 말고, 막히면 4절처럼 즉석 대응한다.

**무엇인가**
- 작업 폴더를 PyCharm 비슷하게 보고 고치는 웹 화면. 파이썬 표준 라이브러리 서버(devview/devview.py) + 미리 빌드한 화면 파일(devview/static) — pip · npm 설치 없이 돈다
- 유저는 IDE 의 Browser 도구에 PORT 8701 을 넣어 연다(서버는 0.0.0.0 에 묶어야 보인다)
- 화면
	- 코드 탭: 파일 트리(git 상태 색) · 편집기(PyCharm 색 · 키맵) · md 는 옵시디언식 라이브 미리보기(콜아웃 색 상자 포함) · CSV 표로 보기
	- Git 탭(Alt+9): 커밋 그래프 · diff · 파일 이력(읽기 전용)
	- 설문 탭(Alt+8): $survey 설문이 뜨는 곳 — 새 설문이 등록되면 2초 안에 자동으로 넘어감
	- 화면 캡처(우상단 카메라 · Ctrl+Alt+P): 지금 화면을 docs/captures/날짜_시각_보기.png 로 저장 → Codex 가 그 파일을 열어 유저 화면을 본다
- 저장: 코드는 입력이 멈추고 1초 뒤 자동 저장 · 다른 곳(IDE 편집기 · Codex)이 먼저 고친 파일은 덮어쓰지 않고 «외부 변경 충돌» 띠

**켜기 · 끄기**
- 떠 있나: curl -s http://127.0.0.1:8701/sv/api/state → json 이면 설문 연결된 devview
- 켜기: bash kit/devview/dv (작업 폴더 ~/workspace, 없으면 지금 폴더 · 포트 8701) · 다른 포트: bash kit/devview/dv 8702
	- Codex 가 띄울 때는 exec_command 에 권한 상승(require_escalated)을 요청한다 — 샌드박스 안에서 띄우면 Browser 도구가 못 닿을 수 있다
- 끄기: bash kit/devview/dv stop · 상태: bash kit/devview/dv status · 서버 기록: ~/.devview/devview.log

**체험에서 확인할 것** (유저가 화면으로 보고, Codex 는 결과를 받아 정리)
1. Browser 도구 PORT 8701 에 화면이 뜨나 — 안 뜨면 샌드박스 안 · 밖 어느 쪽에서 띄웠는지부터
2. md 파일(예: kit/AGENTS.md)을 열면 콜아웃 색 상자 · 표가 보이나
3. 파일을 하나 고쳐 저장 → IDE 편집기 쪽에 반영되나 · 반대로 IDE 에서 고치면 devview 에 «외부 변경» 이 뜨나
4. Git 탭에 커밋 그래프가 나오나(과제 저장소 기준)
5. 설문 탭에 시험 설문이 뜨고 제출되나(5절 프롬프트 3)
6. 캡처 → docs/captures 에 PNG 가 생기고 Codex 가 읽나(5절 프롬프트 6)

**막힐 때**
| 증상 | 할 일 |
|---|---|
| «화면 파일 없음: …» 로 바로 꺼짐 | devview/static 이 빠짐 — 키트를 다시 받았는지 · kit/devview/static/index.html 이 있는지 |
| «포트 8701 을 열 수 없음» | 이미 떠 있음(dv status) 또는 다른 프로그램 → bash kit/devview/dv 8702 로 다른 포트 |
| 서버는 떴는데 Browser 도구에 안 보임 | 샌드박스 안에서 띄움 → 권한 상승으로 다시 · 127.0.0.1 이 아니라 0.0.0.0 인지(dv 는 기본 0.0.0.0) |
| 설문 탭이 없음 | survey.py 를 못 찾음 → bash kit/devview/dv 를 저장소 루트에서 · 또는 python3 kit/devview/devview.py <폴더> --survey kit/.agents/skills/survey/survey.py |
| 화면이 하얗거나 일부만 | 미리보기 새로고침(원형 화살표) → ~/.devview/devview.log 의 오류 줄 |
| 캡처가 안 생김 | docs/captures 쓰기 권한 · 로그의 «캡처» 줄 · 0.6~3초 걸림 |
| 전부 안 됨 | 대회는 devview 없이 IDE 기본 미리보기 + 터미널로 간다(설문은 python3 kit/.agents/skills/survey/survey.py serve --port 8600) |

자세한 기능은 kit/devview/README.md.
