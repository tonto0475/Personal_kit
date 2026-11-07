#!/usr/bin/env python3
"""CSV 데이터 세기 — 데이터 지도(docs/ONTOLOGY.md) 초안의 재료. 표준 라이브러리만(Python 3.8+).

    python3 scripts/ontology/profile.py 파일.csv [파일2.csv ...] [--hide 열,열] [--show 열,열] [--max-rows N]

- 열의 뜻은 모른다. 세기만 한다: 값 종류 · 빈칸 · 모양 · 숫자 범위 · 날짜 범위 · 구별 기준 후보 · 겹침
- 이름 · 연락처처럼 보이는 열은 값을 자동으로 숨긴다(--show 로 풀기 · --hide 로 더 숨기기)
- 못 읽으면 조용히 틀리지 않는다: «못 읽음 — 이유» 를 찍고 종료코드 2
"""
import argparse
import csv
import io
import itertools
import re
import sys
from collections import Counter
from datetime import datetime

ENCODINGS = ("utf-8-sig", "utf-8", "cp949")
BLANK_LIKE = {"na", "n/a", "null", "none", "nan", "-", "#n/a"}
PERSONAL_HINTS = ("name", "inspector", "operator", "worker", "user", "email", "mail", "phone", "tel",
                  "owner", "person", "이름", "성명", "작업자", "검사자", "담당", "연락처", "전화", "메일", "사번")
DATE_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d", "%Y/%m/%d %H:%M:%S",
                "%Y/%m/%d %H:%M", "%Y/%m/%d", "%Y.%m.%d %H:%M:%S", "%Y.%m.%d", "%Y%m%d%H%M%S")
SHOW_ALL_KINDS = 12      # 값 종류가 이 이하이면 전부 보인다(경우 목록 후보)
MAX_BAD_RATIO = 0.05     # 열 수가 다른 줄이 이 비율을 넘으면 못 읽음
NEAR_KEY_RATIO = 0.8     # 짝으로 묶었을 때 줄의 80% 이상이 구별되면 «거의 구별 — 중복 의심» 후보
FMT_WORDS = (("%Y", "YYYY"), ("%m", "MM"), ("%d", "DD"), ("%H", "hh"), ("%M", "mm"), ("%S", "ss"))


class CannotRead(Exception):
    pass


def read_table(path, max_rows):
    raw = open(path, "rb").read()
    if not raw.strip():
        raise CannotRead("빈 파일")
    if raw[:2] in (b"PK", b"\xd0\xcf"):
        raise CannotRead("엑셀 파일로 보임 — CSV 로 저장하거나 직접 읽는 코드를 짤 것")
    if raw.lstrip()[:1] in (b"{", b"["):
        raise CannotRead("JSON 으로 보임 — 이 도구 대상이 아님")
    text, enc = None, None
    for enc in ENCODINGS:
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise CannotRead("인코딩 판별 실패(utf-8 · cp949 둘 다 아님)")
    sample = text[:20000]
    try:
        delim = csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
    except csv.Error:
        delim = ","
    rows = list(csv.reader(io.StringIO(text), delimiter=delim))
    numbered = [(i + 1, r) for i, r in enumerate(rows) if any(c.strip() for c in r)]
    empty_lines = len(rows) - len(numbered)
    if len(numbered) < 2:
        raise CannotRead("머리줄 말고 데이터 줄이 없음")
    width = Counter(len(r) for _, r in numbered).most_common(1)[0][0]
    if width < 2:
        raise CannotRead("열이 1개뿐 — 구분자 판별 실패로 보임(구분자: %r)" % delim)
    skipped = 0
    while numbered and len(numbered[0][1]) != width:
        numbered.pop(0)
        skipped += 1
    head_line, header = numbered[0]
    header = [h.strip() for h in header]
    if any(not h for h in header):
        raise CannotRead("머리줄 판별 실패 — 이름이 빈 열이 있음(%d번째 줄)" % head_line)
    if len(set(header)) != len(header):
        raise CannotRead("머리줄 판별 실패 — 같은 이름의 열이 있음(%d번째 줄)" % head_line)
    body = numbered[1:]
    bad = [n for n, r in body if len(r) != width]
    if body and len(bad) / len(body) > MAX_BAD_RATIO:
        raise CannotRead("열 수가 다른 줄이 %d/%d 줄 — 머리줄이 두 줄이거나 구분자가 섞인 것으로 보임"
                         % (len(bad), len(body)))
    body = [(n, [c.strip() for c in r]) for n, r in body if len(r) == width]
    sampled = len(body) > max_rows
    body = body[:max_rows]
    info = {"encoding": enc, "delim": delim, "head_line": head_line, "skipped": skipped,
            "empty_lines": empty_lines, "bad_lines": bad, "sampled": sampled}
    return header, body, info


