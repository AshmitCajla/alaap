"use client";

import Link from "next/link";
import { useState } from "react";
import { AlertTriangle, Check, Inbox as InboxIcon, MessageSquareText, Phone, PhoneCall, RotateCcw } from "lucide-react";
import { api } from "../../../lib/api";
import { Pill, useData } from "../../../lib/Shell";
import { Empty, ErrorBox, PageHead, Seg, Skeleton, phoneFmt, useToast, when } from "../../../lib/ui";

export default function Inbox() {
  const toast = useToast();
  const [view, setView] = useState("open");
  const { data, error, reload } = useData("/api/tickets");
  const set = (id, status) => api(`/api/tickets/${id}`, { method: "PATCH", body: { status } })
    .then(() => { toast(status === "closed" ? "Marked as done" : "Reopened"); reload(); });
  if (error) return <ErrorBox error={error} />;
  const rows = (data || []).filter((t) => view === "all" || t.status === view);
  return (
    <>
      <PageHead title="Callbacks & complaints" sub="What your assistant couldn't finish and handed to you. Each one was also sent to your WhatsApp.">
        <Seg value={view} onChange={setView} options={[["open", "To do"], ["closed", "Done"], ["all", "All"]]} />
      </PageHead>
      {!data ? <Skeleton rows={3} height={80} /> : !rows.length ? (
        <div className="card"><Empty icon={InboxIcon} title={view === "open" ? "All caught up" : "Nothing here"}>
          {view === "open" ? "Nobody is waiting for a call back right now." : ""}</Empty></div>
      ) : (
        <div className="stack">{rows.map((t) => (
          <div key={t.id} className="card row" style={{ alignItems: "flex-start", gap: 14, borderColor: t.urgency === "urgent" && t.status === "open" ? "var(--bad)" : undefined }}>
            <div className={"avatar " + (t.kind === "complaint" ? "" : "phone")} style={t.kind === "complaint" ? { background: "var(--bad-soft)", color: "var(--bad)" } : {}}>
              {t.kind === "complaint" ? <AlertTriangle size={16} /> : <PhoneCall size={16} />}</div>
            <div style={{ flex: 1, minWidth: 200 }}>
              <div className="row" style={{ gap: 6 }}><b>{t.name || "Customer"}</b><Pill value={t.kind} />{t.urgency === "urgent" && <Pill value="urgent" />}
                <span className="small faint">{when(t.created)}</span></div>
              <div style={{ margin: "4px 0" }}>{t.issue}</div>
              {t.conversation_id && <Link className="small row" style={{ gap: 4 }} href={`/conversations?id=${t.conversation_id}`}><MessageSquareText size={13} />Read the conversation</Link>}
            </div>
            <div className="row" style={{ gap: 6 }}>
              {t.phone && <a className="btn ghost small" href={`tel:${t.phone}`}><Phone size={14} />{phoneFmt(t.phone)}</a>}
              {t.status === "open"
                ? <button className="btn small" onClick={() => set(t.id, "closed")}><Check size={14} />Done</button>
                : <button className="btn plain small" onClick={() => set(t.id, "open")}><RotateCcw size={14} />Reopen</button>}
            </div>
          </div>
        ))}</div>
      )}
    </>
  );
}
