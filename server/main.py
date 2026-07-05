"""AI English 집 서버 — FastAPI 앱.

파이프라인: 브라우저 녹음 → STT(faster-whisper) → Claude(구독) → TTS(Kokoro) → 재생

엔드포인트:
- POST /api/chat  : 버튼 녹음 한 턴 (1단계 방식, 폴백용으로 유지)
- WS   /ws/chat   : 핸즈프리 모드 — 호출어 대기/연속 대화, 문장 단위 오디오 스트리밍(2단계)
- POST /api/reset : 세션 초기화 + 리포트

실행:  ./run.sh   (또는  uvicorn server.main:app --host 0.0.0.0 --port 8100)
"""
import asyncio
import base64
import logging
import time

from fastapi import FastAPI, File, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from . import config, db, stt, tts, wake
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


async def _finish_session() -> dict | None:
    """세션 종료 → 리포트 반환 + 대화 엔진 초기화."""
    global _session_id
    stats = db.session_stats(_session_id) if _session_id else None
    if _session_id:
        db.end_session(_session_id)
        _session_id = None
    await _engine.reset()
    return stats


@app.get("/api/health")
async def health():
    return {
        "ok": True,
        "mock_llm": config.MOCK_LLM,
        "whisper_model": config.WHISPER_MODEL,
        "tts_engine": config.TTS_ENGINE,
        "wake_name": config.WAKE_NAME,
    }


# ──────────────────────────── 1단계: 버튼 녹음 (REST) ────────────────────────────

@app.post("/api/chat")
async def chat(audio: UploadFile = File(...)):
    """오디오 한 턴 처리: STT → 대화 엔진 → TTS (전체 완료 후 한 번에 응답)."""
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
    async with _lock:
        stats = await _finish_session()
    return {"ok": True, "report": stats}


# ──────────────────── 2단계: 핸즈프리 (WebSocket 스트리밍) ────────────────────

async def _stream_reply(ws: WebSocket, result: dict, transcript: str) -> None:
    """응답을 문장 단위로 쪼개 TTS가 끝나는 대로 즉시 전송 → 체감 지연 단축."""
    sentences = wake.split_sentences(result["reply"]) or [result["reply"]]
    for i, sent in enumerate(sentences):
        wav = await asyncio.to_thread(tts.synthesize, sent)
        await ws.send_json({
            "type": "sentence",
            "index": i,
            "total": len(sentences),
            "text": sent,
            "audio_b64": base64.b64encode(wav).decode() if wav else None,
        })
    db.log_turn(_session(), transcript, result["reply"], result["corrections"])
    await ws.send_json({
        "type": "turn_end",
        "transcript": transcript,
        "reply": result["reply"],
        "corrections": result["corrections"],
    })


@app.websocket("/ws/chat")
async def ws_chat(ws: WebSocket):
    """핸즈프리 프로토콜.

    클라이언트 → 서버: 발화 1개당 바이너리 프레임 1개 (webm/ogg 오디오)
    서버 → 클라이언트(JSON):
      state    : {"state": "standby"|"active"}  현재 모드 통지
      ignored  : 호출어 대기 중 이름이 안 불림 / 빈 오디오 → 무시됨
      wake     : 호출 감지, 인사 시작
      sentence : 문장 하나 (text + audio_b64) — 도착 즉시 재생
      turn_end : 턴 완료 (transcript, corrections)
      session_end : "Bye Emma" → 리포트 포함
    """
    await ws.accept()
    state = "standby"
    await ws.send_json({"state": state, "wake_name": config.WAKE_NAME})

    try:
        while True:
            audio_bytes = await ws.receive_bytes()
            async with _lock:
                try:
                    transcript = await asyncio.to_thread(stt.transcribe, audio_bytes)
                except Exception:
                    log.exception("STT 실패(ws)")
                    await ws.send_json({"type": "ignored", "reason": "stt_failed"})
                    continue

                if not transcript:
                    await ws.send_json({"type": "ignored", "reason": "empty"})
                    continue

                if state == "standby":
                    if not wake.is_wake(transcript):
                        log.info("standby 무시: %r", transcript[:50])
                        await ws.send_json({"type": "ignored", "reason": "no_wake",
                                            "heard": transcript})
                        continue
                    # 호출됨 → 새 세션 + 인사
                    state = "active"
                    await _engine.reset()
                    _session()
                    await ws.send_json({"type": "wake", "heard": transcript})
                    await ws.send_json({"state": state})
                    try:
                        result = await _engine.send("")   # 첫 턴: 인사 유도
                    except Exception:
                        log.exception("대화 엔진 실패(인사)")
                        await ws.send_json({"type": "ignored", "reason": "llm_failed"})
                        state = "standby"
                        await ws.send_json({"state": state})
                        continue
                    await _stream_reply(ws, result, transcript)
                    continue

                # active 상태
                if wake.is_end(transcript):
                    report = await _finish_session()
                    state = "standby"
                    await ws.send_json({"type": "session_end", "report": report})
                    await ws.send_json({"state": state})
                    continue

                try:
                    result = await _engine.send(transcript)
                except Exception:
                    log.exception("대화 엔진 실패(ws)")
                    await ws.send_json({"type": "ignored", "reason": "llm_failed"})
                    continue
                await _stream_reply(ws, result, transcript)

    except WebSocketDisconnect:
        log.info("핸즈프리 연결 종료")


@app.on_event("shutdown")
async def shutdown():
    await _engine.close()


# 정적 PWA — 마지막에 마운트해야 /api/* 라우트가 우선함
app.mount("/", StaticFiles(directory=config.WEB_DIR, html=True), name="web")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=config.PORT)
