#!/usr/bin/env python3
# 키트 Codex 설정(kit/.codex/config.toml)을 지금 쓰는 설정(~/.codex/config.toml)에 «없는 키만» 넣는다
#   python3 kit/scripts/codex_config/merge.py            비교만(기본) — 키마다 키트 값 · 지금 값 · 같음/다름/없음
#   python3 kit/scripts/codex_config/merge.py --apply    없는 키만 넣음(백업 → 쓰기 → 다시 읽어 검사 → 실패면 되돌림)
#
# 왜 복사가 아니라 넣기인가
#   - 대회는 과제 폴더가 홈(/home/user)이라 «프로젝트 설정 .codex/config.toml» 과 «전역 설정 ~/.codex/config.toml» 이 같은 파일
#   - 그 파일엔 플랫폼 설정(모델 공급자 · 주소 등)이 있다 → 통째로 바꾸면 Codex 가 안 뜬다
# 지키는 것
#   - 이미 있는 키는 값이 달라도 바꾸지 않는다(«다름» 으로 보고만 — 바꿀지는 유저가)
#   - 키트 키의 값만 출력한다. 그 밖의 키는 이름도 값도 출력하지 않는다(비밀값이 섞였을 수 있음)
#   - 넣은 뒤 파일 전체를 다시 읽어 TOML 이 깨졌으면 백업으로 되돌린다
# 종료코드: 0 정상 · 1 넣기 실패(되돌림) · 2 파일 · 형식 오류
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path

try:
    import tomllib                     # 파이썬 3.11 이상
except ModuleNotFoundError:            # 3.10 이하 — tomli 가 있으면
    try:
        import tomli as tomllib
    except ModuleNotFoundError:
        tomllib = None

# 키트 설정 · 지금 설정 경로
KIT = Path(__file__).resolve().parents[2] / ".codex" / "config.toml"
TARGET = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex") / "config.toml"
# 표 머리줄 «[a.b]» (배열 표 [[…]] 는 제외)
HEADER = re.compile(r"^\s*\[([^\[\]]+)\]\s*(#.*)?$")


# 키트 설정 → (표 경로, 키, 값) 목록. 표 안 표는 따로 펼친다
def flatten(d: dict, path: tuple = ()) -> list:
    out = []
    for k, v in d.items():
        if isinstance(v, dict):
            out += flatten(v, path + (k,))
        else:
            out.append((path, k, v))
    return out


# 값 하나를 TOML 글자로
def render(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, str):
        return json.dumps(v, ensure_ascii=False)
    if isinstance(v, list):
        return "[" + ", ".join(render(x) for x in v) + "]"
    raise ValueError(f"넣을 수 없는 값 형식: {type(v).__name__}")


# 지금 설정에서 값 찾기 — 없으면 (False, None)
def lookup(d: dict, path: tuple, key: str):
    for p in path:
        d = d.get(p)
        if not isinstance(d, dict):
            return False, None
    return (key in d), d.get(key)


# 화면용 값(짧게)
def show(v) -> str:
    s = render(v)
    return s if len(s) <= 70 else s[:67] + "..."


# 머리줄 이름 → 줄 번호(마지막 것). 이름의 공백 · 따옴표는 걷어 낸다
def headers(lines: list) -> dict:
    out = {}
    for i, line in enumerate(lines):
        m = HEADER.match(line)
        if m:
            out[".".join(x.strip().strip('"').strip("'") for x in m.group(1).split("."))] = i
    return out


