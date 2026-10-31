#!/usr/bin/env bash
# ======= 작업 패키지 설치 — 지금 폴더 아래 kit/ 에 풀기만 한다 =======
# 대회 IDE 터미널에서: cd <과제 폴더> && curl -sL tonto0475.github.io/k | bash
# 이 파일을 GitHub Pages 저장소(tonto0475.github.io)에 «k» 라는 이름으로 복사해 둔다
# 대회 파일은 건드리지 않는다 — 어느 문서를 어디에 둘지는 Codex 세션과 정한 뒤 직접 옮긴다
set -eu

# ======= 설정 — 환경변수로 바꿀 수 있다(시험할 때 KIT_URL 에 file:// 주소) =======
REPO="tonto0475/Personal_kit"
BRANCH="main"
DEST="${KIT_DIR:-kit}"
URL="${KIT_URL:-https://github.com/$REPO/archive/refs/heads/$BRANCH.tar.gz}"

# ======= 이미 있으면 멈춘다 — 손댄 kit 을 덮어쓰지 않기 위해 =======
if [ -e "$DEST" ]; then
    echo "중단: $PWD/$DEST 가 이미 있음 (덮어쓰지 않음)"
    exit 1
fi

# ======= 임시 폴더에 받아 푼 뒤 한 번에 옮긴다 — 실패해도 반쯤 풀린 폴더가 남지 않게 =======
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

if ! curl -fsSL --connect-timeout 15 "$URL" -o "$TMP/kit.tar.gz"; then
    echo "받기 실패: $URL (네트워크 차단 · 저장소 비공개 · 주소 오타 확인)"
    exit 1
fi

mkdir "$TMP/x"
# 압축판 맨 위 폴더(Personal_kit-main/)를 벗겨 kit/ 바로 아래에 파일이 오게 한다
if ! tar xzf "$TMP/kit.tar.gz" -C "$TMP/x" --strip-components=1; then
    echo "압축 풀기 실패: $URL"
    exit 1
fi

mv "$TMP/x" "$DEST"
echo "설치 위치: $PWD/$DEST · 파일 $(find "$DEST" -type f | wc -l)개"

# ======= 스킬을 Codex 가 읽는 곳(~/.codex/skills)에 복사 — 설치하면 어디서 띄운 codex 든 $스킬 이 바로 보인다 =======
# 같은 이름이 이미 있으면 건너뛴다(손댄 스킬을 덮어쓰지 않기 위해) · 과제 폴더는 건드리지 않는다
SK="${CODEX_HOME:-$HOME/.codex}/skills"
mkdir -p "$SK"
added=""
for d in "$DEST"/.agents/skills/*/; do
    n="$(basename "$d")"
    if [ ! -e "$SK/$n" ]; then
        cp -r "$d" "$SK/$n" && added="$added $n"
    fi
done
echo "스킬 → $SK :${added:- (새로 넣은 것 없음)} · Codex 를 새로 띄우면 \$ 목록에 보임"

# ======= 키트 안 스킬 폴더 이름 바꿈(.agents → skills) =======
# 키트 = 작업 폴더라 MAIN · INSP · 2ND 는 키트에서 뜬다(ReadyStart.txt 명령) — 키트에 .agents/skills 가 남아 있으면
# ~/.codex/skills 와 같은 이름 스킬이 두 곳에 생겨 «$이름» 이 안 불릴 수 있다 → 설치본만 이름을 바꾼다(원본 저장소는 그대로)
mv "$DEST/.agents" "$DEST/skills_src"

echo "다음: 새 터미널 탭에서 codex → \$ready-start  ← 환경 세팅 · git 등록 + MAIN 재시작 · INSP · 2ND 띄우기 명령(키트에서 뜨게)"
