#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kit handoff — docs/hand_off.md 의 형식 칸만 고친다(본문 글은 에이전트가 파일에서 직접)

    ./kit handoff list                                   섹션마다 진행 결과 · 수정 범위 · 🔴 논의 · 검증 상자 상태
    ./kit handoff show <번호|진행|순서>                  그 부분만 출력
    ./kit handoff section-new <번호> <이름> --risk 저위험|민감   블록 8개 빈 뼈대 + 진행 기록 줄(내용 인자 없음)
    ./kit handoff scope-approve <번호> [--chat]          수정 범위 🟠 → 🟢(🚹 답 줄에 «승인» 이 있어야 · 대화로 받았으면 --chat)
    ./kit handoff scope-change <번호> <파일> <함수> <이유>  승인 뒤 범위 밖 파일 «🟠 변경 N» 줄 + 빈 답 칸 · 상자를 주황으로
    ./kit handoff verify-log <번호> <행> --result 통과|실패|대기 [--desc] [--file] [--func] [--expect] [--actual] [--action] [--commit] [--script]
    ./kit handoff order-add <섹션> [--plan] [--actual] [--basis] [--next]   섹션 작업 순서 표 맨 끝에 한 줄
    ./kit handoff progress <번호> --result 끝남|보류|해당없음|아직 [--commit] [--note]   진행 기록 표의 결과 · 통과 커밋

판단(승인인가 · 통과인가 · 이유)은 에이전트가 하고, 도구는 기호 · 색 · 표 위치 · 시각을 맞춘다.
글 인자는 한 줄만 — 줄바꿈이 들어오면 거부한다(그 블록은 파일에서 직접).
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import KitError, Doc, doc_path, one_line, now_short, split_row, join_row, is_sep, run  # noqa: E402

HEAD_RE = re.compile(r"^## (\d+-\d+) · (.+?) — (.+?)\s*$")
PLACE_HEAD = "## 1-1 · (섹션 이름) — 저위험 / 민감"
SCOPE_RE = re.compile(r"^> \[!(warning|success)\] ✅ 수정 범위")
VERIFY_RE = re.compile(r"^> \[!(decision-open|decision-done)\]- ✅ 검증 기록")
CHANGE_RE = re.compile(r"^> - (🟠|🟢) \*\*변경 (\d+)\*\*")
RISKS = ("저위험", "민감")
RESULT_SIGN = {"통과": "🟢", "실패": "🔴", "대기": "⬜", "🟢": "🟢", "🔴": "🔴", "⬜": "⬜"}
PROGRESS_SIGN = {"끝남": "🟢", "보류": "⏸️", "해당없음": "➖", "아직": "⬜", "🟢": "🟢", "⏸️": "⏸️", "➖": "➖", "⬜": "⬜"}

