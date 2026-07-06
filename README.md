# AI English — 가족용 AI 영어 회화 (집 서버 설치 가이드)

폰/패드 브라우저에서 **"Hey Emma!"** 라고 부르거나 마이크 버튼을 누르고 영어로 말하면,
집 서버가 음성 인식(faster-whisper) → Claude 대화(Max 구독 인증, 자연스러운 교정) →
음성 합성(Kokoro)으로 답해주는 가족용 영어 회화 앱입니다.

- **월 추가 비용 약 0원** (Claude 구독료 + 전기료 1~2천원 외 없음. API 과금 없음)
- 기획서: [`PLAN.md`](PLAN.md) · 시장 조사: [`docs/market-research.md`](docs/market-research.md)

이 문서는 **컴퓨터를 잘 몰라도 따라 할 수 있게** 처음부터 끝까지 순서대로 적었습니다.
위에서부터 차례로 하시면 됩니다. 막히면 그 화면/오류를 그대로 복사해서 Claude에게 물어보세요.

> 🚀 **서버 만들기 전에 먼저 체험해보고 싶다면**: 지금 쓰시는 윈도우 PC에서
> `run.bat` 더블클릭으로 진짜 앱을 돌려볼 수 있습니다 →
> [`docs/windows-quickstart.md`](docs/windows-quickstart.md) (15~30분)

---

## 전체 그림 (뭘 하게 되나요?)

```
[1부] 윈도우 노트북을 Ubuntu 서버로 바꾸기          (약 1시간, USB 필요)
[2부] 서버가 잠들지 않게 설정하기                    (10분)
[3부] 앱 설치하기                                    (20분, 대부분 자동)
[4부] Claude Max 구독 연결하기                       (10분)
[5부] 서버 컴퓨터에서 첫 테스트                      (5분)
[6부] 폰에서 접속하기 (Cloudflare Tunnel)            (20분)
[7부] 부팅하면 자동으로 켜지게 만들기                (10분)
```

---

# [1부] 윈도우 노트북을 Ubuntu 서버로 바꾸기

## 1-1. 왜 Ubuntu인가요?

윈도우는 24시간 서버로 쓰면 자동 업데이트 재부팅, 절전 모드 때문에 자꾸 끊깁니다.
Ubuntu(리눅스)는 무료이고, 몇 달씩 켜둬도 안정적이며, 이 프로젝트의 설치 절차가 모두
Ubuntu 기준으로 준비되어 있습니다.

> ⚠️ **중요: 설치하면 노트북의 윈도우와 모든 파일이 지워집니다.**
> 노트북 안에 필요한 사진/문서가 있다면 USB나 클라우드에 먼저 백업하세요.

## 1-2. 준비물

- 서버로 쓸 노트북 (이하 "서버 노트북")
- **8GB 이상 USB 메모리** 1개 (안의 내용은 지워짐)
- 작업용 컴퓨터 1대 (지금 쓰시는 윈도우 PC — USB를 만드는 용도)
- 와이파이 또는 랜선

## 1-3. 설치 USB 만들기 (작업용 윈도우 PC에서)

1. **Ubuntu 다운로드**: https://ubuntu.com/download/desktop 접속 →
   **Ubuntu 24.04 LTS** 의 `Download` 클릭 → `.iso` 파일(약 6GB) 다운로드.
   (LTS = 장기 지원판. 반드시 LTS로 받으세요)
2. **Rufus 다운로드**: https://rufus.ie 접속 → 최신판 다운로드 (설치 불필요, 실행형)
3. USB 메모리를 꽂고 **Rufus 실행**:
   - 장치: 방금 꽂은 USB 선택 (다른 디스크 선택하지 않게 주의!)
   - 부트 선택: `선택` 버튼 → 다운받은 Ubuntu `.iso` 파일 선택
   - 나머지는 기본값 그대로 → `시작` 클릭
   - "ISO 이미지 모드로 쓰기" 물어보면 → 권장(기본값) 그대로 확인
   - 10분 정도 걸립니다. "준비" 상태가 되면 완료.

## 1-4. 서버 노트북을 USB로 부팅하기

