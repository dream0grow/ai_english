"""호출어("Hey Emma")·종료어("Bye Emma") 판정 + 문장 분리 유틸.

음성 인식이 이름을 조금씩 다르게 적는 것(Emma/Ema/Amma/M.A. 등)을 감안해
단어 단위 유사도 매칭을 쓴다.
"""
import difflib
import re

from . import config

_WORD_RE = re.compile(r"[a-z']+")
_SENT_RE = re.compile(r"[^.!?]+[.!?]*")

# 이름별 흔한 오인식 변형 (기본 emma 기준. 다른 이름도 유사도 매칭으로 커버)
_ALIASES = {
    "emma": {"emma", "ema", "amma", "emmah", "imma", "emo", "emma's"},
}

_END_WORDS = {"bye", "goodbye", "bye-bye", "byebye"}


def _words(text: str) -> list[str]:
    return _WORD_RE.findall(text.lower())


def _name_in(words: list[str]) -> bool:
    name = config.WAKE_NAME
    aliases = _ALIASES.get(name, {name})
    for w in words:
        if w in aliases:
            return True
        if difflib.SequenceMatcher(None, w, name).ratio() >= 0.75:
            return True
    return False


def is_wake(text: str) -> bool:
    """'Hey Emma' / 'Emma?' / 'Hi Emma' 등 — 앞부분에 이름이 나오면 호출로 판정."""
    words = _words(text)
    return bool(words) and _name_in(words[:4])


def is_end(text: str) -> bool:
    """'Bye Emma' / 'Goodbye' 등 — 종료 인사 판정 (문장이 짧을 때만)."""
    words = _words(text)
    return bool(words) and len(words) <= 5 and any(w in _END_WORDS for w in words)


def split_sentences(text: str) -> list[str]:
    """응답을 문장 단위로 분리 — 첫 문장부터 즉시 TTS해 체감 지연을 줄인다."""
    parts = [s.strip() for s in _SENT_RE.findall(text)]
    return [s for s in parts if s]
