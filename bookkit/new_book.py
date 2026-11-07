# -*- coding: utf-8 -*-
r"""새 «과제 파악 책» 시작 — 양식(bookkit/template)을 bookkit/books/<이름>/ 로 복사하고 문서 이름 · 과제 폴더를 넣는다

    python3 bookkit/new_book.py <이름>                      과제 폴더 = 키트 루트의 task_copy/(지급 자료 복사본 · 원본은 읽기만 — $ontology 1-0 ⓪)
    python3 bookkit/new_book.py <이름> --task <과제 폴더>     다른 폴더를 줄 때(연습 · 시험) — 원본을 위로 올라가며 찾지 않는다
    (윈도우는 python3 대신 py -3)

- 이름 = 영문 · 숫자 · _ · - (출력 html 이름 · 스티커 · 읽기 기록의 열쇠가 된다)
- 만드는 것: 장 파일(구조) · content/(장마다 칸 파일 — 집필이 고친다) · contracts/(분석 계약 json 자리) · work/(분석 스크립트 자리)
- 이미 있는 책은 덮어쓰지 않는다(지우고 다시 하려면 그 폴더를 직접 정리한 뒤)
"""
import argparse
import re
import shutil
import sys
from pathlib import Path

# bookkit 폴더(이 파일이 있는 곳)
KIT = Path(__file__).resolve().parent
# 양식 폴더
TEMPLATE = KIT / "template"
# 책들이 놓이는 폴더
BOOKS = KIT / "books"


def show(p):
    """경로 표시 — 지금 폴더 아래면 상대 경로, 아니면 절대 경로(/ 로)"""
    p = Path(p).resolve()
    try:
        return p.relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return p.as_posix()


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="새 과제 파악 책 시작(양식 복사)")
    ap.add_argument("name", help="책 이름(영문 · 숫자 · _ · -)")
    ap.add_argument("--task", help="과제 폴더(README.md · uploads/ 가 있는 곳) — 없으면 키트 루트의 task_copy/")
    a = ap.parse_args(argv)
    if not re.fullmatch(r"[A-Za-z0-9_\-]+", a.name):
        print(f"이름은 영문 · 숫자 · _ · - 만: «{a.name}»")
        return 2
    dest = BOOKS / a.name
    if dest.exists():
        print(f"이미 있다 — 덮어쓰지 않는다: {show(dest)}")
        return 1
    # 기본값 = 키트 루트의 task_copy/ — 원본(루트)을 위로 올라가며 찾지 않는다
    task = Path(a.task).resolve() if a.task else KIT.parent / "task_copy"
    if not ((task / "README.md").is_file() and (task / "uploads").is_dir()):
        print(f"과제 폴더가 아니다(README.md · uploads/ 없음): {task}")
        if not a.task:
            print("task_copy/ 가 없다 — 지급 자료를 먼저 복사한다($ontology 1-0 ⓪) 또는 --task <과제 폴더>")
        return 2
    shutil.copytree(TEMPLATE, dest, ignore=shutil.ignore_patterns("dist", "__pycache__", "*.pyc"))
    (dest / "contracts").mkdir(exist_ok=True)
    (dest / "work").mkdir(exist_ok=True)
    # 문서 이름 — content/meta.py 칸의 "doc"
    meta = dest / "content" / "meta.py"
    s = meta.read_text(encoding="utf-8")
    old = '        "doc": "",'
    if old not in s:
        print("양식 content/meta.py 에 \"doc\" 칸이 없다 — 양식이 바뀌었나?")
        return 1
    meta.write_text(s.replace(old, f'        "doc": "{a.name}",', 1), encoding="utf-8")
    # 과제 폴더 — content/data.py 의 TASK_DIR(분석 틀 · 계약 검사가 원본을 찾을 때)
    if task:
        data = dest / "content" / "data.py"
        d = data.read_text(encoding="utf-8")
        data.write_text(d.replace("TASK_DIR = None", f"TASK_DIR = {str(task)!r}", 1), encoding="utf-8")
    b = show(dest)
    print(f"새 책: {b}  (문서 이름 {a.name} · 과제 폴더 {task})")
    print("다음 — 병렬이면 카드를 나눠 준다(bookkit/cards/README.md), 혼자면 카드 순서대로:")
    print(f"  분석 A1 · A2 · A3 동시 → {b}/contracts/facts.json · reqs.json · steps.json")
    print(f"  검사   python3 bookkit/contracts/check_contract.py {b}/contracts --task {task.as_posix()}")
    print(f"  집필 W1~W5 동시 → {b}/content/<장>.py 의 글 칸")
    print(f"  합치기 python3 bookkit/engine/build_book.py {b} --strict")
    return 0


if __name__ == "__main__":
    sys.exit(main())
