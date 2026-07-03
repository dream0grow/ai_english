/* AI English PWA — 녹음 → /api/chat → 응답 재생
 * 버튼: 길게 누르는 동안 녹음(press-and-hold), 짧게 탭하면 토글 시작/정지
 */
const micBtn = document.getElementById("micBtn");
const chatEl = document.getElementById("chat");
const statusEl = document.getElementById("status");
const resetBtn = document.getElementById("resetBtn");
const reportModal = document.getElementById("reportModal");
const reportBody = document.getElementById("reportBody");
const reportClose = document.getElementById("reportClose");

let mediaRecorder = null;
let chunks = [];
let recording = false;
let busy = false;
let pressTimer = null;
let pressStartedAt = 0;
let currentAudio = null;

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

/* 발화 옆 ✓/✎ 표시 + 교정 접기 패널 (시장조사 벤치마크 UI 패턴) */
function markUserRow(row, corrections) {
  const mark = document.createElement("div");
  if (corrections.length === 0) {
    mark.className = "mark ok";
    mark.textContent = "✓";
  } else {
    mark.className = "mark fix";
    mark.textContent = "✎ 이렇게 말해봐";
  }
  row.appendChild(mark);
}

function addCorrections(corrections) {
  if (!corrections.length) return;
  const d = document.createElement("details");
  d.className = "corrections";
  const s = document.createElement("summary");
  s.textContent = "이렇게 말하면 더 자연스러워요";
  d.appendChild(s);
  for (const c of corrections) {
    const item = document.createElement("div");
    item.className = "corr-item";
    item.innerHTML =
      `<span class="orig"></span> → <span class="fixed"></span>` +
      `<div class="note"></div>`;
    item.querySelector(".orig").textContent = c.original;
    item.querySelector(".fixed").textContent = c.corrected;
    item.querySelector(".note").textContent = c.note || "";
    d.appendChild(item);
  }
  chatEl.appendChild(d);
  chatEl.scrollTop = chatEl.scrollHeight;
}

function stopPlayback() {
  if (currentAudio) { currentAudio.pause(); currentAudio = null; }
  if (window.speechSynthesis) speechSynthesis.cancel();
}

function playReply(reply, audioB64) {
  stopPlayback();
  if (audioB64) {
    currentAudio = new Audio("data:audio/wav;base64," + audioB64);
    currentAudio.play().catch(() => speakFallback(reply));
  } else {
    speakFallback(reply);
  }
}

function speakFallback(text) {
  if (!window.speechSynthesis || !text) return;
  const u = new SpeechSynthesisUtterance(text);
  u.lang = "en-US";
  u.rate = 0.95;
  speechSynthesis.speak(u);
}

async function ensureRecorder() {
  if (mediaRecorder) return;
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: { echoCancellation: true, noiseSuppression: true },
  });
  const mime = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
    ? "audio/webm;codecs=opus"
    : (MediaRecorder.isTypeSupported("audio/mp4") ? "audio/mp4" : "");
  mediaRecorder = new MediaRecorder(stream, mime ? { mimeType: mime } : {});
  mediaRecorder.ondataavailable = (e) => { if (e.data.size) chunks.push(e.data); };
  mediaRecorder.onstop = onRecordingDone;
}

function startRecording() {
  if (recording || busy) return;
  stopPlayback();
  chunks = [];
  mediaRecorder.start();
  recording = true;
  micBtn.classList.add("recording");
  setStatus("듣고 있어요… 영어로 말해보세요");
}

function stopRecording() {
  if (!recording) return;
  recording = false;
  micBtn.classList.remove("recording");
  mediaRecorder.stop();
}

async function onRecordingDone() {
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
    playReply(data.reply, data.audio_b64);
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

/* 버튼 입력: 300ms 이상 누르면 hold 모드(떼면 전송), 짧은 탭은 토글 */
micBtn.addEventListener("pointerdown", async (e) => {
  e.preventDefault();
  try { await ensureRecorder(); } catch {
    setStatus("마이크 권한이 필요해요 (HTTPS 주소로 접속했는지 확인)");
    return;
  }
  if (recording) { stopRecording(); return; }  // 탭 토글 정지
  pressStartedAt = Date.now();
  startRecording();
  pressTimer = setTimeout(() => { pressTimer = null; }, 300);
});

micBtn.addEventListener("pointerup", () => {
  const held = Date.now() - pressStartedAt;
  if (recording && held >= 300) stopRecording();  // hold 모드: 떼면 전송
  // 300ms 미만의 짧은 탭이면 녹음 유지(토글 모드) — 다시 탭하면 정지
});
micBtn.addEventListener("pointerleave", () => {
  const held = Date.now() - pressStartedAt;
  if (recording && held >= 300) stopRecording();
});

resetBtn.addEventListener("click", async () => {
  stopPlayback();
  try {
    const res = await fetch("/api/reset", { method: "POST" });
    const data = await res.json();
    showReport(data.report);
  } catch { /* 리포트 실패해도 초기화는 진행 */ }
  chatEl.innerHTML = "";
  setStatus("새 대화를 시작했어요 — 버튼을 누르고 인사해보세요");
});

function showReport(report) {
  if (!report || (!report.sentences_spoken && !report.corrections?.length)) return;
  let html = `<p>오늘 말한 문장: <b>${report.sentences_spoken}개</b></p>`;
  if (report.corrections?.length) {
    html += `<p style="margin-top:8px"><b>오늘 배운 표현 ${report.corrections.length}개</b></p>`;
    for (const c of report.corrections) {
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
