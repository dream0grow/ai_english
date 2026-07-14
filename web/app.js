/* AI English PWA
 * 1단계: 버튼 녹음 (누르는 동안 hold / 짧은 탭 토글) → POST /api/chat
 * 2단계: 핸즈프리 — 에너지 기반 VAD + "Hey Emma" 호출어 + barge-in + 문장 스트리밍(WS)
 * 3단계: 가족 프로필(온보딩), 주제/롤플레이/슬랭 카드, 단어장, 리포트 확장
 */
const micBtn = document.getElementById("micBtn");
const chatEl = document.getElementById("chat");
const statusEl = document.getElementById("status");
const resetBtn = document.getElementById("resetBtn");
const hfBtn = document.getElementById("hfBtn");
const reportModal = document.getElementById("reportModal");
const reportBody = document.getElementById("reportBody");
const reportClose = document.getElementById("reportClose");
const profileBtn = document.getElementById("profileBtn");
const cardsBtn = document.getElementById("cardsBtn");
const notebookBtn = document.getElementById("notebookBtn");
const cardBanner = document.getElementById("cardBanner");

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

function addTaught(taught) {
  if (!taught || !taught.length) return;
  for (const t of taught) {
    const chip = document.createElement("div");
    chip.className = "taught-chip";
    chip.innerHTML = `✨ 새 표현 <b></b><span class="meaning"></span>`;
    chip.querySelector("b").textContent = t.expression;
    chip.querySelector(".meaning").textContent = t.meaning ? ` — ${t.meaning}` : "";
    chatEl.appendChild(chip);
  }
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
    addTaught(data.taught);
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
      addTaught(msg.taught);
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
  const mins = Math.max(1, Math.round((report.duration_sec || 0) / 60));
  let html = `<div class="report-stats">
    <div class="stat"><b>${report.sentences_spoken}</b><span>말한 문장</span></div>
    <div class="stat"><b>${mins}분</b><span>대화 시간</span></div>
    <div class="stat"><b>${report.streak_days ?? "-"}${report.streak_days != null ? "일" : ""}</b><span>연속 학습 🔥</span></div>
  </div>`;
  if (report.corrections?.length) {
    html += `<p class="report-section">✎ 이렇게 말하면 더 자연스러워요 (${report.corrections.length})</p>`;
    for (let i = 0; i < report.corrections.length; i++) {
      html += `<div class="corr-item"><span class="orig"></span> → ` +
              `<span class="fixed"></span><div class="note"></div></div>`;
    }
  }
  if (report.taught?.length) {
    html += `<p class="report-section">✨ 오늘 새로 배운 표현 (${report.taught.length})</p>`;
    for (let i = 0; i < report.taught.length; i++) {
      html += `<div class="corr-item" data-taught><span class="fixed"></span><div class="note"></div></div>`;
    }
  }
  html += `<p style="margin-top:12px;font-size:13px;color:var(--sub)">배운 표현은 📒 단어장에 저장됐어요. 다음 대화에서 Emma가 자연스럽게 다시 써줄 거예요.</p>`;
  reportBody.innerHTML = html;
  const items = reportBody.querySelectorAll(".corr-item:not([data-taught])");
  (report.corrections || []).forEach((c, i) => {
    items[i].querySelector(".orig").textContent = c.original;
    items[i].querySelector(".fixed").textContent = c.corrected;
    items[i].querySelector(".note").textContent = c.note || "";
  });
  const titems = reportBody.querySelectorAll(".corr-item[data-taught]");
  (report.taught || []).forEach((t, i) => {
    titems[i].querySelector(".fixed").textContent = t.expression;
    titems[i].querySelector(".note").textContent = t.meaning || "";
  });
  reportModal.classList.remove("hidden");
}
reportClose.addEventListener("click", () => reportModal.classList.add("hidden"));

/* ════════════════════ 3단계: 프로필 · 카드 · 단어장 ════════════════════ */
const profileModal = document.getElementById("profileModal");
const profileList = document.getElementById("profileList");
const profileNew = document.getElementById("profileNew");
const onboardModal = document.getElementById("onboardModal");
const onboardForm = document.getElementById("onboardForm");
const onboardCancel = document.getElementById("onboardCancel");
const cardsModal = document.getElementById("cardsModal");
const cardsBody = document.getElementById("cardsBody");
const notebookModal = document.getElementById("notebookModal");
const notebookBody = document.getElementById("notebookBody");

let activeProfile = null;   // {id, name, kind, ...}

const KIND_EMOJI = { child: "🧒", adult: "🧑" };
const LEVEL_LABEL = { beginner: "기초", intermediate: "중급", advanced: "상급" };

