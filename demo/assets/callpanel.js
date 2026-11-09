/* Call scene only: enlarges the customer page and adds a side panel that shows the call's real events
 * (state + transcript messages the server sends to the page). Labelled as a recording overlay. */
(() => {
  const st = document.createElement("style");
  st.textContent = `
    body{background:linear-gradient(135deg,#eef6f4,#f7f3ea)!important}
    .wrap{zoom:1.3;margin:0 0 0 90px!important;padding-top:6px!important}
    .note{display:none}
    #__panel{position:fixed;right:56px;top:56px;bottom:56px;width:840px;font-family:"Plus Jakarta Sans",system-ui,sans-serif;color:#15201e;display:flex;flex-direction:column;gap:18px}
    #__panel .tag{font-size:15px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:#0d7a6f}
    #__panel h2{font-size:38px;margin:2px 0 0;letter-spacing:-.02em}
    #__panel .sub{color:#5b6866;font-size:18px;margin-top:4px}
    .__pipe{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}
    .__st{background:#fff;border:2px solid #e3e8e6;border-radius:18px;padding:18px 18px 16px;transition:all .25s;opacity:.55}
    .__st.on{opacity:1;border-color:#0d7a6f;box-shadow:0 10px 30px rgba(13,122,111,.18);transform:translateY(-3px)}
    .__st b{display:block;font-size:22px}.__st span{display:block;font-size:15px;color:#5b6866;margin-top:3px}
    .__st i{display:inline-block;width:12px;height:12px;border-radius:99px;background:#cfd8d6;margin-right:8px}
    .__st.on i{background:#16a34a;box-shadow:0 0 0 5px rgba(22,163,74,.18)}
    .__log{flex:1;background:#fff;border:1px solid #e3e8e6;border-radius:20px;padding:20px 22px;overflow:hidden;display:flex;flex-direction:column;justify-content:flex-end;gap:12px}
    .__ln{font-size:21px;line-height:1.4;animation:__in .3s ease-out}
    .__ln small{display:block;font-size:13px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:#8a9593;margin-bottom:2px}
    .__ln.a small{color:#0d7a6f}
    @keyframes __in{from{opacity:0;transform:translateY(8px)}}
    #__panel .foot{font-size:13px;color:#8a9593}`;
  document.head.appendChild(st);
  const p = document.createElement("div"); p.id = "__panel";
  p.innerHTML = `<div><div class="tag">Live call · real events from this call</div><h2>What's happening inside Alaap</h2>
    <div class="sub">Each stage lights up when the server reports it.</div></div>
    <div class="__pipe">
      <div class="__st" data-s="listening"><i></i><b>Listening</b><span>Gnani Prisma · streaming speech-to-text</span></div>
      <div class="__st" data-s="thinking"><i></i><b>Thinking</b><span>Gemini · checks slots, prepares the booking</span></div>
      <div class="__st" data-s="speaking"><i></i><b>Speaking</b><span>Gnani Timbre · streaming text-to-speech</span></div>
    </div>
    <div class="__log"></div>
    <div class="foot">Recording overlay. The caller's voice is synthesized; the assistant's side is the live app.</div>`;
  document.body.appendChild(p);
  const log = p.querySelector(".__log");
  let cur = "";
  const set = (s) => { cur = s; p.querySelectorAll(".__st").forEach((x) => x.classList.toggle("on", x.dataset.s === s)); };
  // The server announces "thinking" and "speaking"; listening resumes when the reply's audio has finished playing.
  setInterval(() => { const st = window.__demo.callState(); if (cur === "speaking" && Date.now() > st.lastEnd + 250) set("listening"); }, 150);
  window.addEventListener("demo-call", (e) => {
    const m = e.detail;
    if (m.event === "state") set(m.state);
    if (m.event === "transcript") {
      const d = document.createElement("div"); d.className = "__ln " + (m.role === "customer" ? "c" : "a");
      d.innerHTML = `<small>${m.role === "customer" ? "Caller · heard by Gnani Prisma" : "Riya · spoken by Gnani Timbre"}</small>`;
      d.appendChild(document.createTextNode(m.text));
      log.appendChild(d);
      while (log.children.length > 7) log.removeChild(log.firstChild);
    }
  });
})();
