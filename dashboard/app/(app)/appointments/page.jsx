"use client";

import Link from "next/link";
import { useState } from "react";
import { CalendarDays, Check, MessageSquareText, Phone, UserX } from "lucide-react";
import { api } from "../../../lib/api";
import { Pill, useData } from "../../../lib/Shell";
import { Empty, ErrorBox, PageHead, Seg, Skeleton, dayLabel, phoneFmt, time12, useToast } from "../../../lib/ui";

export default function Appointments() {
  const toast = useToast();
  const [view, setView] = useState("upcoming");
  const { data, error, reload } = useData("/api/appointments?days_back=7&days_ahead=30");
  const set = (a, status) => api(`/api/appointments/${a.id}`, { method: "PATCH", body: { status } })
    .then(() => { toast(status === "done" ? `${a.customer} marked as done` : `${a.customer} marked as no-show`); reload(); })
    .catch((e) => toast(e.message, "bad"));
  if (error) return <ErrorBox error={error} />;

  const now = Date.now() - 60 * 60000;
  const rows = (data || []).filter((a) => {
    const t = new Date(a.start.replace(" ", "T")).getTime();
    return view === "upcoming" ? t >= now && a.status === "booked" : view === "past" ? t < now || a.status !== "booked" : true;
  });
  if (view === "past") rows.reverse();
  const days = [];
  for (const a of rows) {
    const d = a.start.slice(0, 10);
    if (!days.length || days[days.length - 1].day !== d) days.push({ day: d, items: [] });
    days[days.length - 1].items.push(a);
  }

  return (
    <>
      <PageHead title="Appointments" sub="Customers get a WhatsApp confirmation, and a reminder 2 hours before.">
        <Seg value={view} onChange={setView} options={[["upcoming", "Upcoming"], ["past", "Past week"], ["all", "All"]]} />
      </PageHead>
      {!data ? <Skeleton rows={4} /> : !days.length ? (
        <div className="card"><Empty icon={CalendarDays} title={view === "upcoming" ? "No upcoming appointments" : "Nothing here"}>
          When a customer books on a call, WhatsApp or your link, it shows up here instantly.</Empty></div>
      ) : days.map(({ day, items }) => (
        <div key={day} className="section" style={{ marginTop: 18 }}>
          <div className="section-head"><h2>{dayLabel(day)} <span className="muted" style={{ fontWeight: 500 }}>· {items.length} booking{items.length === 1 ? "" : "s"}</span></h2></div>
          <div className="card pad-0"><div className="list">
            {items.map((a) => (
              <div key={a.id} className="list-row" style={{ flexWrap: "wrap" }}>
                <div className="timebox"><b>{time12(a.start).replace(" ", "")}</b><span>{a.service.length > 10 ? "" : a.service}</span></div>
                <div style={{ flex: 1, minWidth: 180 }}>
                  <b>{a.customer}</b> <span className="muted">· {a.service} with {a.staff}</span>
                  <div className="small muted row" style={{ gap: 10, marginTop: 2 }}>
                    <a href={`tel:${a.phone}`} className="row" style={{ gap: 4 }}><Phone size={13} />{phoneFmt(a.phone)}</a>
                    <span>Ref {a.ref}</span><span>via {a.channel === "web" ? "web chat" : a.channel}</span>
                  </div>
                </div>
                <Pill value={a.status} />
                <div className="row" style={{ gap: 6 }}>
                  {a.status === "booked" && <>
                    <button className="btn small" onClick={() => set(a, "done")}><Check size={14} />Done</button>
                    <button className="btn ghost small" onClick={() => set(a, "no_show")}><UserX size={14} />No-show</button>
                  </>}
                  {a.conversation_id && <Link className="icon-btn" title="See the conversation" href={`/conversations?id=${a.conversation_id}`}><MessageSquareText size={15} /></Link>}
                </div>
              </div>
            ))}
          </div></div>
        </div>
      ))}
    </>
  );
}
