"""음성 합성 — Kokoro-82M (오픈소스, 로컬, 무료).

TTS_ENGINE=none 이면 음성 없이 텍스트만 반환하고,
프론트가 브라우저 내장 음성(speechSynthesis)으로 대체 재생한다.
"""
import io
import logging

from . import config

log = logging.getLogger(__name__)

_pipeline = None
_failed = False


def _get_pipeline():
    global _pipeline, _failed
    if _pipeline is None and not _failed:
        try:
            from kokoro import KPipeline

            log.info("Kokoro TTS 로딩 (최초 1회 모델 다운로드)")
            _pipeline = KPipeline(lang_code="a")  # 'a' = American English
        except Exception:
            log.exception("Kokoro 초기화 실패 — 브라우저 음성으로 대체됩니다")
            _failed = True
    return _pipeline


def synthesize(text: str) -> bytes | None:
    """텍스트 → 24kHz mono WAV bytes. 실패/비활성 시 None."""
    if config.TTS_ENGINE != "kokoro" or not text.strip():
        return None
    pipeline = _get_pipeline()
    if pipeline is None:
        return None
    try:
        import numpy as np
        import soundfile as sf

        chunks = [audio for _gs, _ps, audio in pipeline(text, voice=config.TTS_VOICE)]
        if not chunks:
            return None
        wav = np.concatenate(chunks)
        buf = io.BytesIO()
        sf.write(buf, wav, 24000, format="WAV", subtype="PCM_16")
        return buf.getvalue()
    except Exception:
        log.exception("TTS 합성 실패 — 이 턴은 브라우저 음성으로 대체")
        return None
