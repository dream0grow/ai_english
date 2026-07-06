@echo off
chcp 65001 >nul
cd /d %~dp0
echo ============================================
echo   AI English - Windows 실행
echo ============================================

where python >nul 2>nul
if errorlevel 1 (
  echo [오류] Python이 없습니다. https://python.org 에서 설치하세요.
  echo        설치할 때 "Add python.exe to PATH" 반드시 체크!
  pause
  exit /b 1
)

if not exist .venv (
  echo [최초 1회] 가상환경 생성 + 의존성 설치 중... 몇 분 걸립니다.
  python -m venv .venv
  .venv\Scripts\python -m pip install --upgrade pip
  .venv\Scripts\pip install -r requirements.txt
  if errorlevel 1 (
    echo [오류] 설치 실패. 위의 오류 메시지를 Claude에게 보여주세요.
    pause
    exit /b 1
  )
)

if not exist .env (
  echo [안내] .env 파일이 없어 예시를 복사합니다.
  copy .env.example .env >nul
  echo        메모장이 열리면 CLAUDE_CODE_OAUTH_TOKEN= 뒤에 토큰을 붙여넣고 저장하세요.
  echo        (토큰 없이 체험만 하려면 MOCK_LLM=1 로 바꿔도 됩니다)
  notepad .env
)

echo.
echo 서버를 시작합니다. 브라우저에서  http://localhost:8100  을 여세요.
echo (최초 실행은 음성 모델 다운로드로 5~15분 걸릴 수 있습니다. 중지: Ctrl+C)
echo.
.venv\Scripts\python -m uvicorn server.main:app --host 0.0.0.0 --port 8100
pause