# 섹션 뼈대 — docs/hand_off.md 양식의 섹션 블록 그대로(시험이 양식과 같은지 본다)
SECTION_BODY = """> [!warning] ✅ 수정 범위 · 승인 대기 🟠
> **변경 대상 파일** (N개 · 함수 M개)
> - (파일) — (바꿀 함수 이름들)
>
> > [!note]- 자세히 (함수 M개)
> > | 파일   | 클래스   | 함수   | 지금 하는 일   | 변경 전 동작   | 변경 후 동작   |
> > |--------|----------|--------|----------------|----------------|----------------|
> > |        | —        |        |                |                |                |
>
> **생성 예정 파일** (N개)
> - (파일) — (무엇을 하는 파일) / 변경만 하면 «없음»
>
> > 🚹

> [!abstract] ✅ 목표
> (이 섹션에서 구현할 것 요약 한두 줄 — 개요만)
> - **문제**:
> - **원인**:
> - **만들 것 / 안 만들 것**:
> - **제약**:

> [!todo] ✅ 성공 기준
> | 번호   | 조건   | 동작   | 기대 결과   | 확인 방법   | 검증 행   |
> |--------|--------|--------|-------------|-------------|-----------|
> | C1     |        |        |             |             | → API-1   |

> [!quote] ✅ 배경
> - (참고 문서 경로 — 저장소 안 상대 경로(DOC_GUIDE 3절) · 핵심 인용구. 없으면 비워 둠)

> [!decision-open] ✅ 논의 내용 · 1회차 🔴
> **작업 전**
> - 🔴 #1 🤖 (질문) 추천: …
> > 🚹
>
> **작업 중**
> - (없음)
>
> **작업 후**
> - (없음)

> [!summary] ✅ 결과 정리
> - **구현**:
> - **개선**:
> - **미구현**:
> - **결정 → 근거 함수**(결정이 코드에 들어가면 한 줄 · 서술형 · 확인 문제 답의 근거 · $ready-end 외우기 카드가 모은다)
>
> | 결정(항목 번호) | 파일 | 함수(한글) | 시험 |
> |---|---|---|---|
> | (1-1 #1 무엇을 정했나) | (src/core/….py) | (함수_이름) | (tests/test_….py::test_…) |
> - **깨질 수 있는 곳**
> \t- 정상 경로:
> \t- 실패 경로:
> \t- timeout:
> \t- 깨질 조건:
> \t- 남은 위험:
> \t- 다음에 볼 곳:
> - **사람이 승인한 지점**:

> [!decision-open]- ✅ 검증 기록 🔴
> **API**
>
> | 행    | 검증 내용                   |
> |-------|-----------------------------|
> | API-1 | (자연어로 · 코드 이름 없이) |
>
> > [!note]- 상세 기록
> > | 행    | 카테고리   | 대상 파일   | 대상 함수   | 기대   | 실제   | 일치   | 조치   | 조치 일시   |
> > |-------|------------|-------------|-------------|--------|--------|--------|--------|-------------|
> > | API-1 | API        |             |             |        |        | ⬜     |        |             |
> >
> > - 재현 스크립트:
> > - 범위 대조: (바뀐 파일 목록 ↔ 수정 범위 — 목록 밖 파일 없음 / 있음: 파일)
> > - 통과 커밋:

> [!example]- ✅ 코드 개선 제안
> | 대상 파일   | 카테고리   | 문제점   | 중요도   |
> |-------------|------------|----------|----------|
> |             |            |          |          |
>
> - 카테고리: 함수 · 클래스 · 패키지 구조 · 모듈화 · 분기·경계값 · 예외 처리 · 동시성·중복 쓰기 · 하드코딩
> - 중요도: 🔴 필수 개선 · 🟠 잠재 위험 · 🟢 있으면 좋음 · 문제점까지만(개선 방향은 쓰지 않음)""".replace("\\t", "\t")


# ======= 문서 구조 찾기 =======

# 섹션 목록 — [(번호, 이름, 위험도, 시작 줄, 끝 줄(다음 ## 직전))]
def sections(lines):
    heads = [(i, HEAD_RE.match(l)) for i, l in enumerate(lines) if l.startswith("## ")]
    out = []
    for k, (i, m) in enumerate(heads):
        end = heads[k + 1][0] if k + 1 < len(heads) else len(lines)
        if m and m.group(2) != "(섹션 이름)":  # 양식의 빈 섹션은 섹션으로 치지 않는다(section-new 가 이어 씀)
            out.append((m.group(1), m.group(2), m.group(3), i, end))
    return out


# 번호로 섹션 찾기 → (시작, 끝)
def find_section(lines, num):
    for n, _name, _risk, s, e in sections(lines):
        if n == num:
            return s, e
    raise KitError(f"섹션 {num} 없음 — ./kit handoff list 로 번호 확인 · 새로 만들려면 section-new")


# «## 제목» 이 들어간 절(진행 기록 · 섹션 작업 순서) → (시작, 끝)
def find_part(lines, key):
    for i, l in enumerate(lines):
        if l.startswith("## ") and key in l:
            e = next((j for j in range(i + 1, len(lines)) if lines[j].startswith("## ") or lines[j].strip() == "---"), len(lines))
            return i, e
    raise KitError(f"«{key}» 절 없음 — hand_off 양식과 다름")


