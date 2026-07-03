"""AI English 집 서버 — FastAPI 앱.

파이프라인: 브라우저 녹음 → STT(faster-whisper) → Claude(구독) → TTS(Kokoro) → 재생
실행:  ./run.sh   (또는  uvicorn server.main:app --host 0.0.0.0 --port 8100)
"""
import asyncio
import base64
import logging
import time

from fastapi import FastAPI, File, UploadFile
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from . import config, db, stt, tts
from .llm import create_engine

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
log = logging.getLogger("ai_english")

app = FastAPI(title="AI English")

_engine = create_engine()
_lock = asyncio.Lock()          # 저사양 CPU: 한 번에 한 턴만 처리
_session_id: int | None = None


def _session() -> int:
    global _session_id
    if _session_id is None:
        _session_id = db.start_session()
    return _session_id


@app.get("/api/health")
async def health():
    return {
        "ok": True,
        "mock_llm": config.MOCK_LLM,
        "whisper_model": config.WHISPER_MODEL,
        "tts_engine": config.TTS_ENGINE,
    }


@app.post("/api/chat")
async def chat(audio: UploadFile = File(...)):
    """오디오 한 턴 처리: STT → 대화 엔진 → TTS."""
    async with _lock:
        t0 = time.time()
        audio_bytes = await audio.read()

        try:
            transcript = await asyncio.to_thread(stt.transcribe, audio_bytes)
        except Exception:
            log.exception("STT 실패")
            return JSONResponse(status_code=500, content={"error": "stt_failed"})
        t_stt = time.time()

        if not transcript:
            return {"transcript": "", "reply": "", "corrections": [],
                    "audio_b64": None, "empty": True}

        try:
            result = await _engine.send(transcript)
        except Exception:
            log.exception("대화 엔진 실패")
            return JSONResponse(status_code=500, content={"error": "llm_failed"})
        t_llm = time.time()

        wav = await asyncio.to_thread(tts.synthesize, result["reply"])
        t_tts = time.time()

        db.log_turn(_session(), transcript, result["reply"], result["corrections"])
        log.info(
            "턴 완료 stt=%.1fs llm=%.1fs tts=%.1fs | user=%r",
            t_stt - t0, t_llm - t_stt, t_tts - t_llm, transcript[:60],
        )
        return {
            "transcript": transcript,
            "reply": result["reply"],
            "corrections": result["corrections"],
            "audio_b64": base64.b64encode(wav).decode() if wav else None,
            "empty": False,
        }


@app.post("/api/reset")
async def reset():
    """대화 세션 초기화 + 방금 세션의 간단 리포트 반환."""
    global _session_id
    async with _lock:
        stats = db.session_stats(_session_id) if _session_id else None
        if _session_id:
            db.end_session(_session_id)
            _session_id = None
        await _engine.reset()
    return {"ok": True, "report": stats}


@app.on_event("shutdown")
async def shutdown():
    await _engine.close()


# 정적 PWA — 마지막에 마운트해야 /api/* 라우트가 우선함
app.mount("/", StaticFiles(directory=config.WEB_DIR, html=True), name="web")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=config.PORT)
