/* Injected into every page during recording (Playwright add_init_script). Nothing here changes the app:
 * - a visible cursor, click ripples, smooth zoom and highlight rings (headless browsers draw no cursor);
 * - the "microphone" for the call is a synthetic caller voice we play on cue (window.__callerSay);
 * - every audio buffer the page plays, and every call event from the server, is logged with wall-clock time
 *   so the real call audio can be put back on the video's soundtrack. */
(() => {
  if (window.__demo) return;
  const D = (window.__demo = { audio: [], events: [], media: [] });

  // ---------- audio capture ----------
  let nextId = 1;
  const start = AudioBufferSourceNode.prototype.start;
  AudioBufferSourceNode.prototype.start = function (when = 0, offset = 0, duration) {
    try {
      const ctx = this.context, delay = Math.max(0, (when || 0) - ctx.currentTime);
      this.__id = nextId++;
      D.audio.push({ id: this.__id, t: Date.now() + delay * 1000, rate: this.buffer.sampleRate,
                     tag: ctx.__tag || "app", pcm: new Float32Array(this.buffer.getChannelData(0)) });
    } catch (_) {}
    return start.apply(this, arguments);
  };
  const stop = AudioBufferSourceNode.prototype.stop;
  AudioBufferSourceNode.prototype.stop = function () {
    try { D.audio.push({ id: this.__id, stopAt: Date.now() }); } catch (_) {}
    return stop.apply(this, arguments);
  };
  const play = HTMLMediaElement.prototype.play;
  HTMLMediaElement.prototype.play = function () {
    try { if (this.src && this.src.startsWith("data:audio")) D.media.push({ t: Date.now(), src: this.src }); } catch (_) {}
    return play.apply(this, arguments);
  };
  D.dump = () => {  // Int16 base64 per buffer, for the recorder
    const out = [];
    for (const a of D.audio) {
      if (!a.pcm) { out.push({ id: a.id, stopAt: a.stopAt }); continue; }
      const i16 = new Int16Array(a.pcm.length);
      for (let i = 0; i < a.pcm.length; i++) i16[i] = Math.max(-1, Math.min(1, a.pcm[i])) * 32767;
      const u8 = new Uint8Array(i16.buffer); let s = "";
      for (let i = 0; i < u8.length; i += 0x8000) s += String.fromCharCode.apply(null, u8.subarray(i, i + 0x8000));
      out.push({ id: a.id, t: a.t, rate: a.rate, tag: a.tag, b64: btoa(s) });
    }
    return { audio: out, events: D.events, media: D.media };
  };

  // ---------- call events (transcripts and states) ----------
  const WS = window.WebSocket;
  window.WebSocket = function (url, p) {
    const ws = p ? new WS(url, p) : new WS(url);
    ws.addEventListener("message", (e) => {
      try {
        const m = JSON.parse(e.data);
        if (m.event === "transcript" || m.event === "state") {
          D.events.push({ t: Date.now(), ...m });
          window.dispatchEvent(new CustomEvent("demo-call", { detail: m }));
        }
      } catch (_) {}
    });
    return ws;
  };
  window.WebSocket.prototype = WS.prototype;
  Object.assign(window.WebSocket, { CONNECTING: 0, OPEN: 1, CLOSING: 2, CLOSED: 3 });

  // ---------- synthetic caller microphone ----------
  let callerCtx = null, callerDest = null;
  const ensureCaller = () => {
    if (!callerCtx) { callerCtx = new AudioContext(); callerCtx.__tag = "caller"; callerDest = callerCtx.createMediaStreamDestination(); }
  };
  if (navigator.mediaDevices) {
    navigator.mediaDevices.getUserMedia = async () => { ensureCaller(); await callerCtx.resume(); return callerDest.stream; };
  }
  window.__callerSay = async (b64) => {
    ensureCaller(); await callerCtx.resume();
    const ab = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0)).buffer;
    const buf = await callerCtx.decodeAudioData(ab);
    const s = callerCtx.createBufferSource(); s.buffer = buf; s.connect(callerDest); s.start();
    return buf.duration;
  };
  D.callState = () => {
    const app = D.audio.filter((a) => a.tag === "app" && a.pcm);
    const lastEnd = app.reduce((m, a) => Math.max(m, a.t + (a.pcm.length / a.rate) * 1000), 0);
    const lastAt = app.reduce((m, a) => Math.max(m, a.t), 0);
    return { now: Date.now(), lastEnd, lastAt, events: D.events.map((e) => ({ t: e.t, event: e.event, role: e.role, text: e.text, state: e.state })) };
  };

  // ---------- cursor, ripple, zoom, highlight ----------
  const css = `
    #__cur{position:fixed;left:0;top:0;width:26px;height:26px;z-index:2147483647;pointer-events:none;
      transition:transform .7s cubic-bezier(.4,.0,.2,1);transform:translate(960px,1180px)}
    #__cur svg{filter:drop-shadow(0 2px 3px rgba(0,0,0,.35))}
    .__ripple{position:fixed;width:44px;height:44px;margin:-22px 0 0 -22px;border-radius:50%;z-index:2147483646;pointer-events:none;
      border:3px solid rgba(13,122,111,.9);animation:__rip .55s ease-out forwards}
    @keyframes __rip{from{transform:scale(.3);opacity:1}to{transform:scale(1.5);opacity:0}}
    .__hl{position:fixed;z-index:2147483645;pointer-events:none;border:3px solid #e8a33d;border-radius:12px;
      box-shadow:0 0 0 6px rgba(232,163,61,.25);animation:__hlin .35s ease-out}
    @keyframes __hlin{from{opacity:0;transform:scale(1.04)}to{opacity:1;transform:scale(1)}}`;
  const boot = () => {
    if (document.getElementById("__cur")) return;
    const st = document.createElement("style"); st.textContent = css; document.head.appendChild(st);
    const c = document.createElement("div"); c.id = "__cur";
    c.innerHTML = '<svg width="26" height="26" viewBox="0 0 24 24"><path d="M4 2l15 11-6.5 1.2L9 21z" fill="#111" stroke="#fff" stroke-width="1.6" stroke-linejoin="round"/></svg>';
    document.body.appendChild(c);
    try { const p = JSON.parse(sessionStorage.__curpos || "null"); if (p) { c.style.transition = "none"; c.style.transform = `translate(${p[0]}px,${p[1]}px)`; } } catch (_) {}
  };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot); else boot();
  D.move = (x, y, ms = 700) => {
    boot(); const c = document.getElementById("__cur");
    c.style.transition = `transform ${ms}ms cubic-bezier(.4,0,.2,1)`; c.style.transform = `translate(${x - 4}px,${y - 2}px)`;
    try { sessionStorage.__curpos = JSON.stringify([x - 4, y - 2]); } catch (_) {}
  };
  D.ripple = (x, y) => { const r = document.createElement("div"); r.className = "__ripple"; r.style.left = x + "px"; r.style.top = y + "px";
    document.body.appendChild(r); setTimeout(() => r.remove(), 700); };
  D.zoom = (x, y, s = 1.35, ms = 900) => {
    const b = document.documentElement;
    b.style.transition = `transform ${ms}ms cubic-bezier(.4,0,.2,1)`;
    b.style.transformOrigin = `${x + scrollX}px ${y + scrollY}px`; b.style.transform = `scale(${s})`;
  };
  D.unzoom = (ms = 800) => { const b = document.documentElement; b.style.transition = `transform ${ms}ms cubic-bezier(.4,0,.2,1)`; b.style.transform = "none"; };
  D.highlight = (sel, ms = 2600, pad = 8) => {
    const el = typeof sel === "string" ? document.querySelector(sel) : sel; if (!el) return false;
    const r = el.getBoundingClientRect(), h = document.createElement("div"); h.className = "__hl";
    Object.assign(h.style, { left: r.left - pad + "px", top: r.top - pad + "px", width: r.width + 2 * pad + "px", height: r.height + 2 * pad + "px" });
    document.body.appendChild(h); setTimeout(() => { h.style.transition = "opacity .4s"; h.style.opacity = 0; setTimeout(() => h.remove(), 450); }, ms);
    return true;
  };
})();
