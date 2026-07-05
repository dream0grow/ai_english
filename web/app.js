/* AI English PWA
 * 1단계: 버튼 녹음 (누르는 동안 hold / 짧은 탭 토글) → POST /api/chat
 * 2단계: 핸즈프리 — 에너지 기반 VAD + "Hey Emma" 호출어 + barge-in + 문장 스트리밍(WS)
 */
const micBtn = document.getElementById("micBtn");
const chatEl = document.getElementById("chat");
const statusEl = document.getElementById("status");
const resetBtn = document.getElementById("resetBtn");
const hfBtn = document.getElementById("hfBtn");
const reportModal = document.getElementById("reportModal");
const reportBody = document.getElementById("reportBody");
const reportClose = document.getElementById("reportClose");

let stream = null;
let mediaRecorder = null;
let chunks = [];
let recording = false;       // 버튼 모드 녹음 중
let busy = false;
let pressStartedAt = 0;

/* ── 공통 UI ─────────────────────────────────────────────── */
function setStatus(text) { statusEl.textContent = text; }

function addBubble(role, text, extraClass = "") {
  const row = document.createElement("div");
  row.className = "row" + (role === "user" ? " user-row" : "");
  const b = document.createElement("div");
  b.className = `bubble ${role} ${extraClass}`.trim();
  b.textContent = text;
  row.appendChild(b);
  chatEl.appendChild(row);
  chatEl.scrollTop = chatEl.scrollHeight;
  return { row, bubble: b };
}

function markUserRow(row, corrections) {
  const mark = document.createElement("div");
  if (!corrections || corrections.length === 0) {
    mark.className = "mark ok";
    mark.textContent = "✓";
  } else {
    mark.className = "mark fix";
    mark.textContent = "✎ 이렇게 말해봐";
  }
  row.appendChild(mark);
}

function addCorrections(corrections) {
  if (!corrections || !corrections.length) return;
  const d = document.createElement("details");
  d.className = "corrections";
  const s = document.createElement("summary");
  s.textContent = "이렇게 말하면 더 자연스러워요";
  d.appendChild(s);
  for (const c of corrections) {
    const item = document.createElement("div");
    item.className = "corr-item";
    item.innerHTML =
      `<span class="orig"></span> → <span class="fixed"></span><div class="note"></div>`;
    item.querySelector(".orig").textContent = c.original;
    item.querySelector(".fixed").textContent = c.corrected;
    item.querySelector(".note").textContent = c.note || "";
    d.appendChild(item);
  }
  chatEl.appendChild(d);
  chatEl.scrollTop = chatEl.scrollHeight;
}

/* ── 오디오 재생 (문장 큐 + barge-in 중단 지원) ───────────── */
const playQueue = [];
let playing = false;
let currentAudio = null;

function isSpeaking() { return playing; }

function enqueueAudio(text, audioB64) {
  playQueue.push({ text, audioB64 });
  if (!playing) playNext();
}

function playNext() {
  const item = playQueue.shift();
  if (!item) { playing = false; return; }
  playing = true;
  if (item.audioB64) {
    currentAudio = new Audio("data:audio/wav;base64," + item.audioB64);
    currentAudio.onended = playNext;
    currentAudio.onerror = playNext;
    currentAudio.play().catch(() => { speakFallback(item.text, playNext); });
  } else {
    speakFallback(item.text, playNext);
  }
}

function speakFallback(text, onend) {
  if (!window.speechSynthesis || !text) { if (onend) onend(); return; }
  const u = new SpeechSynthesisUtterance(text);
  u.lang = "en-US";
  u.rate = 0.95;
  u.onend = () => onend && onend();
  speechSynthesis.speak(u);
}

function stopPlayback() {
  playQueue.length = 0;
  playing = false;
  if (currentAudio) { currentAudio.pause(); currentAudio = null; }
  if (window.speechSynthesis) speechSynthesis.cancel();
}

/* ── 마이크 준비 ─────────────────────────────────────────── */
async function ensureStream() {
  if (stream) return;
  stream = await navigator.mediaDevices.getUserMedia({
    audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
  });
}

function newRecorder() {
  const mime = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
    ? "audio/webm;codecs=opus"
    : (MediaRecorder.isTypeSupported("audio/mp4") ? "audio/mp4" : "");
  return new MediaRecorder(stream, mime ? { mimeType: mime } : {});
}

