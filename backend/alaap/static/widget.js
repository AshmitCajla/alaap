/* Alaap web widget.
 * Embed: <script src="https://YOUR-ALAAP-HOST/widget.js" data-business="your-slug" defer></script>
 * Text chat, voice messages, and a live call screen that streams audio both ways.
 */
(function () {
  const script = document.currentScript || document.querySelector("script[data-business]");
  const SLUG = script.getAttribute("data-business");
  const API = script.getAttribute("data-api") || new URL(script.src).origin;
  const INLINE = script.getAttribute("data-inline") === "true";
  let info = null, conv = null, busy = false;

  const css = `
  .alaap-btn{position:fixed;right:20px;bottom:20px;width:60px;height:60px;border-radius:50%;border:0;
    background:#0f766e;color:#fff;font-size:26px;box-shadow:0 6px 20px rgba(0,0,0,.25);cursor:pointer;z-index:99999}
  .alaap-box{position:fixed;right:20px;bottom:92px;width:370px;max-width:calc(100vw - 32px);height:600px;
    max-height:calc(100vh - 120px);background:#fff;border-radius:20px;box-shadow:0 12px 40px rgba(0,0,0,.25);
    display:none;flex-direction:column;overflow:hidden;font:15px/1.45 system-ui,-apple-system,sans-serif;color:#1f2937;z-index:99999}
  .alaap-box.inline{position:relative;display:flex;width:100%;max-width:440px;height:640px;margin:0 auto;right:auto;bottom:auto}
  .alaap-box.open{display:flex}
  .alaap-head{background:#0f766e;color:#fff;padding:12px 14px;display:flex;align-items:center;gap:10px}
  .alaap-av{width:38px;height:38px;border-radius:50%;background:#14b8a6;display:grid;place-items:center;font-weight:700}
  .alaap-head .t{flex:1;line-height:1.25}.alaap-head small{opacity:.85;display:block;font-size:12px}
  .alaap-log{flex:1;overflow-y:auto;padding:12px;background:#f4f6f8;display:flex;flex-direction:column;gap:8px}
  .alaap-m{max-width:82%;padding:9px 12px;border-radius:16px;white-space:pre-wrap;word-wrap:break-word}
  .alaap-m.a{background:#fff;border:1px solid #e5e7eb;align-self:flex-start;border-bottom-left-radius:4px}
  .alaap-m.u{background:#0f766e;color:#fff;align-self:flex-end;border-bottom-right-radius:4px}
  .alaap-chips{display:flex;flex-wrap:wrap;gap:6px;margin-top:2px}
  .alaap-chips button{border:1px solid #b9dcd8;background:#fff;color:#0f766e;border-radius:16px;padding:6px 12px;font:inherit;
    font-size:13.5px;cursor:pointer}.alaap-chips button:hover{background:#e6f2f1}
  .alaap-m.n{align-self:center;background:none;color:#6b7280;font-size:13px;padding:2px}
  .alaap-typing{display:inline-flex;gap:4px}.alaap-typing i{width:6px;height:6px;border-radius:50%;background:#9ca3af;
    animation:alaapdot 1s infinite}.alaap-typing i:nth-child(2){animation-delay:.15s}.alaap-typing i:nth-child(3){animation-delay:.3s}
  @keyframes alaapdot{0%,80%,100%{opacity:.3;transform:translateY(0)}40%{opacity:1;transform:translateY(-3px)}}
  .alaap-bar{display:flex;gap:6px;padding:10px;border-top:1px solid #e5e7eb;background:#fff}
  .alaap-bar input{flex:1;border:1px solid #d1d5db;border-radius:20px;padding:9px 14px;font:inherit;outline:none;min-width:0}
  .alaap-bar button{border:0;border-radius:20px;background:#e6f2f1;color:#0f766e;padding:0 12px;font:inherit;cursor:pointer;min-width:42px}
  .alaap-bar button.on{background:#dc2626;color:#fff}
  .alaap-callbtn{background:#fff;color:#0f766e;border:0;border-radius:18px;padding:7px 14px;font:inherit;font-weight:600;cursor:pointer}
  .alaap-call{position:absolute;inset:0;background:linear-gradient(180deg,#0b3b37 0%,#0f766e 60%,#115e59 100%);color:#fff;
    display:none;flex-direction:column;align-items:center;padding:28px 20px 22px;z-index:2}
  .alaap-call.on{display:flex}
  .alaap-call .who{font-size:20px;font-weight:650;margin-top:6px}.alaap-call .biz{opacity:.8;font-size:13px}
  .alaap-call .timer{opacity:.75;font-size:13px;margin-top:4px;font-variant-numeric:tabular-nums}
  .alaap-orbwrap{flex:1;display:grid;place-items:center;width:100%}
  .alaap-orb{width:150px;height:150px;border-radius:50%;position:relative;
    background:radial-gradient(circle at 35% 30%,#ccfbf1,#5eead4 35%,#14b8a6 65%,#0f766e);
    box-shadow:0 0 60px rgba(94,234,212,.45);transition:transform .08s linear}
  .alaap-orb::after{content:"";position:absolute;inset:-14px;border-radius:50%;border:3px solid rgba(255,255,255,.0);
    transition:border-color .2s, transform .08s linear}
  .alaap-orb.user::after{border-color:rgba(255,255,255,.55)}
  .alaap-orb.thinking{animation:alaapthink 1.4s ease-in-out infinite}
  @keyframes alaapthink{0%,100%{filter:brightness(1);transform:scale(.96)}50%{filter:brightness(1.15);transform:scale(1.02)}}
  .alaap-status{font-size:14px;opacity:.9;min-height:20px}
  .alaap-caption{min-height:66px;max-width:100%;text-align:center;font-size:15px;margin:10px 0 16px;opacity:.95}
  .alaap-caption .you{opacity:.7;font-size:13px;display:block}
  .alaap-ctrls{display:flex;gap:22px}
  .alaap-ctrls button{width:60px;height:60px;border-radius:50%;border:0;font-size:24px;cursor:pointer;color:#fff;background:rgba(255,255,255,.18)}
  .alaap-ctrls button.end{background:#dc2626}.alaap-ctrls button.muted{background:#fff;color:#0f766e}
  .alaap-ctrls small{display:block;text-align:center;font-size:11px;opacity:.8;margin-top:4px}`;
  const style = document.createElement("style"); style.textContent = css; document.head.appendChild(style);

  const box = document.createElement("div");
  box.className = "alaap-box" + (INLINE ? " inline" : "");
  box.innerHTML = `<div class="alaap-head"><div class="alaap-av">A</div><div class="t"><b class="nm">…</b>
      <small>AI assistant · Hindi, Punjabi, English</small></div>
      <button class="alaap-callbtn" title="Talk on a live call">📞 Call</button></div>
    <div class="alaap-log"></div>
    <div class="alaap-bar"><input placeholder="Type or tap the mic…" /><button class="mic" title="Voice message">🎤</button>
      <button class="send" title="Send">➤</button></div>
    <div class="alaap-call"><div class="biz"></div><div class="who"></div><div class="timer">00:00</div>
      <div class="alaap-orbwrap"><div class="alaap-orb"></div></div>
      <div class="alaap-status">Connecting…</div><div class="alaap-caption"></div>
      <div class="alaap-ctrls"><div><button class="mute" title="Mute">🎙️</button><small>Mute</small></div>
        <div><button class="end" title="End call">✕</button><small>End</small></div></div></div>`;
  const $ = (s) => box.querySelector(s);
  const log = $(".alaap-log"), input = $("input"), micBtn = $(".mic"), callBtn = $(".alaap-callbtn");
  if (INLINE) script.parentNode.insertBefore(box, script);
  else {
    document.body.appendChild(box);
    const btn = document.createElement("button");
    btn.className = "alaap-btn"; btn.textContent = "💬"; btn.title = "Talk to us";
    btn.onclick = () => { box.classList.toggle("open"); if (box.classList.contains("open")) ensureStarted(); };
    document.body.appendChild(btn);
  }

  function add(text, who) {
    const m = document.createElement("div"); m.className = "alaap-m " + who; m.textContent = text;
    log.appendChild(m); log.scrollTop = log.scrollHeight; return m;
  }
  function typing() {
    const m = document.createElement("div"); m.className = "alaap-m a";
    m.innerHTML = '<span class="alaap-typing"><i></i><i></i><i></i></span>';
    log.appendChild(m); log.scrollTop = log.scrollHeight; return m;
  }
  async function api(path, body, form) {
    const r = await fetch(API + path, form ? { method: "POST", body } :
      { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || r.statusText);
    return r.json();
  }
  async function loadInfo() {
    if (info) return info;
    info = await (await fetch(API + "/api/public/" + SLUG)).json();
    $(".nm").textContent = `${info.assistant} · ${info.name}`;
    $(".alaap-av").textContent = (info.assistant || "A")[0];
    $(".alaap-call .who").textContent = info.assistant; $(".alaap-call .biz").textContent = info.name;
    return info;
  }
  async function ensureStarted() {
    if (conv) return conv;
    await loadInfo();
    conv = await api("/api/chat/" + SLUG + "/start", {});
    add(conv.text, "a");
    chips();
    return conv;
  }

  // One-tap starters so a first-time visitor doesn't face an empty box.
  function chips() {
    const sk = new Set((info && info.skills) || []);
    const opts = [["Rate list", "Aapke rates kya hain?"]];
    if (sk.has("appointments")) opts.push(["Book a slot", "Mujhe appointment book karni hai"]);
    if (sk.has("orders")) opts.push(["Place an order", "Mujhe order karna hai"]);
    if (sk.has("leads")) opts.push(["Fees & batches", "Fees aur batch timings batao"]);
    opts.push(["Timings", "Aap kab khule ho?"], ["Address", "Address kya hai?"]);
    const row = document.createElement("div"); row.className = "alaap-chips";
    opts.forEach(([label, say]) => {
      const b = document.createElement("button"); b.textContent = label;
      b.onclick = () => { row.remove(); send(say); };
      row.appendChild(b);
    });
    log.appendChild(row); log.scrollTop = log.scrollHeight;
  }

  async function send(text) {
    text = (text || "").trim(); if (!text || busy) return;
    const c = log.querySelector(".alaap-chips"); if (c) c.remove();
    busy = true; input.value = ""; add(text, "u");
    const t = typing();
    try {
      await ensureStarted();
      const r = await api(`/api/chat/${conv.conversation_id}/message`, { text, token: conv.token });
      t.textContent = r.text; speakFallback(r.text);
    } catch (e) { t.textContent = "Sorry, something went wrong: " + e.message; }
    busy = false;
  }
  $(".send").onclick = () => send(input.value);
  input.addEventListener("keydown", (e) => { if (e.key === "Enter") send(input.value); });

  /* ---------- browser speech fallback (only when the server has no Gnani key) ---------- */
  let usedBrowserMic = false;
  function speakFallback(text) {
    if ((info && info.voice) || !usedBrowserMic || !window.speechSynthesis) return;
    const u = new SpeechSynthesisUtterance(text); u.lang = "hi-IN"; speechSynthesis.speak(u);
  }

  /* ---------- audio helpers ---------- */
  function downsample(buf, from, to) {
    if (from === to) return buf;
    const ratio = from / to, out = new Float32Array(Math.floor(buf.length / ratio));
    for (let i = 0; i < out.length; i++) {  // average to avoid aliasing hiss
      const a = Math.floor(i * ratio), b = Math.min(buf.length, Math.floor((i + 1) * ratio));
      let s = 0; for (let j = a; j < b; j++) s += buf[j]; out[i] = s / Math.max(1, b - a);
    }
    return out;
  }
  function toPCM16(f32) {
    const out = new Int16Array(f32.length);
    for (let i = 0; i < f32.length; i++) { const s = Math.max(-1, Math.min(1, f32[i])); out[i] = s < 0 ? s * 0x8000 : s * 0x7fff; }
    return out;
  }
  function wav(pcm16, rate) {
    const b = new ArrayBuffer(44 + pcm16.length * 2), v = new DataView(b);
    const w = (o, s) => { for (let i = 0; i < s.length; i++) v.setUint8(o + i, s.charCodeAt(i)); };
    w(0, "RIFF"); v.setUint32(4, 36 + pcm16.length * 2, true); w(8, "WAVE"); w(12, "fmt ");
    v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 1, true); v.setUint32(24, rate, true);
    v.setUint32(28, rate * 2, true); v.setUint16(32, 2, true); v.setUint16(34, 16, true); w(36, "data");
    v.setUint32(40, pcm16.length * 2, true); new Int16Array(b, 44).set(pcm16); return new Blob([b], { type: "audio/wav" });
  }
  const b64 = (u8) => { let s = ""; for (let i = 0; i < u8.length; i += 0x8000) s += String.fromCharCode.apply(null, u8.subarray(i, i + 0x8000)); return btoa(s); };
  const unb64 = (s) => Uint8Array.from(atob(s), (c) => c.charCodeAt(0));
  const level = (f32) => { let s = 0; for (let i = 0; i < f32.length; i += 4) s += f32[i] * f32[i]; return Math.sqrt(s / (f32.length / 4)); };

  async function micStream(onChunk) {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } });
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const src = ctx.createMediaStreamSource(stream), proc = ctx.createScriptProcessor(2048, 1, 1);
    proc.onaudioprocess = (e) => onChunk(downsample(e.inputBuffer.getChannelData(0), ctx.sampleRate, 16000));
    src.connect(proc); proc.connect(ctx.destination);
    return { stop: () => { proc.disconnect(); src.disconnect(); stream.getTracks().forEach((t) => t.stop()); ctx.close(); },
             track: stream.getAudioTracks()[0] };
  }

  /* ---------- voice message (tap to start, tap to send) ---------- */
  let rec = null, chunks = [], recognizer = null;
  micBtn.onclick = async () => {
    await ensureStarted();
    if (info.voice) {
      if (rec) {
        rec.stop(); rec = null; micBtn.classList.remove("on");
        const total = chunks.reduce((n, c) => n + c.length, 0), all = new Float32Array(total);
        let o = 0; chunks.forEach((c) => { all.set(c, o); o += c.length; });
        const fd = new FormData(); fd.append("token", conv.token); fd.append("audio", wav(toPCM16(all), 16000), "voice.wav");
        const note = add("🎤 …", "u"), t = typing();
        try {
          const r = await api(`/api/chat/${conv.conversation_id}/voice`, fd, true);
          note.textContent = "🎤 " + (r.heard || "(not clear)"); t.textContent = r.text;
          if (r.audio) new Audio("data:audio/wav;base64," + r.audio).play();
        } catch (e) { t.textContent = "Sorry: " + e.message; }
        return;
      }
      chunks = []; rec = await micStream((c) => chunks.push(c)); micBtn.classList.add("on");
      return;
    }
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) { add("Voice isn't available in this browser; please type.", "n"); return; }
    if (recognizer) { recognizer.stop(); return; }
    recognizer = new SR(); recognizer.lang = "hi-IN"; recognizer.interimResults = false;
    recognizer.onresult = (e) => { usedBrowserMic = true; send(e.results[0][0].transcript); };
    recognizer.onend = () => { recognizer = null; micBtn.classList.remove("on"); };
    micBtn.classList.add("on"); recognizer.start();
  };

  /* ---------- live call screen ---------- */
  let call = null;
  const screen = $(".alaap-call"), orb = $(".alaap-orb"), statusEl = $(".alaap-status"), caption = $(".alaap-caption");
  const STATUS = (n, f) => ({
    listening: `${n} sun ${f ? "rahi" : "raha"} hai…`, thinking: `${n} dekh ${f ? "rahi" : "raha"} hai…`,
    speaking: `${n} bol ${f ? "rahi" : "raha"} hai`, connecting: "Connecting…" });

  callBtn.onclick = async () => {
    if (call) return;
    await loadInfo().catch(() => {});
    if (!info || !info.voice) { await ensureStarted().catch(() => {}); add("Live calls need the server's Gnani key. Use the mic or type instead.", "n"); return; }
    const S = STATUS(info.assistant, info.female);
    screen.classList.add("on"); statusEl.textContent = S.connecting; caption.innerHTML = "";
    const ws = new WebSocket(API.replace(/^http/, "ws") + "/ws/call/" + SLUG);
    const out = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
    const gain = out.createGain(), analyser = out.createAnalyser(); analyser.fftSize = 512;
    gain.connect(analyser); analyser.connect(out.destination);
    let playAt = 0, sources = [], mic = null, muted = false, micLevel = 0, state = "connecting", raf = 0, micBlocked = false;
    const started = Date.now();
    const timer = setInterval(() => {
      const s = Math.floor((Date.now() - started) / 1000);
      $(".timer").textContent = String(Math.floor(s / 60)).padStart(2, "0") + ":" + String(s % 60).padStart(2, "0");
    }, 500);
    const buf = new Uint8Array(analyser.fftSize);
    const animate = () => {
      analyser.getByteTimeDomainData(buf);
      let s = 0; for (let i = 0; i < buf.length; i++) { const x = (buf[i] - 128) / 128; s += x * x; }
      const out = Math.sqrt(s / buf.length);
      const talking = out > 0.02;
      orb.style.transform = `scale(${1 + Math.min(0.35, out * 2.2)})`;
      orb.classList.toggle("user", !talking && micLevel > 0.04);
      orb.classList.toggle("thinking", state === "thinking" && !talking);
      if (orb.classList.contains("user")) orb.style.transform = `scale(${1 + Math.min(0.12, micLevel)})`;
      raf = requestAnimationFrame(animate);
    };
    animate();
    const setCaption = (who, text) => {
      if (who === "customer") caption.innerHTML = `<span class="you">You: ${text.replace(/</g, "&lt;")}</span>`;
      else caption.innerHTML = (caption.querySelector(".you")?.outerHTML || "") + text.replace(/</g, "&lt;");
    };

    ws.onopen = async () => {
      ws.send(JSON.stringify({ event: "start", start: { media_format: { sample_rate: 16000 } } }));
      try {
        mic = await micStream((f32) => {
          micLevel = level(f32);
          if (muted) f32 = new Float32Array(f32.length);
          if (ws.readyState === 1) ws.send(JSON.stringify({ event: "media", media: { payload: b64(new Uint8Array(toPCM16(f32).buffer)) } }));
        });
      } catch (e) { micBlocked = true; statusEl.textContent = "Microphone blocked. Allow it in the browser and call again."; }
    };
    ws.onmessage = (e) => {
      const m = JSON.parse(e.data);
      if (m.event === "media") {
        const u8 = unb64(m.media.payload), pcm = new Int16Array(u8.buffer, u8.byteOffset, u8.byteLength / 2);
        const ab = out.createBuffer(1, pcm.length, 16000), ch = ab.getChannelData(0);
        for (let i = 0; i < pcm.length; i++) ch[i] = pcm[i] / 0x8000;
        const src = out.createBufferSource(); src.buffer = ab; src.connect(gain);
        playAt = Math.max(playAt, out.currentTime + 0.03); src.start(playAt); playAt += ab.duration; sources.push(src);
        src.onended = () => { sources = sources.filter((x) => x !== src); };
      } else if (m.event === "clear") {
        sources.forEach((s) => { try { s.stop(); } catch (_) {} }); sources = []; playAt = 0;
      } else if (m.event === "state") {
        state = m.state; if (!micBlocked) statusEl.textContent = S[m.state] || "";
      } else if (m.event === "transcript") {
        setCaption(m.role, m.text);
        add(m.text, m.role === "customer" ? "u" : "a");
      }
    };
    const hangup = () => {
      if (!call) return;
      try { ws.send(JSON.stringify({ event: "stop" })); } catch (_) {}
      try { ws.close(); } catch (_) {}
      if (mic) mic.stop(); cancelAnimationFrame(raf); clearInterval(timer);
      setTimeout(() => out.close(), 300);
      screen.classList.remove("on"); call = null; add("Call ended", "n");
    };
    ws.onclose = () => {
      // let the goodbye finish playing before closing the screen
      const left = Math.max(0, playAt - out.currentTime) * 1000;
      setTimeout(hangup, left + 300);
    };
    $(".end").onclick = hangup;
    $(".mute").onclick = () => { muted = !muted; $(".mute").classList.toggle("muted", muted); };
    call = { hangup };
  };

  if (INLINE) ensureStarted().catch((e) => add("Could not connect: " + e.message, "n"));
})();
