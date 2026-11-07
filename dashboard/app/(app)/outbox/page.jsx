"use client";

import { Mic, Send } from "lucide-react";
import { Pill, useData } from "../../../lib/Shell";
import { Empty, ErrorBox, PageHead, Skeleton, phoneFmt, when } from "../../../lib/ui";

const KIND = { confirmation: "Booking confirmed", reminder: "Reminder", cancellation: "Cancelled", order_summary: "Order summary",
  payment_link: "Payment link", owner_alert: "Alert to you", daily_summary: "Daily summary", feedback: "Feedback request",
  reorder: "Reorder reminder", winback: "Win-back offer", lead_followup: "Lead follow-up", change: "Booking changed",
  welcome: "Welcome", payment_received: "Payment received", order_status: "Order update" };

export default function Outbox() {
  const { data, error } = useData("/api/outbox");
  if (error) return <ErrorBox error={error} />;
  const unsent = (data || []).some((o) => o.status === "logged");
  return (
    <>
      <PageHead title="Messages sent" sub="Confirmations, reminders, payment links and follow-ups your assistant sends on WhatsApp." />
      {unsent && <div className="callout info" style={{ marginBottom: 16 }}><Send size={18} /><div><b>Not sent</b> means WhatsApp isn't connected yet, so messages are kept here.
        Connect it in Settings → Channels (or ask the Alaap team).</div></div>}
      {!data ? <Skeleton rows={4} /> : !data.length ? (
        <div className="card"><Empty icon={Send} title="No messages yet">After the first booking or order, confirmations and reminders show up here.</Empty></div>
      ) : (
        <div className="card pad-0"><div className="list">{data.map((o) => (
          <div key={o.id} className="list-row" style={{ alignItems: "flex-start", flexWrap: "wrap" }}>
            <div style={{ width: 170, flex: "none" }}>
              <b className="small">{KIND[o.kind] || o.kind.replaceAll("_", " ")}</b>
              <div className="small muted">to {phoneFmt(o.to)}</div>
              <div className="tiny faint">{when(o.send_after)}</div>
            </div>
            <div style={{ flex: 1, minWidth: 220, whiteSpace: "pre-wrap", fontSize: 14 }}>{o.body}
              {o.has_audio && <div className="small muted row" style={{ gap: 4 }}><Mic size={13} />with a voice note</div>}
              {o.error && <div className="small err">{o.error}</div>}</div>
            <Pill value={o.status} />
          </div>
        ))}</div></div>
      )}
    </>
  );
}