function setProfileChip() {
  if (activeProfile) {
    profileBtn.textContent = `${KIND_EMOJI[activeProfile.kind] || "👤"} ${activeProfile.name}`;
    profileBtn.classList.add("named");
  } else {
    profileBtn.textContent = "👤";
    profileBtn.classList.remove("named");
  }
}

async function loadProfiles() {
  const res = await fetch("/api/profiles");
  const data = await res.json();
  return data;
}

function renderProfileList(profiles, activeId) {
  profileList.innerHTML = "";
  for (const p of profiles) {
    const btn = document.createElement("button");
    btn.className = "profile-item" + (p.id === activeId ? " active" : "");
    btn.innerHTML = `<span class="p-emoji"></span>
      <span><span class="p-name"></span><div class="p-sub"></div></span>`;
    btn.querySelector(".p-emoji").textContent = KIND_EMOJI[p.kind] || "👤";
    btn.querySelector(".p-name").textContent = p.name;
    btn.querySelector(".p-sub").textContent =
      `${p.kind === "child" ? "아이" : "성인"} · ${LEVEL_LABEL[p.level] || p.level}`;
    btn.addEventListener("click", () => selectProfile(p.id));
    profileList.appendChild(btn);
  }
}

async function selectProfile(pid) {
  try {
    const res = await fetch(`/api/profiles/${pid}/select`, { method: "POST" });
    if (!res.ok) throw new Error("select failed");
    const data = await res.json();
    activeProfile = data.profile;
    setProfileChip();
    profileModal.classList.add("hidden");
    chatEl.innerHTML = "";
    cardBanner.classList.add("hidden");
    stopPlayback();
    const streak = data.streak_days ? ` (연속 ${data.streak_days}일째 🔥)` : "";
    setStatus(`${activeProfile.name}로 시작!${streak} — ` +
      (handsFree.on ? '"Hey Emma!" 라고 불러보세요' : "버튼을 누르고 인사해보세요"));
  } catch {
    setStatus("프로필 전환에 실패했어요 — 다시 시도해주세요");
  }
}

async function openProfilePicker() {
  const data = await loadProfiles();
  if (!data.profiles.length) { openOnboarding(); return; }
  renderProfileList(data.profiles, data.active);
  profileModal.classList.remove("hidden");
}

profileBtn.addEventListener("click", openProfilePicker);
profileNew.addEventListener("click", () => {
  profileModal.classList.add("hidden");
  openOnboarding();
});

/* ── 온보딩 폼 ── */
function openOnboarding() {
  onboardForm.reset();
  onboardModal.querySelectorAll(".seg, .radio-col").forEach((group) => {
    group.querySelectorAll("button").forEach((b, i) =>
      b.classList.toggle("on", b.dataset.val === "adult" || (group.dataset.name === "level" && i === 0)));
  });
  onboardModal.classList.remove("hidden");
}
onboardCancel.addEventListener("click", async () => {
  onboardModal.classList.add("hidden");
  const data = await loadProfiles();
  if (data.profiles.length) openProfilePicker();
});

// 세그먼트/라디오 버튼 토글 (kind, level)
onboardModal.querySelectorAll(".seg, .radio-col").forEach((group) => {
  group.querySelectorAll("button").forEach((btn) => {
    btn.addEventListener("click", () => {
      group.querySelectorAll("button").forEach((b) => b.classList.remove("on"));
      btn.classList.add("on");
    });
  });
});

onboardForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = new FormData(onboardForm);
  const body = {
    name: (form.get("name") || "").trim(),
    kind: onboardModal.querySelector('.seg[data-name="kind"] button.on')?.dataset.val || "adult",
    level: onboardModal.querySelector('.radio-col[data-name="level"] button.on')?.dataset.val || "beginner",
    goals: (form.get("goals") || "").trim(),
    interests: (form.get("interests") || "").trim(),
  };
  try {
    const res = await fetch("/api/profiles", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (!res.ok) {
      setStatus(data.error === "name_exists" ? "이미 있는 이름이에요" : "프로필 생성 실패");
      return;
    }
    activeProfile = data.profile;
    setProfileChip();
    onboardModal.classList.add("hidden");
    chatEl.innerHTML = "";
    setStatus(`${activeProfile.name}, 반가워요! — ` +
      (handsFree.on ? '"Hey Emma!" 라고 불러보세요' : "버튼을 누르고 인사해보세요"));
  } catch {
    setStatus("서버 연결에 문제가 있어요 — 잠시 후 다시");
  }
});

/* ── 카드 (주제/롤플레이/슬랭) ── */
const CARD_GROUP_LABEL = { topic: "🗣 주제", roleplay: "🎭 롤플레이", slang: "✨ 표현 배우기" };