# 인용 상자 끝(첫 줄부터 «>» 로 시작하는 줄이 이어지는 데까지) → 끝 줄(포함 안 함)
def box_end(lines, i):
    j = i + 1
    while j < len(lines) and lines[j].startswith(">"):
        j += 1
    return j


# 범위 안 표의 행 목록 → [(줄 번호, prefix, 칸)] (머리 · 구분 줄 제외) · head 를 주면 머리 첫 칸이 그것인 표만
def table_rows(lines, s, e, head=None):
    rows, cur = [], None
    for i in range(s, e):
        pre, cells = split_row(lines[i])
        if cells is None:
            cur = None
            continue
        if cur is None:
            cur = cells  # 머리
            continue
        if is_sep(cells):
            continue
        if head is None or (cur and cur[0] == head):
            rows.append((i, pre, cells))
    return rows


# ======= 명령 =======

def cmd_list(doc, a):
    lines = doc.lines
    prog = {}
    try:
        ps, pe = find_part(lines, "진행 기록")
        for _i, _p, c in table_rows(lines, ps, pe, "번호"):
            prog[c[0]] = c
    except KitError:
        pass
    secs = sections(lines)
    if not secs:
        print("섹션 없음 — section-new 로 만든다")
        return 0
    for n, name, risk, s, e in secs:
        seg = lines[s:e]
        scope = "—"
        for l in seg:
            if SCOPE_RE.match(l):
                scope = "🟢" if "[!success]" in l else "🟠"
        red = sum(1 for l in seg if re.match(r"^> -? ?🔴", l))
        ver = "—"
        for l in seg:
            m = VERIFY_RE.match(l)
            if m:
                ver = "🟢" if m.group(1) == "decision-done" else "🔴"
        pr = prog.get(n)
        res = f"{pr[3]} {pr[4]}" if pr and len(pr) >= 5 else "—"
        print(f"{n} · {name} — {risk} · 결과 {res} · 수정 범위 {scope} · 🔴 줄 {red} · 검증 {ver} · {doc.path.name}:{s + 1}")
    return 0


def cmd_show(doc, a):
    lines = doc.lines
    if a.what == "진행":
        s, e = find_part(lines, "진행 기록")
    elif a.what == "순서":
        s, e = find_part(lines, "섹션 작업 순서")
    else:
        s, e = find_section(lines, a.what)
    print(f"# {doc.path.name}:{s + 1}-{e}")
    print("\n".join(lines[s:e]).rstrip())
    return 0


def cmd_section_new(doc, a):
    num = a.num
    if not re.fullmatch(r"\d+-\d+", num):
        raise KitError(f"번호 «{num}» — «1-2» 꼴")
    name = one_line("이름", a.name, 40, cell=True)
    if a.risk not in RISKS:
        raise KitError("--risk 는 저위험 · 민감 중 하나")
    lines = doc.lines
    if any(n == num for n, *_ in sections(lines)):
        raise KitError(f"섹션 {num} 이 이미 있음")
    head = f"## {num} · {name} — {a.risk}"
    if PLACE_HEAD in lines:
        # 양식의 빈 섹션 1-1 을 첫 섹션으로 쓴다(제목 줄만 바꿈)
        at = lines.index(PLACE_HEAD)
        lines[at] = head
    else:
        while lines and lines[-1].strip() == "":
            lines.pop()
        at = len(lines) + 3
        lines += ["", "---", "", head, ""] + SECTION_BODY.split("\n") + [""]
    # 진행 기록 표 — 양식 빈 줄이면 바꾸고, 아니면 맨 끝에 한 줄
    ps, pe = find_part(lines, "진행 기록")
    rows = table_rows(lines, ps, pe, "번호")
    new_row = join_row("", [num, name, a.risk, "⬜", "—"])
    place = [r for r in rows if r[2][1] == "(섹션 이름)"]
    if place:
        lines[place[0][0]] = new_row
    elif rows:
        lines.insert(rows[-1][0] + 1, new_row)
    else:
        raise KitError("진행 기록 표가 없음 — hand_off 양식과 다름")
    doc.save()
    print(f"섹션 {num} · {name} — {a.risk} 만듦 · {doc.path.name}:{at + 1} · 진행 기록 ⬜")
    print("다음: 목표 · 성공 기준 · 배경 · 수정 범위는 파일에서 직접 채운다")
    return 0


