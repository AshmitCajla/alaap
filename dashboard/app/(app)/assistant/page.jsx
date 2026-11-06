"use client";

import { useEffect, useRef, useState } from "react";
import { api } from "../../../lib/api";

const EXAMPLES = ["aaj kitne orders aaye?", "kal ka schedule batao", "Facial ka rate 900 kar do",
  "yaad rakhna, parking dukaan ke peeche hai", "Sunday ko 11 se 5 khulenge", "kal shop band hai, sab appointments shift karo"];

export default function Assistant() {
  const [conv, setConv] = useState(null);
  const [msgs, setMsgs] = useState([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const end = useRef(null);

  const started = useRef(false);
  useEffect(() => {
    if (started.current) return;  // React dev mode runs effects twice; start one conversation only
    started.current = true;
    api("/api/owner-chat/start", { method: "POST" })
      .then((r) => { setConv(r.conversation_id); setMsgs([{ role: "alaap", text: r.text }]); })
      .catch((e) => setMsgs([{ role: "alaap", text: "Could not start: " + e.message }]));
  }, []);
  useEffect(() => {
    end.current?.scrollIntoView({ behavior: "smooth" });  // block body: scrollIntoView may return a Promise
  }, [msgs]);

  async function send(t) {
    t = (t ?? text).trim();
    if (!t || !conv || busy) return;
    setText(""); setBusy(true);
    setMsgs((m) => [...m, { role: "me", text: t }, { role: "alaap", text: "…" }]);
    try {
      const r = await api(`/api/owner-chat/${conv}`, { method: "POST", body: { text: t } });
      setMsgs((m) => [...m.slice(0, -1), { role: "alaap", text: r.text }]);
    } catch (e) {
      setMsgs((m) => [...m.slice(0, -1), { role: "alaap", text: "Error: " + e.message }]);
    }
    setBusy(false);
  }

  return (
    <>
      <h1>Ask Alaap</h1>
      <p className="sub">Talk to your front desk like you would to a manager — ask for numbers, or tell it new prices, timings and
        things to tell customers, and it updates itself. You can also message it from your own number on WhatsApp.</p>
      <div className="card">
        <div className="chat" style={{ minHeight: 260 }}>
          {msgs.map((m, i) => <div key={i} className={"msg " + m.role}>{m.text}</div>)}
          <div ref={end} />
        </div>
        <div className="row" style={{ marginTop: 12, flexWrap: "nowrap" }}>
          <input value={text} placeholder="Type in Hindi, Punjabi or English…" onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && send()} />
          <button className="btn" disabled={busy} onClick={() => send()}>Send</button>
        </div>
        <div className="row" style={{ marginTop: 10 }}>
          {EXAMPLES.map((x) => <button key={x} className="btn ghost small" onClick={() => send(x)}>{x}</button>)}
        </div>
      </div>
    </>
  );
}