/* ════════════════════ 버튼 모드 (1단계, REST) ════════════════════ */
async function buttonModeStart() {
  if (recording || busy || handsFree.on) return;
  stopPlayback();
  await ensureStream();
  chunks = [];
  mediaRecorder = newRecorder();
  mediaRecorder.ondataavailable = (e) => { if (e.data.size) chunks.push(e.data); };
  mediaRecorder.onstop = buttonModeSend;
  mediaRecorder.start();
  recording = true;
  micBtn.classList.add("recording");
  setStatus("듣고 있어요… 영어로 말해보세요");
}

function buttonModeStop() {
  if (!recording) return;
  recording = false;
  micBtn.classList.remove("recording");
  mediaRecorder.stop();
}

async function buttonModeSend() {
  const blob = new Blob(chunks, { type: mediaRecorder.mimeType || "audio/webm" });
  chunks = [];
  if (blob.size < 2000) { setStatus("너무 짧아요 — 다시 말해보세요"); return; }

  busy = true;
  micBtn.classList.add("busy");
  setStatus("생각 중…");
  const thinking = addBubble("ai", "…", "thinking");

  try {
    const form = new FormData();
    form.append("audio", blob, "speech.webm");
    const res = await fetch("/api/chat", { method: "POST", body: form });
    if (!res.ok) throw new Error("server " + res.status);
    const data = await res.json();

    thinking.row.remove();
    if (data.empty) { setStatus("잘 못 들었어요 — 다시 말해보세요"); return; }

    const userRow = addBubble("user", data.transcript);
    markUserRow(userRow.row, data.corrections);
    addBubble("ai", data.reply);
    addCorrections(data.corrections);
    enqueueAudio(data.reply, data.audio_b64);
    setStatus("버튼을 누르고 대답해보세요");
  } catch (err) {
    thinking.row.remove();
    console.error(err);
    setStatus("서버 연결에 문제가 있어요 — 잠시 후 다시");
  } finally {
    busy = false;
    micBtn.classList.remove("busy");
  }
}

micBtn.addEventListener("pointerdown", async (e) => {
  e.preventDefault();
  if (handsFree.on) { setStatus("핸즈프리 모드에서는 그냥 말하면 돼요"); return; }
  try { await ensureStream(); } catch {
    setStatus("마이크 권한이 필요해요 (HTTPS 주소로 접속했는지 확인)");
    return;
  }
  if (recording) { buttonModeStop(); return; }   // 탭 토글 정지
  pressStartedAt = Date.now();
  buttonModeStart();
});
micBtn.addEventListener("pointerup", () => {
  if (recording && Date.now() - pressStartedAt >= 300) buttonModeStop();
});
micBtn.addEventListener("pointerleave", () => {
  if (recording && Date.now() - pressStartedAt >= 300) buttonModeStop();
});

/* ════════════════════ 핸즈프리 모드 (2단계, WS) ════════════════════
 * 에너지 기반 VAD: 노이즈 바닥을 측정해 임계값을 잡고,
 * 말 시작(150ms 지속) → 녹음 표시, 말 끝(900ms 침묵) → 발화 전송.
 * Emma가 말하는 중 사용자가 말을 시작하면 재생 즉시 중단(barge-in).
 */
const handsFree = {
  on: false,
  ws: null,
  state: "standby",         // 서버가 알려주는 standby | active
  audioCtx: null,
  analyser: null,
  vadTimer: null,
  recorder: null,
  recChunks: [],
  inSpeech: false,
  speechFrames: 0,
  silenceFrames: 0,
  noiseFloor: 0.008,
  calibFrames: 0,
  calibSum: 0,
  lastRecycle: 0,
  discardNext: false,
  wakeLock: null,
  idleTimer: null,
};

const FRAME_MS = 64;
const START_FRAMES = 3;      // ~190ms 연속 소리 → 말 시작
const END_FRAMES = 14;       // ~900ms 침묵 → 말 끝
const MIN_UTTER_MS = 500;

hfBtn.addEventListener("click", () => (handsFree.on ? hfStop() : hfStart()));