# «승인» 답인가 — 🚹 뒤 글에 «승인» 이 있고 부정이 아니면
def is_approval(line: str) -> bool:
    t = line.split("🚹", 1)[1] if "🚹" in line else ""
    if "승인" not in t:
        return False
    return not re.search(r"미승인|승인\s*(안|못|X|x|보류|거절)|불승인", t)


# 섹션의 마지막 수정 범위 상자 → (시작, 끝)
def last_scope(lines, s, e):
    hits = [i for i in range(s, e) if SCOPE_RE.match(lines[i])]
    if not hits:
        raise KitError("수정 범위 상자가 없음")
    i = hits[-1]
    return i, box_end(lines, i)


def cmd_scope_approve(doc, a):
    lines = doc.lines
    s, e = find_section(lines, a.num)
    bs, be = last_scope(lines, s, e)
    title = lines[bs]
    pending = [i for i in range(bs, be) if (m := CHANGE_RE.match(lines[i])) and m.group(1) == "🟠"]
    done = []
    if pending:
        for i in pending:
            ans = lines[i + 1] if i + 1 < be and "🚹" in lines[i + 1] else ""
            if not a.chat and not is_approval(ans):
                n = CHANGE_RE.match(lines[i]).group(2)
                raise KitError(f"변경 {n} 의 🚹 답 줄에 «승인» 이 없음({doc.path.name}:{i + 2}) — 대화로 승인받았으면 --chat")
        for i in pending:
            lines[i] = lines[i].replace("🟠 **변경", "🟢 **변경", 1)
            done.append(f"변경 {CHANGE_RE.match(lines[i]).group(2)}")
    else:
        if "[!success]" in title:
            print(f"섹션 {a.num} 수정 범위는 이미 승인 🟢")
            return 0
        hum = [i for i in range(bs, be) if lines[i].startswith("> > 🚹")]
        ans = lines[hum[-1]] if hum else ""
        if not a.chat and not is_approval(ans):
            raise KitError(f"수정 범위 🚹 답 줄에 «승인» 이 없음({doc.path.name}:{(hum[-1] + 1) if hum else bs + 1}) — 대화로 승인받았으면 --chat")
        done.append("수정 범위")
    lines[bs] = re.sub(r"(?:변경 \d+ )?승인 대기 🟠\s*$", "승인 🟢", title.replace("[!warning]", "[!success]", 1))
    doc.save()
    print(f"섹션 {a.num} · {' · '.join(done)} 승인 🟢 · {doc.path.name}:{bs + 1}" + (" (대화 승인)" if a.chat else ""))
    return 0


def cmd_scope_change(doc, a):
    path = one_line("파일", a.path, 120)
    func = one_line("함수", a.func, 120)
    why = one_line("이유", a.why, 120)
    lines = doc.lines
    s, e = find_section(lines, a.num)
    bs, be = last_scope(lines, s, e)
    nums = [int(m.group(2)) for i in range(bs, be) if (m := CHANGE_RE.match(lines[i]))]
    n = max(nums, default=0) + 1
    # «변경 대상 파일» 목록 끝(이어지는 «> - » 줄과 그 답 칸 다음)
    try:
        h = next(i for i in range(bs, be) if lines[i].startswith("> **변경 대상 파일**"))
    except StopIteration:
        raise KitError("«변경 대상 파일» 줄이 없음")
    j = h + 1
    while j < be and (lines[j].startswith("> - ") or lines[j].startswith("> > 🚹")):
        j += 1
    lines[j:j] = [f"> - 🟠 **변경 {n}** · {path} — {func} · {why}(등록 {now_short()[6:]})", "> > 🚹"]
    title = lines[bs].replace("[!success]", "[!warning]", 1)
    title = re.sub(r"(?:변경 \d+ )?승인(?: 대기)? (?:🟢|🟠)\s*$", f"변경 {n} 승인 대기 🟠", title)
    lines[bs] = title
    doc.save()
    print(f"섹션 {a.num} · 변경 {n} 등록 🟠 · {doc.path.name}:{j + 1} — 재승인 전에는 그 파일에 손대지 않는다")
    return 0