def parse_date(v):
    for f in DATE_FORMATS:
        try:
            return datetime.strptime(v, f), f, False
        except ValueError:
            pass
    try:
        d = datetime.fromisoformat(v.replace("Z", "+00:00"))
        return d, "ISO", d.tzinfo is not None
    except ValueError:
        return None, None, False


def shape(v):
    s = re.sub(r"[0-9]", "9", v)
    s = re.sub(r"[A-Za-z]", "A", s)
    return re.sub(r"[가-힣]", "가", s)


def is_number(v):
    try:
        float(v.replace(",", ""))
        return True
    except ValueError:
        return False


def describe_column(name, values, hidden):
    out = []
    blanks = sum(1 for v in values if v == "")
    blank_like = Counter(v for v in values if v.lower() in BLANK_LIKE)
    vals = [v for v in values if v != "" and v.lower() not in BLANK_LIKE]
    kinds = Counter(vals)
    kind = "글자"
    dates = [parse_date(v) for v in vals] if vals else []
    ok_dates = [d for d in dates if d[0] is not None]
    if vals and all(is_number(v) for v in vals):
        kind = "숫자(정수)" if all(re.fullmatch(r"-?\d+", v.replace(",", "")) for v in vals) else "숫자(소수)"
    elif vals and len(ok_dates) >= 0.95 * len(vals):
        kind = "날짜 · 시각"
    out.append("### %s — %s" % (name, kind))
    line = "- 빈칸 %d · 값 종류 %d" % (blanks, len(kinds))
    if blank_like:
        line += " · 빈칸 비슷한 글자 %s" % ", ".join("«%s» %d" % kv for kv in blank_like.items())
    out.append(line)
    if kind.startswith("숫자") and vals:
        nums = [float(v.replace(",", "")) for v in vals]
        out.append("- 범위 %s ~ %s · 0 인 값 %d · 음수 %d" % (fmt(min(nums)), fmt(max(nums)),
                                                        sum(1 for x in nums if x == 0),
                                                        sum(1 for x in nums if x < 0)))
    if kind == "날짜 · 시각":
        fmts = Counter(d[1] for d in ok_dates)
        tz = sum(1 for d in ok_dates if d[2])
        seq = [d[0] for d in ok_dates]
        try:
            order = ("오름차순" if seq == sorted(seq) else "내림차순" if seq == sorted(seq, reverse=True)
                     else "섞임")
            rng = "%s ~ %s" % (min(seq), max(seq))
        except TypeError:
            order, rng = "판별 불가(시간대 표시가 있는 값과 없는 값이 섞임)", "판별 불가"
        out.append("- 형식 %s · 예: %s · 시간대 표시 %s" % (
            " / ".join("%s %d개" % (readable(f), k) for f, k in fmts.items()), vals[0],
            "있음 %d개" % tz if tz else "없음"))
        out.append("- 범위 %s · 파일 안 순서: %s · 날짜로 못 읽은 값 %d" % (rng, order, len(vals) - len(ok_dates)))
    if kind == "글자" and vals:
        shapes = Counter(shape(v) for v in vals)
        if len(shapes) <= 5:
            out.append("- 모양 %d가지: %s" % (len(shapes), ", ".join("%s %d개" % kv for kv in shapes.most_common())))
        else:
            out.append("- 모양 %d가지 — 많이 나온 것: %s" % (
                len(shapes), ", ".join("%s %d개" % kv for kv in shapes.most_common(3))))
    if hidden:
        out.append("- 값: 표시 안 함(숨긴 열)")
    elif not kind.startswith("숫자(소수)") and kind != "날짜 · 시각":
        if len(kinds) <= SHOW_ALL_KINDS:
            out.append("- 값 전부: %s" % ", ".join("%s %d" % kv for kv in kinds.most_common()))
        else:
            out.append("- 많이 나온 값: %s · 외 %d종" % (
                ", ".join("%s %d" % kv for kv in kinds.most_common(5)), len(kinds) - 5))
    return out, kind


def readable(f):
    for a, b in FMT_WORDS:
        f = f.replace(a, b)
    return f


def fmt(x):
    return str(int(x)) if x == int(x) else "%g" % x


