# 윈도우 PC에서 바로 체험하기 (서버 만들기 전 미리 써보기)

Ubuntu 서버를 만들기 전에, **지금 쓰시는 윈도우 컴퓨터에서 진짜 앱을 돌려볼 수 있습니다.**
진짜 음성 인식 + 진짜 Emma(Max 구독)로 동작합니다. 이미 `git clone`을 하셨다면 15~30분이면 됩니다.

> 차이점: 윈도우 체험판은 **이 컴퓨터의 브라우저에서만** 사용합니다(localhost).
> 폰으로 쓰려면 HTTPS가 필요해서 그건 Ubuntu 서버 + Cloudflare Tunnel 단계에서 합니다.

## 1. Python 설치 (5분)

1. https://www.python.org/downloads/ → **Download Python 3.12.x** 클릭
2. 설치 첫 화면에서 **"Add python.exe to PATH" 체크박스를 반드시 체크** → Install Now
3. 확인: 시작 메뉴 → `cmd` 입력 → 명령 프롬프트에서 `python --version` → 버전이 나오면 OK

## 2. Node.js 설치 + Claude 구독 토큰 발급 (10분)

1. https://nodejs.org → **LTS** 버전 다운로드 → 설치 (전부 기본값 Next)
2. **새** 명령 프롬프트를 열고(기존 창은 닫기):

```bat
npm install -g @anthropic-ai/claude-code
claude setup-token
```

3. 브라우저가 열리면 **Max 구독 계정으로 로그인** → 승인 →
   명령 프롬프트에 `sk-ant-oat01-...` 토큰이 출력됩니다. 마우스로 긁어 복사(Ctrl+C).

> `claude` 명령이 안 되면: Git for Windows가 필요할 수 있습니다 → https://git-scm.com 에서
> 설치 후 명령 프롬프트를 새로 열어 재시도.

## 3. 실행 (더블클릭 한 번)

1. 파일 탐색기로 클론받은 `ai_english` 폴더에 들어가서 **`run.bat` 더블클릭**
2. 최초 1회: 자동으로 설치가 진행되고, 메모장이 열리면
   `CLAUDE_CODE_OAUTH_TOKEN=` 뒤에 복사해둔 토큰 붙여넣기 → 저장 → 닫기
3. 검은 창에 `Uvicorn running...` 이 보이면 성공
   (최초에는 음성 모델 다운로드로 5~15분 걸릴 수 있습니다 — 창을 닫지 마세요)

> "Windows 보안 경고(방화벽)" 창이 뜨면 "액세스 허용"을 눌러주세요.

## 4. 대화해보기

1. 크롬(또는 엣지)에서 **http://localhost:8100** 접속
2. 마이크 권한 "허용"
3. 두 가지 방법:
   - **버튼 모드**: 마이크 버튼을 누른 채 "Hello Emma!" 말하고 떼기
   - **핸즈프리 모드**: 🎙 핸즈프리 버튼 클릭 → 잠깐 조용히(소음 측정) → **"Hey Emma!"**
4. 끝낼 때: "Bye Emma" → 오늘의 리포트 확인

## 문제 해결

| 증상 | 해결 |
|---|---|
| run.bat이 바로 꺼짐 | 폴더에서 주소창에 `cmd` 입력 → `run.bat` 실행하면 오류가 보임. 그걸 Claude에게 |
| 목소리가 기계음/안 나옴 | `.env`에서 `TTS_ENGINE=none` → 브라우저 음성으로 대체. (Kokoro가 윈도우에서 안 될 때) |
| 응답이 너무 느림 | `.env`에서 `WHISPER_MODEL=tiny` |
| Emma가 대답 안 함 | 검은 창의 오류 확인. 토큰 문제면 `claude setup-token` 재발급 |
| 마이크 인식 안 됨 | 크롬 주소창 왼쪽 자물쇠 → 사이트 설정 → 마이크 허용 |

체험 후 마음에 들면 README의 [1부]로 가서 서버 노트북에 정식 설치하면
가족 모두 폰에서 쓸 수 있게 됩니다. 윈도우 PC에서 만든 `.env`의 토큰은
서버에서도 그대로 재사용할 수 있습니다.
