"""음성 인식 — faster-whisper (오픈소스, 로컬, 무료)."""
import io
import logging

from . import config

log = logging.getLogger(__name__)

_model = None


def _get_model():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel

        log.info("Whisper 모델 로딩: %s (최초 1회 다운로드)", config.WHISPER_MODEL)
        _model = WhisperModel(config.WHISPER_MODEL, device="cpu", compute_type="int8")
    return _model


def transcribe(audio_bytes: bytes) -> str:
    """브라우저 녹음(webm/ogg/wav)을 영어 텍스트로 변환."""
    model = _get_model()
    segments, _info = model.transcribe(
        io.BytesIO(audio_bytes),
        language="en",
        beam_size=1,           # 저사양 CPU 속도 우선
        vad_filter=True,       # 앞뒤 무음 제거
        condition_on_previous_text=False,
    )
    text = " ".join(seg.text.strip() for seg in segments).strip()
    return text