def key_report(header, body, kinds, hidden):
    out = ["## 구별 기준 후보 — 무엇이 같으면 같은 줄인가"]
    n = len(body)
    cols = list(range(len(header)))
    single, single_date = [], []
    for c in cols:
        vals = [r[c] for _, r in body]
        if "" not in vals and len(set(vals)) == n:
            (single_date if kinds[c] == "날짜 · 시각" else single).append(header[c])
    out.append("- 혼자서 구별되는 열: %s" % (", ".join(single) or "없음"))
    if single_date:
        out.append("- 혼자서 구별되는 날짜 · 시각 열: %s — 우연히 안 겹친 것일 수 있음" % ", ".join(single_date))
    usable = [c for c in cols if kinds[c] not in ("숫자(소수)", "날짜 · 시각") and header[c] not in hidden
              and header[c] not in single and header[c] not in single_date]
    if len(usable) > 30:
        out.append("- 둘을 합친 구별 기준 찾기는 건너뜀 — 대상 열이 %d개(30개 초과)" % len(usable))
        return out
    exact, near = [], []
    for a, b in itertools.combinations(usable, 2):
        groups = {}
        for line, r in body:
            groups.setdefault((r[a], r[b]), []).append((line, r))
        if any("" in k for k in groups):
            continue
        overlap = n - len(groups)
        if overlap == 0:
            exact.append((a, b))
        elif len(groups) >= NEAR_KEY_RATIO * n:
            near.append((overlap, a, b, [g for g in groups.values() if len(g) > 1]))
    out.append("- 둘을 합쳐야 구별되는 짝: %s" % (", ".join("%s + %s" % (header[a], header[b]) for a, b in exact)
                                         or "없음"))
    if not near:
        out.append("- 거의 구별되지만 겹치는 줄이 있는 짝(중복 의심): 없음")
    for overlap, a, b, dup_groups in sorted(near, key=lambda x: x[0])[:5]:
        out.append("- 거의 구별되지만 겹침 — %s + %s : 겹치는 묶음 %d개(%d줄)" % (
            header[a], header[b], len(dup_groups), sum(len(g) for g in dup_groups)))
        show = [c for c in cols if c not in (a, b) and header[c] not in hidden]
        for g in dup_groups[:4]:
            parts = ["%d번째 줄(%s)" % (line, ", ".join(r[c] or "빈칸" for c in show)) for line, r in g]
            out.append("\t- %s · %s → %s" % (g[0][1][a], g[0][1][b], " / ".join(parts)))
        if len(dup_groups) > 4:
            out.append("\t- … 외 %d묶음" % (len(dup_groups) - 4))
    out.append("- 날짜 · 시각 열과 소수 숫자 열은 짝 찾기에서 뺌(붙이면 거의 다 구별돼 보여서)")
    return out


def profile(path, hide, show, max_rows):
    header, body, info = read_table(path, max_rows)
    hidden = set(h for h in header if h in hide or (any(k in h.lower() for k in PERSONAL_HINTS) and h not in show))
    out = ["# 데이터 세기 — %s" % path]
    out.append("- 읽기: 인코딩 %s · 구분자 «%s» · 머리줄 %d번째 줄 · 데이터 %d줄 · 열 %d개%s" % (
        info["encoding"], "탭" if info["delim"] == "\t" else info["delim"], info["head_line"], len(body),
        len(header), " · 🔴 앞부분 %d줄만 센 표본" % len(body) if info["sampled"] else ""))
    if info["skipped"]:
        out.append("- 머리줄 앞 %d줄을 건너뜀(설명 줄로 보임)" % info["skipped"])
    if info["bad_lines"]:
        out.append("- 🔴 열 수가 다른 줄 %d개 — 세기에서 뺌: %s" % (
            len(info["bad_lines"]), ", ".join("%d번째" % x for x in info["bad_lines"][:5])))
    if info["empty_lines"]:
        out.append("- 빈 줄 %d개" % info["empty_lines"])
    if hidden:
        out.append("- 값을 숨긴 열: %s — 이름 · 연락처처럼 보이거나 --hide 로 지정. 보려면 --show 열이름"
                   % ", ".join(sorted(hidden)))
    whole = Counter(tuple(r) for _, r in body)
    out.append("- 완전히 같은 줄: %d묶음" % sum(1 for v in whole.values() if v > 1))
    out.append("")
    out.append("## 열마다")
    kinds = []
    for c, name in enumerate(header):
        lines, kind = describe_column(name, [r[c] for _, r in body], name in hidden)
        out.extend(lines)
        kinds.append(kind)
    out.append("")
    out.extend(key_report(header, body, kinds, hidden))
    return "\n".join(out)


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="CSV 데이터 세기 — 데이터 지도 초안용")
    ap.add_argument("files", nargs="+")
    ap.add_argument("--hide", default="", help="값을 숨길 열(쉼표로)")
    ap.add_argument("--show", default="", help="자동 숨김을 풀 열(쉼표로)")
    ap.add_argument("--max-rows", type=int, default=200000)
    a = ap.parse_args(argv)
    hide = set(x.strip() for x in a.hide.split(",") if x.strip())
    show = set(x.strip() for x in a.show.split(",") if x.strip())
    code = 0
    for f in a.files:
        try:
            print(profile(f, hide, show, a.max_rows))
        except CannotRead as e:
            print("# 데이터 세기 — %s\n- 🔴 못 읽음 — %s" % (f, e))
            code = 2
        except OSError as e:
            print("# 데이터 세기 — %s\n- 🔴 못 읽음 — 파일 열기 실패: %s" % (f, e))
            code = 2
        print()
    return code


if __name__ == "__main__":
    sys.exit(main())