# 없는 키를 글자로 넣는다 — 최상위 키는 첫 머리줄 앞, 있는 표는 그 머리줄 바로 아래, 없는 표는 끝에 새로
def insert(text: str, missing: list) -> str:
    lines = text.splitlines()
    top = [f"{k} = {render(v)}" for p, k, v in missing if not p]
    by_table = {}
    for p, k, v in missing:
        if p:
            by_table.setdefault(".".join(p), []).append(f"{k} = {render(v)}")
    hs = headers(lines)
    # 있는 표 — 아래쪽부터 넣어야 앞쪽 줄 번호가 안 밀린다
    for name in sorted((n for n in by_table if n in hs), key=lambda n: hs[n], reverse=True):
        at = hs[name] + 1
        lines[at:at] = ["# ── 키트에서 넣음(merge.py) ──"] + by_table[name]
    # 없는 표 — 끝에
    for name in [n for n in by_table if n not in hs]:
        lines += ["", f"[{name}]", "# ── 키트에서 넣음(merge.py) ──"] + by_table[name]
    # 최상위 키 — 첫 머리줄 앞(머리줄이 없으면 맨 끝). 위에서 표를 붙였으니 머리줄 위치를 다시 잰다
    if top:
        hs = headers(lines)
        first = min(hs.values()) if hs else len(lines)
        lines[first:first] = ["# ── 키트에서 넣음(merge.py) ──"] + top + [""]
    return "\n".join(lines) + "\n"


def main() -> int:
    for s in (sys.stdout, sys.stderr):
        s.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="키트 Codex 설정을 지금 설정에 없는 키만 넣기")
    ap.add_argument("--apply", action="store_true", help="없는 키를 실제로 넣음(기본은 비교만)")
    ap.add_argument("--kit", type=Path, default=KIT)
    ap.add_argument("--target", type=Path, default=TARGET)
    a = ap.parse_args()
    if tomllib is None:
        print("TOML 읽기 도구 없음 — 파이썬 3.11 이상 필요", file=sys.stderr)
        return 2
    if not a.kit.is_file():
        print(f"키트 설정 없음: {a.kit}", file=sys.stderr)
        return 2
    kit = tomllib.loads(a.kit.read_text(encoding="utf-8"))
    text = a.target.read_text(encoding="utf-8") if a.target.is_file() else ""
    try:
        cur = tomllib.loads(text)
    except Exception as e:
        print(f"지금 설정이 TOML 로 안 읽힘 — 손대지 않음: {e}", file=sys.stderr)
        return 2
    print(f"키트: {a.kit}\n지금: {a.target}{'' if text else ' (없음 — 새로 만듦)'}")
    print(f"{'키':<34} {'판정':<4}  키트 값  →  지금 값")
    missing = []
    for path, key, val in flatten(kit):
        name = ".".join(path + (key,))
        has, now = lookup(cur, path, key)
        if not has:
            verdict = "없음"
            missing.append((path, key, val))
        elif now == val:
            verdict = "같음"
        else:
            verdict = "다름"
        print(f"{name:<34} {verdict:<4}  {show(val)}  →  {show(now) if has else '-'}")
    print(f"요약: 넣을 것 {len(missing)}개 · 다름(그대로 둠) "
          f"{sum(1 for p, k, v in flatten(kit) if lookup(cur, p, k)[0] and lookup(cur, p, k)[1] != v)}개")
    if not a.apply:
        print("비교만 함 — 넣으려면 --apply")
        return 0
    if not missing:
        print("넣을 것 없음")
        return 0
    backup = None
    if a.target.is_file():
        backup = a.target.with_name(a.target.name + time.strftime(".bak_kit_%Y%m%d_%H%M%S"))
        shutil.copy2(a.target, backup)
    a.target.parent.mkdir(parents=True, exist_ok=True)
    new = insert(text, missing)
    a.target.write_text(new, encoding="utf-8")
    # 다시 읽어 검사 — 깨졌거나 넣은 값이 안 보이면 되돌림
    try:
        after = tomllib.loads(new)
        bad = [".".join(p + (k,)) for p, k, v in missing if lookup(after, p, k) != (True, v)]
    except Exception as e:
        bad = [f"TOML 깨짐: {e}"]
    if bad:
        if backup:
            shutil.copy2(backup, a.target)
        else:
            a.target.unlink()
        print(f"넣기 실패 — 되돌림: {bad}", file=sys.stderr)
        return 1
    print(f"넣음 {len(missing)}개 · 백업 {backup or '(원래 파일 없음)'} · Codex 를 새로 띄우면 적용")
    return 0


if __name__ == "__main__":
    sys.exit(main())
