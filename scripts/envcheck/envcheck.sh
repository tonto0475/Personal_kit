#!/usr/bin/env bash
# ======= envcheck 0단계 — 파이썬이 없어도 도는 부분 =======
# 실행: bash scripts/envcheck/envcheck.sh [--no-install] [--where 이름]
# python3 가 있고 3.8 이상이면 같은 폴더의 envcheck.py 로 넘긴다. 없으면 여기서 결과를 내고 끝낸다
HERE="$(cd "$(dirname "$0")" && pwd)"

missing=""
for b in git node curl; do
    command -v "$b" >/dev/null 2>&1 || missing="$missing $b"
done

if ! command -v python3 >/dev/null 2>&1; then
    echo "envcheck · 0단계"
    echo "A0 NOPY python3 없음 — 키트 도구(설문 · devview · envcheck.py) 전부 못 씀"
    [ -n "$missing" ] && echo "A1 NOBIN$missing"
    echo "요약: A0"
    exit 1
fi

if ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)'; then
    echo "envcheck · 0단계"
    echo "A0 PYOLD $(python3 -V 2>&1) — 키트 도구는 3.8 이상"
    [ -n "$missing" ] && echo "A1 NOBIN$missing"
    echo "요약: A0"
    exit 1
fi

if [ ! -f "$HERE/envcheck.py" ]; then
    echo "envcheck.py 없음: $HERE (두 파일을 같은 폴더에 둔다)"
    exit 1
fi

exec python3 "$HERE/envcheck.py" "$@"
