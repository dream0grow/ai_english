"""AI English 집 서버 — FastAPI 앱.

파이프라인: 브라우저 녹음 → STT(faster-whisper) → Claude(구독) → TTS(Kokoro) → 재생

엔드포인트:
- POST /api/chat            : 버튼 녹음 한 턴 (1단계 방식, 폴백용으로 유지)
- WS   /ws/chat             : 핸즈프리 — 호출어 대기/연속 대화, 문장 스트리밍(2단계)
- POST /api/reset           : 세션 초기화 + 리포트
- GET/POST /api/profiles    : 가족 프로필 목록/생성(온보딩) (3단계)
- POST /api/profiles/{id}/select : 프로필 전환
- GET  /api/cards, POST /api/cards/select : 주제/롤플레이/슬랭 카드
- GET  /api/notebook        : 단어장 (교정 + 배운 표현)
- GET  /api/history         : 과거 세션 기록 (부모용)

실행:  ./run.sh   (또는  uvicorn server.main:app --host 0.0.0.0 --port 8100)
"""
import asyncio
import base64
import logging
import time

from fastapi import FastAPI, File, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import cards, config, db, prompts, stt, tts, wake
from .llm import create_engine

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
log = logging.getLogger("ai_english")

app = FastAPI(title="AI English")

_engine = create_engine()
_lock = asyncio.Lock()          # 저사양 CPU: 한 번에 한 턴만 처리
_session_id: int | None = None
_profile_id: int | None = None  # 활성 프로필 (기기 하나를 가족이 번갈아 사용)
_card_id: str | None = None     # 다음 세션에 적용할 시나리오 카드 (1회용)
_due_injected: list[int] = []   # 이번 세션에 재등장시킨 복습 항목 id


def _active_profile() -> dict | None:
    return db.get_profile(_profile_id) if _profile_id else None


def _prepare_engine() -> list[int]:
    """활성 프로필·카드·기억·복습 큐로 시스템 프롬프트 구성 (세션 시작 직전 호출)."""
    profile = _active_profile()
    kind = profile["kind"] if profile else None
    card = cards.get_card(_card_id, kind) if _card_id else None
    facts = db.recent_facts(_profile_id) if profile else []
    due = db.due_items(_profile_id) if profile else []
    _engine.set_system_prompt(prompts.build_system_prompt(profile, card, facts, due))
    if profile:
        log.info("세션 준비: profile=%s card=%s facts=%d due=%d",
                 profile["name"], _card_id, len(facts), len(due))
    return [d["id"] for d in due]


def _session() -> int:
    global _session_id, _due_injected
    if _session_id is None:
        _due_injected = _prepare_engine()
        _session_id = db.start_session(_profile_id)
    return _session_id


async def _finish_session() -> dict | None:
    """세션 종료 → 리포트 반환 + 대화 엔진 초기화. 카드는 1회용이라 함께 해제."""
    global _session_id, _card_id, _due_injected
    stats = db.session_stats(_session_id) if _session_id else None
    if _session_id:
        db.mark_reviewed(_due_injected)   # 재등장시킨 표현은 복습 간격 연장
        db.end_session(_session_id)
        _session_id = None
    _due_injected = []
    _card_id = None
    await _engine.reset()
    return stats


def _log_turn(transcript: str, result: dict) -> None:
    db.log_turn(_session(), transcript, result["reply"], result["corrections"],
                profile_id=_profile_id,
                memory=result.get("memory"), taught=result.get("taught"))


@app.get("/api/health")
async def health():
    return {
        "ok": True,
        "mock_llm": config.MOCK_LLM,
        "whisper_model": config.WHISPER_MODEL,
        "tts_engine": config.TTS_ENGINE,
        "wake_name": config.WAKE_NAME,
    }


# ──────────────────── 3단계: 프로필 (온보딩·전환) ────────────────────

class ProfileIn(BaseModel):
    name: str
    kind: str = "adult"            # 'child' | 'adult'
    level: str = "beginner"        # 'beginner' | 'intermediate' | 'advanced'
    goals: str = ""                # 온보딩: 학습 목표
    interests: str = ""            # 온보딩: 관심사·상황 (기억 루프 시드)