cardsBtn.addEventListener("click", async () => {
  try {
    const res = await fetch("/api/cards");
    const data = await res.json();
    renderCards(data.cards, data.active);
    cardsModal.classList.remove("hidden");
  } catch { setStatus("카드를 불러오지 못했어요"); }
});

function renderCards(cardList, activeId) {
  cardsBody.innerHTML = "";
  const free = document.createElement("button");
  free.className = "card-item" + (activeId ? "" : " active");
  free.innerHTML = `<span class="c-emoji">💬</span><span><span class="c-title">자유 대화</span>
    <div class="c-desc">주제 없이 편하게 수다</div></span>`;
  free.addEventListener("click", () => pickCard(null));
  cardsBody.appendChild(free);

  const groups = {};
  for (const c of cardList) (groups[c.kind] ||= []).push(c);
  for (const kind of ["topic", "roleplay", "slang"]) {
    if (!groups[kind]) continue;
    const wrap = document.createElement("div");
    wrap.className = "cards-group";
    wrap.innerHTML = `<h3>${CARD_GROUP_LABEL[kind] || kind}</h3>`;
    for (const c of groups[kind]) {
      const btn = document.createElement("button");
      btn.className = "card-item" + (c.id === activeId ? " active" : "");
      btn.innerHTML = `<span class="c-emoji"></span><span><span class="c-title"></span>
        <div class="c-desc"></div></span>`;
      btn.querySelector(".c-emoji").textContent = c.emoji;
      btn.querySelector(".c-title").textContent = c.title;
      btn.querySelector(".c-desc").textContent = c.desc;
      btn.addEventListener("click", () => pickCard(c));
      wrap.appendChild(btn);
    }
    cardsBody.appendChild(wrap);
  }
}

async function pickCard(card) {
  try {
    const res = await fetch("/api/cards/select", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ card_id: card ? card.id : null }),
    });
    if (!res.ok) throw new Error();
    cardsModal.classList.add("hidden");
    chatEl.innerHTML = "";
    stopPlayback();
    if (card) {
      cardBanner.textContent = `${card.emoji} ${card.title} — ${card.desc}`;
      cardBanner.classList.remove("hidden");
      setStatus(handsFree.on ? '"Hey Emma!" 라고 부르면 시작해요'
                             : "버튼을 누르고 시작해보세요");
    } else {
      cardBanner.classList.add("hidden");
      setStatus("자유 대화로 바꿨어요");
    }
  } catch { setStatus("카드 선택에 실패했어요"); }
}

document.getElementById("cardsClose").addEventListener("click",
  () => cardsModal.classList.add("hidden"));

/* ── 단어장 ── */
notebookBtn.addEventListener("click", async () => {
  try {
    const res = await fetch("/api/notebook");
    if (res.status === 400) { setStatus("먼저 프로필을 선택해주세요"); openProfilePicker(); return; }
    const data = await res.json();
    renderNotebook(data.items);
    notebookModal.classList.remove("hidden");
  } catch { setStatus("단어장을 불러오지 못했어요"); }
});

function renderNotebook(items) {
  if (!items.length) {
    notebookBody.innerHTML =
      `<p class="nb-empty">아직 비어 있어요. Emma와 대화하면 교정받은 문장과 새 표현이 자동으로 저장돼요.</p>`;
    return;
  }
  notebookBody.innerHTML = "";
  for (const it of items) {
    const d = document.createElement("div");
    d.className = "nb-item";
    d.innerHTML = `<span class="nb-expr"></span><span class="nb-tag"></span>
      <div class="nb-meaning"></div>`;
    d.querySelector(".nb-expr").textContent = it.expression;
    const tag = d.querySelector(".nb-tag");
    tag.textContent = it.source === "taught" ? "새 표현" : "교정";
    tag.classList.add(it.source);
    d.querySelector(".nb-meaning").textContent = it.meaning || "";
    notebookBody.appendChild(d);
  }
}

document.getElementById("notebookClose").addEventListener("click",
  () => notebookModal.classList.add("hidden"));

/* ── 시작: 프로필 선택부터 (가족 공용 기기) ── */
(async function init() {
  try {
    const data = await loadProfiles();
    if (!data.profiles.length) { openOnboarding(); return; }
    if (data.active) {
      activeProfile = data.profiles.find((p) => p.id === data.active) || null;
      setProfileChip();
    }
    if (!activeProfile) openProfilePicker();
  } catch { /* 서버 미기동 등 — 기존 동작(프로필 없이)로 진행 */ }
})();

/* 화면이 다시 보일 때 WakeLock 재요청 (탭 전환 후 복귀) */
document.addEventListener("visibilitychange", async () => {
  if (document.visibilityState === "visible" && handsFree.on) {
    try { handsFree.wakeLock = await navigator.wakeLock?.request("screen"); } catch {}
  }
});