1. 서버 노트북을 **완전히 종료**하고, 만든 USB를 꽂습니다.
2. 전원을 켜자마자 **부팅 메뉴 키를 연타**합니다. 제조사마다 다릅니다:

   | 제조사 | 부팅 메뉴 키 |
   |---|---|
   | 삼성 | `F10` 또는 `Esc` |
   | LG | `F10` |
   | 레노버 | `F12` |
   | HP | `F9` 또는 `Esc` |
   | Dell | `F12` |
   | ASUS | `F8` 또는 `Esc` |

3. 부팅 메뉴가 나오면 **USB 이름이 들어간 항목**(예: `UEFI: SanDisk...`)을 선택.
4. 보라색 화면 → `Try or Install Ubuntu` 선택(그냥 엔터).

> 💡 부팅 메뉴가 안 뜨고 윈도우가 켜져버리면: 다시 종료하고 다른 키로 재시도.
> 그래도 안 되면 "제조사명 + 부팅 메뉴 키"로 검색하면 바로 나옵니다.

## 1-5. Ubuntu 설치 진행

설치 마법사가 뜨면 순서대로:

1. 언어: **한국어** 선택 → `Ubuntu 설치`
2. 키보드: 기본값(한국어) → 다음
3. 네트워크: **와이파이 연결** (집 와이파이 선택, 비밀번호 입력) → 다음
4. 설치 형태: **"대화형 설치"** → **"기본 설치"** → 다음
5. 서드파티 소프트웨어: **두 체크박스 모두 체크** (드라이버 때문에 중요) → 다음
6. 설치 방식: **"디스크를 지우고 Ubuntu 설치"** 선택 → 다음
   (⚠️ 이 단계에서 윈도우가 지워집니다. 백업 확인!)
7. 계정 만들기:
   - 이름/컴퓨터 이름: 자유 (예: `family` / `english-server`)
   - **비밀번호: 짧고 기억하기 쉬운 것** (자주 입력하게 됩니다)
   - "로그인할 때 비밀번호 필요" 선택
8. 시간대: Seoul 확인 → 설치 시작 → 15~20분 대기 → **"지금 다시 시작"** →
   "USB를 제거하라"는 메시지가 나오면 USB 뽑고 엔터.

재부팅 후 로그인하면 Ubuntu 바탕화면이 나옵니다. 축하합니다, 서버가 생겼습니다!

## 1-6. 설치 직후 할 일

바탕화면에서 `Ctrl + Alt + T` 를 누르면 **터미널**(검은 창)이 열립니다.
앞으로 모든 명령은 이 터미널에 입력합니다. 한 줄씩 복사 → 붙여넣기(`Ctrl+Shift+V`) → 엔터.

```bash
# 시스템 최신화 (5~10분. 중간에 비밀번호 물으면 로그인 비밀번호 입력 — 화면에 안 보여도 입력되고 있음)
sudo apt update && sudo apt upgrade -y
```

---

# [2부] 서버가 잠들지 않게 설정하기

24시간 서버의 핵심입니다. 3가지를 끕니다.

```bash
# 1) 절전 모드 완전 비활성화
sudo systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target

# 2) 노트북 덮개를 닫아도 꺼지지 않게
sudo sed -i 's/^#*HandleLidSwitch=.*/HandleLidSwitch=ignore/' /etc/systemd/logind.conf
sudo sed -i 's/^#*HandleLidSwitchExternalPower=.*/HandleLidSwitchExternalPower=ignore/' /etc/systemd/logind.conf
sudo systemctl restart systemd-logind
```

3) **화면 자동 잠금/절전 끄기** (마우스로): 설정 → 전원 → "화면 끄기"는 꺼짐 또는 자유,
"자동 절전"은 **끄기**.

이제 전원 어댑터를 연결한 채 덮개를 닫아 구석에 두면 됩니다.

> 💡 배터리 보호: 설정 → 전원에 "배터리 충전 한도 80%" 옵션이 있으면 켜두세요 (노트북 수명↑).

---

# [3부] 앱 설치하기

```bash
# 1) 필요한 프로그램 설치
sudo apt install -y git python3 python3-venv espeak-ng ffmpeg curl

# 2) 코드 받기 (GitHub 로그인을 물으면: 아이디 + Personal Access Token)
cd ~
git clone https://github.com/dream0grow/ai_english.git
cd ai_english
git checkout claude/ai-english-learning-app-q9hk3q

# 3) 설정 파일 만들기
cp .env.example .env
```

