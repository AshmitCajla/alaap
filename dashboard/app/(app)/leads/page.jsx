"use client";

import Link from "next/link";
import { MessageSquareText, Phone, Target } from "lucide-react";
import { api } from "../../../lib/api";
import { useData } from "../../../lib/Shell";
import { Empty, ErrorBox, PageHead, Skeleton, phoneFmt, useToast, when } from "../../../lib/ui";

const STATUSES = [["new", "New"], ["contacted", "Contacted"], ["visit_booked", "Visit booked"], ["won", "Won"], ["lost", "Lost"]];

export default function Leads() {
  const toast = useToast();
  const { data, error, reload } = useData("/api/leads");
  const set = (id, status) => api(`/api/leads/${id}`, { method: "PATCH", body: { status } }).then(() => { toast("Lead updated"); reload(); });
  if (error) return <ErrorBox error={error} />;
  return (
    <>
      <PageHead title="Leads" sub="People interested in buying or joining. Hot leads (70+) are sent to your WhatsApp right away." />
      {!data ? <Skeleton rows={3} height={90} /> : !data.length ? (
        <div className="card"><Empty icon={Target} title="No leads yet">When someone asks about joining or buying, your assistant asks a few questions and saves them here.</Empty></div>
      ) : (
        <div className="card pad-0"><div className="list">{data.map((l) => (
          <div key={l.id} className="list-row" style={{ flexWrap: "wrap", alignItems: "flex-start" }}>
            <div className="timebox" style={{ background: l.score >= 70 ? "var(--good-soft)" : l.score >= 40 ? "var(--warn-soft)" : "var(--panel-2)" }}>
              <b style={{ color: l.score >= 70 ? "var(--good)" : l.score >= 40 ? "var(--warn)" : "var(--muted)" }}>{l.score}</b><span>{l.score >= 70 ? "hot" : l.score >= 40 ? "warm" : "cold"}</span></div>
            <div style={{ flex: 1, minWidth: 220 }}>
              <b>{l.name || "Someone"}</b> <span className="muted small">· {when(l.created)}</span>
              <div>{l.need}</div>
              <div className="small muted row" style={{ gap: 12, marginTop: 4 }}>
                <a href={`tel:${l.phone}`} className="row" style={{ gap: 4 }}><Phone size={13} />{phoneFmt(l.phone)}</a>
                {l.budget && <span>Budget {l.budget}</span>}{l.location && <span>{l.location}</span>}{l.preferred_time && <span>Wants: {l.preferred_time}</span>}
              </div>
            </div>
            <div className="row" style={{ gap: 6 }}>
              <select value={l.status} onChange={(e) => set(l.id, e.target.value)} style={{ width: 150 }}>
                {STATUSES.map(([v, t]) => <option key={v} value={v}>{t}</option>)}</select>
              {l.conversation_id && <Link className="icon-btn" title="Conversation" href={`/conversations?id=${l.conversation_id}`}><MessageSquareText size={15} /></Link>}
            </div>
          </div>
        ))}</div></div>
      )}
    </>
  );
}
