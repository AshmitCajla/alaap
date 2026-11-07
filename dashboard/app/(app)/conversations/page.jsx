"use client";

import { useEffect, useState } from "react";
import { ArrowLeft, MessagesSquare, Phone } from "lucide-react";
import { api } from "../../../lib/api";
import { Pill, useData } from "../../../lib/Shell";
import { CHANNEL, ChannelIcon, Empty, ErrorBox, PageHead, Seg, Skeleton, phoneFmt, time12, when } from "../../../lib/ui";

export default function Conversations() {
  const { data, error } = useData("/api/conversations?limit=100");
  const [open, setOpen] = useState(null);
  const [detail, setDetail] = useState(null);
  const [showTools, setShowTools] = useState(false);
  const [filter, setFilter] = useState("all");

  useEffect(() => {
    const id = new URLSearchParams(window.location.search).get("id");
    if (id) setOpen(Number(id));
  }, []);
  useEffect(() => { setDetail(null); if (open) api(`/api/conversations/${open}`).then(setDetail); }, [open]);

  if (error) return <ErrorBox error={error} />;
  const rows = (data || []).filter((c) => filter === "all" || (filter === "needs" ? c.handoff || ["callback", "complaint"].includes(c.outcome) : c.channel === filter));

  return (
    <>
      <PageHead title="Conversations" sub="Every call, WhatsApp and web chat — read exactly what was said." />
      <div className="split">
        <div className={open ? "hide-sm" : ""}>
          <Seg value={filter} onChange={setFilter} options={[["all", "All"], ["phone", "Calls"], ["whatsapp", "WhatsApp"], ["web", "Web"], ["needs", "Needs you"]]} />
          <div className="card pad-0" style={{ maxHeight: "72vh", overflowY: "auto" }}>
            {!data ? <div className="card-body"><Skeleton rows={6} height={44} /></div> : !rows.length ?
              <Empty icon={MessagesSquare} title="No conversations here yet" /> :
              rows.map((c) => (
                <div key={c.id} className={"list-item" + (open === c.id ? " on" : "")} onClick={() => setOpen(c.id)}>
                  <div className="row" style={{ gap: 10, flexWrap: "nowrap" }}>
                    <div className={"avatar " + c.channel}><ChannelIcon channel={c.channel} /></div>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div className="row between small" style={{ flexWrap: "nowrap" }}>
                        <span className="muted nowrap">{c.caller ? phoneFmt(c.caller) : (CHANNEL[c.channel] || CHANNEL.web).label}</span>
                        <span className="faint nowrap">{when(c.started)}</span>
                      </div>
                      <div style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", fontSize: 14 }}>{c.first}</div>
                    </div>
                  </div>
                  {(c.outcome || c.handoff) && <div style={{ marginTop: 6, marginLeft: 46 }}>{c.handoff ? <Pill value="handoff" /> : <Pill value={c.outcome} />}</div>}
                </div>
              ))}
          </div>
        </div>
        <div className={"card" + (open ? "" : " hide-sm")} style={{ alignSelf: "start" }}>
          {!open ? <Empty icon={MessagesSquare} title="Pick a conversation">You'll see every message and what your assistant did.</Empty>
          : !detail ? <Skeleton rows={4} height={36} /> : (
            <>
              <button className="btn plain small show-sm" style={{ marginBottom: 8 }} onClick={() => setOpen(null)}><ArrowLeft size={15} />All conversations</button>
              <div className="row between" style={{ marginBottom: 14, paddingBottom: 12, borderBottom: "1px solid var(--line-2)" }}>
                <div className="row" style={{ gap: 10 }}>
                  <div className={"avatar " + detail.channel}><ChannelIcon channel={detail.channel} /></div>
                  <div><b>{detail.caller ? phoneFmt(detail.caller) : "Unknown number"}</b>
                    <div className="small muted">{(CHANNEL[detail.channel] || CHANNEL.web).label}{detail.call_seconds ? ` · ${Math.max(1, Math.round(detail.call_seconds / 60))} min call` : ""}</div></div>
                </div>
                <div className="row">
                  {detail.caller && <a className="btn ghost small" href={`tel:${detail.caller}`}><Phone size={14} />Call back</a>}
                  <label className="check small" style={{ margin: 0 }}>
                    <input type="checkbox" checked={showTools} onChange={(e) => setShowTools(e.target.checked)} />Show what it checked</label>
                </div>
              </div>
              <div className="chat">
                {detail.messages.filter((m) => showTools || m.role !== "tool").map((m, i) => (
                  <div key={i} className={"msg " + m.role}>{m.text}<span className="meta">{time12(m.at)}{m.latency_ms ? ` · ${(m.latency_ms / 1000).toFixed(1)}s` : ""}</span></div>
                ))}
              </div>
            </>
          )}
        </div>
      </div>
    </>
  );
}
