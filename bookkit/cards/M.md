# M — 합치기 (MAIN · 지휘 세션 · 1분)

**쓸 파일**: 없음 — 고칠 곳은 해당 카드 담당에게 돌려준다(시간이 없으면 그 칸만 직접)

## 1차판(A2 PASS · W1 · W6 · W2 의 3장 뒤)
- `python3 bookkit/engine/build_book.py <책> --stage 1 --strict` → 종료 코드 0(구조 바뀜만 본다 · 빈 칸은 회색 «2차판에서 채워짐») → 유저에게 결과 html 경로 · devview 주소를 바로 준다
- 빌드가 `dist/<이름>.blocks.json`(블록 ID · 내용 해시)를 남긴다 — 2차판이 이것과 견줘 «새로» 띠를 단다(지우지 않는다)
- 판은 덮어쓰지 않는다 — 빌드마다 새 파일 `dist/<이름>__v<N>_<판 이름>.html`(자동 · `<이름>.html` 은 최신 복사본) · 유저가 방향을 바꾼 판은 `--label "<짧은 이름>"` · 내용(content)을 고쳐도 앞 판 html 은 그대로 남는다

## 계약이 PASS 될 때마다(셋을 기다리지 않는다 · 쉬는 서브에게 `followup_task`)
- steps PASS → W4 · W5 / facts PASS → W2(2장 · 부록) · W3 / 숫자 칸(W1 · W6)은 그 칸의 계약이 PASS 될 때마다 알린다 · A 서브에게 «이어서 지도»
- steps 가 `"data": "raw"` 였으면 facts PASS 뒤 A3 에게 정리한 자료로 다시(4장 숫자는 `F[…]` 라 다시 빌드하면 따라온다)

## 중간판(장이 끝날 때마다 — 1차판 뒤 · 2차판 전)
- 장 끝 신호를 받으면 바로: `python3 bookkit/engine/build_book.py <책> --stage 1 --chapters <지금까지 끝난 장 전부> --label "<N장까지>" --strict` → 유저에게 경로 한 줄(턴을 끝내지 않는다)
- 예: `--chapters s1,s3,s5,s4 --label 4장까지` → `dist/<이름>__v<N>_4장까지.html` · 장 이름 = pv · s1 ~ s5 · apx · 4장 = W4 · W5 둘 다 · apx = W2 · W6 둘 다 끝나야 끝이다
- 안 끝난 장 · 빈 칸 = 회색 · strict 는 구조 바뀜만 본다 · «새로» 띠 = 앞 판 대비

## 2차판 순서
1. 계약 셋 함께(교차 검사 — 여기서 한 번): `python3 bookkit/contracts/check_contract.py <책>/contracts --task <과제 폴더>` → 셋 다 PASS(`{F['…']}` 이름이 다 맞아야 PASS)
2. 완성 확인: `python3 bookkit/engine/build_book.py <책> --stage 2 --strict` → 종료 코드 0 · «빈 칸 0» · «구조 바뀜» 0 · 경고 «각주 없이 처음 나온 코드 이름» 0
   - 빈 칸이 남으면 «빈 칸: 장 · 칸» 의 장으로 담당 카드를 찾는다(meta · s1 → W1 · s2 · s3 · apx A_ · B_ → W2 · pv → W3 · s4 앞 → W4 · s4 뒤 → W5 · s5 · apx C_ · 그림_시스템층 → W6 · shared 의 그림 · 재생기 → A1 · A3)
   - «표 … 행이 표 밖» 경고 = 표의 bad_cells · notes 행 번호가 틀렸다 → 그 표를 낸 사람에게
   - «식 글자 남음» = `--strict` 실패 — 책에 «{F['…']}» 가 글자 그대로 나온다 → 그 블록의 계약 칸(원본 조각 · 결함 칩)을 낸 A1 에게
   - «서식 경고» 0 으로(v3 와 모양이 갈리는 곳 · RULES.md 6절 칸 길이표) — 블록 ID 의 장으로 담당을 찾는다 · 계약 칸 길이(«v3 한도» · «너무 짧다»)는 1번 검사 경고에서 A1 · A2 에게 · «⟪…⟫ 자리가 남았다» = steps.json `"data": "raw"` → A3 가 정리한 자료로 다시
3. 검사: `python3 bookkit/engine/book/check_book.py <책>/dist/<이름>.html` → PASS · 쪽 수
   - FAIL = 쪽보다 큰 블록 · 가로 넘침 → 그 칸 글을 줄이거나 표를 나눈다(구조는 그대로 · 크기 기준 RULES.md 6절)
   - SKIP(브라우저 없음)은 PASS 가 아니다 — 보고에 «검사 SKIP» 이라고 적는다
4. 지도 마무리: `$ontology` 1-9(A1 · A2 · A3 «이어서 지도» 가 끝난 뒤 — 쉬운 말 검사 · 가장 큰 함정 · 지금 상태 · diff 확인 뒤 docs/ONTOLOGY.md 만 커밋)
5. 보고: 결과 html 전체 경로 · 블록 · 각주 · 빈 칸 0 · 검사 결과 · 비워 둔 칸과 이유 · devview 로 여는 법(페이지 서버 포트 8801 · 주소 `/bookkit/books/<이름>/dist/<이름>.html`)

## 끝 신호
1차판: `--stage 1 --strict` 종료 코드 0 · 2차판: `--stage 2 --strict` 종료 코드 0 + check_book PASS(또는 SKIP 명시)