def cmd_verify_log(doc, a):
    row = a.row
    if not re.fullmatch(r"[A-Z]+-\d+", row):
        raise KitError(f"행 «{row}» — «API-1» 꼴(카테고리 대문자-번호)")
    sign = RESULT_SIGN.get(a.result)
    if not sign:
        raise KitError("--result 는 통과 · 실패 · 대기")
    vals = {k: one_line(k, getattr(a, k), 120, cell=True) for k in ("desc", "file", "func", "expect", "actual", "action")}
    commit = one_line("commit", a.commit, 40, cell=True)
    script = one_line("script", a.script, 160)
    cat = row.split("-")[0]
    lines = doc.lines
    s, e = find_section(lines, a.num)
    vb = next((i for i in range(s, e) if VERIFY_RE.match(lines[i])), None)
    if vb is None:
        raise KitError(f"섹션 {a.num} 에 검증 기록 상자가 없음")
    ve = box_end(lines, vb)
    det = next((i for i in range(vb, ve) if lines[i].startswith("> > [!note]- 상세 기록")), None)
    if det is None:
        raise KitError("검증 기록 상자에 «상세 기록» 표가 없음 — 양식대로 고친 뒤 다시")
    # ⓪ 양식의 빈 예시 행(«(자연어로 · 코드 이름 없이)»)이 다른 행이면 걷어 낸다 — 남겨 두면 상자가 영영 빨강
    for i, p, c in table_rows(lines, vb, det, "행"):
        if c[0] != row and len(c) > 1 and c[1].startswith("(자연어로"):
            ph = c[0]
            d = [r for r in table_rows(lines, det, ve, "행") if r[2][0] == ph and not any(x for x in r[2][2:6]) and not any(x for x in r[2][7:])]
            for k in sorted([i] + [r[0] for r in d], reverse=True):
                del lines[k]
            # 요약 표가 비면 그 카테고리 머리 · 표 머리 · 구분 줄 · 빈 줄도
            h = next((k for k in range(vb, det) if lines[k].strip() == f"> **{ph.split('-')[0]}**"), None)
            if h is not None and not table_rows(lines, h, h + 4, "행"):
                del lines[h:h + 5]
            ve = box_end(lines, vb)
            det = next(k for k in range(vb, ve) if lines[k].startswith("> > [!note]- 상세 기록"))
            break
    # ① 요약 표(카테고리 머리 아래) — 행이 있으면 검증 내용만(준 경우) · 없으면 새 행(--desc 필요)
    summ = [(i, p, c) for i, p, c in table_rows(lines, vb, det, "행")]
    hit = [r for r in summ if r[2][0] == row]
    if hit:
        i, p, c = hit[0]
        if vals["desc"]:
            lines[i] = join_row(p, [row, vals["desc"]])
    else:
        if not vals["desc"]:
            raise KitError(f"요약 표에 {row} 가 없음 — 새 행이면 --desc «바깥에서 보이는 검증 내용 한 줄»")
        cat_head = next((i for i in range(vb, det) if lines[i].strip() == f"> **{cat}**"), None)
        if cat_head is not None:
            rows = [r for r in summ if r[0] > cat_head]
            nxt = next((i for i in range(cat_head + 1, det) if lines[i].startswith("> **")), det)
            rows = [r for r in rows if r[0] < nxt]
            at = rows[-1][0] + 1 if rows else cat_head + 4
            lines.insert(at, join_row("> ", [row, vals["desc"]]))
        else:
            block = [f"> **{cat}**", ">", "> | 행 | 검증 내용 |", "> |---|---|", join_row("> ", [row, vals["desc"]]), ">"]
            lines[det:det] = block
        ve = box_end(lines, vb)
        det = next(i for i in range(vb, ve) if lines[i].startswith("> > [!note]- 상세 기록"))
    # ② 상세 표 — 행이 있으면 준 칸만 바꾸고, 없으면 새 행
    drows = table_rows(lines, det, ve, "행")
    dhit = [r for r in drows if r[2][0] == row]
    stamp = now_short() if sign != "⬜" else None
    if dhit:
        i, p, c = dhit[0]
        c = (c + [""] * 9)[:9]
    else:
        i, p, c = None, "> > ", [row, cat, "", "", "", "", "⬜", "", ""]
    for k, col in (("file", 2), ("func", 3), ("expect", 4), ("actual", 5), ("action", 7)):
        if vals[k] is not None:
            c[col] = vals[k]
    c[6] = sign
    if stamp:
        c[8] = stamp
    if i is None:
        at = drows[-1][0] + 1 if drows else det + 3
        lines.insert(at, join_row(p, c))
    else:
        lines[i] = join_row(p, c)
    ve = box_end(lines, vb)
    # ③ 재현 스크립트 · 통과 커밋 줄(덧붙이기)
    for key, val in (("> > - 재현 스크립트:", script), ("> > - 통과 커밋:", commit if sign == "🟢" else None)):
        if not val:
            continue
        k = next((i for i in range(det, ve) if lines[i].startswith(key)), None)
        if k is None:
            continue
        cur = lines[k].rstrip()
        if val not in cur:
            lines[k] = cur + (" " if cur.endswith(":") else " · ") + val
    # ④ 상자 색 — 상세 표가 모두 🟢 면 초록, 하나라도 아니면 빨강
    marks = [r[2][6] for r in table_rows(lines, det, ve, "행") if len(r[2]) > 6]
    ok = bool(marks) and all(m == "🟢" for m in marks)
    head = lines[vb]
    head = head.replace("[!decision-open]", "[!decision-done]") if ok else head.replace("[!decision-done]", "[!decision-open]")
    head = re.sub(r"(🔴|🟢)\s*$", "🟢" if ok else "🔴", head)
    lines[vb] = head
    doc.save()
    left = sum(1 for m in marks if m != "🟢")
    print(f"섹션 {a.num} · {row} {sign} · 검증 상자 {'🟢' if ok else '🔴'}(남은 행 {left}) · {doc.path.name}:{vb + 1}")
    return 0


