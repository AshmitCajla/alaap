"use client";

import { useEffect, useRef, useState } from "react";
import { ArrowUp, Bot, CalendarClock, IndianRupee, MapPin, Clock, Ban, BarChart3 } from "lucide-react";
import { api } from "../../../lib/api";
import { PageHead } from "../../../lib/ui";

const EXAMPLES = [
  [BarChart3, "aaj kitne orders/bookings aaye?"], [CalendarClock, "kal ka schedule batao"],
  [IndianRupee, "Facial ka rate 900 kar do"], [MapPin, "yaad rakhna, parking dukaan ke peeche hai"],
  [Clock, "Sunday ko 11 se 5 khulenge"], [Ban, "kal shop band hai"],
];

export default function Assistant() {
  const [conv, setConv] = useState(null);
  const [msgs, setMsgs] = useState([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const box = useRef(null);
  const input = useRef(null);

  const started = useRef(false);
  useEffect(() => {
    if (started.current) return;  // React dev mode runs effects twice; start one conversation only
    started.current = true;
    api("/api/owner-chat/start", { method: "POST" })
      .then((r) => { setConv(r.conversation_id); setMsgs([{ role: "alaap", text: r.text }]); })
      .catch((e) => setMsgs([{ role: "alaap", text: "Could not start: " + e.message }]));
  }, []);
  useEffect(() => {
    if (box.current) box.current.scrollTop = box.current.scrollHeight;
  }, [msgs]);

  async function send(t) {
    t = (t ?? text).trim();
    if (!t || !conv || busy) return;
    setText(""); setBusy(true);
    setMsgs((m) => [...m, { role: "me", text: t }, { role: "alaap", text: "", typing: true }]);
    try {
      const r = await api(`/api/owner-chat/${conv}`, { method: "POST", body: { text: t } });
      setMsgs((m) => [...m.slice(0, -1), { role: "alaap", text: r.text }]);
    } catch (e) {
      setMsgs((m) => [...m.slice(0, -1), { role: "alaap", text: "Sorry, that didn't go through: " + e.message }]);
    }
    setBusy(false);
    input.current?.focus();
  }

  return (
    <>
      <PageHead title="Ask Alaap" sub="Talk to your assistant like a manager: ask for numbers, or tell it new prices, timings or things customers should know. It updates itself." />
      <div className="card pad-0" style={{ display: "flex", flexDirection: "column", height: "min(66vh, 620px)" }}>
        <div ref={box} className="chat" style={{ flex: 1, maxHeight: "none", padding: 18 }}>
          {msgs.map((m, i) => (
            <div key={i} className="row" style={{ gap: 8, alignItems: "flex-end", flexWrap: "nowrap", justifyContent: m.role === "me" ? "flex-end" : "flex-start" }}>
              {m.role === "alaap" && <span className="logo" style={{ width: 28, height: 28 }}><Bot size={15} /></span>}
              <div className={"msg " + m.role} style={{ maxWidth: "80%" }}>{m.typing ? <span className="muted">typing…</span> : m.text}</div>
            </div>
          ))}
          {msgs.length <= 1 && (
            <div style={{ marginTop: 12 }}>
              <div className="small muted" style={{ marginBottom: 8 }}>Try one of these:</div>
              <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(210px, 1fr))", gap: 8 }}>
                {EXAMPLES.map(([Icon, x]) => (
                  <button key={x} className="btn ghost" style={{ justifyContent: "flex-start", whiteSpace: "normal", textAlign: "left", fontWeight: 500 }}
                    onClick={() => send(x)} disabled={!conv}><Icon size={16} color="var(--brand)" style={{ flex: "none" }} />{x}</button>
                ))}
              </div>
            </div>
          )}
        </div>
        <div className="row" style={{ padding: 12, borderTop: "1px solid var(--line-2)", flexWrap: "nowrap" }}>
          <input ref={input} value={text} placeholder="Type in Hindi, Punjabi or English…" onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && send()} aria-label="Message" />
          <button className="btn" disabled={busy || !text.trim()} onClick={() => send()} aria-label="Send"><ArrowUp size={18} /></button>
        </div>
      </div>
      <p className="small muted" style={{ marginTop: 10 }}>Tip: you can also send these messages from your own number on WhatsApp.</p>
    </>
  );
}
