# AI English — 프로젝트 메모리

가족용(초등 3~5 아이 + 성인) AI 영어 회화 학습 앱. 폰/패드 PWA + 집 서버(구형 노트북,
i3-6100U/8GB/Ubuntu)에서 STT→Claude→TTS 파이프라인 구동. 월 추가 비용 0원이 핵심 제약.

## 핵심 문서 (먼저 읽을 것)

- `PLAN.md` — 전체 기획서 (아키텍처, 3가지 사용 흐름, 교육 설계, 업그레이드 전략, 로드맵)
- `docs/market-research.md` — 시장 조사 보고서 (10개 앱 비교, 벤치마킹, 셀링포인트)
- `docs/research-raw/` — 딥리서치 원본 (검증 주장 20개, 기각 4개, 검색 결과, JSON)
- `README.md` — 집 서버 설치·실행 가이드

## 확정된 의사결정 (재논의 불필요)

1. **Claude 구독(Pro/Max) 인증** 사용, API 아님 — `claude setup-token` → `CLAUDE_CODE_OAUTH_TOKEN`.
   정책 변경 대비 `server/llm.py`의 `DialogEngine` 추상화로 교체 지점 단일화.
2. **음성은 오픈소스 로컬**: STT=faster-whisper(base), TTS=Kokoro-82M. 발음 점수 기능은
   의도적으로 배제(시장조사: 업계 전반 부정확 검증됨).
3. **교정은 Recast**: 대화 중 지적 금지, 자연스럽게 되받기. 교정 내역은
   `<reply>/<corrections>` 태그로 병행 추출(`server/prompts.py`, `server/llm.py:parse_response`).
4. **파이프라인 방식 우선**, 실시간(speech-to-speech)은 나중에 하이브리드로 업그레이드
   (Claude는 학습 분석기로 유지). 근거는 PLAN.md §4.
5. 차별화 기능 = **"기억+재등장 루프"** (family_facts, learned_items 테이블 — 스키마 선반영됨).
6. UI 교정 표시는 업계 표준 패턴: 발화 옆 ✓/✎, 취소선→굵게, 탭하면 한국어 설명.
7. 게이미피케이션은 streak + 발화량만 (Duolingo식 과보상 배제).

## 현재 상태 (로드맵 기준)

- [x] 기획서 + 시장 조사
- [x] **1단계 MVP**: 음성 대화 루프 — `server/`(FastAPI+STT+TTS+Claude) + `web/`(PWA) 완성
  - 검증: MOCK 모드로 배선 전체 통과. **Whisper/Kokoro 실모델은 미검증**
    (원격 개발 환경이 huggingface.co 차단 — 집 서버에서 첫 실행 시 확인 필요)
- [ ] **2단계 (다음)**: 호출어("영어야!") + VAD 핸즈프리 + barge-in + 문장 단위 스트리밍 TTS(지연 1.5~2초)
- [ ] 3단계: 가족 프로필, 세션 리포트 확장, 단어장, 주제/롤플레이 카드, 기억+재등장 루프
- [ ] 4단계: 간격 반복, 슬랭 커리큘럼, 통계, (선택) 실시간 하이브리드

## 개발·실행 방법

```bash
# 테스트 (Claude 토큰/모델 다운로드 없이)
python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt
echo "MOCK_LLM=1
TTS_ENGINE=none
WHISPER_MODEL=tiny" > .env
./run.sh          # http://localhost:8100

# 실사용: README.md의 3~5단계 (토큰 발급, Cloudflare Tunnel)
```

- 브랜치: `claude/ai-english-learning-app-q9hk3q` 에서 개발·푸시
- 파이썬 3.10+, 의존성은 `requirements.txt` 단일 관리
- 저사양 서버 전제: 무거운 의존성 추가 금지, 턴 처리는 `main.py`의 asyncio.Lock으로 직렬화 유지

## 코드 지도

| 파일 | 역할 | 주의점 |
|---|---|---|
| `server/llm.py` | 대화 엔진 추상화 — **업그레이드/교체 지점** | 출력 계약 {reply, corrections} 유지 |
| `server/prompts.py` | Recast 프롬프트 v1 | 출력 태그 형식 바꾸면 parse_response도 수정 |
| `server/main.py` | API: /api/chat, /api/reset | 정적 마운트는 반드시 마지막 |
| `server/db.py` | SQLite — 3단계용 스키마 이미 포함 | |
| `web/app.js` | 녹음(hold/tap 토글), 교정 UI, TTS 폴백 | audio_b64 null이면 speechSynthesis 폴백 |
