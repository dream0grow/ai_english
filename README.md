# AI English — 가족용 AI 영어 회화 (집 서버)

폰/패드 브라우저에서 마이크 버튼을 누르고 영어로 말하면, 집 서버가
음성 인식(faster-whisper) → Claude 대화(구독 인증, Recast 교정) → 음성 합성(Kokoro)으로
답해주는 가족용 영어 회화 앱입니다. **월 추가 비용 약 0원** (Claude 구독 + 전기료만).

- 기획서: [`PLAN.md`](PLAN.md) · 시장 조사: [`docs/market-research.md`](docs/market-research.md)

---

## 1. 준비물

- 24시간 켜둘 컴퓨터 1대 — **Ubuntu 24.04 LTS 권장** (i3-6100U/8GB 급이면 충분)
- Claude **Pro 또는 Max 구독** 계정
- Cloudflare 무료 계정 (폰에서 HTTPS로 접속하기 위해 필요)

> 노트북을 서버로 쓸 때: 전원 연결 + 절전 끄기. Ubuntu에서 덮개를 닫아도 꺼지지 않게 하려면
> `/etc/systemd/logind.conf`에서 `HandleLidSwitch=ignore` 설정 후 `sudo systemctl restart systemd-logind`.

## 2. 설치 (집 서버에서)

```bash
# 시스템 패키지
sudo apt update
sudo apt install -y python3 python3-venv git espeak-ng ffmpeg

# 코드 받기
git clone https://github.com/dream0grow/ai_english.git
cd ai_english

# 설정 파일 만들기
cp .env.example .env
```

## 3. Claude 구독 토큰 발급

Claude Code CLI를 설치하고 구독 계정으로 장기 토큰을 발급합니다.

```bash
# Node.js가 없다면: sudo apt install -y nodejs npm
npm install -g @anthropic-ai/claude-code

claude setup-token
# → 브라우저가 열리면 구독 계정으로 로그인 → sk-ant-oat01-... 토큰 출력
```

출력된 토큰을 `.env`의 `CLAUDE_CODE_OAUTH_TOKEN=`에 붙여넣습니다.

> 참고: 개인 용도의 Agent SDK 구독 사용은 Anthropic이 공식 지원합니다
> (정책 변경 시 사전 공지 예정). 정책이 바뀌면 `.env`에 API 키를 넣는 방식으로
> 전환할 수 있게 설계되어 있습니다.

## 4. 실행

```bash
./run.sh
```

- 최초 실행 시 의존성 설치 + Whisper/Kokoro 모델 다운로드(수백 MB)로 몇 분 걸립니다.
- `http://<서버IP>:8100` 이 뜨면 성공. 같은 컴퓨터 브라우저에서 `http://localhost:8100`
  으로 열어 마이크 테스트를 해보세요 (localhost는 HTTPS 없이도 마이크 허용).

### 토큰 없이 배선만 테스트

`.env`에 `MOCK_LLM=1`을 넣으면 Claude 없이 고정 응답으로 전체 파이프라인을 확인할 수 있습니다.

## 5. 폰에서 접속 — Cloudflare Tunnel (HTTPS)

브라우저는 **HTTPS가 아니면 마이크를 막기 때문에**, 폰 접속에는 터널이 필요합니다.

**빠른 테스트용 (계정 불필요, 실행할 때마다 주소 바뀜):**

```bash
# cloudflared 설치
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb -o cloudflared.deb
sudo dpkg -i cloudflared.deb

cloudflared tunnel --url http://localhost:8100
# → https://xxxx.trycloudflare.com 주소가 출력됨 → 폰에서 접속
```

**고정 주소 (권장, Cloudflare 계정 + 보유 도메인 필요):**

```bash
cloudflared tunnel login
cloudflared tunnel create ai-english
cloudflared tunnel route dns ai-english english.내도메인.com
cloudflared tunnel run --url http://localhost:8100 ai-english
```

폰 브라우저에서 접속 → 공유 메뉴 → **"홈 화면에 추가"** 하면 앱처럼 사용할 수 있습니다.

## 6. 부팅 시 자동 시작 (선택)

```bash
sudo tee /etc/systemd/system/ai-english.service > /dev/null <<EOF
[Unit]
Description=AI English server
After=network.target

[Service]
WorkingDirectory=$(pwd)
ExecStart=$(pwd)/run.sh
Restart=always
User=$USER

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl enable --now ai-english
```

## 7. 설정 다이얼 (.env)

| 문제 | 해결 |
|---|---|
| 응답이 느리다 | `WHISPER_MODEL=tiny` (인식 속도 2배) |
| 목소리 생성이 느리다 | `TTS_ENGINE=none` (브라우저 내장 음성으로 대체, 음질 하락) |
| 인식이 부정확하다 | `WHISPER_MODEL=small` (느려짐) |
| 더 똑똑한 대화 | `CLAUDE_MODEL=opus` (Max 구독, 사용 한도 소모 빠름) |

## 8. 문제 해결

- **마이크 권한 팝업이 안 뜸** → HTTPS 주소(터널)로 접속했는지 확인. `http://IP`로는 마이크 불가
  (예외: 서버 컴퓨터 자신의 `localhost`).
- **Kokoro 오류** → `sudo apt install espeak-ng` 확인. 계속 실패하면 `TTS_ENGINE=none`으로 우선 사용.
- **Claude 응답 없음** → `claude setup-token` 재발급, `.env` 토큰 확인.
  구독 사용 한도(5시간 윈도우)에 걸리면 잠시 후 재시도.
- **포트 충돌** → `.env`의 `PORT` 변경.

## 프로젝트 구조

```
server/   FastAPI 앱 (stt/tts/llm/db — llm.py의 DialogEngine이 교체 지점)
web/      PWA 프론트 (마이크 버튼, 대화 자막, 교정 패널)
docs/     시장 조사 보고서
```
