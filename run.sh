#!/usr/bin/env bash
# AI English 서버 실행 — 처음이면 가상환경을 만들고 의존성을 설치한다.
set -e
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
  echo "▸ 가상환경 생성 및 의존성 설치 (최초 1회, 몇 분 걸립니다)"
  python3 -m venv .venv
  ./.venv/bin/pip install --upgrade pip
  ./.venv/bin/pip install -r requirements.txt
fi

if [ ! -f .env ]; then
  echo "⚠ .env 파일이 없습니다. cp .env.example .env 후 토큰을 채워주세요."
  echo "  (테스트만 하려면 .env에 MOCK_LLM=1 설정)"
  exit 1
fi

PORT=$(grep -E '^PORT=' .env | cut -d= -f2)
PORT=${PORT:-8100}
echo "▸ 서버 시작: http://0.0.0.0:${PORT}  (같은 공유기의 폰에서는 http://<이 컴퓨터 IP>:${PORT})"
exec ./.venv/bin/uvicorn server.main:app --host 0.0.0.0 --port "${PORT}"
