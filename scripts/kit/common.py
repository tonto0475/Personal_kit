# -*- coding: utf-8 -*-
"""kit 도구 공통 — 키트 폴더 찾기 · 한 줄 인자 검사 · 문서 읽기/쓰기(줄 끝 유지 · 🚹 줄 보존 검사 · 잠금)

도구는 «어디에 · 어떤 형식으로» 만 맡는다. 글 내용은 에이전트가 한 줄로 넘기고, 여러 줄 글은 파일을 직접 고친다.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

# 키트 폴더 = 이 파일의 두 단계 위(scripts/kit/common.py → 키트)
KIT = Path(__file__).resolve().parents[2]


class KitError(Exception):
    """도구가 거부한 입력 · 문서 상태 — 종료코드 2 로 한 줄 출력"""


# 출력 인코딩을 코드에서 고정 — 로캘이 C · cp949 여도 한글이 깨지지 않게
def utf8_out() -> None:
    for st in (sys.stdout, sys.stderr):
        if st is not None and hasattr(st, "reconfigure"):
            st.reconfigure(encoding="utf-8", errors="replace")


# 한 줄 인자 검사 — 여러 줄 글은 도구로 받지 않는다(그 블록은 파일에서 직접)
# name: 인자 이름 / value: 값 / limit: 최대 글자 수 / cell: 표 칸이면 «|» 도 거부
def one_line(name: str, value, limit: int = 200, cell: bool = False):
    if value is None:
        return None
    v = str(value).strip()
    if "\n" in v or "\r" in v:
        raise KitError(f"{name}: 여러 줄 글은 받지 않는다 — 그 블록은 파일에서 직접 고친다")
    if len(v) > limit:
        raise KitError(f"{name}: {len(v)}자 — {limit}자 안의 한 줄로(자세한 글은 파일에서 직접)")
    if cell and "|" in v:
        raise KitError(f"{name}: 표 칸에 «|» 는 못 쓴다")
    return v


# 지금 시각(«MM-DD HH:MM»)
def now_short() -> str:
    return time.strftime("%m-%d %H:%M")


# 문서 경로 — 인자로 주면 그것, 아니면 키트 안 기본 경로
def doc_path(given, default_rel: str) -> Path:
    p = Path(given) if given else KIT / default_rel
    if not p.is_file():
        raise KitError(f"문서 없음: {p}")
    return p


class Doc:
    """줄 단위 문서 — 읽은 줄 끝(\\n · \\r\\n)을 그대로 지켜 쓴다. with 안에서만 잠금"""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.lock = self.path.with_name("." + self.path.name + ".lock")

    def __enter__(self):
        # 잠금 — 다른 도구 호출과 동시에 쓰지 않게(10초 기다려도 안 풀리면 거부)
        t0 = time.time()
        while True:
            try:
                fd = os.open(str(self.lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.close(fd)
                break
            except FileExistsError:
                if time.time() - t0 > 10:
                    raise KitError(f"잠금 파일이 남아 있음: {self.lock} — 다른 kit 호출이 없으면 이 파일 하나만 지운다")
                time.sleep(0.1)
        with open(self.path, encoding="utf-8", newline="") as f:
            self.raw = f.read()
        self.nl = "\r\n" if "\r\n" in self.raw else "\n"
        self.lines = self.raw.split(self.nl)
        return self

    def __exit__(self, *exc):
        try:
            os.remove(str(self.lock))
        except OSError:
            pass
        return False

    # 고친 줄을 쓴다 — 🚹 줄이 하나라도 바뀌거나 사라지면 거부(유저 줄 불가침)
    def save(self) -> None:
        new = self.nl.join(self.lines)
        if new == self.raw:
            return
        old_h = sorted(l for l in self.raw.split(self.nl) if "🚹" in l)
        new_h = sorted(l for l in self.lines if "🚹" in l)
        lost = [l for l in old_h if old_h.count(l) > new_h.count(l)]
        if lost:
            raise KitError(f"🚹 줄이 바뀌게 돼 쓰지 않음: {lost[0][:80]}")
        tmp = self.path.with_name(self.path.name + ".kit_tmp")
        with open(tmp, "w", encoding="utf-8", newline="") as f:
            f.write(new)
        os.replace(str(tmp), str(self.path))


# 표 한 줄 «| a | b |» → 칸 목록(앞의 «> » 인용 기호는 prefix 로 따로)
def split_row(line: str):
    s = line
    prefix = ""
    while s.startswith(">"):
        prefix += ">"
        s = s[1:]
        if s.startswith(" "):
            prefix += " "
            s = s[1:]
    s = s.strip()
    if not (s.startswith("|") and s.endswith("|")):
        return None, None
    return prefix, [c.strip() for c in s[1:-1].split("|")]


# 칸 목록 → 표 한 줄
def join_row(prefix: str, cells) -> str:
    return prefix + "| " + " | ".join(cells) + " |"


# 표의 구분 줄(|---|)인가
def is_sep(cells) -> bool:
    return bool(cells) and all(c and set(c) <= set("-: ") for c in cells)


# 실행 진입 — KitError 는 한 줄 · 종료코드 2
def run(main) -> None:
    utf8_out()
    try:
        sys.exit(main() or 0)
    except KitError as e:
        print(f"거부: {e}", file=sys.stderr)
        sys.exit(2)
