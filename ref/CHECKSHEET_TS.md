# CHECKSHEET_TS — TypeScript · Node 과제 점검표

> 과제가 TypeScript · Node 일 때 유저가 펴 보는 명령표. Codex 가 따르는 규칙 문서가 아니다(규칙은 AGENTS.md · docs/).
> 이 폴더는 ref/.gitignore(*) 때문에 과제 저장소 git 에 커밋되지 않는다.
> «실측» 표시는 WSL(Ubuntu · node v20.20.2 · npm 10.8.2 · jest 30.5.2 · vitest 4.1.12, 2026-10-29)의 임시 폴더에서 실제로 돌려 확인한 값이다.

## 목차

1. 설치
2. 테스트 실행
3. 자주 나는 오류 → 원인
4. 예상된 실패 표시 — test.failing · test.fails

---

> [!warning] 1. 설치
>
> | 명령 | 하는 일 |
> |---|---|
> | node --version · npm --version | 버전 확인. package.json 의 "engines" 와 맞는지 본다 |
> | npm ci | package-lock.json 그대로 설치(잠금 파일과 package.json 이 어긋나면 멈춤). **잠금 파일이 있으면 이것** |
> | npm install | 잠금 파일이 없을 때 · 새 패키지를 넣을 때(잠금 파일이 바뀜) |
> | npm install --save-dev 이름 | 개발용 패키지 추가(테스트 도구 등) |
> | npm install --legacy-peer-deps … | 함께 필요한 패키지(peer) 계산에서 npm 이 죽을 때. 실측: vitest 4 설치가 «Cannot read properties of null (reading 'edgesOut')» 로 실패 → 이 옵션으로 성공 |
> | npm run | package.json 의 "scripts" 목록 보기 — test · build · lint 이름부터 확인 |
>
> - 🔴 전역 설치(-g) 하지 않는다 — 과제 폴더 안에만
> - 🔴 npx jest 는 jest 가 설치돼 있지 않으면 **경고만 찍고 임시로 내려받아 실행**한다(실측) — 버전이 과제와 다를 수 있다. 먼저 npm ci

---

> [!verify] 2. 테스트 실행
>
> | 명령 | 하는 일 |
> |---|---|
> | npm test | package.json "scripts"."test" 실행 — 과제가 정한 방법이라 **이것부터** |
> | npx vitest run | vitest 한 번 실행 후 종료(run 을 빼면 감시 모드로 안 끝남) |
> | npx jest | jest 실행 |
> | npx vitest run src/add.test.ts · npx jest src/add.test.ts | 파일 하나만 |
> | npx vitest run -t "이름" · npx jest -t "이름" | 이름에 그 글자가 든 테스트만 |
> | npm test -- -t "이름" | npm test 에 옵션 넘기기(-- 뒤가 테스트 도구로 감) |
>
> **결과 읽기**
>
> | 표시 | 뜻 |
> |---|---|
> | jest «Tests: 1 failed, 3 passed» · vitest «Tests 1 failed \| 3 passed» | 실패 · 통과 수 |
> | 종료코드 0 · 1 | 전부 통과 · 실패 있음(둘 다 실측) |
> | -t 로 고른 테스트가 없음 | jest · vitest 모두 «1 skipped» · **종료코드 0**(실측). pytest(5)와 달라 통과로 착각하기 쉽다 — 마지막 줄의 수를 본다 |

---

> [!example] 3. 자주 나는 오류 → 원인
>
> | 오류 문구 | 원인 · 처리 |
> |---|---|
> | SyntaxError: Cannot use import statement outside a module | CommonJS 로 읽는 파일에 import. package.json "type":"commonjs" 에서 실측. "type":"module" 로 바꾸거나 파일을 .mjs 로 |
> | Warning: [MODULE_TYPELESS_PACKAGE_JSON] … doesn't parse as CommonJS | "type" 이 없는 package.json 에서 import 를 쓰면 node 20.20 은 경고 후 ESM 으로 실행(실측). 경고를 없애려면 "type" 을 적는다 |
> | ReferenceError: require is not defined in ES module scope | "type":"module" 인데 require 사용(실측). import 로 바꾸거나 .cjs 로 |
> | Error: Cannot find module './nope' | 경로 오타 · 파일 없음 · npm ci 안 함(실측) |
> | Error [ERR_MODULE_NOT_FOUND]: Cannot find module '…/util' | ESM 에서 import 경로의 확장자(.js)를 뺌(실측). ESM 은 './util.js' 처럼 확장자까지 적는다(TS 소스여도 .js) |
> | Jest encountered an unexpected token · SyntaxError: … Missing initializer in const declaration | jest 에 TS 설정이 없음 — .ts 를 그냥 자바스크립트로 읽다 «: number» 에서 막힘(실측). ts-jest 또는 babel 설정 필요. vitest 는 설정 없이 .ts 를 읽는다 |
> | error TS2322: Type 'string' is not assignable to type 'number' | TS 타입 오류 — npx tsc --noEmit 로 전체 타입 검사(테스트 도구는 타입 검사를 건너뛰는 경우가 많다) |
> | npm error Cannot read properties of null (reading 'edgesOut') | npm 의 peer 계산 오류 — --legacy-peer-deps 로 설치(1절, 실측) |

---

> [!danger] 4. 예상된 실패 표시 — test.failing · test.fails
>
> pytest 의 xfail(strict=True) 와 같은 쓰임: **버그가 남아 있으면 통과, 고쳐졌는데 표시가 남아 있으면 실패.** 재현 테스트를 먼저 커밋하고, 고친 뒤 표시를 떼는 흐름.
>
> ```js
> // jest — add(1, 2) 가 3 이어야 하는데 버그로 -1
> test.failing('add 버그 남음', () => { expect(add(1, 2)).toBe(3); });
>
> // vitest
> import { test, expect } from 'vitest';
> test.fails('add 버그 남음', () => { expect(add(1, 2)).toBe(3); });
> ```
>
> | 경우 | jest test.failing | vitest test.fails |
> |---|---|---|
> | 버그 남음 | 통과 «Tests: 1 passed» · 종료코드 0 | 통과 «Tests 1 expected fail» · 종료코드 0 |
> | 고쳐짐(표시 남음) | 실패 «Failing test passed even though it was supposed to fail. Remove `.failing` to remove error.» · 종료코드 1 | 실패 «Error: Expect test to fail» · 종료코드 1 |
>
> - 위 표는 전부 실측(2026-10-29 · jest 30.5.2 · vitest 4.1.12 · node v20.20.2)
> - 이름이 다르다: jest 는 failing, vitest 는 fails. 서로 바꿔 쓰지 않는다(바꿔 썼을 때의 문구는 미확인)
> - 고친 뒤에는 표시만 떼서 일반 test 로 — 그러면 같은 테스트가 회귀 테스트가 된다