> 💡 **Personal Access Token 만드는 법** (리포지토리가 비공개인 경우):
> 폰이나 다른 PC에서 github.com 로그인 → 우상단 프로필 → Settings →
> 맨 아래 Developer settings → Personal access tokens → Tokens (classic) →
> Generate new token (classic) → 이름 자유, 기간 No expiration, **repo 체크** → 생성 →
> `ghp_...` 문자열 복사. git이 비밀번호를 물을 때 이걸 붙여넣습니다.

---

# [4부] Claude Max 구독 연결하기

**API 키가 아니라 Max 구독으로 연결합니다.** 추가 과금이 없습니다.

```bash
# 1) Node.js 설치 (Claude Code CLI 실행에 필요)
sudo apt install -y nodejs npm

# 2) Claude Code CLI 설치
sudo npm install -g @anthropic-ai/claude-code

# 3) 구독 토큰 발급
claude setup-token
```

- 브라우저가 열리면 **Max 구독 계정으로 로그인** → 승인.
- 터미널에 `sk-ant-oat01-...` 로 시작하는 긴 토큰이 출력됩니다. 전체를 복사하세요.

```bash
# 4) 토큰을 설정 파일에 넣기 (파일 편집기가 열림)
nano .env
```

- 화살표로 `CLAUDE_CODE_OAUTH_TOKEN=` 줄로 이동, `=` 뒤에 토큰 붙여넣기
  (터미널 붙여넣기: `Ctrl+Shift+V`)
- 저장: `Ctrl+O` → 엔터, 종료: `Ctrl+X`

> ✅ 이 앱은 구독 전용으로 설계되어 있습니다: API 키(`ANTHROPIC_API_KEY`)가 환경에 있어도
> 자동으로 제거하고, 시작 로그에 `구독(OAuth 토큰) 인증 — API 과금 없음`을 표시합니다.

---

# [5부] 서버 컴퓨터에서 첫 테스트

```bash
cd ~/ai_english
./run.sh
```

- **최초 실행은 5~15분** 걸립니다 (파이썬 패키지 + 음성 모델 수백 MB 다운로드).
- `Uvicorn running on http://0.0.0.0:8100` 이 보이면 성공.

서버 노트북의 브라우저(Firefox)에서 `http://localhost:8100` 접속:

1. 마이크 버튼을 **누른 채** "Hello Emma, how are you?" 라고 말하고 손을 뗍니다.
2. 몇 초 후 Emma의 음성 답변과 자막이 나오면 **전체 파이프라인 성공!** 🎉

문제가 있으면 터미널의 오류 메시지를 복사해서 Claude에게 물어보세요.
서버 중지는 터미널에서 `Ctrl+C`.

> 💡 토큰 없이 배선만 확인하려면 `.env`에 `MOCK_LLM=1` 을 추가하고 실행하세요
> (Emma 대신 고정 응답이 나옵니다). 확인 후엔 다시 `MOCK_LLM=0`.

---

# [6부] 폰에서 접속하기 — Cloudflare Tunnel

폰 브라우저는 **HTTPS가 아니면 마이크 사용을 차단**합니다. Cloudflare Tunnel(무료)이
집 서버를 안전한 HTTPS 주소로 만들어줍니다. 공유기 설정(포트포워딩)이 전혀 필요 없습니다.

## 6-1. cloudflared 설치

```bash
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb -o /tmp/cloudflared.deb
sudo dpkg -i /tmp/cloudflared.deb
```

## 6-2. 방법 A — 즉석 테스트 (가입 불필요, 주소가 매번 바뀜)

```bash
# 앱 서버가 켜진 상태에서, 새 터미널(Ctrl+Alt+T)을 열고:
cloudflared tunnel --url http://localhost:8100
```

몇 초 후 `https://무작위단어.trycloudflare.com` 주소가 출력됩니다.
**폰 브라우저에서 이 주소로 접속** → 마이크 권한 "허용" → 대화 테스트!

## 6-3. 방법 B — 고정 주소 (권장, 실사용용)

Cloudflare 계정과 도메인이 필요합니다. 도메인이 없다면 연 1~2만원짜리를
Cloudflare(dash.cloudflare.com → 도메인 등록)에서 사면 연동이 가장 쉽습니다.

```bash
cloudflared tunnel login          # 브라우저 열리면 Cloudflare 로그인 → 도메인 선택
cloudflared tunnel create ai-english
cloudflared tunnel route dns ai-english emma.내도메인.com
cloudflared tunnel run --url http://localhost:8100 ai-english
```

