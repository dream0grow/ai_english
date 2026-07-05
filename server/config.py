"""환경 설정 — .env 파일과 환경변수에서 로드."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

PORT = int(os.getenv("PORT", "8100"))

WHISPER_MODEL = os.getenv("WHISPER_MODEL", "base")

TTS_ENGINE = os.getenv("TTS_ENGINE", "kokoro").lower()  # kokoro | none
TTS_VOICE = os.getenv("TTS_VOICE", "af_heart")

MOCK_LLM = os.getenv("MOCK_LLM", "0") == "1"
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "sonnet") or None

# 호출어 — "Hey <이름>!" 으로 대화 시작 (핸즈프리 모드)
WAKE_NAME = os.getenv("WAKE_NAME", "emma").strip().lower()

DB_PATH = str(ROOT / "data" / "ai_english.db")
WEB_DIR = str(ROOT / "web")
