#!/usr/bin/env bash
# 실행: bash run.sh — 0.0.0.0 · 포트 3000(바꾸려면 PORT=8080 bash run.sh) · reload 끔
set -e
cd "$(dirname "$0")"

# 패키지 설치(처음 한 번)
# python3 -m pip install -r requirements.txt

# 서버 실행 — 키트 안 .venv 가 있으면 그 파이썬(대회 기계는 PEP668 이라 venv 에 설치), 없으면 시스템 python3
PY=python3
if [ -x .venv/bin/python ]; then PY=.venv/bin/python; fi
"$PY" -m src.ui.app