def cmd_order_add(doc, a):
    sec = one_line("섹션", a.section, 10, cell=True)
    cells = {k: one_line(k, getattr(a, k), 160, cell=True) for k in ("plan", "actual", "basis", "next")}
    if not (cells["plan"] or cells["actual"]):
        raise KitError("--plan(예정) 이나 --actual(실제) 중 하나는 준다")
    lines = doc.lines
    s, e = find_part(lines, "섹션 작업 순서")
    rows = table_rows(lines, s, e, "순서")
    if not rows:
        raise KitError("섹션 작업 순서 표가 없음")
    place = [r for r in rows if "(왜 이 순서인가)" in r[2][2]]
    real = [r for r in rows if r not in place]
    n = max((int(r[2][0]) for r in real if r[2][0].isdigit()), default=0) + 1
    new = join_row("", [str(n), sec] + [cells[k] or "—" for k in ("plan", "actual", "basis", "next")])
    if place:
        lines[place[0][0]] = new
        at = place[0][0]
    else:
        at = rows[-1][0] + 1
        lines.insert(at, new)
    doc.save()
    print(f"섹션 작업 순서 {n} · {sec} 덧붙임 · {doc.path.name}:{at + 1}")
    return 0


def cmd_progress(doc, a):
    sign = PROGRESS_SIGN.get(a.result)
    if not sign:
        raise KitError("--result 는 끝남 · 보류 · 해당없음 · 아직")
    commit = one_line("commit", a.commit, 60, cell=True)
    note = one_line("note", a.note, 40, cell=True)
    lines = doc.lines
    s, e = find_part(lines, "진행 기록")
    rows = table_rows(lines, s, e, "번호")
    hit = [r for r in rows if r[2][0] == a.num]
    if not hit:
        raise KitError(f"진행 기록 표에 {a.num} 이 없음 — section-new 로 만든 섹션인지 확인")
    i, p, c = hit[0]
    c = (c + [""] * 5)[:5]
    c[3] = sign + (f" {note}" if note else "")
    if commit:
        c[4] = commit
    lines[i] = join_row(p, c)
    doc.save()
    print(f"진행 기록 {a.num} · {c[3]} · 통과 커밋 {c[4]} · {doc.path.name}:{i + 1}")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="kit handoff", description="hand_off.md 형식 칸 도구(본문 글은 파일에서 직접)")
    ap.add_argument("--doc", default=None, help="hand_off 경로(기본 키트 docs/hand_off.md)")
    sub = ap.add_subparsers(dest="cmd", required=True, metavar="명령")
    sub.add_parser("list", help="섹션별 상태")
    p = sub.add_parser("show", help="섹션 · 진행 · 순서만 출력")
    p.add_argument("what", help="섹션 번호 · 진행 · 순서")
    p = sub.add_parser("section-new", help="섹션 빈 뼈대 + 진행 기록 줄")
    p.add_argument("num")
    p.add_argument("name")
    p.add_argument("--risk", required=True, help="저위험 · 민감")
    p = sub.add_parser("scope-approve", help="수정 범위 🟠 → 🟢")
    p.add_argument("num")
    p.add_argument("--chat", action="store_true", help="대화로 «승인» 을 받음(🚹 줄 검사 생략)")
    p = sub.add_parser("scope-change", help="범위 밖 파일 «🟠 변경 N» 등록")
    p.add_argument("num")
    p.add_argument("path", help="파일")
    p.add_argument("func", help="바꿀 함수")
    p.add_argument("why", help="이유 한 줄")
    p = sub.add_parser("verify-log", help="검증 기록 행 · 상자 색")
    p.add_argument("num")
    p.add_argument("row", help="API-1 꼴")
    p.add_argument("--result", required=True, help="통과 · 실패 · 대기")
    for k, h in (("desc", "요약 표 검증 내용(새 행이면 필수)"), ("file", "대상 파일"), ("func", "대상 함수"),
                 ("expect", "기대"), ("actual", "실제"), ("action", "조치"), ("commit", "통과 커밋(통과일 때 덧붙임)"),
                 ("script", "재현 스크립트 경로(덧붙임)")):
        p.add_argument(f"--{k}", default=None, help=h)
    p = sub.add_parser("order-add", help="섹션 작업 순서 표에 한 줄")
    p.add_argument("section")
    for k, h in (("plan", "예정(계획한 순서 · 이유 한 줄)"), ("actual", "실제(회차 · 한 일 · 커밋)"),
                 ("basis", "결정 근거(항목 번호)"), ("next", "다음")):
        p.add_argument(f"--{k}", default=None, help=h)
    p = sub.add_parser("progress", help="진행 기록 결과 · 통과 커밋")
    p.add_argument("num")
    p.add_argument("--result", required=True, help="끝남 · 보류 · 해당없음 · 아직")
    p.add_argument("--commit", default=None)
    p.add_argument("--note", default=None, help="결과 옆 짧은 말(«3회차 중»)")
    a = ap.parse_args(argv)
    fn = {"list": cmd_list, "show": cmd_show, "section-new": cmd_section_new, "scope-approve": cmd_scope_approve,
          "scope-change": cmd_scope_change, "verify-log": cmd_verify_log, "order-add": cmd_order_add,
          "progress": cmd_progress}[a.cmd]
    with Doc(doc_path(a.doc, "docs/hand_off.md")) as doc:
        return fn(doc, a)


if __name__ == "__main__":
    run(main)
