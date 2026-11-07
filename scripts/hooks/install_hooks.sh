#!/usr/bin/env bash
# 압축 직후 참조 목록 훅 넣기 — 유저 터미널에서 한 번: bash scripts/hooks/install_hooks.sh (키트가 kit/ 안이면 bash kit/scripts/hooks/install_hooks.sh)
#   ~/.codex/hooks.json 이 없으면 만든다 · 있으면 덮어쓰지 않고 넣을 내용만 보여 준다
#   훅 = SessionStart(compact) 하나 → 압축 직후 «인계 칸 · 내 역할 스킬의 어느 절» 경로 목록만 모델에 넣음(본문 없음 · 스크립트: hand-on/compact_hook.py)
#   왜 유저 터미널: Codex 샌드박스에서는 .codex 폴더가 읽기 전용이다
#   다음: codex 를 새로 띄우고 /hooks 에서 훅을 «신뢰» → 신뢰 기록이 ~/.codex/config.toml [hooks.state] 에 해시로 남는다
set -eu
HERE="$(cd "$(dirname "$0")" && pwd)"
KIT="$(cd "$HERE/../.." && pwd)"
CODEX="${CODEX_HOME:-$HOME/.codex}"
# 훅 스크립트 — install.sh 가 복사한 곳 먼저, 없으면 키트 안
HOOK="$CODEX/skills/hand-on/compact_hook.py"
[ -f "$HOOK" ] || HOOK="$KIT/.agents/skills/hand-on/compact_hook.py"
[ -f "$HOOK" ] || HOOK="$KIT/skills_src/skills/hand-on/compact_hook.py"
[ -f "$HOOK" ] || { echo "중단: compact_hook.py 없음 ($HOOK)"; exit 1; }

JSON=$(cat <<EOF
{
  "hooks": {
    "SessionStart": [
      { "matcher": "^compact$",
        "hooks": [ { "type": "command", "command": "python3 '$HOOK'", "timeout": 20 } ] }
    ]
  }
}
EOF
)

mkdir -p "$CODEX"
if [ -e "$CODEX/hooks.json" ]; then
    echo "이미 있음: $CODEX/hooks.json — 덮어쓰지 않음. 아래 SessionStart 덩이를 손으로 합친다(옛 PreCompact 덩이가 있으면 지운다):"
    echo "$JSON"
    exit 1
fi
printf '%s\n' "$JSON" > "$CODEX/hooks.json"
python3 -c "import json,sys; json.load(open(sys.argv[1]))" "$CODEX/hooks.json"
echo "훅 넣음: $CODEX/hooks.json (스크립트 $HOOK)"
echo "다음: codex 를 새로 띄우고 /hooks 에서 SessionStart 훅 하나를 신뢰 — 신뢰 전에는 실행 안 됨"
