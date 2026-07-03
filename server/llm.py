"""대화 엔진 — 기획서 §4의 업그레이드 대비 추상화 계층.

DialogEngine 인터페이스: send(user_text) -> {"reply": str, "corrections": [...]}
- ClaudeEngine : Claude Agent SDK + 구독 OAuth 토큰 (기본)
- MockEngine   : 토큰 없이 파이프라인 테스트용

나중에 실시간(speech-to-speech) 엔진으로 교체해도 이 인터페이스 출력만
유지하면 DB/리포트/복습 코드는 무수정 (하이브리드 업그레이드 경로).
"""
import json
import logging
import re
from abc import ABC, abstractmethod

from . import config
from .prompts import FIRST_TURN_HINT, SYSTEM_PROMPT

log = logging.getLogger(__name__)

_REPLY_RE = re.compile(r"<reply>\s*(.*?)\s*</reply>", re.S)
_CORR_RE = re.compile(r"<corrections>\s*(.*?)\s*</corrections>", re.S)


def parse_response(raw: str) -> dict:
    """<reply>/<corrections> 태그 파싱. 실패 시 전체 텍스트를 reply로 폴백."""
    reply_m = _REPLY_RE.search(raw)
    reply = reply_m.group(1).strip() if reply_m else raw.strip()

    corrections = []
    corr_m = _CORR_RE.search(raw)
    if corr_m:
        try:
            data = json.loads(corr_m.group(1))
            if isinstance(data, list):
                corrections = [
                    {
                        "original": str(c.get("original", "")),
                        "corrected": str(c.get("corrected", "")),
                        "note": str(c.get("note", "")),
                    }
                    for c in data
                    if isinstance(c, dict) and c.get("corrected")
                ]
        except (json.JSONDecodeError, AttributeError):
            log.warning("corrections JSON 파싱 실패 — 이 턴은 교정 없이 진행")

    # 태그 파싱이 아예 실패해 원문에 태그가 섞여 있으면 제거
    if not reply_m:
        reply = _CORR_RE.sub("", reply).strip()

    return {"reply": reply, "corrections": corrections}


class DialogEngine(ABC):
    @abstractmethod
    async def send(self, user_text: str) -> dict:
        """사용자 발화 텍스트 → {"reply", "corrections"}"""

    @abstractmethod
    async def reset(self) -> None:
        """대화 세션 초기화"""

    async def close(self) -> None:
        pass


class MockEngine(DialogEngine):
    """토큰 없이 STT→응답→TTS 배선을 검증하기 위한 고정 응답 엔진."""

    def __init__(self):
        self._turn = 0

    async def send(self, user_text: str) -> dict:
        self._turn += 1
        corrections = []
        if "go to park" in user_text.lower():
            corrections = [{
                "original": "I go to park yesterday",
                "corrected": "I went to the park yesterday",
                "note": "과거 일은 went, 장소 앞에는 the를 붙여요",
            }]
        return {
            "reply": f"Oh, that sounds fun! You said: {user_text or '(nothing)'} — "
                     "What else did you do today?",
            "corrections": corrections,
        }

    async def reset(self) -> None:
        self._turn = 0


class ClaudeEngine(DialogEngine):
    """Claude Agent SDK — 구독 OAuth 토큰(CLAUDE_CODE_OAUTH_TOKEN)으로 인증.

    ClaudeSDKClient는 연결을 유지하며 멀티턴 대화를 이어간다.
    """

    def __init__(self):
        self._client = None
        self._first_turn = True

    async def _ensure_client(self):
        if self._client is None:
            from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient

            options = ClaudeAgentOptions(
                system_prompt=SYSTEM_PROMPT,
                allowed_tools=[],
                max_turns=1,
                model=config.CLAUDE_MODEL,
            )
            self._client = ClaudeSDKClient(options=options)
            await self._client.connect()

    async def send(self, user_text: str) -> dict:
        from claude_agent_sdk import AssistantMessage, TextBlock

        await self._ensure_client()
        prompt = user_text
        if self._first_turn:
            prompt = f"{FIRST_TURN_HINT}\n\nLearner: {user_text}" if user_text else FIRST_TURN_HINT
            self._first_turn = False

        await self._client.query(prompt)
        raw = ""
        async for message in self._client.receive_response():
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        raw += block.text
        return parse_response(raw)

    async def reset(self) -> None:
        await self.close()
        self._first_turn = True

    async def close(self) -> None:
        if self._client is not None:
            try:
                await self._client.disconnect()
            except Exception:
                log.exception("Claude 세션 종료 중 오류(무시)")
            self._client = None


def create_engine() -> DialogEngine:
    if config.MOCK_LLM:
        log.warning("MOCK_LLM=1 — Claude 대신 고정 응답 모드로 동작")
        return MockEngine()
    return ClaudeEngine()
