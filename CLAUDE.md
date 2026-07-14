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
- [x] **2단계**: 핸즈프리 — 호출어 **"Hey Emma"**(`server/wake.py`, 유사도 매칭으로 오인식 커버),
  에너지 기반 VAD(web/app.js, 노이즈 캘리브레이션+적응 임계값), barge-in(재생 중 발화 감지 시
  즉시 중단, 재생 중엔 임계값 2.2배), 문장 단위 TTS 스트리밍(`/ws/chat` WebSocket, 첫 문장부터
  즉시 재생), Wake Lock, "Bye Emma" 종료→리포트
  - 검증: MOCK 모드로 WS 프로토콜 전체(호출→인사→대화→교정→종료→standby 복귀) 통과.
    **미검증: Whisper/Kokoro 실모델, 실기기 VAD 체감 튜닝**(원격 환경 huggingface 차단 —
    집 서버 첫 실행 시 확인. VAD 임계값·침묵 판정(END_FRAMES=900ms)은 실사용 후 조정 여지)
- [x] **3단계**: 학습 기능 — 가족 프로필(**아이 1+성인 2, 총 3인**; 온보딩=자기평가 레벨
  3단계+목표+관심사→family_facts 시드), 아이 프로필 콘텐츠 필터(프롬프트+카드 목록 이중),
  세션 리포트 확장(교정/새 표현/발화량/스트릭, SQLite 영구 저장), 단어장(교정+taught 자동
  저장), 주제/롤플레이/슬랭 카드(`server/cards.py`, 1회용 시나리오), 기억+재등장 루프
  (`<memory>`/`<taught>` 태그 → family_facts/learned_items 저장, 세션 시작 시 프롬프트
  주입, next_due 간격 1일→2.5일→…)
  - 검증: MOCK+STT 몽키패치로 E2E 통과(온보딩→카드 필터→대화→저장→리포트→단어장→WS→
    레거시 DB 마이그레이션). **미검증: 실 Claude가 4태그 형식을 안정 출력하는지**(집 서버
    확인 필요. 파싱 실패 시 해당 턴만 빈 배열로 폴백하므로 대화는 안 끊김)
- [ ] **4단계 (다음)**: 간격 반복 고도화, 슬랭 커리큘럼, 통계 대시보드, 레벨 승급 제안
  (발화 데이터 근거는 3단계 스키마에 쌓이는 중), (선택) 실시간 하이브리드

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
| `server/llm.py` | 대화 엔진 추상화 — **업그레이드/교체 지점** | 출력 계약 {reply, corrections, memory, taught} 유지. set_system_prompt는 reset() 후 적용 |
| `server/prompts.py` | 프롬프트 v2 — build_system_prompt(프로필·카드·기억·복습큐 조립) | 출력 태그 형식 바꾸면 parse_response도 수정. 아이 필터는 여기(_CHILD_SAFETY) |
| `server/cards.py` | 주제/롤플레이/슬랭 카드 데이터 | child_ok=False는 아이에게 목록·선택 모두 차단 |
| `server/main.py` | API: chat/reset/profiles/cards/notebook/history + WS | 정적 마운트는 반드시 마지막. 활성 프로필·카드는 서버 전역(가족 공용 기기 1대 전제) |
| `server/db.py` | SQLite — profiles/learned_items/family_facts 실사용 중 | _migrate()가 2단계 레거시 DB 보정. 옛 빈 테이블은 drop 후 재생성 |
| `web/app.js` | 녹음, 교정 UI, TTS 폴백 + 프로필/온보딩/카드/단어장 | audio_b64 null이면 speechSynthesis 폴백. 시작 시 프로필 선택 강제 |