이후 가족 모두 `https://emma.내도메인.com` 으로 접속하면 됩니다.

## 6-4. 폰에서 앱처럼 만들기

- **iPhone(Safari)**: 접속 → 공유 버튼(⬆) → **"홈 화면에 추가"**
- **Android(Chrome)**: 접속 → 메뉴(⋮) → **"홈 화면에 추가"**

홈 화면 아이콘으로 열면 주소창 없는 전체 화면 앱처럼 동작합니다.

---

# [7부] 부팅하면 자동으로 켜지게 만들기

정전이나 재부팅 후에도 자동으로 살아나게 합니다.

```bash
# 앱 서버 자동 시작
sudo tee /etc/systemd/system/ai-english.service > /dev/null <<EOF
[Unit]
Description=AI English server
After=network-online.target

[Service]
WorkingDirectory=/home/$USER/ai_english
ExecStart=/home/$USER/ai_english/run.sh
Restart=always
User=$USER

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl enable --now ai-english

# (방법 B를 쓰는 경우) 터널도 자동 시작
sudo cloudflared service install
sudo systemctl enable --now cloudflared
```

확인:

```bash
systemctl status ai-english     # 초록색 active (running) 이면 정상. q로 나가기
```

이후에는 노트북 전원만 켜면 모든 것이 자동으로 올라옵니다.

---

# 사용법 요약

| 하고 싶은 것 | 방법 |
|---|---|
| 대화 시작 (핸즈프리) | 앱에서 🎙 핸즈프리 켜기 → **"Hey Emma!"** 라고 부르기 |
| 대화 시작 (버튼) | 마이크 버튼 누른 채 말하고 떼기 |
| AI 말 끊기 | Emma가 말하는 중에 그냥 말을 시작하면 됨 (barge-in) |
| 대화 끝내기 | "Bye Emma!" → 오늘의 리포트가 뜸 |
| 새 대화 | 우상단 "새 대화" 버튼 |

# 설정 다이얼 (.env 수정 후 서버 재시작: `sudo systemctl restart ai-english`)

| 문제 | 해결 |
|---|---|
| 응답이 느리다 | `WHISPER_MODEL=tiny` (인식 2배 빠름, 정확도 소폭↓) |
| 음성 생성이 느리다 | `TTS_ENGINE=none` (브라우저 내장 음성으로 대체) |
| 인식이 부정확하다 | `WHISPER_MODEL=small` (정확도↑, 느려짐) |
| 더 똑똑한 대화 | `CLAUDE_MODEL=opus` (Max 한도 소모 빠름) |
| 호출어 바꾸기 | `WAKE_NAME=emma` 를 다른 영어 이름으로 |

# 문제 해결

- **마이크 권한 팝업이 안 뜸** → 주소가 `https://`인지 확인. `http://IP` 로는 마이크 불가
  (예외: 서버 자신의 `localhost`). 폰 설정에서 브라우저 마이크 권한도 확인.
- **"Hey Emma"를 못 알아들음** → 조용한 곳에서 또렷하게. 그래도 안 되면
  `WHISPER_MODEL=small`로 올려보기. 스피커 볼륨이 크면 자기 소리에 반응할 수 있으니 조정.
- **Kokoro 오류 / 목소리가 안 나옴** → `sudo apt install espeak-ng` 확인.
  임시로 `.env`에 `TTS_ENGINE=none` (브라우저 음성 폴백).
- **Claude 응답 없음** → 구독 사용 한도(5시간 윈도우)일 수 있음. 잠시 후 재시도.
  계속되면 `claude setup-token` 재발급.
- **서버 로그 보기** → `journalctl -u ai-english -f` (실시간, Ctrl+C로 종료)
- **업데이트 받기** → `cd ~/ai_english && git pull && sudo systemctl restart ai-english`

# 프로젝트 구조

```
server/   FastAPI 앱 — stt / tts / llm(교체 지점) / db / WebSocket 스트리밍
web/      PWA — 핸즈프리(VAD+호출어+barge-in), 버튼 녹음, 교정 UI
docs/     시장 조사 보고서 + 딥리서치 원본
CLAUDE.md 프로젝트 메모리 (Claude Code가 자동으로 읽음)
```
