"use client";

import { useEffect, useState } from "react";
import { api } from "../../../lib/api";
import { Pill, useData } from "../../../lib/Shell";

export default function Conversations() {
  const { data, error } = useData("/api/conversations?limit=100");
  const [open, setOpen] = useState(null);
  const [detail, setDetail] = useState(null);
  const [showTools, setShowTools] = useState(false);

  useEffect(() => {
    const id = new URLSearchParams(window.location.search).get("id");
    if (id) setOpen(Number(id));
  }, []);
  useEffect(() => { if (open) api(`/api/conversations/${open}`).then(setDetail); }, [open]);

  if (error) return <div className="err">{error}</div>;
  return (
    <>
      <h1>Conversations</h1>
      <p className="sub">Every call, WhatsApp and web chat, with what Alaap did.</p>
      <div className="split">
        <div className="card" style={{ padding: 0, maxHeight: "70vh", overflowY: "auto" }}>
          {!data ? <div className="muted" style={{ padding: 12 }}>Loading…</div> : data.length === 0 ?
            <div className="muted" style={{ padding: 12 }}>No conversations yet.</div> :
            data.map((c) => (
              <div key={c.id} className={"list-item" + (open === c.id ? " on" : "")} onClick={() => setOpen(c.id)}>
                <div className="row" style={{ justifyContent: "space-between" }}>
                  <span className="small muted">{c.started} · {c.channel}</span>
                  <span>{c.outcome && <Pill value={c.outcome} />} {c.handoff && <Pill value="urgent" />}</span>
                </div>
                <div className="small">{c.first}</div>
              </div>
            ))}
        </div>
        <div className="card">
          {!detail ? <div className="muted">Pick a conversation.</div> : (
            <>
              <div className="row" style={{ justifyContent: "space-between", marginBottom: 10 }}>
                <div className="small muted">#{detail.id} · {detail.channel} · {detail.caller || "unknown number"}
                  {detail.call_seconds ? ` · ${Math.round(detail.call_seconds / 6) / 10} min` : ""}</div>
                <label className="row small" style={{ margin: 0, width: "auto" }}>
                  <input type="checkbox" style={{ width: "auto" }} checked={showTools} onChange={(e) => setShowTools(e.target.checked)} />
                  show what Alaap checked</label>
              </div>
              <div className="chat">
                {detail.messages.filter((m) => showTools || m.role !== "tool").map((m, i) => (
                  <div key={i} className={"msg " + m.role} title={m.at + (m.latency_ms ? ` · ${m.latency_ms} ms` : "")}>{m.text}</div>
                ))}
              </div>
            </>
          )}
        </div>
      </div>
    </>
  );
}
