#!/usr/bin/env python3
# ======= 과제 파일 가볍게 훑기 — 2ND «파악시작» 용 =======
# 과제로 받은 원래 파일(키트 · 도구 폴더 · 숨김 폴더 제외)의 목록 · 크기 · 줄 수와,
# CSV 마다 헤더 + 맨 위 5행을 마크다운 표로 출력한다(무겁게 분석하지 않는다 — 처음 몇 줄만 읽음)
#   python3 ~/.codex/skills/2nd/task_peek.py [과제 루트]        기본 = git 루트(없으면 지금 폴더)
#   python3 ~/.codex/skills/2nd/task_peek.py <루트> --rows 5 --width 24
# 출력은 채팅에 그대로 붙일 수 있는 마크다운 · 표준 라이브러리만
import argparse
import csv
import io
import subprocess
import sys
from pathlib import Path

# 콘솔 · 파이프로 한글을 내보내므로 출력 인코딩을 코드에서 고정
sys.stdout.reconfigure(encoding="utf-8")

# 훑지 않는 폴더 — 키트(작업 폴더) · 도구 · 가상환경 · 숨김
SKIP_DIRS = {"kit", "node_modules", ".venv", "venv", "__pycache__", "task_copy"}
# 한 파일에서 읽는 최대 바이트(줄 수 세기용 — 큰 파일도 이만큼만 세고 «약» 으로 표시)
COUNT_LIMIT = 64 * 1024 * 1024


# 과제 루트 — 인자가 없으면 git 루트, 그것도 없으면 지금 폴더
def find_root(given):
    if given:
        return Path(given).resolve()
    try:
        out = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True)
        return Path(out.stdout.strip()).resolve()
    except (OSError, subprocess.CalledProcessError):
        return Path.cwd().resolve()


# 훑을 파일 목록 — 숨김(.으로 시작) · SKIP_DIRS 아래는 뺀다
def task_files(root):
    found = []
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root)
        if any(part.startswith(".") or part in SKIP_DIRS for part in rel.parts[:-1]) or rel.name.startswith("."):
            continue
        if p.is_file():
            found.append(p)
    return found


# 사람이 읽는 크기
def human(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f}{unit}" if unit == "B" else f"{n:.1f}{unit}"
        n /= 1024


# 줄 수 — 앞 COUNT_LIMIT 바이트만 센다(넘으면 비율로 추정해 «약»)
def line_count(p):
    size = p.stat().st_size
    with open(p, "rb") as fh:
        data = fh.read(COUNT_LIMIT)
    n = data.count(b"\n") + (1 if data and not data.endswith(b"\n") else 0)
    if size > COUNT_LIMIT and data:
        return f"약 {int(n * size / len(data)):,}"
    return f"{n:,}"


# 앞부분 글 — utf-8(BOM 포함) → cp949 순서로 풀어 본다
def head_text(p, nbytes=256 * 1024):
    with open(p, "rb") as fh:
        raw = fh.read(nbytes)
    for enc in ("utf-8-sig", "cp949"):
        try:
            return raw.decode(enc), enc
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace"), "utf-8(깨짐 대체)"


# 표 칸 — 줄바꿈 · | 를 지우고 길이를 자른다
def cell(v, width):
    v = str(v).replace("\n", " ").replace("|", "/").strip()
    return v if len(v) <= width else v[: width - 1] + "…"


# CSV 하나 → 헤더 + 맨 위 rows 행 마크다운 표
def csv_table(p, rows, width):
    text, enc = head_text(p)
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    reader = csv.reader(io.StringIO(text), dialect)
    lines = []
    for i, r in enumerate(reader):
        lines.append(r)
        if i >= rows:
            break
    if not lines:
        return f"(빈 파일 · {enc})"
    header, body = lines[0], lines[1:]
    ncol = max(len(header), *(len(r) for r in body)) if body else len(header)
    header = header + [""] * (ncol - len(header))
    out = [f"열 {ncol}개 · 인코딩 {enc} · 구분자 {repr(dialect.delimiter)}", "",
           "| " + " | ".join(cell(h, width) or f"(열{i + 1})" for i, h in enumerate(header)) + " |",
           "|" + "---|" * ncol]
    for r in body:
        r = r + [""] * (ncol - len(r))
        out.append("| " + " | ".join(cell(v, width) for v in r[:ncol]) + " |")
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description="과제 파일 가볍게 훑기(목록 · CSV 헤더 + 맨 위 행)")
    ap.add_argument("root", nargs="?", default=None, help="과제 루트(기본 git 루트)")
    ap.add_argument("--rows", type=int, default=5, help="CSV 마다 보일 행 수(헤더 제외)")
    ap.add_argument("--width", type=int, default=24, help="표 칸 최대 글자 수")
    a = ap.parse_args(argv)
    root = find_root(a.root)
    files = task_files(root)
    print(f"## 과제 파일 — {root}  (키트 · 숨김 · task_copy 제외 · {len(files)}개)\n")
    print("| 파일 | 크기 | 줄 수 |\n|---|---|---|")
    for p in files:
        print(f"| {p.relative_to(root).as_posix()} | {human(p.stat().st_size)} | {line_count(p)} |")
    csvs = [p for p in files if p.suffix.lower() in (".csv", ".tsv")]
    for p in csvs:
        print(f"\n### {p.relative_to(root).as_posix()}\n")
        print(csv_table(p, a.rows, a.width))
    if not csvs:
        print("\n(CSV 없음)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
