# ======= 앱 컨테이너 양식 — 키트 부품(lib/deploy) · 과제 저장소 루트(<루트>)에 .dockerignore 와 같이 복사해 쓴다 =======
# 빌드: docker build -t app .                                   (<루트> 에서 · 작업 폴더가 kit/ 가 아니면 --build-arg APP_DIR=폴더)
# 실행: docker run --rm -p 3000:3000 -v app-data:/app/data app   (포트 · 볼륨은 아래 ENV 와 같게)
# 시험: docker run --rm app python -m pytest -q tests
# 로컬과 같은 시작 명령(run.sh) · 같은 포트 · 0.0.0.0 — 바꿀 곳은 APP_DIR · ENV · EXPOSE 셋뿐(확인은 $ready-end R8)
FROM python:3.11-slim

# ======= 파이썬 동작 — 로그가 docker logs 에 바로 보이고 이미지에 캐시 · .pyc 가 남지 않게 =======
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PYTHONUTF8=1 LANG=C.UTF-8 \
    PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1

# ======= 작업 폴더 — 키트 = 작업 폴더라 앱 · run.sh · requirements 가 <루트>/kit 에 있다 =======
ARG APP_DIR=kit
WORKDIR /app

# ======= 라이브러리 먼저 — 코드만 바뀌면 설치 층을 다시 쓰지 않아 다시 빌드가 빠르다 =======
COPY ${APP_DIR}/requirements.txt ./
RUN pip install -r requirements.txt

# ======= 앱 — 빼는 것(.env · .venv · 키트 도구 · DB)은 .dockerignore 가 정한다 =======
COPY ${APP_DIR}/ ./

# ======= 설정 — 실행할 때 -e 이름=값 으로 바꾼다 · 앱이 읽는 이름으로 고치고 안 쓰는 줄은 지운다 =======
# DB 는 볼륨 폴더(/app/data) 안 — 컨테이너를 지워도 남고, 켜질 때 표가 없으면 앱이 만든다
ENV HOST=0.0.0.0 PORT=3000 DB_PATH=/app/data/app.db
EXPOSE 3000

# ======= 켜졌나 — /health 가 200 이면 docker ps 에 healthy · 앱에 /health 가 없으면 이 두 줄을 지운다 =======
HEALTHCHECK --interval=10s --timeout=3s --start-period=30s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('PORT', '3000') + '/health', timeout=2)" || exit 1

# ======= 시작 — 로컬과 같은 run.sh(run.sh 가 exec 로 파이썬을 띄워 docker stop 신호를 앱이 직접 받는다) =======
CMD ["bash", "run.sh"]