async function hfStart() {
  try { await ensureStream(); } catch {
    setStatus("마이크 권한이 필요해요 (HTTPS 주소로 접속했는지 확인)");
    return;
  }
  stopPlayback();

  // WebSocket 연결
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  handsFree.ws = new WebSocket(`${proto}//${location.host}/ws/chat`);
  handsFree.ws.onmessage = (e) => hfOnMessage(JSON.parse(e.data));
  handsFree.ws.onclose = () => { if (handsFree.on) hfStop("연결이 끊겼어요"); };
  handsFree.ws.onerror = () => {};

  // VAD 준비
  handsFree.audioCtx = new (window.AudioContext || window.webkitAudioContext)();
  const src = handsFree.audioCtx.createMediaStreamSource(stream);
  handsFree.analyser = handsFree.audioCtx.createAnalyser();
  handsFree.analyser.fftSize = 2048;
  src.connect(handsFree.analyser);
  handsFree.calibFrames = 0; handsFree.calibSum = 0;
  handsFree.inSpeech = false; handsFree.speechFrames = 0; handsFree.silenceFrames = 0;

  hfNewRecorder();
  handsFree.vadTimer = setInterval(hfVadTick, FRAME_MS);

  // 화면 꺼짐 방지
  try { handsFree.wakeLock = await navigator.wakeLock?.request("screen"); } catch {}

  handsFree.on = true;
  hfBtn.classList.add("active");
  hfBtn.textContent = "🎙 핸즈프리 켜짐";
  micBtn.classList.add("dimmed");
  setStatus('준비 중… 잠시 조용히 해주세요 (소음 측정)');
}

function hfStop(reason) {
  handsFree.on = false;
  clearInterval(handsFree.vadTimer);
  clearTimeout(handsFree.idleTimer);
  try { handsFree.recorder?.state !== "inactive" && handsFree.recorder.stop(); } catch {}
  handsFree.recorder = null;
  try { handsFree.audioCtx?.close(); } catch {}
  try { handsFree.ws?.close(); } catch {}
  try { handsFree.wakeLock?.release(); } catch {}
  stopPlayback();
  hfBtn.classList.remove("active");
  hfBtn.textContent = "🎙 핸즈프리";
  micBtn.classList.remove("dimmed");
  setStatus(reason || "핸즈프리를 껐어요 — 버튼으로도 대화할 수 있어요");
}

function hfNewRecorder() {
  handsFree.recChunks = [];
  handsFree.recorder = newRecorder();
  handsFree.recorder.ondataavailable = (e) => { if (e.data.size) handsFree.recChunks.push(e.data); };
  handsFree.recorder.onstop = hfOnRecorderStop;
  handsFree.recorder.start();
  handsFree.lastRecycle = Date.now();
}

function hfVadTick() {
  if (!handsFree.analyser) return;
  const buf = new Uint8Array(handsFree.analyser.fftSize);
  handsFree.analyser.getByteTimeDomainData(buf);
  let sum = 0;
  for (let i = 0; i < buf.length; i++) { const v = (buf[i] - 128) / 128; sum += v * v; }
  const rms = Math.sqrt(sum / buf.length);

  // 처음 ~1.3초: 주변 소음 측정
  if (handsFree.calibFrames < 20) {
    handsFree.calibFrames++;
    handsFree.calibSum += rms;
    if (handsFree.calibFrames === 20) {
      handsFree.noiseFloor = handsFree.calibSum / 20;
      hfStatusIdle();
    }
    return;
  }

  let threshold = Math.max(handsFree.noiseFloor * 3, 0.012);
  if (isSpeaking()) threshold *= 2.2;   // Emma 재생 중엔 더 큰 소리만 barge-in으로 인정

  if (rms > threshold) {
    handsFree.speechFrames++;
    handsFree.silenceFrames = 0;
    if (!handsFree.inSpeech && handsFree.speechFrames >= START_FRAMES) {
      handsFree.inSpeech = true;
      handsFree.speechStart = Date.now();
      if (isSpeaking()) stopPlayback();          // ★ barge-in: 즉시 입 다물기
      setStatus("듣고 있어요…");
    }
  } else {
    handsFree.speechFrames = 0;
    if (handsFree.inSpeech) {
      handsFree.silenceFrames++;
      if (handsFree.silenceFrames >= END_FRAMES) {
        handsFree.inSpeech = false;
        handsFree.silenceFrames = 0;
        const dur = Date.now() - handsFree.speechStart;
        handsFree.discardNext = dur < MIN_UTTER_MS;
        handsFree.recorder.stop();               // → hfOnRecorderStop에서 전송
      }
    } else if (Date.now() - handsFree.lastRecycle > 8000) {
      // 오래 조용하면 녹음 버퍼를 비워 메모리/전송량 관리
      handsFree.discardNext = true;
      handsFree.recorder.stop();
    }
  }
}

function hfOnRecorderStop() {
  const blob = new Blob(handsFree.recChunks,
    { type: handsFree.recorder?.mimeType || "audio/webm" });
  const discard = handsFree.discardNext;
  handsFree.discardNext = false;
  if (handsFree.on) hfNewRecorder();             // 즉시 다음 녹음 시작
  if (discard || blob.size < 2000) return;
  if (handsFree.ws?.readyState === WebSocket.OPEN) {
    handsFree.ws.send(blob);
    setStatus("생각 중…");
  }
}