@app.get("/api/profiles")
async def profiles_list():
    return {"profiles": db.list_profiles(), "active": _profile_id}


@app.post("/api/profiles")
async def profiles_create(p: ProfileIn):
    global _profile_id
    if not p.name.strip():
        return JSONResponse(status_code=400, content={"error": "name_required"})
    if p.kind not in ("child", "adult"):
        return JSONResponse(status_code=400, content={"error": "bad_kind"})
    if p.level not in prompts.LEVEL_GUIDES:
        return JSONResponse(status_code=400, content={"error": "bad_level"})
    if any(x["name"] == p.name.strip() for x in db.list_profiles()):
        return JSONResponse(status_code=400, content={"error": "name_exists"})
    async with _lock:
        pid = db.create_profile(p.name, p.kind, p.level, p.goals, p.interests)
        await _finish_session()
        _profile_id = pid
    return {"ok": True, "profile": db.get_profile(pid), "active": pid}


@app.post("/api/profiles/{pid}/select")
async def profiles_select(pid: int):
    global _profile_id
    profile = db.get_profile(pid)
    if not profile:
        return JSONResponse(status_code=404, content={"error": "no_such_profile"})
    async with _lock:
        if pid != _profile_id:
            await _finish_session()   # 프로필 전환 → 진행 중이던 세션은 종료
            _profile_id = pid
    return {"ok": True, "profile": profile,
            "streak_days": db.streak_days(pid)}


# ──────────────── 3단계: 카드 (주제/롤플레이/슬랭 모드) ────────────────

class CardIn(BaseModel):
    card_id: str | None = None     # None이면 자유 대화로 해제


@app.get("/api/cards")
async def cards_list():
    profile = _active_profile()
    return {"cards": cards.list_cards(profile["kind"] if profile else None),
            "active": _card_id}


@app.post("/api/cards/select")
async def cards_select(c: CardIn):
    global _card_id
    profile = _active_profile()
    kind = profile["kind"] if profile else None
    if c.card_id is not None and not cards.get_card(c.card_id, kind):
        return JSONResponse(status_code=400, content={"error": "no_such_card"})
    async with _lock:
        await _finish_session()    # 새 시나리오는 새 대화로 시작
        _card_id = c.card_id
    return {"ok": True, "active": _card_id}


# ──────────────── 3단계: 단어장 / 학습 기록 ────────────────

@app.get("/api/notebook")
async def notebook():
    if not _profile_id:
        return JSONResponse(status_code=400, content={"error": "no_profile"})
    return {"items": db.notebook(_profile_id)}


@app.get("/api/history")
async def history():
    if not _profile_id:
        return JSONResponse(status_code=400, content={"error": "no_profile"})
    return {"sessions": db.history(_profile_id),
            "streak_days": db.streak_days(_profile_id)}


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

        _session()   # 첫 턴이면 프로필 프롬프트를 엔진에 적용한 뒤 세션 시작

        try:
            result = await _engine.send(transcript)
        except Exception:
            log.exception("대화 엔진 실패")
            return JSONResponse(status_code=500, content={"error": "llm_failed"})
        t_llm = time.time()

        wav = await asyncio.to_thread(tts.synthesize, result["reply"])
        t_tts = time.time()

        _log_turn(transcript, result)
        log.info(
            "턴 완료 stt=%.1fs llm=%.1fs tts=%.1fs | user=%r",
            t_stt - t0, t_llm - t_stt, t_tts - t_llm, transcript[:60],
        )
        return {
            "transcript": transcript,
            "reply": result["reply"],
            "corrections": result["corrections"],
            "taught": result.get("taught", []),
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
    _log_turn(transcript, result)
    await ws.send_json({
        "type": "turn_end",
        "transcript": transcript,
        "reply": result["reply"],
        "corrections": result["corrections"],
        "taught": result.get("taught", []),
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
      turn_end : 턴 완료 (transcript, corrections, taught)
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
                    # 호출됨 → 새 세션 + 인사 (프로필 프롬프트는 _session()에서 적용)
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