function hfStatusIdle() {
  if (!handsFree.on) return;
  setStatus(handsFree.state === "standby"
    ? '"Hey Emma!" 라고 불러보세요'
    : "말씀하세요 — Emma가 듣고 있어요");
}

function hfOnMessage(msg) {
  if (msg.state) {
    handsFree.state = msg.state;
    hfStatusIdle();
    return;
  }
  switch (msg.type) {
    case "ignored":
      hfStatusIdle();
      break;
    case "wake": {
      const row = addBubble("user", msg.heard);
      markUserRow(row.row, []);
      setStatus("Emma가 인사해요!");
      break;
    }
    case "sentence":
      if (msg.index === 0) addBubble("ai", msg.text).bubble.dataset.streaming = "1";
      else {
        const last = chatEl.querySelector('.bubble.ai[data-streaming="1"]');
        if (last) last.textContent += " " + msg.text;
      }
      enqueueAudio(msg.text, msg.audio_b64);      // 문장 도착 즉시 재생 → 지연 단축
      break;
    case "turn_end": {
      const streamingBubble = chatEl.querySelector('.bubble.ai[data-streaming="1"]');
      if (streamingBubble) delete streamingBubble.dataset.streaming;
      if (msg.transcript && msg.corrections) {
        // 사용자 발화 말풍선을 응답 위에 삽입
        const row = document.createElement("div");
        row.className = "row user-row";
        const b = document.createElement("div");
        b.className = "bubble user";
        b.textContent = msg.transcript;
        row.appendChild(b);
        const aiRow = streamingBubble?.parentElement;
        if (aiRow && msg.transcript !== lastShownTranscript(aiRow)) {
          chatEl.insertBefore(row, aiRow);
          markUserRow(row, msg.corrections);
        }
        addCorrections(msg.corrections);
      }
      hfStatusIdle();
      hfArmIdleTimer();
      break;
    }
    case "session_end":
      addBubble("ai", "Bye! See you next time! 👋");
      showReport(msg.report);
      hfStatusIdle();
      break;
  }
}

function lastShownTranscript(beforeRow) {
  let el = beforeRow.previousElementSibling;
  while (el && !el.classList.contains("user-row")) el = el.previousElementSibling;
  return el ? el.querySelector(".bubble")?.textContent : null;
}

function hfArmIdleTimer() {
  clearTimeout(handsFree.idleTimer);
  // 2분간 대화가 없으면 배터리를 위해 안내만 (연결은 유지)
  handsFree.idleTimer = setTimeout(() => {
    if (handsFree.on && handsFree.state === "active") {
      setStatus('쉬는 중 — 계속하려면 그냥 말하거나, 끝내려면 "Bye Emma"');
    }
  }, 120000);
}

/* ── 리셋/리포트 ─────────────────────────────────────────── */
resetBtn.addEventListener("click", async () => {
  stopPlayback();
  try {
    const res = await fetch("/api/reset", { method: "POST" });
    const data = await res.json();
    showReport(data.report);
  } catch { /* 리포트 실패해도 초기화는 진행 */ }
  chatEl.innerHTML = "";
  setStatus(handsFree.on ? '"Hey Emma!" 라고 불러보세요'
                         : "새 대화를 시작했어요 — 버튼을 누르고 인사해보세요");
});

function showReport(report) {
  if (!report || (!report.sentences_spoken && !report.corrections?.length)) return;
  let html = `<p>오늘 말한 문장: <b>${report.sentences_spoken}개</b></p>`;
  if (report.corrections?.length) {
    html += `<p style="margin-top:8px"><b>오늘 배운 표현 ${report.corrections.length}개</b></p>`;
    for (let i = 0; i < report.corrections.length; i++) {
      html += `<div class="corr-item"><span class="orig"></span> → ` +
              `<span class="fixed"></span><div class="note"></div></div>`;
    }
  }
  reportBody.innerHTML = html;
  const items = reportBody.querySelectorAll(".corr-item");
  (report.corrections || []).forEach((c, i) => {
    items[i].querySelector(".orig").textContent = c.original;
    items[i].querySelector(".fixed").textContent = c.corrected;
    items[i].querySelector(".note").textContent = c.note || "";
  });
  reportModal.classList.remove("hidden");
}
reportClose.addEventListener("click", () => reportModal.classList.add("hidden"));

/* 화면이 다시 보일 때 WakeLock 재요청 (탭 전환 후 복귀) */
document.addEventListener("visibilitychange", async () => {
  if (document.visibilityState === "visible" && handsFree.on) {
    try { handsFree.wakeLock = await navigator.wakeLock?.request("screen"); } catch {}
  }
});
